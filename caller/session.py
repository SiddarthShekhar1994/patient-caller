"""One call, end to end: dial, run the STT -> LLM -> TTS pipeline, save everything."""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone

from livekit.agents import AgentServer, AgentSession, JobContext, JobProcess, room_io
from livekit.plugins import cartesia, deepgram, openai, silero
from livekit.plugins.turn_detector.english import EnglishModel

from .agent import PatientAgent
from .bargein import BargeIn
from .config import AGENT_NAME, CALL_TIME_LIMIT_S, CLINIC_NUMBER, load_config
from .recording import call_dir_for, save_meta, save_recording
from .review import check_goals
from .scenarios import load_scenario
from .telephony import CLINIC_IDENTITY, dial_clinic, hang_up
from .transcript import Transcript

log = logging.getLogger("caller")

# Cartesia "Katie": a warm, conversational adult voice. Scenarios can override it.
DEFAULT_VOICE = "f786b574-daa5-4673-aa0c-cbe3e8534c02"


def prewarm(proc: JobProcess) -> None:
    # Load the VAD once per worker process instead of on every call.
    proc.userdata["vad"] = silero.VAD.load()


# One warm process is plenty: calls run one at a time. The longer shutdown
# timeout leaves room to save the recording and run the goal check.
server = AgentServer(setup_fnc=prewarm, num_idle_processes=1, shutdown_process_timeout=30.0)


@server.rtc_session(agent_name=AGENT_NAME)
async def entrypoint(ctx: JobContext) -> None:
    cfg = load_config()
    scenario = load_scenario(json.loads(ctx.job.metadata or "{}").get("scenario", ""))
    log.info("scenario %s in room %s", scenario.id, ctx.room.name)

    session = AgentSession(
        # The room audio arrives already resampled to 16 kHz (see RoomOptions below),
        # which Deepgram and Silero both take natively, so neither resamples again.
        stt=deepgram.STT(model="nova-3", language="en-US", sample_rate=16000),
        llm=openai.LLM(model=cfg.llm_model, temperature=0.8),
        tts=cartesia.TTS(model="sonic-3", voice=scenario.persona.get("voice", DEFAULT_VOICE)),
        vad=ctx.proc.userdata["vad"],
        turn_handling={
            # The turn detector reads the words, not just the silence, so a
            # mid-sentence pause from the receptionist doesn't hand us the turn.
            "turn_detection": EnglishModel(),
            "endpointing": {"min_delay": 0.5, "max_delay": 3.0},
            "interruption": {"enabled": True},
            # Start the LLM while the turn detector is still deciding; saves a few hundred ms.
            "preemptive_generation": {"enabled": True},
        },
    )
    agent = PatientAgent(scenario)

    await ctx.connect()
    try:
        await dial_clinic(ctx, cfg)
    except Exception as e:
        sip = (getattr(e, "metadata", None) or {}).get("sip_status_code", "?")
        log.error("call failed (SIP %s): %s", sip, getattr(e, "message", e))
        await hang_up()  # removes the room so `py -m caller run` stops waiting
        ctx.shutdown("dial failed")
        return

    # Start after the clinic picks up so the recording has no ringing at the
    # front. The bot never speaks first; it waits for the receptionist.
    call_dir = call_dir_for(ctx.room.name)
    transcript = Transcript(call_dir)
    transcript.attach(session)
    await session.start(
        agent=agent,
        room=ctx.room,
        room_options=room_io.RoomOptions(
            participant_identity=CLINIC_IDENTITY,
            close_on_disconnect=True,  # clinic hangs up -> session ends
            delete_room_on_close=True,  # session ends -> room goes away
        ),
    )
    # Time everything from the recording's own start so transcript timestamps
    # line up with recording.ogg.
    recorder = getattr(session, "_recorder_io", None)
    t0 = getattr(recorder, "recording_started_at", None) or time.time()
    transcript.start_clock(t0)
    if scenario.flags.get("barge_in"):
        BargeIn(session, transcript, scenario.flags["barge_in"])
    print(f"--- connected: {scenario.title} ---", flush=True)

    async def time_limit() -> None:
        await asyncio.sleep(CALL_TIME_LIMIT_S)
        log.warning("hit the %ss limit, hanging up", CALL_TIME_LIMIT_S)
        agent.ended_by = agent.ended_by or "time_limit"
        await hang_up()

    timer = asyncio.create_task(time_limit())

    async def finish() -> None:
        timer.cancel()
        await session.aclose()  # flushes the recorder
        recording = save_recording(ctx.session_directory, call_dir)
        try:
            reached = await asyncio.wait_for(
                check_goals(cfg.llm_model, transcript.as_text(), scenario.goals), timeout=15
            )
        except Exception as e:
            log.warning("goal check failed: %s", e)
            reached = [None] * len(scenario.goals)
        transcript.save_json(scenario, reached)
        save_meta(
            call_dir,
            room=ctx.room.name,
            scenario=scenario.id,
            started_at=datetime.fromtimestamp(t0, timezone.utc).isoformat(timespec="seconds"),
            duration_s=round(time.time() - t0, 1),
            ended_by=agent.ended_by or "clinic",
            caller_number=cfg.caller_number,
            dialed=CLINIC_NUMBER,
            recording=recording.name if recording else None,
            providers={
                "stt": "deepgram nova-3",
                "llm": f"openai {cfg.llm_model}",
                "tts": "cartesia sonic-3",
                "vad": "silero",
                "turn_detection": "livekit turn-detector (english)",
            },
        )
        print(f"--- saved to calls/{call_dir.name} (goals reached: {reached}) ---", flush=True)

    ctx.add_shutdown_callback(finish)
