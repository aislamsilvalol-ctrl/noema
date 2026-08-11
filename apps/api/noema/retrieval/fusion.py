"""Reciprocal Rank Fusion.

Dense and sparse search return scores on incompatible scales — cosine similarity and
``ts_rank_cd`` cannot be averaged into anything meaningful. RRF ignores the scores
entirely and fuses on *rank*, which is what makes it robust to two retrievers that
disagree about what a good score looks like.

Pure functions: no database, no models.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

__all__ = ["RRF_K", "Ranked", "fuse"]

#: The standard damping constant. Larger values flatten the contribution of top
#: ranks; 60 is the value the original paper settled on and it behaves well here.
RRF_K: Final = 60


@dataclass(frozen=True, slots=True)
class Ranked:
    """One result with its fused score and where it came from."""

    chunk_id: uuid.UUID
    score: float
    dense_rank: int | None = None
    sparse_rank: int | None = None

    @property
    def found_by_both(self) -> bool:
        """Agreement between two independent retrievers is a strong signal."""
        return self.dense_rank is not None and self.sparse_rank is not None


def fuse(
    dense: Sequence[uuid.UUID],
    sparse: Sequence[uuid.UUID],
    *,
    k: int = RRF_K,
    limit: int | None = None,
) -> list[Ranked]:
    """Fuse two ranked id lists.

    Each list contributes ``1 / (k + rank)`` per document, so a result ranked well
    by both retrievers outranks one that only a single retriever loved.
    """
    if k <= 0:
        raise ValueError("k must be positive")

    scores: dict[uuid.UUID, float] = {}
    dense_ranks: dict[uuid.UUID, int] = {}
    sparse_ranks: dict[uuid.UUID, int] = {}

    for rank, chunk_id in enumerate(dense, start=1):
        dense_ranks.setdefault(chunk_id, rank)
        scores[chunk_id] = scores.get(chunk_id, 0.0) + 1 / (k + rank)

    for rank, chunk_id in enumerate(sparse, start=1):
        sparse_ranks.setdefault(chunk_id, rank)
        scores[chunk_id] = scores.get(chunk_id, 0.0) + 1 / (k + rank)

    ranked = [
        Ranked(
            chunk_id=chunk_id,
            score=score,
            dense_rank=dense_ranks.get(chunk_id),
            sparse_rank=sparse_ranks.get(chunk_id),
        )
        for chunk_id, score in scores.items()
    ]

    # Ties broken by the better of the two ranks, so the ordering is deterministic
    # rather than dictionary-insertion order.
    ranked.sort(
        key=lambda r: (
            -r.score,
            min(r.dense_rank or 10**6, r.sparse_rank or 10**6),
            str(r.chunk_id),
        )
    )
    return ranked[:limit] if limit else ranked


def max_possible_score(k: int = RRF_K) -> float:
    """The score of a document ranked first by both retrievers.

    Used to normalise the fused score into the 0 to 1 range the answer threshold is
    expressed in, so the threshold means the same thing regardless of ``k``.
    """
    return 2 / (k + 1)
