"""Phase 3: a lecture segment becomes concepts, relations and evidenced claims.

Every object that comes out of here carries two things the rest of the pipeline
refuses to work without:

* **Evidence.** `source_id`, `start_ms`, `end_ms` — the exact stretch of the
  exact lecture the model was reading. A claim whose timestamp does not contain
  it is a claim nobody can check, and Phase 6 measures precisely that.
* **Support.** `source_supported` when the segment itself carries the object,
  `inferred` when the model connected it. The flag is stored, never collapsed:
  a knowledge base that forgets which half it invented is a knowledge base that
  cannot be corrected.

What the model returns is a proposal. This module validates before anything
travels: names bounded, difficulty clamped, relations pointing only at concepts
that were actually returned, self-relations dropped, unknown enum values
discarded rather than coerced into a plausible neighbour. A segment the model
fails on is skipped and logged — losing one segment of a lecture is a smaller
loss than a graph with invented edges in it.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from noema.academic.captions import Segment
from noema.core.logging import get_logger
from noema.prompts import PROMPT_DIR, load
from noema.providers.base import (
    Message,
    ProviderError,
    Role,
    StructuredRequest,
    TaskClass,
)

log = get_logger(__name__)


class Structured(Protocol):
    """The one thing this module needs from a gateway.

    Typed as what is used rather than as `AIGateway`, so a test can pass a
    stand-in that answers with the payloads models really return, and so
    nothing here quietly grows a dependency on the rest of the gateway.
    """

    async def structured(self, request: StructuredRequest) -> dict[str, Any]: ...


MAX_NAME = 200
MAX_DEFINITION = 600
MAX_CLAIM = 400
MAX_CONCEPTS = 12
MAX_RELATIONS = 24
MAX_CLAIMS = 12
MAX_LIST = 8

SCHEMA: dict[str, Any] = json.loads(
    (PROMPT_DIR / "extract.lecture.schema.json").read_text(encoding="utf-8")
)


class Support(StrEnum):
    source_supported = "source_supported"
    inferred = "inferred"


class Epistemic(StrEnum):
    fact = "fact"
    model = "model"
    theory = "theory"
    interpretation = "interpretation"
    hypothesis = "hypothesis"
    example = "example"


class RelationKind(StrEnum):
    prerequisite_of = "prerequisite_of"
    part_of = "part_of"
    related_to = "related_to"
    used_in = "used_in"
    contrasts_with = "contrasts_with"
    example_of = "example_of"


@dataclass(frozen=True, slots=True)
class Evidence:
    """Where in which lecture. Everything derived carries one of these."""

    source_id: str
    start_ms: int
    end_ms: int
    segment: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "segment": self.segment,
        }


@dataclass(frozen=True, slots=True)
class Concept:
    name: str
    definition: str
    difficulty: float
    support: Support
    evidence: Evidence

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "definition": self.definition,
            "difficulty": self.difficulty,
            "support": self.support.value,
            "evidence": self.evidence.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class Relation:
    source: str
    target: str
    kind: RelationKind
    support: Support
    evidence: Evidence

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "kind": self.kind.value,
            "support": self.support.value,
            "evidence": self.evidence.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class Claim:
    text: str
    concept: str
    epistemic: Epistemic
    support: Support
    evidence: Evidence

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "concept": self.concept,
            "epistemic": self.epistemic.value,
            "support": self.support.value,
            "evidence": self.evidence.as_dict(),
        }


@dataclass(slots=True)
class Extraction:
    """What one segment yielded, with the counts a review queue is built on."""

    evidence: Evidence
    concepts: list[Concept] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    misconceptions: list[str] = field(default_factory=list)
    quality: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (self.concepts or self.claims)

    @property
    def inferred_share(self) -> float:
        """How much of this segment's output the model supplied rather than read."""
        supports: list[Support] = [
            *(c.support for c in self.concepts),
            *(r.support for r in self.relations),
            *(c.support for c in self.claims),
        ]
        if not supports:
            return 0.0
        inferred = sum(1 for s in supports if s is Support.inferred)
        return inferred / len(supports)

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.evidence.as_dict(),
            "quality": self.quality,
            "inferred_share": round(self.inferred_share, 3),
            "concepts": [c.as_dict() for c in self.concepts],
            "relations": [r.as_dict() for r in self.relations],
            "claims": [c.as_dict() for c in self.claims],
            "examples": self.examples,
            "misconceptions": self.misconceptions,
        }


