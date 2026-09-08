"""Phase 4: many lectures' extractions become one atlas, disagreement included.

Extraction produces one segment's view at a time, so the same concept arrives
from four lectures under three names, defined slightly differently each time.
Reconciliation folds those into one entry per concept and keeps what folding
would otherwise destroy:

* **Which lectures support it.** A concept seen in one segment of one lecture
  and a concept seen across four courses are not the same kind of thing, and
  `confidence` says which one this is.
* **Definitions that disagree.** When two sources define a concept differently
  the difference is recorded, not resolved. One source saying a limit is "what
  the function approaches" and another giving epsilon-delta is not an error to
  be voted on.
* **What was inferred.** A concept that only ever arrived marked `inferred` is
  marked that way here too, however many times it arrived: repetition by one
  model is not evidence.

Nothing here writes to the database. It produces a plan a person reads —
`merge`, `review` or `create` per concept, borrowing `knowledge.resolution`'s
own thresholds so the academic pipeline and the notebook pipeline decide
sameness the same way. The graph the product serves is only ever changed by
someone approving that plan.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from noema.academic.extraction import Extraction, RelationKind, Support
from noema.knowledge.resolution import Decision, normalize_name, resolve

#: Two definitions this similar are the same statement in different words.
SAME_DEFINITION = 0.72

#: A definition shorter than this is not a definition to disagree about.
MIN_DEFINITION = 24


@dataclass(frozen=True, slots=True)
class Mention:
    """One lecture's view of a concept: the words, and where they were said."""

    source_id: str
    start_ms: int
    end_ms: int
    name: str
    definition: str
    support: Support

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "name": self.name,
            "definition": self.definition,
            "support": self.support.value,
        }


@dataclass(frozen=True, slots=True)
class Disagreement:
    """Two sources defining the same concept differently. Kept, not resolved."""

    left: Mention
    right: Mention
    similarity: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "left": self.left.as_dict(),
            "right": self.right.as_dict(),
            "similarity": round(self.similarity, 3),
        }


@dataclass(slots=True)
class ReconciledConcept:
    key: str
    name: str
    aliases: list[str] = field(default_factory=list)
    mentions: list[Mention] = field(default_factory=list)
    disagreements: list[Disagreement] = field(default_factory=list)
    difficulty: float = 0.5
    #: What a reviewer is asked to do, and why.
    decision: str = Decision.CREATE.value
    target_id: str | None = None
    reason: str = ""

    @property
    def lectures(self) -> set[str]:
        return {m.source_id for m in self.mentions}

    @property
    def source_supported(self) -> bool:
        """At least one segment carried it, rather than a model connecting it."""
        return any(m.support is Support.source_supported for m in self.mentions)

    @property
    def confidence(self) -> float:
        """How much of an atlas this concept has behind it, from 0 to 1.

        Agreement across *lectures* counts; a concept repeated twenty times in
        one lecture is one lecture's word. An entry no segment ever supported is
        capped low however often the model produced it.
        """
        breadth = min(len(self.lectures), 4) / 4
        value = 0.25 + 0.75 * breadth
        if not self.source_supported:
            value = min(value, 0.3)
        if self.disagreements:
            value *= 0.8
        return round(value, 3)

    @property
    def definition(self) -> str:
        """The longest definition a source actually gave. Not a merge of them."""
        supported = [
            m.definition
            for m in self.mentions
            if m.support is Support.source_supported and m.definition
        ]
        pool = supported or [m.definition for m in self.mentions if m.definition]
        return max(pool, key=len) if pool else ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "aliases": self.aliases,
            "definition": self.definition,
            "difficulty": round(self.difficulty, 3),
            "confidence": self.confidence,
            "source_supported": self.source_supported,
            "lectures": sorted(self.lectures),
            "mentions": [m.as_dict() for m in self.mentions],
            "disagreements": [d.as_dict() for d in self.disagreements],
            "decision": self.decision,
            "target_id": self.target_id,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class ReconciledEdge:
    source: str
    target: str
    kind: RelationKind
    lectures: tuple[str, ...]
    source_supported: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "kind": self.kind.value,
            "lectures": list(self.lectures),
            "source_supported": self.source_supported,
        }


@dataclass(slots=True)
class Atlas:
    concepts: list[ReconciledConcept] = field(default_factory=list)
    edges: list[ReconciledEdge] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "concepts": [c.as_dict() for c in self.concepts],
            "edges": [e.as_dict() for e in self.edges],
        }

    @property
    def to_review(self) -> list[ReconciledConcept]:
        return [c for c in self.concepts if c.decision == Decision.REVIEW.value]


