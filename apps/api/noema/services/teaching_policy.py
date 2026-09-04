"""The teaching policy: what makes a Professor reply a lesson step.

Two things live here. `principles()` is the TEACHING_PRINCIPLES layer that is
appended to the tutor prompt for the intents that teach (explain, deepen): the
arc, diagnosis first, how to answer wrong/partial/right, strategy switching,
depth, and the instruction to end the reply with a machine-readable
<PEDAGOGY>…</PEDAGOGY> record. `SidecarFilter` and `parse_pedagogy` are the
other half: the record must never reach the learner, and only validated fields
may enter the session's state.

The record rides on the same completion rather than a second model call, so
metadata costs no extra round trip and arrives with the reply. The filter holds
back only the tail that could be the start of the marker, so streaming stays
token-by-token until the record begins.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from noema.prompts import Prompt, load

__all__ = ["CLOSE", "OPEN", "SidecarFilter", "parse_pedagogy", "principles"]

OPEN = "<PEDAGOGY>"
CLOSE = "</PEDAGOGY>"

LEVELS = frozenset({"introductory", "foundational", "intermediate", "advanced", "expert"})
STRATEGIES = frozenset(
    {
        "definition",
        "analogy",
        "scenario",
        "worked_example",
        "prerequisite",
        "socratic",
        "contrast",
        "summary",
    }
)
SITUATIONS = frozenset(
    {
        "first_contact",
        "confused",
        "wrong",
        "partial",
        "correct",
        "deepen",
        "move_on",
        "off_topic",
    }
)
NEXT_ACTIONS = frozenset({"check", "explain", "deepen", "move_on", "review"})
VERDICTS = frozenset({"understood", "partial", "misunderstood", "unknown"})
STRENGTHS = frozenset({"weak", "moderate", "strong"})
PLAN_STATUS = frozenset({"done", "current", "planned"})


def principles() -> Prompt:
    return load("teaching.principles")


@dataclass
class SidecarFilter:
    """Split a streamed reply into what the learner sees and the record.

    `feed` returns text safe to show. Once the opening marker has begun, nothing
    more is shown; everything from there is collected as the record. A partial
    tail that *might* be the start of the marker is held back until the next
    chunk settles it, so a stray "<" in prose is delayed by one chunk, never lost.
    """

    shown: str = ""
    record: str = ""
    _pending: str = field(default="", repr=False)
    _in_record: bool = field(default=False, repr=False)

    def feed(self, text: str) -> str:
        if self._in_record:
            self.record += text
            return ""
        buffer = self._pending + text
        start = buffer.find(OPEN)
        if start != -1:
            visible, self.record = buffer[:start], buffer[start + len(OPEN) :]
            self._in_record = True
            self._pending = ""
            self.shown += visible
            return visible
        # Hold back a tail that is a proper prefix of the marker.
        hold = 0
        for size in range(min(len(OPEN) - 1, len(buffer)), 0, -1):
            if OPEN.startswith(buffer[-size:]):
                hold = size
                break
        visible, self._pending = (
            buffer[: len(buffer) - hold],
            buffer[len(buffer) - hold :],
        )
        self.shown += visible
        return visible

    def flush(self) -> str:
        """The stream ended: release any held tail that never became a marker."""
        if self._in_record:
            return ""
        visible, self._pending = self._pending, ""
        self.shown += visible
        return visible

    def pedagogy(self) -> dict[str, Any] | None:
        return parse_pedagogy(self.record)


def parse_pedagogy(raw: str) -> dict[str, Any] | None:
    """Validate the record. Unknown or malformed fields are dropped, never stored.

    Returns None when there is no usable record at all, so callers can record
    the turn without metadata rather than fail it.
    """
    text = raw.strip()
    if text.endswith(CLOSE):
        text = text[: -len(CLOSE)].strip()
    if not text:
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None

    out: dict[str, Any] = {}
    for key, limit in (
        ("subject", 200),
        ("current_topic", 200),
        ("current_concept", 200),
        ("session_goal", 400),
        ("misconception", 400),
        ("misconception_resolved", 400),
    ):
        value = _text(data.get(key))
        if value:
            out[key] = value[:limit]

    for key, allowed in (
        ("learner_level", LEVELS),
        ("depth", LEVELS),
        ("strategy", STRATEGIES),
        ("situation", SITUATIONS),
        ("next_action", NEXT_ACTIONS),
    ):
        value = _text(data.get(key)).lower()
        if value in allowed:
            out[key] = value

    evidence = data.get("mastery_evidence")
    if isinstance(evidence, dict):
        concept = _text(evidence.get("concept"))
        verdict = _text(evidence.get("verdict")).lower()
        strength = _text(evidence.get("strength")).lower()
        if concept and verdict in VERDICTS and verdict != "unknown":
            out["mastery_evidence"] = {
                "concept": concept[:200],
                "verdict": verdict,
                "strength": strength if strength in STRENGTHS else "weak",
            }

    plan = data.get("plan")
    if isinstance(plan, list):
        items = []
        for entry in plan[:12]:
            if not isinstance(entry, dict):
                continue
            topic = _text(entry.get("topic"))
            status = _text(entry.get("status")).lower()
            if topic:
                items.append(
                    {
                        "topic": topic[:200],
                        "status": status if status in PLAN_STATUS else "planned",
                    }
                )
        if items:
            out["plan"] = items

    return out or None


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""
