"""The patient persona and its one tool, end_call."""

import asyncio

from livekit.agents import Agent, AgentSession, RunContext, StopResponse, function_tool

from .scenarios import Scenario
from .telephony import hang_up


def build_instructions(s: Scenario) -> str:
    p = s.persona
    goals = "\n".join(f"{i}. {g}" for i, g in enumerate(s.goals, 1))
    insurance = f" Insurance: {p['insurance']}." if p.get("insurance") else ""
    style = p.get("style", "friendly and relaxed")

    return f"""You are {p['name']}, a patient phoning a medical clinic. The other voice is the clinic's receptionist. You are the caller, never staff, so never offer help or ask how you can help.

Your details, given only when asked: date of birth {p['dob']}, phone {p['phone']}.{insurance}

What you want from this call, in order:
{goals}
You're done when: {s.done_when}

The receptionist answers first. Reply to their greeting by saying why you're calling.

How you talk: {style}. It's a phone call, so keep each turn to one or two short sentences with one idea. Use contractions and the odd "um" or "yeah, that works". No lists, no markdown. Say dates and times the way people do out loud, like "next Tuesday at ten". Spell nothing unless asked.

Answer their questions, then steer back to your next goal. If they drift or stall, politely bring it back. Never invent details you weren't given; say you're not sure.

When your goals are met, or they clearly can't help after a couple of tries, say a short goodbye and call end_call in the same turn."""


class PatientAgent(Agent):
    def __init__(self, scenario: Scenario) -> None:
        super().__init__(instructions=build_instructions(scenario))
        self._ending = False

    async def on_user_turn_completed(self, turn_ctx, new_message) -> None:
        # Once we've said goodbye, the receptionist's "bye" shouldn't start a new reply.
        if self._ending:
            raise StopResponse()

    @function_tool
    async def end_call(self, context: RunContext) -> None:
        """Hang up. Call this right after your goodbye, once your goals are met
        or the receptionist clearly can't help."""
        self._ending = True
        await context.wait_for_playout()
        await _let_them_finish(context.session)
        await hang_up()


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
