"""Study goals — the deadline, the plan, and whether it's honest about the date.

`plan_path` itself is already unit-tested in `test_path.py` as a pure function.
What's untested here is the orchestration around it: which concepts a goal
actually considers (only ones with a question to practise them), what an absent
mastery row means (unlearned, not zero-and-forgotten), and that `achieved()`
only fires once nothing is left to do.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.errors import NotFound
from noema.db.base import utcnow
from noema.db.models import (
    Concept,
    ConceptEdge,
    ConceptMastery,
    ConceptStatus,
    EdgeKind,
    Goal,
    Notebook,
    Question,
    QuestionType,
    Subject,
    User,
    Workspace,
)
from noema.db.repository import OwnedRepository
from noema.study.goals import achieved, path_for

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def notebook(db: AsyncSession, user: User) -> Notebook:
    workspace = await OwnedRepository(db, Workspace, user.id).create(
        title="Bio", slug=f"bio-{uuid.uuid4().hex[:8]}"
    )
    subject = await OwnedRepository(db, Subject, user.id).create(
        workspace_id=workspace.id, title="Cells", slug=f"cells-{uuid.uuid4().hex[:8]}"
    )
    return await OwnedRepository(db, Notebook, user.id).create(
        subject_id=subject.id,
        title="Organelles",
        slug=f"org-{uuid.uuid4().hex[:8]}",
        retrieval_settings={},
    )


async def make_concept(
    db: AsyncSession, user: User, notebook: Notebook, name: str
) -> Concept:
    subject = await db.get(Subject, notebook.subject_id)
    assert subject is not None
    concept = Concept(
        owner_id=user.id,
        workspace_id=subject.workspace_id,
        name=name,
        normalized_name=name.lower(),
        status=ConceptStatus.ACTIVE,
        difficulty_prior=0.5,
        aliases=[],
        source_chunk_ids=[],
    )
    db.add(concept)
    await db.flush()
    return concept


async def make_question(
    db: AsyncSession, user: User, notebook: Notebook, concept: Concept
) -> Question:
    question = Question(
        owner_id=user.id,
        notebook_id=notebook.id,
        concept_id=concept.id,
        type=QuestionType.OPEN,
        prompt=f"Explain {concept.name}.",
        payload={},
    )
    db.add(question)
    await db.flush()
    return question


async def set_mastery(
    db: AsyncSession, user: User, concept: Concept, value: float
) -> None:
    db.add(ConceptMastery(owner_id=user.id, concept_id=concept.id, mastery=value))
    await db.flush()


async def make_goal(
    db: AsyncSession, user: User, notebook: Notebook, **overrides: object
) -> Goal:
    defaults: dict[str, object] = {
        "owner_id": user.id,
        "notebook_id": notebook.id,
        "title": "Midterm",
        "due_on": (utcnow() + timedelta(days=30)).date(),
        "target_mastery": 80.0,
        "minutes_per_day": 60,
    }
    defaults.update(overrides)
    goal = Goal(**defaults)
    db.add(goal)
    await db.flush()
    return goal


async def test_path_for_raises_not_found_for_a_missing_goal(
    db: AsyncSession, user: User
) -> None:
    with pytest.raises(NotFound):
        await path_for(db, uuid.uuid4(), owner_id=user.id)


async def test_path_for_raises_not_found_for_another_owners_goal(
    db: AsyncSession, user: User, other_user: User, notebook: Notebook
) -> None:
    goal = await make_goal(db, user, notebook)

    with pytest.raises(NotFound):
        await path_for(db, goal.id, owner_id=other_user.id)


async def test_a_notebook_with_no_questions_has_an_empty_reachable_path(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    goal = await make_goal(db, user, notebook)

    _, path = await path_for(db, goal.id, owner_id=user.id)

    assert path.milestones == []
    assert path.feasibility.reachable is True


async def test_a_concept_with_no_question_is_excluded_from_the_plan(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    tested = await make_concept(db, user, notebook, "Mitochondria")
    untested = await make_concept(db, user, notebook, "Golgi Apparatus")
    await make_question(db, user, notebook, tested)
    await set_mastery(db, user, tested, 10.0)
    await set_mastery(db, user, untested, 10.0)

    goal = await make_goal(db, user, notebook, target_mastery=80.0)
    _, path = await path_for(db, goal.id, owner_id=user.id)

    assert {m.concept_id for m in path.milestones} == {tested.id}


async def test_a_concept_already_at_target_needs_no_milestone(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    concept = await make_concept(db, user, notebook, "Mitochondria")
    await make_question(db, user, notebook, concept)
    await set_mastery(db, user, concept, 95.0)

    goal = await make_goal(db, user, notebook, target_mastery=80.0)
    _, path = await path_for(db, goal.id, owner_id=user.id)

    assert path.milestones == []
    assert path.feasibility.reachable is True


async def test_a_concept_with_no_mastery_row_is_treated_as_unlearned(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    """`_targets`: no evidence is not the same as zero ability, but it plans as
    unlearned — otherwise an untouched concept would let a goal call itself met."""
    concept = await make_concept(db, user, notebook, "Mitochondria")
    await make_question(db, user, notebook, concept)

    goal = await make_goal(db, user, notebook, target_mastery=80.0)
    _, path = await path_for(db, goal.id, owner_id=user.id)

    assert len(path.milestones) == 1
    assert path.milestones[0].from_mastery == 0.0


async def test_a_prerequisite_outside_the_goal_does_not_block_it(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    """A prerequisite with no question of its own is outside the goal entirely —
    "someone else's problem today", per the module's own docstring."""
    outside = await make_concept(db, user, notebook, "Cell Membrane")
    inside = await make_concept(db, user, notebook, "Mitochondria")
    await make_question(db, user, notebook, inside)
    db.add(
        ConceptEdge(
            owner_id=user.id,
            src_id=outside.id,
            dst_id=inside.id,
            kind=EdgeKind.PREREQUISITE_OF,
        )
    )
    await set_mastery(db, user, inside, 10.0)
    await db.flush()

    goal = await make_goal(db, user, notebook, target_mastery=80.0)
    _, path = await path_for(db, goal.id, owner_id=user.id)

    assert len(path.milestones) == 1


async def test_achieved_is_sticky_once_set(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    goal = await make_goal(db, user, notebook)
    stamp = utcnow()
    goal.achieved_at = stamp

    _, path = await path_for(db, goal.id, owner_id=user.id)

    assert achieved(goal, path) == stamp


async def test_achieved_is_none_while_milestones_remain(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    concept = await make_concept(db, user, notebook, "Mitochondria")
    await make_question(db, user, notebook, concept)
    await set_mastery(db, user, concept, 10.0)

    goal = await make_goal(db, user, notebook, target_mastery=80.0)
    _, path = await path_for(db, goal.id, owner_id=user.id)

    assert achieved(goal, path) is None


async def test_achieved_fires_the_moment_nothing_remains(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    concept = await make_concept(db, user, notebook, "Mitochondria")
    await make_question(db, user, notebook, concept)
    await set_mastery(db, user, concept, 95.0)

    goal = await make_goal(db, user, notebook, target_mastery=80.0)
    _, path = await path_for(db, goal.id, owner_id=user.id)

    assert achieved(goal, path) is not None
