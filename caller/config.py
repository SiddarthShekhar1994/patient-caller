"""Env loading and the dial guard.

The clinic number is a constant in code on purpose. Scenario files and .env
can't change where a call goes, and check_destination() runs right before
every dial as a second lock.
"""

import os
import re
from dataclasses import dataclass

from dotenv import load_dotenv

CLINIC_NUMBER = "+18054398008"

# The worker registers under this name; `py -m caller run` dispatches to it.
AGENT_NAME = "patient-caller"

# Hard stop for a call, counted from when the clinic picks up.
CALL_TIME_LIMIT_S = 240

_E164 = re.compile(r"^\+[1-9]\d{7,14}$")

_REQUIRED = (
    "LIVEKIT_URL",
    "LIVEKIT_API_KEY",
    "LIVEKIT_API_SECRET",
    "SIP_OUTBOUND_TRUNK_ID",
    "CALLER_NUMBER",
    "DEEPGRAM_API_KEY",
    "OPENAI_API_KEY",
    "CARTESIA_API_KEY",
)


class DialGuardError(RuntimeError):
    pass


def check_destination(number: str) -> str:
    """Return the number if it's the clinic line. Raise for anything else."""
    if number != CLINIC_NUMBER:
        raise DialGuardError(
            f"refusing to dial {number!r}: this bot only calls {CLINIC_NUMBER}"
        )
    return number


@dataclass(frozen=True)
class Config:
    livekit_url: str
    livekit_api_key: str
    livekit_api_secret: str
    sip_trunk_id: str
    caller_number: str
    llm_model: str


def load_config() -> Config:
    load_dotenv()
    missing = [k for k in _REQUIRED if not os.environ.get(k, "").strip()]
    if missing:
        raise SystemExit("Missing from .env: " + ", ".join(missing))

    caller = os.environ["CALLER_NUMBER"].strip()
    if not _E164.match(caller):
        raise SystemExit(f"CALLER_NUMBER must look like +18055550123, got {caller!r}")

    trunk = os.environ["SIP_OUTBOUND_TRUNK_ID"].strip()
    if not trunk.startswith("ST_"):
        raise SystemExit(f"SIP_OUTBOUND_TRUNK_ID should start with ST_, got {trunk!r}")

    return Config(
        livekit_url=os.environ["LIVEKIT_URL"].strip(),
        livekit_api_key=os.environ["LIVEKIT_API_KEY"].strip(),
        livekit_api_secret=os.environ["LIVEKIT_API_SECRET"].strip(),
        sip_trunk_id=trunk,
        caller_number=caller,
        llm_model=os.environ.get("LLM_MODEL", "").strip() or "gpt-4.1-mini",
    )
