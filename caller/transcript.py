"""Live transcript: stamps each turn with when that speaker started talking,
measured from the moment the clinic picked up.

Phase 1 prints to the console. File output comes in Phase 2.
"""

import time

from livekit.agents import AgentSession

# The session's "user" is the clinic's receptionist agent; "assistant" is our patient.
_SPEAKER = {"user": "AGENT", "assistant": "PATIENT"}


class Transcript:
    def __init__(self) -> None:
        self.t0: float | None = None
        self.lines: list[dict] = []
        self._started = {"user": None, "assistant": None}

    def mark_connected(self) -> None:
        self.t0 = time.time()

    def attach(self, session: AgentSession) -> None:
        @session.on("user_state_changed")
        def _on_user(ev) -> None:
            if ev.new_state == "speaking" and self._started["user"] is None:
                self._started["user"] = time.time()

        @session.on("agent_state_changed")
        def _on_agent(ev) -> None:
            if ev.new_state == "speaking" and self._started["assistant"] is None:
                self._started["assistant"] = time.time()

        @session.on("conversation_item_added")
        def _on_item(ev) -> None:
            item = ev.item
            role = getattr(item, "role", None)
            text = getattr(item, "text_content", None)
            if role not in _SPEAKER or not text:
                return
            # A turn can span several bursts of speech; keep the first one, then reset.
            started = self._started[role] or item.created_at
            self._started[role] = None
            self._add(_SPEAKER[role], text, started, getattr(item, "interrupted", False))

    def _add(self, speaker: str, text: str, started: float, interrupted: bool) -> None:
        offset = max(0.0, started - (self.t0 or started))
        line = {"t": round(offset, 1), "speaker": speaker, "text": text, "interrupted": interrupted}
        self.lines.append(line)
        print(format_line(line), flush=True)


def format_line(line: dict) -> str:
    m, s = divmod(int(line["t"]), 60)
    cut = " [cut off]" if line["interrupted"] else ""
    return f"[{m:02d}:{s:02d}] {line['speaker']}: {line['text']}{cut}"
