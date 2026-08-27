"""The knowledge graph's API surface, against a real database.

`noema/knowledge/resolution.py` and `noema/knowledge/graph.py` are already
well-tested as pure/near-pure logic. What's tested here is the route layer that
sits on top: tenancy on every lookup, the rename-clash check, what a merge
actually does to edges (repoint, or delete when it would become a self-loop),
and that cycle detection is actually wired into edge creation.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from noema.api.v1.concepts import (
    ConceptUpdate,
    EdgeIn,
    MergeRequest,
    concept_graph,
    create_edge,
    delete_edge,
    get_concept,
    list_concepts,
    merge_concepts,
    update_concept,
)
from noema.core.errors import Conflict, NotFound
from noema.db.models import (
    Concept,
    ConceptEdge,
    ConceptStatus,
    EdgeKind,
    EdgeOrigin,
    User,
    Workspace,
)
from noema.db.repository import OwnedRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def workspace(db: AsyncSession, user: User) -> Workspace:
    return await OwnedRepository(db, Workspace, user.id).create(
        title="Biology", slug=f"bio-{uuid.uuid4().hex[:8]}"
    )


async def make_concept(
    db: AsyncSession,
    user: User,
    workspace: Workspace,
    name: str,
    *,
    status: ConceptStatus = ConceptStatus.ACTIVE,
    definition: str | None = None,
    aliases: list[str] | None = None,
    source_chunk_ids: list[uuid.UUID] | None = None,
) -> Concept:
    concept = Concept(
        owner_id=user.id,
        workspace_id=workspace.id,
        name=name,
        normalized_name=name.lower(),
        status=status,
        difficulty_prior=0.5,
        definition=definition,
        aliases=aliases or [],
        source_chunk_ids=source_chunk_ids or [],
    )
    db.add(concept)
    await db.flush()
    return concept


async def make_edge(
    db: AsyncSession,
    user: User,
    src: Concept,
    dst: Concept,
    *,
    kind: EdgeKind = EdgeKind.PREREQUISITE_OF,
    origin: EdgeOrigin = EdgeOrigin.EXTRACTED,
) -> ConceptEdge:
    edge = ConceptEdge(
        owner_id=user.id, src_id=src.id, dst_id=dst.id, kind=kind, origin=origin
    )
    db.add(edge)
    await db.flush()
    return edge


# ---------------------------------------------------------------------------
# list_concepts
# ---------------------------------------------------------------------------


async def test_list_concepts_defaults_to_active_only(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    await make_concept(db, user, workspace, "Mitochondria", status=ConceptStatus.ACTIVE)
    await make_concept(db, user, workspace, "Ribosome", status=ConceptStatus.CANDIDATE)
    await make_concept(db, user, workspace, "Golgi", status=ConceptStatus.REJECTED)

    out = await list_concepts(
        user=user, db=db, workspace_id=None, status_filter=None, limit=200
    )

    assert [c.name for c in out] == ["Mitochondria"]


async def test_list_concepts_respects_an_explicit_status_filter(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    await make_concept(db, user, workspace, "Ribosome", status=ConceptStatus.CANDIDATE)

    out = await list_concepts(
        user=user,
        db=db,
        workspace_id=None,
        status_filter=ConceptStatus.CANDIDATE,
        limit=200,
    )

    assert [c.name for c in out] == ["Ribosome"]


async def test_list_concepts_is_scoped_to_a_workspace(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    other_workspace = await OwnedRepository(db, Workspace, user.id).create(
        title="Chemistry", slug=f"chem-{uuid.uuid4().hex[:8]}"
    )
    await make_concept(db, user, workspace, "Mitochondria")
    await make_concept(db, user, other_workspace, "Covalent Bond")

    out = await list_concepts(
        user=user, db=db, workspace_id=workspace.id, status_filter=None, limit=200
    )

    assert [c.name for c in out] == ["Mitochondria"]


async def test_list_concepts_never_shows_another_owners_concepts(
    db: AsyncSession, user: User, other_user: User, workspace: Workspace
) -> None:
    other_workspace = await OwnedRepository(db, Workspace, other_user.id).create(
        title="Bio", slug=f"bio2-{uuid.uuid4().hex[:8]}"
    )
    await make_concept(db, other_user, other_workspace, "Mitochondria")

    out = await list_concepts(
        user=user, db=db, workspace_id=None, status_filter=None, limit=200
    )

    assert out == []


# ---------------------------------------------------------------------------
# get_concept / update_concept
# ---------------------------------------------------------------------------


async def test_get_concept_raises_not_found_for_another_owners_concept(
    db: AsyncSession, user: User, other_user: User, workspace: Workspace
) -> None:
    concept = await make_concept(db, other_user, workspace, "Mitochondria")

    with pytest.raises(NotFound):
        await get_concept(concept.id, user=user, db=db)


async def test_update_concept_renames_and_updates_the_normalized_name(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    concept = await make_concept(db, user, workspace, "Mitocondria")

    out = await update_concept(
        concept.id, ConceptUpdate(name="Mitochondria"), user=user, db=db
    )

    assert out.name == "Mitochondria"
    await db.refresh(concept)
    assert concept.normalized_name == "mitochondria"


async def test_update_concept_rejects_a_rename_that_clashes_in_the_same_workspace(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    await make_concept(db, user, workspace, "Ribosome")
    concept = await make_concept(db, user, workspace, "Mitochondria")

    with pytest.raises(Conflict):
        await update_concept(concept.id, ConceptUpdate(name="Ribosome"), user=user, db=db)


async def test_update_concept_allows_a_name_already_used_in_another_workspace(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    other_workspace = await OwnedRepository(db, Workspace, user.id).create(
        title="Chemistry", slug=f"chem-{uuid.uuid4().hex[:8]}"
    )
    await make_concept(db, user, other_workspace, "Ribosome")
    concept = await make_concept(db, user, workspace, "Mitochondria")

    out = await update_concept(
        concept.id, ConceptUpdate(name="Ribosome"), user=user, db=db
    )

    assert out.name == "Ribosome"


async def test_update_concept_clears_the_definition_on_an_empty_string(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    concept = await make_concept(db, user, workspace, "Mitochondria", definition="x")

    out = await update_concept(concept.id, ConceptUpdate(definition=""), user=user, db=db)

    assert out.definition is None


async def test_update_concept_clears_the_definition_on_an_explicit_null(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    """`definition` has no NOT NULL constraint, so an explicit ``null`` is a
    real request to clear a wrong or outdated AI-extracted definition, not
    something to silently ignore — a graph that quietly undoes a user's
    correction is worse than no graph, per this module's own docstring."""
    concept = await make_concept(db, user, workspace, "Mitochondria", definition="x")

    out = await update_concept(
        concept.id, ConceptUpdate(definition=None), user=user, db=db
    )

    assert out.definition is None


