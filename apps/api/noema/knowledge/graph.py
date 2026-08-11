"""Persisting extracted concepts into the workspace graph.

Everything a user has decided is permanent. Re-ingesting a source may add concepts
and edges; it never renames, un-merges or contradicts a choice the person made. A
graph that quietly undoes your corrections is one you stop correcting.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import asdict, dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.logging import get_logger
from noema.db.models import Concept, ConceptEdge, ConceptStatus, EdgeKind, EdgeOrigin
from noema.knowledge.extraction import ExtractedConcept
from noema.knowledge.resolution import (
    Decision,
    normalize_name,
    resolve,
    would_create_cycle,
)
from noema.providers.base import EmbedRequest, ProviderError
from noema.providers.gateway import AIGateway

log = get_logger(__name__)

__all__ = ["GraphUpdate", "apply_extraction"]

#: How many existing concepts to compare a candidate against. Resolution only needs
#: the nearest few; scanning the whole workspace buys nothing.
NEIGHBOURS = 5

#: A concept seen in this many distinct chunks is corroborated, and stops being a
#: candidate. One mention is an extraction artefact as often as it is a concept.
CORROBORATION_THRESHOLD = 2


@dataclass(frozen=True, slots=True)
class GraphUpdate:
    created: int = 0
    merged: int = 0
    needs_review: int = 0
    promoted: int = 0
    edges_added: int = 0
    cycles_rejected: int = 0


async def apply_extraction(
    session: AsyncSession,
    concepts: Sequence[ExtractedConcept],
    *,
    owner_id: uuid.UUID,
    workspace_id: uuid.UUID,
    gateway: AIGateway | None,
    embedding_model: str | None = None,
) -> GraphUpdate:
    """Resolve extracted concepts against the workspace and store what survives."""
    if not concepts:
        return GraphUpdate()

    embeddings = await _embed_names(gateway, [c.name for c in concepts], embedding_model)
    by_name: dict[str, Concept] = {}
    created = merged = needs_review = promoted = 0

    for index, extracted in enumerate(concepts):
        embedding = embeddings[index] if embeddings else None
        existing = await _neighbours(session, workspace_id, extracted.name, embedding)
        match = resolve(extracted.name, existing)

        if match.decision is Decision.MERGE and match.target_id:
            concept = await session.get(Concept, uuid.UUID(match.target_id))
            if concept is not None:
                _absorb(concept, extracted)
                merged += 1
            else:
                concept = await _create(
                    session, extracted, owner_id, workspace_id, embedding
                )
                created += 1
        else:
            concept = await _create(session, extracted, owner_id, workspace_id, embedding)
            created += 1
            if match.decision is Decision.REVIEW:
                # Left as a candidate with the suspected twin recorded, for a human
                # to confirm. Auto-merging a maybe is how distinct ideas silently
                # collapse into one.
                concept.aliases = [*concept.aliases, f"?similar:{match.target_id}"]
                needs_review += 1

        if _corroborated(concept) and concept.status is ConceptStatus.CANDIDATE:
            concept.status = ConceptStatus.ACTIVE
            promoted += 1

        by_name[normalize_name(extracted.name)] = concept

    await session.flush()

    edges_added, cycles_rejected = await _link(
        session, concepts, by_name, owner_id, workspace_id
    )

    update = GraphUpdate(
        created=created,
        merged=merged,
        needs_review=needs_review,
        promoted=promoted,
        edges_added=edges_added,
        cycles_rejected=cycles_rejected,
    )
    log.info("graph.updated", **asdict(update))
    return update


async def _create(
    session: AsyncSession,
    extracted: ExtractedConcept,
    owner_id: uuid.UUID,
    workspace_id: uuid.UUID,
    embedding: list[float] | None,
) -> Concept:
    concept = Concept(
        owner_id=owner_id,
        workspace_id=workspace_id,
        name=extracted.name,
        normalized_name=normalize_name(extracted.name),
        definition=extracted.definition or None,
        difficulty_prior=extracted.difficulty,
        status=ConceptStatus.CANDIDATE,
        source_chunk_ids=[uuid.UUID(cid) for cid in extracted.source_chunk_ids],
        embedding=embedding,
        aliases=[],
    )
    session.add(concept)
    await session.flush()
    return concept


def _absorb(concept: Concept, extracted: ExtractedConcept) -> None:
    """Fold a new sighting into an existing concept.

    The definition only fills a gap — an existing one may have been written by the
    user, and overwriting it would be exactly the silent undo we refuse elsewhere.
    """
    incoming = {uuid.UUID(cid) for cid in extracted.source_chunk_ids}
    concept.source_chunk_ids = sorted(set(concept.source_chunk_ids) | incoming)

    if not concept.definition and extracted.definition:
        concept.definition = extracted.definition

    if normalize_name(extracted.name) != concept.normalized_name:
        alias = extracted.name.strip()
        if alias and alias not in concept.aliases:
            concept.aliases = [*concept.aliases, alias]


def _corroborated(concept: Concept) -> bool:
    return len(concept.source_chunk_ids) >= CORROBORATION_THRESHOLD


async def _neighbours(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    name: str,
    embedding: list[float] | None,
) -> list[tuple[str, str, float]]:
    """The concepts a candidate might be a duplicate of."""
    normalized = normalize_name(name)

    exact = await session.scalar(
        select(Concept).where(
            Concept.workspace_id == workspace_id,
            Concept.normalized_name == normalized,
            Concept.status != ConceptStatus.MERGED,
        )
    )
    if exact is not None:
        return [(str(exact.id), exact.normalized_name, 1.0)]

    if embedding is None:
        return []

    distance = Concept.embedding.cosine_distance(embedding)
    rows = (
        await session.execute(
            select(Concept.id, Concept.normalized_name, distance)
            .where(
                Concept.workspace_id == workspace_id,
                Concept.embedding.is_not(None),
                Concept.status != ConceptStatus.MERGED,
            )
            .order_by(distance)
            .limit(NEIGHBOURS)
        )
    ).all()

    return [(str(cid), name, 1.0 - float(dist)) for cid, name, dist in rows]


async def _link(
    session: AsyncSession,
    concepts: Sequence[ExtractedConcept],
    by_name: dict[str, Concept],
    owner_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> tuple[int, int]:
    """Insert edges, rejecting any prerequisite that would close a loop."""
    existing_edges = [
        (str(src), str(dst))
        for src, dst in (
            await session.execute(
                select(ConceptEdge.src_id, ConceptEdge.dst_id)
                .join(Concept, Concept.id == ConceptEdge.src_id)
                .where(
                    Concept.workspace_id == workspace_id,
                    ConceptEdge.kind == EdgeKind.PREREQUISITE_OF,
                )
            )
        ).all()
    ]

    seen = {
        (str(src), str(dst), kind)
        for src, dst, kind in (
            await session.execute(
                select(ConceptEdge.src_id, ConceptEdge.dst_id, ConceptEdge.kind)
                .join(Concept, Concept.id == ConceptEdge.src_id)
                .where(Concept.workspace_id == workspace_id)
            )
        ).all()
    }

    added = rejected = 0

    for extracted in concepts:
        target = by_name.get(normalize_name(extracted.name))
        if target is None:
            continue

        for prerequisite_name in extracted.prerequisites:
            source = by_name.get(normalize_name(prerequisite_name))
            if source is None:
                continue

            src, dst = str(source.id), str(target.id)
            if would_create_cycle(existing_edges, src, dst):
                # An extraction error, not a modelling nuance: left in place it makes
                # the prerequisite engine recurse forever looking for where to start.
                log.warning(
                    "graph.cycle_rejected",
                    prerequisite=source.name,
                    concept=target.name,
                )
                rejected += 1
                continue

            if _add_edge(
                session, seen, owner_id, source, target, EdgeKind.PREREQUISITE_OF
            ):
                existing_edges.append((src, dst))
                added += 1

        for relation in extracted.relations:
            other = by_name.get(normalize_name(relation.target))
            if other is not None and _add_edge(
                session, seen, owner_id, target, other, relation.kind
            ):
                added += 1

    await session.flush()
    return added, rejected


def _add_edge(
    session: AsyncSession,
    seen: set[tuple[str, str, EdgeKind]],
    owner_id: uuid.UUID,
    source: Concept,
    target: Concept,
    kind: EdgeKind,
) -> bool:
    key = (str(source.id), str(target.id), kind)
    if source.id == target.id or key in seen:
        return False

    session.add(
        ConceptEdge(
            owner_id=owner_id,
            src_id=source.id,
            dst_id=target.id,
            kind=kind,
            weight=0.6,
            origin=EdgeOrigin.EXTRACTED,
        )
    )
    seen.add(key)
    return True


async def _embed_names(
    gateway: AIGateway | None, names: Sequence[str], model: str | None
) -> list[list[float]] | None:
    """Embed candidate names so near-duplicates are found by meaning.

    Without embeddings, resolution falls back to exact normalised names — which
    still catches the common case and never merges two things wrongly.
    """
    if gateway is None or not names:
        return None
    try:
        response = await gateway.embed(EmbedRequest(texts=list(names), model=model))
    except ProviderError as exc:
        log.warning("graph.name_embedding_failed", error=str(exc))
        return None
    return [list(vector) for vector in response.vectors]
