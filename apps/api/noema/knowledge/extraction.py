"""Turning chunks into candidate concepts.

The model's output is a proposal, never a fact. Everything here validates before it
travels: names bounded, difficulty clamped, self-references dropped, and anything
that fails the schema discarded rather than half-imported.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from noema.core.logging import get_logger
from noema.db.models import EdgeKind
from noema.prompts import PROMPT_DIR, load
from noema.providers.base import (
    Message,
    ProviderError,
    Role,
    StructuredRequest,
    TaskClass,
)
from noema.providers.gateway import AIGateway

log = get_logger(__name__)

__all__ = ["ExtractedConcept", "extract_concepts", "parse_extraction"]

#: Batched so a 600-chunk textbook does not become 600 round trips.
BATCH_SIZE = 5

MAX_NAME_LENGTH = 200
MAX_DEFINITION_LENGTH = 600
MAX_CONCEPTS_PER_BATCH = 25

#: Read once at import, for the same reason as the card schema: a static file
#: shipped with the code has no business being read inside the event loop.
SCHEMA: dict[str, Any] = json.loads(
    (PROMPT_DIR / "extract.concepts.schema.json").read_text(encoding="utf-8")
)


@dataclass(frozen=True, slots=True)
class Relation:
    target: str
    kind: EdgeKind


@dataclass(frozen=True, slots=True)
class ExtractedConcept:
    name: str
    definition: str
    difficulty: float
    prerequisites: list[str] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    source_chunk_ids: list[str] = field(default_factory=list)


async def extract_concepts(
    gateway: AIGateway,
    chunks: Sequence[tuple[str, str]],
    *,
    model: str | None = None,
) -> list[ExtractedConcept]:
    """Extract concepts from ``(chunk_id, text)`` pairs.

    A batch that fails is skipped, not fatal: losing the concepts from five chunks
    of a textbook is a smaller loss than losing the ingest.
    """
    prompt = load("extract.concepts")
    found: list[ExtractedConcept] = []

    for start in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[start : start + BATCH_SIZE]
        passages = "\n\n".join(
            f"<passage id={index}>\n{text.strip()}\n</passage>"
            for index, (_, text) in enumerate(batch, start=1)
        )

        try:
            payload = await gateway.structured(
                StructuredRequest(
                    messages=[
                        Message(role=Role.SYSTEM, content=prompt.body),
                        # Delimited and labelled as material: the passages are the
                        # user's documents, which can contain text aimed at the model.
                        Message(
                            role=Role.USER, content=f"<PASSAGES>\n{passages}\n</PASSAGES>"
                        ),
                    ],
                    json_schema=SCHEMA,
                    task=TaskClass.EXTRACT_CONCEPTS,
                    model=model,
                )
            )
        except ProviderError as exc:
            log.warning("extraction.batch_failed", offset=start, error=str(exc))
            continue

        chunk_ids = [chunk_id for chunk_id, _ in batch]
        found.extend(parse_extraction(payload, chunk_ids))

    return found


def parse_extraction(
    payload: dict[str, Any], source_chunk_ids: Sequence[str]
) -> list[ExtractedConcept]:
    """Validate and clean a model response.

    Structured output means the shape is right, not that the content is sane. A
    concept naming itself as its own prerequisite is a real thing models produce.
    """
    raw = payload.get("concepts")
    if not isinstance(raw, list):
        return []

    concepts: list[ExtractedConcept] = []
    for item in raw[:MAX_CONCEPTS_PER_BATCH]:
        if not isinstance(item, dict):
            continue

        name = str(item.get("name") or "").strip()[:MAX_NAME_LENGTH]
        if not name:
            continue

        prerequisites = _names(item.get("prerequisites"), exclude=name)
        relations = _relations(item.get("relations"), exclude=name)

        concepts.append(
            ExtractedConcept(
                name=name,
                definition=str(item.get("definition") or "").strip()[
                    :MAX_DEFINITION_LENGTH
                ],
                difficulty=_clamp(item.get("difficulty")),
                prerequisites=prerequisites,
                relations=relations,
                source_chunk_ids=list(source_chunk_ids),
            )
        )

    return concepts


def _names(value: Any, *, exclude: str) -> list[str]:
    if not isinstance(value, list):
        return []

    seen: dict[str, None] = {}
    for entry in value:
        name = str(entry or "").strip()[:MAX_NAME_LENGTH]
        # A concept is never its own prerequisite; models emit this often enough
        # that dropping it here is cheaper than validating it downstream.
        if name and name.lower() != exclude.lower():
            seen.setdefault(name, None)
    return list(seen)


def _relations(value: Any, *, exclude: str) -> list[Relation]:
    if not isinstance(value, list):
        return []

    relations: list[Relation] = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        target = str(entry.get("target") or "").strip()[:MAX_NAME_LENGTH]
        if not target or target.lower() == exclude.lower():
            continue
        try:
            kind = EdgeKind(str(entry.get("kind")))
        except ValueError:
            continue
        # prerequisite_of arrives through its own field; accepting it here too would
        # let the model state the relation in the direction it prefers.
        if kind is EdgeKind.PREREQUISITE_OF:
            continue
        relations.append(Relation(target=target, kind=kind))

    return relations


def _clamp(value: Any) -> float:
    try:
        difficulty = float(value)
    except (TypeError, ValueError):
        return 0.5
    return min(max(difficulty, 0.0), 1.0)