async def test_update_concept_leaves_the_definition_alone_when_omitted(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    concept = await make_concept(db, user, workspace, "Mitochondria", definition="x")

    out = await update_concept(concept.id, ConceptUpdate(name="Mito"), user=user, db=db)

    assert out.definition == "x"


async def test_update_concept_changes_status(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    concept = await make_concept(
        db, user, workspace, "Mitochondria", status=ConceptStatus.CANDIDATE
    )

    out = await update_concept(
        concept.id, ConceptUpdate(status="active"), user=user, db=db
    )

    assert out.status is ConceptStatus.ACTIVE


# ---------------------------------------------------------------------------
# merge_concepts
# ---------------------------------------------------------------------------


async def test_merge_unions_chunk_ids_and_collects_aliases(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    chunk_a, chunk_b = uuid.uuid4(), uuid.uuid4()
    target = await make_concept(
        db, user, workspace, "Mitochondria", source_chunk_ids=[chunk_a]
    )
    source = await make_concept(
        db,
        user,
        workspace,
        "Powerhouse of the Cell",
        aliases=["Mito"],
        source_chunk_ids=[chunk_b],
    )

    out = await merge_concepts(
        MergeRequest(source_ids=[source.id], target_id=target.id), user=user, db=db
    )

    assert set(out.source_chunk_ids) == {chunk_a, chunk_b}
    assert set(out.aliases) == {"Powerhouse of the Cell", "Mito"}


async def test_merge_keeps_the_targets_own_definition(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    target = await make_concept(
        db, user, workspace, "Mitochondria", definition="Target's own."
    )
    source = await make_concept(db, user, workspace, "Powerhouse", definition="Source's.")

    out = await merge_concepts(
        MergeRequest(source_ids=[source.id], target_id=target.id), user=user, db=db
    )

    assert out.definition == "Target's own."


async def test_merge_falls_back_to_the_sources_definition_when_the_target_has_none(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    target = await make_concept(db, user, workspace, "Mitochondria")
    source = await make_concept(db, user, workspace, "Powerhouse", definition="Source's.")

    out = await merge_concepts(
        MergeRequest(source_ids=[source.id], target_id=target.id), user=user, db=db
    )

    assert out.definition == "Source's."


async def test_merge_marks_the_source_merged_and_the_target_active(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    target = await make_concept(
        db, user, workspace, "Mitochondria", status=ConceptStatus.CANDIDATE
    )
    source = await make_concept(db, user, workspace, "Powerhouse")

    await merge_concepts(
        MergeRequest(source_ids=[source.id], target_id=target.id), user=user, db=db
    )

    await db.refresh(source)
    await db.refresh(target)
    assert source.status is ConceptStatus.MERGED
    assert source.merged_into_id == target.id
    assert target.status is ConceptStatus.ACTIVE


async def test_merge_repoints_edges_from_the_source_to_the_target(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    target = await make_concept(db, user, workspace, "Mitochondria")
    source = await make_concept(db, user, workspace, "Powerhouse")
    other = await make_concept(db, user, workspace, "Cell Membrane")
    edge = await make_edge(db, user, other, source, kind=EdgeKind.PREREQUISITE_OF)

    await merge_concepts(
        MergeRequest(source_ids=[source.id], target_id=target.id), user=user, db=db
    )

    await db.refresh(edge)
    assert edge.dst_id == target.id


async def test_merge_deletes_an_edge_that_would_become_a_self_loop(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    target = await make_concept(db, user, workspace, "Mitochondria")
    source = await make_concept(db, user, workspace, "Powerhouse")
    edge = await make_edge(db, user, target, source, kind=EdgeKind.PART_OF)

    await merge_concepts(
        MergeRequest(source_ids=[source.id], target_id=target.id), user=user, db=db
    )

    assert await db.get(ConceptEdge, edge.id) is None


async def test_merge_rejects_concepts_from_different_workspaces(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    other_workspace = await OwnedRepository(db, Workspace, user.id).create(
        title="Chemistry", slug=f"chem-{uuid.uuid4().hex[:8]}"
    )
    target = await make_concept(db, user, workspace, "Mitochondria")
    source = await make_concept(db, user, other_workspace, "Covalent Bond")

    with pytest.raises(Conflict):
        await merge_concepts(
            MergeRequest(source_ids=[source.id], target_id=target.id), user=user, db=db
        )


async def test_merge_deletes_a_redundant_edge_instead_of_colliding_with_the_targets_own(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    """`(src_id, dst_id, kind)` is uniquely constrained. If target already has
    its own edge to `other`, blindly reassigning source's edge to target would
    hit that constraint — this must delete the redundant one instead."""
    target = await make_concept(db, user, workspace, "Mitochondria")
    source = await make_concept(db, user, workspace, "Powerhouse")
    other = await make_concept(db, user, workspace, "Cell Membrane")
    targets_own_edge = await make_edge(
        db, user, other, target, kind=EdgeKind.PREREQUISITE_OF
    )
    sources_edge = await make_edge(db, user, other, source, kind=EdgeKind.PREREQUISITE_OF)

    await merge_concepts(
        MergeRequest(source_ids=[source.id], target_id=target.id), user=user, db=db
    )

    assert await db.get(ConceptEdge, targets_own_edge.id) is not None
    assert await db.get(ConceptEdge, sources_edge.id) is None


async def test_merging_a_concept_into_itself_is_a_no_op_for_that_entry(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    target = await make_concept(db, user, workspace, "Mitochondria")

    out = await merge_concepts(
        MergeRequest(source_ids=[target.id], target_id=target.id), user=user, db=db
    )

    assert out.id == target.id
    assert out.status is ConceptStatus.ACTIVE


# ---------------------------------------------------------------------------
# concept_graph
# ---------------------------------------------------------------------------


async def test_concept_graph_finds_direct_neighbours(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    root = await make_concept(db, user, workspace, "Mitochondria")
    neighbour = await make_concept(db, user, workspace, "Cell Membrane")
    await make_edge(db, user, neighbour, root)

    graph = await concept_graph(root.id, user=user, db=db, depth=1)

    assert {n.id for n in graph.nodes} == {root.id, neighbour.id}
    assert len(graph.edges) == 1


async def test_concept_graph_respects_the_depth_limit(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    a = await make_concept(db, user, workspace, "A")
    b = await make_concept(db, user, workspace, "B")
    c = await make_concept(db, user, workspace, "C")
    await make_edge(db, user, a, b)
    await make_edge(db, user, b, c)

    graph = await concept_graph(a.id, user=user, db=db, depth=1)

    assert {n.id for n in graph.nodes} == {a.id, b.id}


async def test_concept_graph_raises_not_found_for_another_owners_concept(
    db: AsyncSession, user: User, other_user: User, workspace: Workspace
) -> None:
    concept = await make_concept(db, other_user, workspace, "Mitochondria")

    with pytest.raises(NotFound):
        await concept_graph(concept.id, user=user, db=db, depth=1)


# ---------------------------------------------------------------------------
# create_edge / delete_edge
# ---------------------------------------------------------------------------


async def test_create_edge_rejects_a_self_loop(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    concept = await make_concept(db, user, workspace, "Mitochondria")

    with pytest.raises(Conflict):
        await create_edge(
            EdgeIn(src_id=concept.id, dst_id=concept.id, kind=EdgeKind.RELATED_TO),
            user=user,
            db=db,
        )


async def test_create_edge_rejects_a_duplicate_edge(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    """`(src_id, dst_id, kind)` is uniquely constrained at the DB level; a
    repeat request must get a clean 409, not an unhandled IntegrityError."""
    a = await make_concept(db, user, workspace, "Mitochondria")
    b = await make_concept(db, user, workspace, "Cell Membrane")
    await make_edge(db, user, a, b, kind=EdgeKind.RELATED_TO)

    with pytest.raises(Conflict):
        await create_edge(
            EdgeIn(src_id=a.id, dst_id=b.id, kind=EdgeKind.RELATED_TO), user=user, db=db
        )


async def test_create_edge_allows_the_same_pair_with_a_different_kind(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    a = await make_concept(db, user, workspace, "Mitochondria")
    b = await make_concept(db, user, workspace, "Cell Membrane")
    await make_edge(db, user, a, b, kind=EdgeKind.RELATED_TO)

    edge = await create_edge(
        EdgeIn(src_id=a.id, dst_id=b.id, kind=EdgeKind.PART_OF), user=user, db=db
    )

    assert edge.kind is EdgeKind.PART_OF


async def test_create_edge_rejects_concepts_from_different_workspaces(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    other_workspace = await OwnedRepository(db, Workspace, user.id).create(
        title="Chemistry", slug=f"chem-{uuid.uuid4().hex[:8]}"
    )
    a = await make_concept(db, user, workspace, "Mitochondria")
    b = await make_concept(db, user, other_workspace, "Covalent Bond")

    with pytest.raises(Conflict):
        await create_edge(
            EdgeIn(src_id=a.id, dst_id=b.id, kind=EdgeKind.RELATED_TO), user=user, db=db
        )


async def test_create_edge_defaults_to_user_origin(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    a = await make_concept(db, user, workspace, "Mitochondria")
    b = await make_concept(db, user, workspace, "Cell Membrane")

    out = await create_edge(
        EdgeIn(src_id=a.id, dst_id=b.id, kind=EdgeKind.PART_OF), user=user, db=db
    )

    assert out.origin is EdgeOrigin.USER


async def test_create_edge_rejects_a_direct_prerequisite_cycle(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    a = await make_concept(db, user, workspace, "A")
    b = await make_concept(db, user, workspace, "B")
    await create_edge(
        EdgeIn(src_id=a.id, dst_id=b.id, kind=EdgeKind.PREREQUISITE_OF), user=user, db=db
    )

    with pytest.raises(Conflict):
        await create_edge(
            EdgeIn(src_id=b.id, dst_id=a.id, kind=EdgeKind.PREREQUISITE_OF),
            user=user,
            db=db,
        )


async def test_create_edge_rejects_a_transitive_prerequisite_cycle(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    a = await make_concept(db, user, workspace, "A")
    b = await make_concept(db, user, workspace, "B")
    c = await make_concept(db, user, workspace, "C")
    await create_edge(
        EdgeIn(src_id=a.id, dst_id=b.id, kind=EdgeKind.PREREQUISITE_OF), user=user, db=db
    )
    await create_edge(
        EdgeIn(src_id=b.id, dst_id=c.id, kind=EdgeKind.PREREQUISITE_OF), user=user, db=db
    )

    with pytest.raises(Conflict):
        await create_edge(
            EdgeIn(src_id=c.id, dst_id=a.id, kind=EdgeKind.PREREQUISITE_OF),
            user=user,
            db=db,
        )


async def test_create_edge_does_not_cycle_check_non_prerequisite_kinds(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    a = await make_concept(db, user, workspace, "A")
    b = await make_concept(db, user, workspace, "B")
    await create_edge(
        EdgeIn(src_id=a.id, dst_id=b.id, kind=EdgeKind.RELATED_TO), user=user, db=db
    )

    out = await create_edge(
        EdgeIn(src_id=b.id, dst_id=a.id, kind=EdgeKind.RELATED_TO), user=user, db=db
    )

    assert out.src_id == b.id


async def test_delete_edge_raises_not_found_for_a_missing_edge(
    db: AsyncSession, user: User
) -> None:
    with pytest.raises(NotFound):
        await delete_edge(uuid.uuid4(), user=user, db=db)


async def test_delete_edge_raises_not_found_for_another_owners_edge(
    db: AsyncSession, user: User, other_user: User, workspace: Workspace
) -> None:
    a = await make_concept(db, other_user, workspace, "A")
    b = await make_concept(db, other_user, workspace, "B")
    edge = await make_edge(db, other_user, a, b)

    with pytest.raises(NotFound):
        await delete_edge(edge.id, user=user, db=db)


async def test_delete_edge_removes_it(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    a = await make_concept(db, user, workspace, "A")
    b = await make_concept(db, user, workspace, "B")
    edge = await make_edge(db, user, a, b)

    await delete_edge(edge.id, user=user, db=db)

    assert await db.get(ConceptEdge, edge.id) is None
