"""Live transcript and reply latency, timed from the start of the recording
(which starts the moment the clinic picks up), so a timestamp here is the
same spot in recording.ogg.

transcript.txt is appended line by line as the call happens, so a crash
mid-call still leaves everything said so far on disk.
"""

import json
import time
from pathlib import Path

from livekit.agents import AgentSession

# The session's "user" is the clinic's receptionist agent; "assistant" is our patient.
_SPEAKER = {"user": "AGENT", "assistant": "PATIENT"}


class Transcript:
    def __init__(self, call_dir: Path) -> None:
        self.call_dir = call_dir
        self.t0: float | None = None
        self.lines: list[dict] = []
        self.latency: list[dict] = []
        self._started = {"user": None, "assistant": None}
        self._eou: float | None = None
        self._ttft: float | None = None
        self._txt = call_dir / "transcript.txt"

    def start_clock(self, t0: float) -> None:
        self.t0 = t0

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

        @session.on("metrics_collected")
        def _on_metrics(ev) -> None:
            m = ev.metrics
            if m.type == "eou_metrics":
                self._eou = m.end_of_utterance_delay
            elif m.type == "llm_metrics":
                self._ttft = m.ttft
            elif m.type == "tts_metrics" and self._eou is not None:
                parts = {"turn_end": self._eou, "llm": self._ttft or 0.0, "tts": m.ttfb}
                total = sum(parts.values())
                self.latency.append({k: round(v, 2) for k, v in {**parts, "total": total}.items()})
                print(f"        reply latency {total:.1f}s  (turn end {parts['turn_end']:.1f}"
                      f" + llm {parts['llm']:.1f} + tts {parts['tts']:.1f})", flush=True)
                self._eou = self._ttft = None

    def _add(self, speaker: str, text: str, started: float, interrupted: bool) -> None:
        offset = max(0.0, started - (self.t0 or started))
        line = {"t": round(offset, 1), "speaker": speaker, "text": text, "interrupted": interrupted}
        self.lines.append(line)
        formatted = format_line(line)
        print(formatted, flush=True)
        with self._txt.open("a", encoding="utf-8") as f:
            f.write(formatted + "\n")

    def save_json(self, scenario, goals_reached: list[bool | None]) -> None:
        data = {
            "scenario": scenario.id,
            "title": scenario.title,
            "persona": scenario.persona,
            "goals": [{"goal": g, "reached": r} for g, r in zip(scenario.goals, goals_reached)],
            "lines": self.lines,
            "reply_latency_s": self.latency,
        }
        (self.call_dir / "transcript.json").write_text(json.dumps(data, indent=2), encoding="utf-8")

    def as_text(self) -> str:
        return "\n".join(format_line(line) for line in self.lines)


def format_line(line: dict) -> str:
    m, s = divmod(int(line["t"]), 60)
    cut = " [cut off]" if line["interrupted"] else ""
    return f"[{m:02d}:{s:02d}] {line['speaker']}: {line['text']}{cut}"
