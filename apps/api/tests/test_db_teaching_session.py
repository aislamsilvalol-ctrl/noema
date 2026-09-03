"""The lesson, remembered.

What matters here is the part the Professor never had: that a session found
tomorrow is the one started today, that turns come back in order, that the
state a reply's metadata changes is *replaced* (SQLAlchemy does not see a list
edited in place), and that another user's session id is nobody's business.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.errors import NotFound
from noema.db.models import TeachingSession, TurnRole, User
from noema.services.teaching_session import TeachingSessions, render_session

pytestmark = pytest.mark.asyncio


async def test_a_first_message_starts_a_session_in_the_learners_words(
    db: AsyncSession, user: User
) -> None:
    sessions = TeachingSessions(db, user.id)

    resumed = await sessions.start_or_resume(
        session_id=None,
        notebook_id=None,
        learning_goal="  Me ensine Psicologia segundo Freud. ",
    )

    assert resumed.created is True
    assert resumed.session.learning_goal == "Me ensine Psicologia segundo Freud."
    assert resumed.session.session_goal == ""  # the professor's, written later
    assert resumed.session.turn_count == 0


async def test_the_same_id_tomorrow_is_the_same_session(
    db: AsyncSession, user: User
) -> None:
    sessions = TeachingSessions(db, user.id)
    first = await sessions.start_or_resume(
        session_id=None, notebook_id=None, learning_goal="Freud"
    )
    await sessions.record_learner(first.session, "Freud")
    await sessions.record_noema(first.session, "Vamos por partes.", intent="explain")

    again = await sessions.start_or_resume(
        session_id=first.session.id, notebook_id=None, learning_goal="ignored"
    )

    assert again.created is False
    assert again.session.id == first.session.id
    assert again.session.turn_count == 2
    assert again.session.learning_goal == "Freud"


async def test_turns_come_back_oldest_first(db: AsyncSession, user: User) -> None:
    sessions = TeachingSessions(db, user.id)
    session = (
        await sessions.start_or_resume(
            session_id=None, notebook_id=None, learning_goal="x"
        )
    ).session

    await sessions.record_learner(session, "one")
    await sessions.record_noema(session, "two", intent="explain")
    await sessions.record_learner(session, "three")

    history = await sessions.history(session)
    assert [t.content for t in history] == ["one", "two", "three"]
    assert [t.role for t in history] == [
        TurnRole.LEARNER,
        TurnRole.NOEMA,
        TurnRole.LEARNER,
    ]
    assert session.last_turn_at is not None


async def test_an_ended_session_cannot_be_resumed(db: AsyncSession, user: User) -> None:
    sessions = TeachingSessions(db, user.id)
    session = (
        await sessions.start_or_resume(
            session_id=None, notebook_id=None, learning_goal="x"
        )
    ).session
    await sessions.end(session)

    with pytest.raises(NotFound):
        await sessions.start_or_resume(
            session_id=session.id, notebook_id=None, learning_goal="x"
        )


async def test_another_users_session_is_not_found(
    db: AsyncSession, user: User, other_user: User
) -> None:
    mine = TeachingSessions(db, user.id)
    session = (
        await mine.start_or_resume(session_id=None, notebook_id=None, learning_goal="x")
    ).session

    theirs = TeachingSessions(db, other_user.id)
    with pytest.raises(NotFound):
        await theirs.start_or_resume(
            session_id=session.id, notebook_id=None, learning_goal="x"
        )


async def test_latest_open_is_where_the_learner_left_off(
    db: AsyncSession, user: User
) -> None:
    sessions = TeachingSessions(db, user.id)
    older = (
        await sessions.start_or_resume(
            session_id=None, notebook_id=None, learning_goal="a"
        )
    ).session
    await sessions.record_learner(older, "a")
    newer = (
        await sessions.start_or_resume(
            session_id=None, notebook_id=None, learning_goal="b"
        )
    ).session
    await sessions.record_learner(newer, "b")
    ended = (
        await sessions.start_or_resume(
            session_id=None, notebook_id=None, learning_goal="c"
        )
    ).session
    await sessions.record_learner(ended, "c")
    await sessions.end(ended)

    latest = await sessions.latest_open(notebook_id=None)
    assert latest is not None
    assert latest.id == newer.id


# ── What a reply's metadata does to the session ──────────────────────────────


def make_session() -> TeachingSession:
    # Detached, never flushed: column defaults have not applied, so the state
    # a fresh row would have is set here explicitly.
    return TeachingSession(
        owner_id=uuid.uuid4(),
        learning_goal="Freud",
        subject="",
        current_topic="",
        current_concept="",
        session_goal="",
        learner_level="foundational",
        depth="foundational",
        strategy="conceptual_explanation",
        turn_count=0,
    )


def test_pedagogy_moves_the_lesson_forward() -> None:
    session = make_session()
    # Column defaults only materialise at flush; a detached instance starts None.
    session.plan, session.understanding, session.misconceptions = [], [], []

    TeachingSessions.apply_pedagogy(
        session,
        {
            "subject": "Psicologia",
            "current_topic": "Freud",
            "current_concept": "Inconsciente",
            "session_goal": "Foundation of Freud's model of the psyche.",
            "learner_level": "foundational",
            "depth": "foundational",
            "strategy": "example_first",
            "plan": [
                {"topic": "Contexto histórico", "status": "done"},
                {"topic": "Inconsciente", "status": "current"},
                {"topic": "Recalque", "status": "planned"},
            ],
            "mastery_evidence": {
                "concept": "Inconsciente",
                "verdict": "partial",
                "strength": "free_explanation",
            },
            "misconception": "Tudo que esqueci está no inconsciente.",
        },
        turn_index=4,
    )

    assert session.current_concept == "Inconsciente"
    assert session.subject == "Psicologia"
    assert session.strategy == "example_first"
    assert [p["status"] for p in session.plan] == ["done", "current", "planned"]
    assert session.understanding[-1]["verdict"] == "partial"
    assert session.understanding[-1]["turn"] == 4
    assert session.misconceptions == ["Tudo que esqueci está no inconsciente."]


def test_a_resolved_misconception_leaves_the_list() -> None:
    session = make_session()
    session.plan, session.understanding = [], []
    session.misconceptions = ["Id é sinônimo de inconsciente."]

    TeachingSessions.apply_pedagogy(
        session,
        {"misconception_resolved": "Id é sinônimo de inconsciente."},
        turn_index=9,
    )

    assert session.misconceptions == []


def test_lists_are_replaced_not_mutated() -> None:
    """SQLAlchemy does not notice a JSONB list edited in place.

    Mutating would keep the change in memory and never write it — the bug that
    looks like it works until the next request.
    """
    session = make_session()
    session.plan = []
    original_understanding = session.understanding = []
    original_misconceptions = session.misconceptions = []

    TeachingSessions.apply_pedagogy(
        session,
        {
            "mastery_evidence": {
                "concept": "x",
                "verdict": "correct",
                "strength": "application",
            },
            "misconception": "y",
        },
        turn_index=1,
    )

    assert session.understanding is not original_understanding
    assert session.misconceptions is not original_misconceptions


def test_an_unknown_level_is_ignored_not_stored() -> None:
    session = make_session()
    session.plan, session.understanding, session.misconceptions = [], [], []

    TeachingSessions.apply_pedagogy(
        session, {"learner_level": "galaxy-brain"}, turn_index=1
    )

    assert session.learner_level == "foundational"


def test_render_says_where_the_lesson_is_and_nothing_it_does_not_know() -> None:
    session = make_session()
    session.plan, session.understanding, session.misconceptions = [], [], []

    bare = render_session(session)
    assert "Learner's goal, in their words: Freud" in bare
    assert "Plan:" not in bare
    assert "Misconceptions" not in bare

    TeachingSessions.apply_pedagogy(
        session,
        {
            "subject": "Psicologia",
            "current_concept": "Inconsciente",
            "plan": [{"topic": "Inconsciente", "status": "current"}],
            "misconception": "Esquecer é reprimir.",
        },
        turn_index=2,
    )
    rich = render_session(session)
    assert "Psicologia → Inconsciente" in rich
    assert "[current] Inconsciente" in rich
    assert "Esquecer é reprimir." in rich
