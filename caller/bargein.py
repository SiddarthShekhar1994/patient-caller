"""Deliberate barge-in, for the one scenario that tests how the clinic copes
with being cut off. Normal calls never do this; it only runs when a
scenario sets flags.barge_in.

Trigger: once the patient has said one of `after_patient_says`, the next time
the receptionist talks for longer than `min_agent_speech_s`, the patient cuts
in with `instructions`, and that line can't itself be interrupted.
"""

import asyncio
import time

from livekit.agents import AgentSession

from .transcript import Transcript


class BargeIn:
    def __init__(self, session: AgentSession, transcript: Transcript, flag: dict) -> None:
        self._session = session
        self._transcript = transcript
        self._triggers = [t.lower() for t in flag["after_patient_says"]]
        self._min_s = float(flag.get("min_agent_speech_s", 2.5))
        self._instructions = flag["instructions"]
        self._speaking_since: float | None = None
        self.done = False
        session.on("user_state_changed", self._on_user_state)

    def _on_user_state(self, ev) -> None:
        if self.done:
            return
        if ev.new_state == "speaking":
            self._speaking_since = since = time.time()
            asyncio.create_task(self._maybe_cut_in(since))
        else:
            self._speaking_since = None

    async def _maybe_cut_in(self, since: float) -> None:
        await asyncio.sleep(self._min_s)
        if self.done or self._speaking_since != since:
            return  # they stopped talking, or a newer stretch of speech took over
        said = " ".join(l["text"].lower() for l in self._transcript.lines if l["speaker"] == "PATIENT")
        if not any(t in said for t in self._triggers):
            return
        self.done = True
        print("        >>> barging in", flush=True)
        self._session.generate_reply(instructions=self._instructions, allow_interruptions=False)
