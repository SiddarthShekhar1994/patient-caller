"""LLM checks on finished calls. For now: which scenario goals were reached."""

import json

from openai import AsyncOpenAI

_GOALS_PROMPT = """Here is a phone call between a patient and a clinic receptionist, then the patient's goals.
For each goal, decide from the transcript alone whether it was actually achieved.
Reply as JSON: {"reached": [true or false, one per goal, in order]}"""


async def check_goals(model: str, transcript_text: str, goals: list[str]) -> list[bool | None]:
    if not transcript_text.strip():
        return [False] * len(goals)
    goal_list = "\n".join(f"{i}. {g}" for i, g in enumerate(goals, 1))
    resp = await AsyncOpenAI().chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _GOALS_PROMPT},
            {"role": "user", "content": f"TRANSCRIPT:\n{transcript_text}\n\nGOALS:\n{goal_list}"},
        ],
    )
    reached = json.loads(resp.choices[0].message.content or "{}").get("reached", [])
    if len(reached) != len(goals):
        return [None] * len(goals)
    return [bool(r) for r in reached]