#: Given a concept's normalised key, the product's nearest concepts to it, as
#: ``(concept_id, normalized_name, similarity)`` — `knowledge.resolution`'s own
#: shape. Per name, not a fixed list: similarity is a property of the pair, and
#: a list computed once would rank every candidate against the same numbers.
#: The argument is the key, not the display name: the caller's index is built
#: on normalised names, and passing whichever spelling won a vote would make
#: the lookup depend on how the lecturer happened to say it.
Nearest = Callable[[str], Sequence[tuple[str, str, float]]]


def reconcile(
    extractions: Iterable[Extraction],
    *,
    nearest: Nearest | None = None,
) -> Atlas:
    """Fold many segments' extractions into one atlas with a plan per concept.

    ``nearest`` looks the product's own concepts up for one normalised key — an
    embedding
    query in the application, a dictionary in a test. Without it every concept
    is planned as `create`, which is the right answer when there is nothing to
    merge into.
    """
    # Read once: the caller may well pass a generator over a JSONL file, and
    # the edges pass below needs the same extractions the concepts pass saw.
    batch = list(extractions)
    by_key: dict[str, ReconciledConcept] = {}
    difficulties: dict[str, list[float]] = {}

    for extraction in batch:
        for concept in extraction.concepts:
            key = normalize_name(concept.name)
            if not key:
                continue
            entry = by_key.setdefault(key, ReconciledConcept(key=key, name=concept.name))
            mention = Mention(
                source_id=concept.evidence.source_id,
                start_ms=concept.evidence.start_ms,
                end_ms=concept.evidence.end_ms,
                name=concept.name,
                definition=concept.definition,
                support=concept.support,
            )
            _record_disagreement(entry, mention)
            entry.mentions.append(mention)
            if concept.name not in entry.aliases and concept.name != entry.name:
                entry.aliases.append(concept.name)
            difficulties.setdefault(key, []).append(concept.difficulty)

    for key, entry in by_key.items():
        values = difficulties.get(key) or [0.5]
        entry.difficulty = sum(values) / len(values)
        # The name a reader sees is the one the sources used most often, with
        # ties going to the first — not the longest, which is how "the chain
        # rule of differentiation" wins a vote it should lose.
        counts: dict[str, int] = {}
        first_seen: dict[str, int] = {}
        for position, mention in enumerate(entry.mentions):
            counts[mention.name] = counts.get(mention.name, 0) + 1
            first_seen.setdefault(mention.name, position)
        entry.name = max(counts, key=lambda name: (counts[name], -first_seen[name]))
        entry.aliases = sorted({m.name for m in entry.mentions} - {entry.name})
        match = resolve(entry.name, nearest(entry.key) if nearest else ())
        entry.decision = match.decision.value
        entry.target_id = match.target_id
        entry.reason = match.reason

    edges: dict[tuple[str, str, RelationKind], ReconciledEdge] = {}
    for extraction in batch:
        for relation in extraction.relations:
            source = normalize_name(relation.source)
            target = normalize_name(relation.target)
            if source not in by_key or target not in by_key or source == target:
                continue
            edge_key = (source, target, relation.kind)
            known = edges.get(edge_key)
            lectures = tuple(
                sorted({*(known.lectures if known else ()), relation.evidence.source_id})
            )
            edges[edge_key] = ReconciledEdge(
                source=source,
                target=target,
                kind=relation.kind,
                lectures=lectures,
                source_supported=(
                    (known.source_supported if known else False)
                    or relation.support is Support.source_supported
                ),
            )

    atlas = Atlas(
        concepts=sorted(by_key.values(), key=lambda c: (-c.confidence, c.key)),
        edges=sorted(edges.values(), key=lambda e: (e.source, e.target, e.kind.value)),
    )
    return atlas


def _record_disagreement(entry: ReconciledConcept, mention: Mention) -> None:
    """Compare this definition with the ones already seen; keep the differences.

    Only definitions long enough to say something are compared, and only against
    mentions from *other* lectures: one lecture phrasing a concept two ways over
    ten minutes is a lecture, not a disagreement between sources.
    """
    if len(mention.definition) < MIN_DEFINITION:
        return
    for other in entry.mentions:
        if other.source_id == mention.source_id:
            continue
        if len(other.definition) < MIN_DEFINITION:
            continue
        similarity = SequenceMatcher(
            None, other.definition.lower(), mention.definition.lower()
        ).ratio()
        if similarity < SAME_DEFINITION:
            entry.disagreements.append(
                Disagreement(left=other, right=mention, similarity=similarity)
            )
