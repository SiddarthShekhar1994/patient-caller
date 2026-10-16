"""Phone side: dial the clinic over the SIP trunk, hang up, and start calls from the CLI."""

import asyncio
import json
from datetime import datetime

from google.protobuf.duration_pb2 import Duration
from livekit import api
from livekit.agents import JobContext, get_job_context

from .config import AGENT_NAME, CALL_TIME_LIMIT_S, CLINIC_NUMBER, Config, check_destination

CLINIC_IDENTITY = "clinic"


async def dial_clinic(ctx: JobContext, cfg: Config) -> None:
    """Ring the clinic and return once they pick up. Raises api.TwirpError if the call fails."""
    await ctx.api.sip.create_sip_participant(
        api.CreateSIPParticipantRequest(
            sip_trunk_id=cfg.sip_trunk_id,
            sip_call_to=check_destination(CLINIC_NUMBER),
            sip_number=cfg.caller_number,
            room_name=ctx.room.name,
            participant_identity=CLINIC_IDENTITY,
            participant_name="Clinic",
            wait_until_answered=True,
            ringing_timeout=Duration(seconds=45),
            # Backstop in case our own timer fails: the SIP service drops the call itself.
            max_call_duration=Duration(seconds=CALL_TIME_LIMIT_S + 30),
        )
    )


async def hang_up() -> None:
    """Deleting the room disconnects everyone, which ends the phone call."""
    ctx = get_job_context()
    await ctx.api.room.delete_room(api.DeleteRoomRequest(room=ctx.room.name))


def _lk(cfg: Config) -> api.LiveKitAPI:
    return api.LiveKitAPI(cfg.livekit_url, cfg.livekit_api_key, cfg.livekit_api_secret)


async def start_call(cfg: Config, scenario_id: str) -> str:
    """Ask the running worker to join a fresh room and place the call. Returns the room name."""
    room = f"call-{datetime.now():%Y%m%d-%H%M%S}-{scenario_id}"
    async with _lk(cfg) as lk:
        await lk.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name=AGENT_NAME,
                room=room,
                metadata=json.dumps({"scenario": scenario_id}),
            )
        )
    return room


async def wait_for_call_end(cfg: Config, room: str, timeout_s: float = 360) -> bool:
    """Poll until the room has come and gone. False if it never showed up or never ended."""
    seen = False
    loop = asyncio.get_running_loop()
    start = loop.time()
    deadline = start + timeout_s
    async with _lk(cfg) as lk:
        while loop.time() < deadline:
            rooms = (await lk.room.list_rooms(api.ListRoomsRequest(names=[room]))).rooms
            if rooms:
                seen = True
            elif seen:
                return True
            elif loop.time() - start > 30:
                print("Still no room after 30s. Is `py -m caller worker` running?")
                return False
            await asyncio.sleep(2)
    return False
