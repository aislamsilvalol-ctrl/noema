"""CurriculumEngine: a goal → a course plan the lesson moves through.

Macro-structure plus next steps, never a hundred lessons written in advance:
three to six modules, each with two to four lessons, each naming the two to
four concepts it teaches. The plan is stored on the journey as JSON and
revised as the learner shows what they already know (a lesson skipped stays
in the plan, marked skipped — a plan should say what was decided).

The one structured call runs once, on the first turn; every later turn reads
the plan from the row. If the call fails, a one-module plan built from the
goal's subject stands in and the professor teaches from it — the plan can be
regenerated later without losing anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from noema.core.logging import get_logger
from noema.prompts import load
from noema.providers.base import (
    Message,
    ProviderError,
    Role,
    StructuredRequest,
    TaskClass,
)
from noema.providers.gateway import AIGateway

from .intent import LearningGoal

log = get_logger(__name__)

__all__ = [
    "Position",
    "advance_lesson",
    "build_plan",
    "concepts_of_current_lesson",
    "fallback_plan",
    "mark_lesson",
    "next_lessons",
    "public_plan",
    "render_plan",
    "skip_lesson",
    "validate_plan",
]

STATUSES = ("planned", "current", "done", "skipped")
MAX_MODULES = 6
MAX_LESSONS = 4
MAX_CONCEPTS = 4

PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "modules": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "lessons": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "concepts": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": ["title", "concepts"],
                        },
                    },
                },
                "required": ["title", "lessons"],
            },
        }
    },
    "required": ["modules"],
}


@dataclass(frozen=True, slots=True)
class Position:
    module: int
    lesson: int


async def build_plan(
    gateway: AIGateway, goal: LearningGoal, *, model: str | None
) -> dict[str, Any]:
    prompt = load("professor.curriculum")
    user = (
        f"Subject: {goal.subject}\nObjective: {goal.objective}\n"
        f"Learner level: {goal.inferred_level}\nDesired depth: {goal.desired_depth}\n"
        f"Prerequisites they may lack: {', '.join(goal.prerequisites) or 'unknown'}\n"
        f"Language of the lesson: {goal.language or 'the language of the objective'}"
    )
    try:
        payload = await gateway.structured(
            StructuredRequest(
                messages=[
                    Message(role=Role.SYSTEM, content=prompt.body),
                    Message(role=Role.USER, content=user),
                ],
                json_schema=PLAN_SCHEMA,
                task=TaskClass.SUMMARIZE,
                model=model,
                metadata={"feature": "professor.curriculum"},
            )
        )
    except ProviderError as exc:
        log.warning("professor.curriculum_failed", error=str(exc))
        return fallback_plan(goal)
    plan = validate_plan(payload)
    return plan if plan["modules"] else fallback_plan(goal)


def fallback_plan(goal: LearningGoal) -> dict[str, Any]:
    return {
        "modules": [
            {
                "title": goal.subject,
                "status": "current",
                "lessons": [
                    {
                        "title": goal.subject,
                        "status": "current",
                        "concepts": [goal.subject],
                    }
                ],
            }
        ],
        "generated": False,
    }


def validate_plan(payload: dict[str, Any]) -> dict[str, Any]:
    """Only well-formed, non-empty modules and lessons survive; the first
    lesson becomes current."""
    modules: list[dict[str, Any]] = []
    raw_modules = payload.get("modules")
    for raw in raw_modules if isinstance(raw_modules, list) else []:
        if not isinstance(raw, dict):
            continue
        title = _text(raw.get("title"))
        lessons: list[dict[str, Any]] = []
        raw_lessons = raw.get("lessons")
        for lesson in raw_lessons if isinstance(raw_lessons, list) else []:
            if not isinstance(lesson, dict):
                continue
            ltitle = _text(lesson.get("title"))
            raw_concepts = lesson.get("concepts")
            concepts = [
                c.strip()[:120]
                for c in (raw_concepts if isinstance(raw_concepts, list) else [])
                if isinstance(c, str) and c.strip()
            ][:MAX_CONCEPTS]
            if ltitle and concepts:
                lessons.append(
                    {"title": ltitle[:160], "status": "planned", "concepts": concepts}
                )
            if len(lessons) >= MAX_LESSONS:
                break
        if title and lessons:
            modules.append(
                {"title": title[:160], "status": "planned", "lessons": lessons}
            )
        if len(modules) >= MAX_MODULES:
            break
    if modules:
        modules[0]["status"] = "current"
        modules[0]["lessons"][0]["status"] = "current"
    return {"modules": modules, "generated": True}


def _lesson(plan: dict[str, Any], position: Position) -> dict[str, Any] | None:
    try:
        return plan["modules"][position.module]["lessons"][position.lesson]  # type: ignore[no-any-return]
    except (IndexError, KeyError, TypeError):
        return None


def concepts_of_current_lesson(plan: dict[str, Any], position: Position) -> list[str]:
    lesson = _lesson(plan, position)
    return list(lesson["concepts"]) if lesson else []


def next_lessons(plan: dict[str, Any], position: Position, count: int = 2) -> list[str]:
    """Titles of the lessons after the current one, across module borders."""
    out: list[str] = []
    modules = plan.get("modules", [])
    m, li = position.module, position.lesson + 1
    while m < len(modules) and len(out) < count:
        lessons = modules[m]["lessons"]
        while li < len(lessons) and len(out) < count:
            if lessons[li].get("status") != "skipped":
                out.append(lessons[li]["title"])
            li += 1
        m, li = m + 1, 0
    return out


def mark_lesson(plan: dict[str, Any], position: Position, status: str) -> dict[str, Any]:
    """A new plan dict with that lesson's status changed (JSONB is replaced,
    never mutated in place — see teaching_session.py)."""
    if status not in STATUSES:
        return plan
    import copy

    updated = copy.deepcopy(plan)
    lesson = _lesson(updated, position)
    if lesson is not None:
        lesson["status"] = status
    module = updated["modules"][position.module] if lesson is not None else None
    if module is not None and all(
        lesson_["status"] in ("done", "skipped") for lesson_ in module["lessons"]
    ):
        module["status"] = "done"
    return updated


def advance_lesson(
    plan: dict[str, Any], position: Position
) -> tuple[dict[str, Any], Position | None]:
    """Mark the current lesson done and make the next one current."""
    return _move(plan, position, "done")


def skip_lesson(
    plan: dict[str, Any], position: Position
) -> tuple[dict[str, Any], Position | None]:
    return _move(plan, position, "skipped")


def _move(
    plan: dict[str, Any], position: Position, status: str
) -> tuple[dict[str, Any], Position | None]:
    updated = mark_lesson(plan, position, status)
    modules = updated.get("modules", [])
    m, li = position.module, position.lesson + 1
    while m < len(modules):
        if li < len(modules[m]["lessons"]):
            modules[m]["status"] = "current"
            modules[m]["lessons"][li]["status"] = "current"
            return updated, Position(m, li)
        m, li = m + 1, 0
    return updated, None


def render_plan(plan: dict[str, Any], position: Position) -> str:
    """The plan for the prompt: where we are and what comes next, compactly."""
    modules = plan.get("modules", [])
    if not modules:
        return ""
    done = sum(
        1
        for module in modules
        for lesson in module["lessons"]
        if lesson.get("status") in ("done", "skipped")
    )
    total = sum(len(module["lessons"]) for module in modules)
    current = _lesson(plan, position)
    lines = [f"Course: {len(modules)} modules, {total} lessons, {done} done."]
    if current is not None:
        module = modules[position.module]
        lines.append(f"Current module: {module['title']}")
        lines.append(
            f"Current lesson: {current['title']} — concepts: "
            + ", ".join(current["concepts"])
        )
    upcoming = next_lessons(plan, position)
    if upcoming:
        lines.append("Next: " + " → ".join(upcoming))
    return "\n".join(lines)


def public_plan(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """What the client draws: titles and statuses, no prompts."""
    return [
        {
            "title": module["title"],
            "status": module.get("status", "planned"),
            "lessons": [
                {
                    "title": lesson["title"],
                    "status": lesson.get("status", "planned"),
                    "concepts": list(lesson.get("concepts", [])),
                }
                for lesson in module["lessons"]
            ],
        }
        for module in plan.get("modules", [])
    ]


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""
