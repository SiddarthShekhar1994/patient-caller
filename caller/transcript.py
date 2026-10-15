"""Live transcript and reply gaps, timed from the start of the recording
(which starts the moment the clinic picks up), so a timestamp here is the
same spot in recording.ogg.

transcript.txt is appended line by line as the call happens, so a crash
mid-call still leaves everything said so far on disk.
"""

import json
import re
import time
from pathlib import Path

from livekit.agents import AgentSession

# The session's "user" is the clinic's receptionist agent; "assistant" is our patient.
_SPEAKER = {"user": "AGENT", "assistant": "PATIENT"}

# The test line's greeting names the company that runs it. That name must not
# end up in the repo, so it's masked in everything we save (and isn't spelled
# out here either).
_COMPANY = re.compile(r"pretty\W*good\W*a\W?i\b|\bp\W?g\W?a\W?i\b", re.IGNORECASE)


# Speech-to-text sometimes drops the last word of the name in "Part of ...".
# Only that greeting is masked, since the first two words are an everyday phrase.
_COMPANY_GREETING = re.compile(r"(part\W+of\W+)pretty\W*good\b", re.IGNORECASE)


def redact(text: str) -> str:
    return _COMPANY_GREETING.sub(r"\1[company]", _COMPANY.sub("[company]", text))


class Transcript:
    def __init__(self, call_dir: Path) -> None:
        self.call_dir = call_dir
        self.t0: float | None = None
        self.lines: list[dict] = []
        self.latency: list[dict] = []
        self._started = {"user": None, "assistant": None}
        self._eou: float | None = None
        self._eou_at: float | None = None
        self._user_stopped: float | None = None
        self._txt = call_dir / "transcript.txt"

    def start_clock(self, t0: float) -> None:
        self.t0 = t0

    def attach(self, session: AgentSession) -> None:
        @session.on("user_state_changed")
        def _on_user(ev) -> None:
            if ev.new_state == "speaking":
                now = time.time()
                # A fresh stretch of speech after a real pause starts a new turn, even if
                # the last one never became a transcript line (e.g. a skipped reply).
                if self._started["user"] is None or (
                    self._user_stopped and now - self._user_stopped > 2.0
                ):
                    self._started["user"] = now
            elif ev.old_state == "speaking":
                self._user_stopped = time.time()

        @session.on("agent_state_changed")
        def _on_agent(ev) -> None:
            if ev.new_state != "speaking":
                return
            now = time.time()
            if self._started["assistant"] is None:
                self._started["assistant"] = now
            if self._eou_at is not None:
                self._log_gap(self._eou, now - self._eou_at)
                self._eou_at = None

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
            # Our own lines are added once they finish playing, so "now" is their end.
            ended = time.time()
            if role == "user" and self._user_stopped and self._user_stopped >= started:
                ended = self._user_stopped
            self._add(_SPEAKER[role], text, started, ended, getattr(item, "interrupted", False))

        @session.on("metrics_collected")
        def _on_metrics(ev) -> None:
            if ev.metrics.type == "eou_metrics":
                # Delay from the end of their speech to us deciding the turn is over.
                self._eou = ev.metrics.end_of_utterance_delay
                self._eou_at = time.time()

    def _log_gap(self, turn_detection: float, to_audio: float) -> None:
        """The silence the receptionist hears: end of their speech to our first audio."""
        total = turn_detection + to_audio
        self.latency.append({"turn_detection": round(turn_detection, 2),
                             "llm_and_tts": round(to_audio, 2), "total": round(total, 2)})
        print(f"        reply gap {total:.1f}s  (turn detection {turn_detection:.1f}"
              f" + llm/tts {to_audio:.1f})", flush=True)

    def _add(self, speaker: str, text: str, started: float, ended: float, interrupted: bool) -> None:
        t0 = self.t0 or started
        offset = max(0.0, started - t0)
        line = {"t": round(offset, 1), "end": round(max(offset, ended - t0), 1),
                "speaker": speaker, "text": redact(text), "interrupted": interrupted}
        self.lines.append(line)
        formatted = format_line(line)
        print(formatted, flush=True)
        with self._txt.open("a", encoding="utf-8") as f:
            f.write(formatted + "\n")

    def save_json(self, scenario, goals_reached: list[bool | None]) -> None:
        # Lines were appended as each turn finished; an interruption can finish them
        # out of order, so the final files are sorted by start time.
        self.lines.sort(key=lambda line: line["t"])
        self._txt.write_text(self.as_text() + "\n", encoding="utf-8")
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