async def extract_segment(
    gateway: Structured,
    segment: Segment,
    *,
    source_id: str,
    lecture: str = "",
    course: str = "",
    model: str | None = None,
) -> Extraction:
    """One segment → one Extraction. A failure returns an empty one, never raises."""
    evidence = Evidence(
        source_id=source_id,
        start_ms=segment.start_ms,
        end_ms=segment.end_ms,
        segment=segment.index,
    )
    result = Extraction(evidence=evidence, quality=list(segment.quality))
    if not segment.usable:
        return result
    prompt = load("extract.lecture")
    context = " · ".join(part for part in (course, lecture) if part)
    try:
        payload = await gateway.structured(
            StructuredRequest(
                messages=[
                    Message(role=Role.SYSTEM, content=prompt.body),
                    # Delimited and labelled as material: a transcript is speech
                    # someone else recorded, and it can contain anything.
                    Message(
                        role=Role.USER,
                        content=(
                            f"<LECTURE>{context}</LECTURE>\n"
                            f"<SEGMENT start_ms={segment.start_ms} "
                            f"end_ms={segment.end_ms}>\n{segment.text}\n</SEGMENT>"
                        ),
                    ),
                ],
                json_schema=SCHEMA,
                task=TaskClass.EXTRACT_CONCEPTS,
                model=model,
            )
        )
    except ProviderError as exc:
        log.warning(
            "academic.extraction.failed",
            source_id=source_id,
            segment=segment.index,
            error=str(exc),
        )
        return result
    return parse_extraction(payload, evidence, quality=list(segment.quality))


async def extract_segments(
    gateway: Structured,
    segments: Sequence[Segment],
    *,
    source_id: str,
    lecture: str = "",
    course: str = "",
    model: str | None = None,
) -> list[Extraction]:
    """Every segment of one lecture, in order. Sequential: order is cheap here."""
    out: list[Extraction] = []
    for segment in segments:
        out.append(
            await extract_segment(
                gateway,
                segment,
                source_id=source_id,
                lecture=lecture,
                course=course,
                model=model,
            )
        )
    return out


def parse_extraction(
    payload: dict[str, Any], evidence: Evidence, *, quality: list[str] | None = None
) -> Extraction:
    """Validate a model response into an Extraction. Structure is not sanity."""
    result = Extraction(evidence=evidence, quality=quality or [])
    names: dict[str, str] = {}  # lowercased → as returned, for relation targets

    for item in _items(payload.get("concepts"), MAX_CONCEPTS):
        name = _text(item.get("name"), MAX_NAME)
        if not name or name.lower() in names:
            continue
        names[name.lower()] = name
        result.concepts.append(
            Concept(
                name=name,
                definition=_text(item.get("definition"), MAX_DEFINITION),
                difficulty=_clamp(item.get("difficulty")),
                support=_support(item.get("support")),
                evidence=evidence,
            )
        )

    for item in _items(payload.get("relations"), MAX_RELATIONS):
        source = names.get(_text(item.get("source"), MAX_NAME).lower())
        target = names.get(_text(item.get("target"), MAX_NAME).lower())
        # An edge to a concept the model did not return is an edge into nothing:
        # the graph would gain a node no segment supports.
        if not source or not target or source == target:
            continue
        kind = _enum(RelationKind, item.get("kind"))
        if kind is None:
            continue
        result.relations.append(
            Relation(
                source=source,
                target=target,
                kind=kind,
                support=_support(item.get("support")),
                evidence=evidence,
            )
        )

    for item in _items(payload.get("claims"), MAX_CLAIMS):
        text = _text(item.get("text"), MAX_CLAIM)
        if not text:
            continue
        epistemic = _enum(Epistemic, item.get("epistemic"))
        if epistemic is None:
            # An untagged claim is the one thing this pipeline cannot store:
            # the tag is what stops a model being read as a fact.
            continue
        result.claims.append(
            Claim(
                text=text,
                concept=names.get(_text(item.get("concept"), MAX_NAME).lower(), ""),
                epistemic=epistemic,
                support=_support(item.get("support")),
                evidence=evidence,
            )
        )

    result.examples = _strings(payload.get("examples"))
    result.misconceptions = _strings(payload.get("misconceptions"))
    return result


def _items(value: Any, limit: int) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value[:limit] if isinstance(item, dict)]


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out = [_text(entry, MAX_CLAIM) for entry in value[:MAX_LIST]]
    return [entry for entry in out if entry]


def _text(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit].strip()


def _clamp(value: Any) -> float:
    try:
        difficulty = float(value)
    except (TypeError, ValueError):
        return 0.5
    return min(max(difficulty, 0.0), 1.0)


def _support(value: Any) -> Support:
    """Anything that is not explicitly `source_supported` is treated as inferred.

    The asymmetry is the point: an unmarked object is one nobody promised the
    segment carried, and calling it supported would launder exactly the thing
    the flag exists to keep visible.
    """
    return (
        Support.source_supported
        if str(value) == Support.source_supported.value
        else Support.inferred
    )


def _enum(kind: type[StrEnum], value: Any) -> Any:
    try:
        return kind(str(value))
    except ValueError:
        return None
