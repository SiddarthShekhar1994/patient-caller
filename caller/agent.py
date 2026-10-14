"""The patient persona and its one tool, end_call."""

import asyncio
import re

from livekit.agents import Agent, AgentSession, RunContext, StopResponse, function_tool

from .scenarios import Scenario
from .telephony import hang_up

# Small models sometimes write a tool call out as text ("functions.end_call()")
# instead of making it. If that reached TTS, the patient would read it aloud.
_LEAK = re.compile(r"\s*functions\.\w+\([^)]*\)")
_LEAK_START = "functions."


def build_instructions(s: Scenario) -> str:
    p = s.persona
    goals = "\n".join(f"{i}. {g}" for i, g in enumerate(s.goals, 1))
    insurance = f" Insurance: {p['insurance']}." if p.get("insurance") else ""
    style = p.get("style", "friendly and relaxed")
    extra = f"\n{p['extra']}\n" if p.get("extra") else ""

    return f"""You are {p['name']}, a patient phoning a medical clinic; the other voice is its receptionist. You're the caller, never staff, so never offer help.

Your details, given only when asked: date of birth {p['dob']}, phone {p['phone']}.{insurance}

What you want from this call, in order:
{goals}
You're done when: {s.done_when}
{extra}
The receptionist answers first. Reply to their greeting by saying why you're calling.

How you talk: {style}. It's a phone call, so keep each turn to one or two short sentences with one idea. Use contractions and the odd "um" or "yeah, that works". No lists, no markdown. Say dates and times the way people do out loud, like "next Tuesday at ten". Spell nothing unless asked.

Answer their questions, then steer back to your next goal; if they drift, politely bring it back. Never invent details you weren't given.

When your goals are met and nothing they asked is still open, or they clearly can't help after a couple of tries, say a short goodbye and use the end_call tool. Never say the tool's name out loud."""


class PatientAgent(Agent):
    def __init__(self, scenario: Scenario) -> None:
        super().__init__(instructions=build_instructions(scenario))
        self._ending = False
        self.ended_by: str | None = None

    async def on_user_turn_completed(self, turn_ctx, new_message) -> None:
        # Once we've said goodbye, the receptionist's "bye" shouldn't start a new reply.
        if self._ending:
            raise StopResponse()

    @function_tool
    async def end_call(self, context: RunContext) -> None:
        """Hang up. Use this right after your goodbye, once your goals are met
        or the receptionist clearly can't help."""
        self._ending = True
        self.ended_by = "patient"
        await context.wait_for_playout()
        await _let_them_finish(self.session)
        await hang_up()

    async def llm_node(self, chat_ctx, tools, model_settings):
        held, leaked = "", False
        async for chunk in Agent.default.llm_node(self, chat_ctx, tools, model_settings):
            if isinstance(chunk, str):
                text = chunk
            elif chunk.delta and chunk.delta.content:
                text = chunk.delta.content
                chunk.delta.content = None
                if chunk.delta.tool_calls:
                    yield chunk
            else:
                yield chunk
                continue
            clean, held, found = _strip_leaks(held + text)
            leaked |= found
            if clean:
                yield clean

        clean, _, found = _strip_leaks(held, final=True)
        if clean:
            yield clean
        if (leaked or found) and not self._ending:
            # Treat the written-out call as the real thing.
            self._ending = True
            self.ended_by = "patient"
            asyncio.create_task(self._hang_up_after_speaking())

    async def _hang_up_after_speaking(self) -> None:
        await asyncio.sleep(0.5)
        for _ in range(300):  # up to 30 s for the goodbye to play out
            if self.session.agent_state != "speaking":
                break
            await asyncio.sleep(0.1)
        await _let_them_finish(self.session)
        await hang_up()


def _strip_leaks(buf: str, final: bool = False) -> tuple[str, str, bool]:
    """Split buf into (text safe to speak, text held back, whether a leak was removed)."""
    cleaned = _LEAK.sub("", buf)
    found = cleaned != buf
    idx = cleaned.find(_LEAK_START)
    if idx != -1:  # an unfinished "functions.x(" is waiting for its ")"
        return (cleaned[:idx], "", True) if final else (cleaned[:idx], cleaned[idx:], found)
    if not final:  # hold back a tail that could still grow into "functions."
        for k in range(min(len(cleaned), len(_LEAK_START) - 1), 0, -1):
            if _LEAK_START.startswith(cleaned[-k:]):
                return cleaned[:-k], cleaned[-k:], found
    return cleaned, "", found


async def _let_them_finish(session: AgentSession, quiet_s: float = 1.5, max_s: float = 8.0) -> None:
    """Wait until the receptionist has been quiet for a moment, so we don't cut off their goodbye."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max_s
    quiet_since = loop.time()
    while loop.time() < deadline:
        if session.user_state == "speaking":
            quiet_since = loop.time()
        elif loop.time() - quiet_since >= quiet_s:
            return
        await asyncio.sleep(0.1)
