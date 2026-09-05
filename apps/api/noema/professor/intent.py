"""LearningIntentParser: "Quero aprender X" → a structured goal.

One economy-tier structured call on the first message of a journey. If it
fails, the goal is still usable: the subject is the sentence with the asking
words removed, the level is foundational, and the professor finds out the
rest by teaching — which is what a first lesson does anyway.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
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

log = get_logger(__name__)

__all__ = ["LearningGoal", "fallback_goal", "parse_goal"]

LEVELS = ("introductory", "foundational", "intermediate", "advanced", "expert")

GOAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "subject": {"type": "string"},
        "objective": {"type": "string"},
        "inferred_level": {"type": "string", "enum": list(LEVELS)},
        "desired_depth": {"type": "string", "enum": list(LEVELS)},
        "prerequisites": {"type": "array", "items": {"type": "string"}},
        "language": {"type": "string"},
    },
    "required": [
        "subject",
        "objective",
        "inferred_level",
        "desired_depth",
        "prerequisites",
    ],
}

_ASKING = re.compile(
    r"^\s*(eu\s+)?(quero|queria|gostaria de|preciso|vou|me ensin[ae]|ensina|ensine|"
    r"i want to|i'd like to|i need to|teach me|help me|quiero|necesito|enséñame)\s+"
    r"(aprender|entender|estudar|saber|dominar|learn|understand|study|know|master|"
    r"aprender|entender|estudiar)?\s*",
    re.IGNORECASE,
)
_TRAILING = re.compile(r"[.!?…]+$")


@dataclass(frozen=True, slots=True)
class LearningGoal:
    subject: str
    objective: str
    inferred_level: str = "foundational"
    desired_depth: str = "foundational"
    prerequisites: tuple[str, ...] = field(default_factory=tuple)
    language: str = ""
    #: False when the parser could not run and the goal is the fallback.
    parsed: bool = True


def fallback_goal(text: str) -> LearningGoal:
    """The goal without a model: the sentence, minus the asking."""
    one_line = " ".join(text.split())
    subject = _TRAILING.sub("", _ASKING.sub("", one_line, count=1)).strip()
    if not subject:
        subject = one_line[:120]
    # A level the learner stated in the same breath is worth reading.
    lowered = one_line.lower()
    level = "foundational"
    if any(w in lowered for w in ("do zero", "from scratch", "desde cero", "iniciante")):
        level = "introductory"
    elif any(w in lowered for w in ("aprofundar", "avan", "deeper", "advanced")):
        level = "intermediate"
    return LearningGoal(
        subject=subject[:200],
        objective=one_line[:400],
        inferred_level=level,
        desired_depth="intermediate" if level == "intermediate" else "foundational",
        parsed=False,
    )


async def parse_goal(gateway: AIGateway, text: str, *, model: str | None) -> LearningGoal:
    prompt = load("professor.parse_goal")
    try:
        payload = await gateway.structured(
            StructuredRequest(
                messages=[
                    Message(role=Role.SYSTEM, content=prompt.body),
                    Message(role=Role.USER, content=text.strip()[:2000]),
                ],
                json_schema=GOAL_SCHEMA,
                task=TaskClass.CLASSIFY_INTENT,
                model=model,
                metadata={"feature": "professor.parse_goal"},
            )
        )
    except ProviderError as exc:
        log.warning("professor.parse_goal_failed", error=str(exc))
        return fallback_goal(text)

    subject = _text(payload.get("subject"))
    if not subject:
        return fallback_goal(text)
    level = _text(payload.get("inferred_level")).lower()
    depth = _text(payload.get("desired_depth")).lower()
    prerequisites = payload.get("prerequisites")
    return LearningGoal(
        subject=subject[:200],
        objective=_text(payload.get("objective"))[:400] or subject,
        inferred_level=level if level in LEVELS else "foundational",
        desired_depth=depth if depth in LEVELS else "foundational",
        prerequisites=tuple(
            p.strip()[:120]
            for p in (prerequisites if isinstance(prerequisites, list) else [])
            if isinstance(p, str) and p.strip()
        )[:6],
        language=_text(payload.get("language"))[:16],
    )


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""
