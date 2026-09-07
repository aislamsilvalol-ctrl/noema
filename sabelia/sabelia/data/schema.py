"""The Learning Event: the one record every model in Sabelia is trained on.

Design notes
------------
* **Versioned.** ``schema_version`` is on every event. A model registry entry
  records which schema it was trained against; an adapter that emits an
  older version is upgraded explicitly (``upgrade``), never silently.
* **Pseudonymous.** ``student_id`` is an opaque string. The product that
  emits events is responsible for pseudonymising identity before events
  reach the pipeline; nothing here needs a name, an e-mail or an account.
* **Minimal.** Every field either feeds a model input, a target, or the
  split logic. There is no free text. The ``confidence`` field is the
  learner's *stated* confidence on an answer (a pedagogical signal), not an
  inferred trait.
* **Time in seconds.** ``timestamp`` is UNIX seconds (float). Response
  latency is milliseconds because that is how products measure it.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator

SCHEMA_VERSION = 1


class EventType(StrEnum):
    """What kind of interaction produced the event.

    ``answer`` is any graded response (quiz, check, exam item).
    ``recall`` is a spaced-repetition showing graded by the learner or by
    the system (flashcard). ``exposure`` is being taught a concept without
    a graded response; it carries no ``correct`` and is never a prediction
    target, but it is context the sequence models may use.
    """

    answer = "answer"
    recall = "recall"
    exposure = "exposure"


class LearningEvent(BaseModel):
    schema_version: int = Field(default=SCHEMA_VERSION, ge=1)
    event_id: str
    student_id: str
    concept_id: str
    item_id: str | None = None
    timestamp: float = Field(description="UNIX seconds")
    event_type: EventType = EventType.answer
    correct: bool | None = Field(default=None, description="Graded outcome; None for exposures")
    difficulty: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Item difficulty if known, 0 easy … 1 hard"
    )
    response_ms: int | None = Field(default=None, ge=0)
    hints: int = Field(default=0, ge=0)
    attempt: int = Field(default=1, ge=1, description="1 for the first attempt at this item")
    confidence: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Learner-stated confidence, if asked"
    )
    session_id: str | None = None
    source: str = Field(default="unknown", description="Dataset or product that emitted it")
    extra: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _graded_events_have_outcome(self) -> LearningEvent:
        if self.event_type is not EventType.exposure and self.correct is None:
            raise ValueError("answer and recall events must carry `correct`")
        return self

    @property
    def is_graded(self) -> bool:
        return self.correct is not None


def upgrade(raw: dict[str, Any]) -> LearningEvent:
    """Bring an event dict of any known schema version to the current one."""
    version = int(raw.get("schema_version", 1))
    if version > SCHEMA_VERSION:
        raise ValueError(f"event schema {version} is newer than this library ({SCHEMA_VERSION})")
    # v1 is the first version; upgrades are added here as the schema moves.
    return LearningEvent.model_validate({**raw, "schema_version": SCHEMA_VERSION})
