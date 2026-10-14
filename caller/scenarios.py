"""Scenario files: one YAML per call, loaded and checked here.

Unknown top-level fields are rejected, so a scenario can't sneak in its own
destination number. The number we dial lives only in config.py.
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

SCENARIO_DIR = Path(__file__).resolve().parent.parent / "scenarios"

_REQUIRED = {"id", "title", "persona", "goals", "done_when"}
_ALLOWED = _REQUIRED | {"flags", "notes"}
_PERSONA_REQUIRED = {"name", "dob", "phone"}


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    persona: dict
    goals: list[str]
    done_when: str
    flags: dict = field(default_factory=dict)
    notes: str = ""


def list_scenario_ids() -> list[str]:
    return sorted(p.stem for p in SCENARIO_DIR.glob("*.yaml"))


def load_scenario(scenario_id: str) -> Scenario:
    path = SCENARIO_DIR / f"{scenario_id}.yaml"
    if not path.is_file():
        known = ", ".join(list_scenario_ids()) or "none"
        raise SystemExit(f"No scenario {scenario_id!r}. Known: {known}")

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    problems = []
    if missing := _REQUIRED - data.keys():
        problems.append(f"missing {sorted(missing)}")
    if unknown := data.keys() - _ALLOWED:
        problems.append(f"unknown fields {sorted(unknown)}")
    if data.get("id") != scenario_id:
        problems.append(f"id must match the file name ({scenario_id})")
    if missing := _PERSONA_REQUIRED - (data.get("persona") or {}).keys():
        problems.append(f"persona missing {sorted(missing)}")
    goals = data.get("goals")
    if not goals or not all(isinstance(g, str) for g in goals):
        problems.append("goals must be a non-empty list of strings")
    if problems:
        raise SystemExit(f"{path.name}: " + "; ".join(problems))

    return Scenario(**data)
