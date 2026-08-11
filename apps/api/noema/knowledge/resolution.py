"""Deciding when two extracted concepts are the same thing.

This is the part that decides whether the knowledge graph is useful or noise. A
model asked the same question twice returns "Backpropagation", "back-propagation"
and "the backprop algorithm"; treated as three concepts, mastery fragments across
them and the graph becomes unreadable.

Deterministic and pure, on purpose: merging is destructive and a user who cannot
predict it will not trust it.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

__all__ = [
    "Decision",
    "Match",
    "normalize_name",
    "resolve",
    "would_create_cycle",
]

#: Above this, two names mean the same thing and merge without asking.
AUTO_MERGE: Final = 0.92

#: Between this and AUTO_MERGE, a human decides. Below it, they are different.
REVIEW: Final = 0.80

PLURAL_EXCEPTIONS: Final = frozenset({"series", "axis", "basis", "analysis", "lens"})
LEADING_ARTICLE = re.compile(r"^(the|a|an)\s+", re.IGNORECASE)
PUNCTUATION = re.compile(r"[^\w\s]")
WHITESPACE = re.compile(r"\s+")


class Decision(StrEnum):
    MERGE = "merge"
    REVIEW = "review"
    CREATE = "create"


@dataclass(frozen=True, slots=True)
class Match:
    decision: Decision
    target_id: str | None = None
    similarity: float = 0.0
    reason: str = ""


def normalize_name(name: str) -> str:
    """Fold the differences that are never meaningful.

    Case, accents, punctuation, leading articles and trailing plurals. Everything
    else is left alone: "gradient descent" and "stochastic gradient descent" are
    genuinely different concepts and normalisation must not conflate them.
    """
    text = unicodedata.normalize("NFKD", name)
    text = "".join(
        character for character in text if not unicodedata.combining(character)
    )
    text = text.lower().strip()
    text = LEADING_ARTICLE.sub("", text)
    text = PUNCTUATION.sub(" ", text)
    text = WHITESPACE.sub(" ", text).strip()

    words = text.split()
    if words and words[-1] not in PLURAL_EXCEPTIONS:
        last = words[-1]
        if last.endswith("ies") and len(last) > 4:
            words[-1] = last[:-3] + "y"
        elif last.endswith("es") and len(last) > 4 and last[-3] in "sxzo":
            words[-1] = last[:-2]
        elif last.endswith("s") and not last.endswith("ss") and len(last) > 3:
            words[-1] = last[:-1]

    return " ".join(words)


def resolve(
    candidate_name: str,
    existing: Sequence[tuple[str, str, float]],
) -> Match:
    """Decide what to do with an extracted concept.

    ``existing`` is ``(concept_id, normalized_name, cosine_similarity)`` for the
    nearest concepts already in the workspace.

    An exact normalised-name match is decisive on its own — no embedding is going to
    tell us that "Chain Rule" and "chain rule" are different.
    """
    normalized = normalize_name(candidate_name)
    if not normalized:
        return Match(Decision.CREATE, reason="empty name")

    for concept_id, name, similarity in existing:
        if name == normalized:
            return Match(
                Decision.MERGE,
                target_id=concept_id,
                similarity=max(similarity, 1.0),
                reason="identical after normalisation",
            )

    ranked = sorted(existing, key=lambda item: item[2], reverse=True)
    if not ranked:
        return Match(Decision.CREATE, reason="nothing to compare against")

    concept_id, name, similarity = ranked[0]

    if similarity >= AUTO_MERGE:
        return Match(
            Decision.MERGE,
            target_id=concept_id,
            similarity=similarity,
            reason=f"near-identical to {name!r}",
        )
    if similarity >= REVIEW:
        return Match(
            Decision.REVIEW,
            target_id=concept_id,
            similarity=similarity,
            reason=f"possibly the same as {name!r}",
        )
    return Match(Decision.CREATE, similarity=similarity, reason="distinct enough")


def would_create_cycle(edges: Sequence[tuple[str, str]], src: str, dst: str) -> bool:
    """Whether adding ``src -> dst`` would close a loop.

    Prerequisites have to be a DAG. "A is a prerequisite of B, and B of A" is not a
    subtle modelling nuance — it is an extraction error, and left in place it would
    make the prerequisite engine recurse forever looking for where to start.
    """
    if src == dst:
        return True

    outgoing: dict[str, list[str]] = {}
    for source, target in edges:
        outgoing.setdefault(source, []).append(target)

    # Reachable from dst; if src is among them, the new edge closes the loop.
    seen: set[str] = set()
    stack = [dst]
    while stack:
        node = stack.pop()
        if node == src:
            return True
        if node in seen:
            continue
        seen.add(node)
        stack.extend(outgoing.get(node, []))

    return False
