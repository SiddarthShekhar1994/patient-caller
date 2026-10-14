"""One call, end to end: build the STT -> LLM -> TTS pipeline, dial, enforce the time limit."""

import asyncio
import json
import logging

from livekit import api
from livekit.agents import AgentServer, AgentSession, JobContext, JobProcess, room_io
from livekit.plugins import cartesia, deepgram, openai, silero
from livekit.plugins.turn_detector.english import EnglishModel

from .agent import PatientAgent
from .config import AGENT_NAME, CALL_TIME_LIMIT_S, load_config
from .scenarios import load_scenario
from .telephony import CLINIC_IDENTITY, dial_clinic, hang_up
from .transcript import Transcript

log = logging.getLogger("caller")

# Cartesia "Katie": a warm, conversational adult voice. Scenarios can override it.
DEFAULT_VOICE = "f786b574-daa5-4673-aa0c-cbe3e8534c02"


def prewarm(proc: JobProcess) -> None:
    # Load the VAD once per worker process instead of on every call.
    proc.userdata["vad"] = silero.VAD.load()


# One warm process is plenty: calls run one at a time.
server = AgentServer(setup_fnc=prewarm, num_idle_processes=1)


@server.rtc_session(agent_name=AGENT_NAME)
async def entrypoint(ctx: JobContext) -> None:
    cfg = load_config()
    scenario = load_scenario(json.loads(ctx.job.metadata or "{}").get("scenario", ""))
    log.info("scenario %s in room %s", scenario.id, ctx.room.name)

    session = AgentSession(
        # Phone audio is 8 kHz narrowband. LiveKit resamples the track to 8 kHz
        # before Deepgram, so we send what the line actually carries.
        stt=deepgram.STT(model="nova-3", language="en-US", sample_rate=8000),
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
    transcript = Transcript()
    transcript.attach(session)

    await ctx.connect()
    # Start listening before we dial so the receptionist's greeting isn't lost.
    # We never call generate_reply here: the clinic speaks first.
    started = asyncio.create_task(
        session.start(
            agent=PatientAgent(scenario),
            room=ctx.room,
            room_options=room_io.RoomOptions(
                participant_identity=CLINIC_IDENTITY,
                close_on_disconnect=True,  # clinic hangs up -> session ends
                delete_room_on_close=True,  # session ends -> room goes away
            ),
        )
    )

    try:
        await dial_clinic(ctx, cfg)
    except api.TwirpError as e:
        sip = (getattr(e, "metadata", None) or {}).get("sip_status_code", "?")
        log.error("call failed (SIP %s): %s", sip, e.message)
        started.cancel()
        await hang_up()  # removes the room so `py -m caller run` stops waiting
        ctx.shutdown("dial failed")
        return

    transcript.mark_connected()
    print(f"--- connected: {scenario.title} ---", flush=True)
    await started

    timer = asyncio.create_task(_time_limit())

    async def _stop_timer() -> None:
        timer.cancel()

    ctx.add_shutdown_callback(_stop_timer)


async def _time_limit() -> None:
    await asyncio.sleep(CALL_TIME_LIMIT_S)
    log.warning("hit the %ss limit, hanging up", CALL_TIME_LIMIT_S)
    await hang_up()
