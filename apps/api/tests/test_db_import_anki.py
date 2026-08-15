"""Storing an imported Anki deck.

The parser has its own tests; these cover the half that touches the database,
and mostly they cover one scenario: importing the same deck twice. People
re-export a deck after adding a hundred cards and import it again, and the
failure that matters is not a duplicate — it is a card someone has been studying
for two years having its schedule reset to whatever the file said.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from anki_deck import CREATED, build
from sqlalchemy import delete, func, select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from noema.db.models import (
    Card,
    CardOrigin,
    CardSchedule,
    CardState,
    CardType,
    Concept,
    ConceptMastery,
    ConceptStatus,
    Notebook,
    Subject,
    User,
    Workspace,
)
from noema.db.repository import OwnedRepository
from noema.engines.fsrs import Rating
from noema.knowledge.resolution import normalize_name
from noema.services.imports import ImportReport, import_anki
from noema.study.review import record_review

pytestmark = pytest.mark.asyncio


async def notebook_for(
    db: AsyncSession, owner: User, *, workspace: Workspace | None = None
) -> Notebook:
    if workspace is None:
        workspace = await OwnedRepository(db, Workspace, owner.id).create(
            title="Languages", slug=f"lang-{uuid.uuid4().hex[:8]}"
        )
    subject = await OwnedRepository(db, Subject, owner.id).create(
        workspace_id=workspace.id, title="Japanese", slug=f"jp-{uuid.uuid4().hex[:8]}"
    )
    return await OwnedRepository(db, Notebook, owner.id).create(
        subject_id=subject.id,
        title="Core 2k",
        slug=f"core-{uuid.uuid4().hex[:8]}",
        retrieval_settings={},
    )


async def cards_in(db: AsyncSession, notebook: Notebook) -> list[Card]:
    rows = await db.execute(
        select(Card).where(Card.notebook_id == notebook.id).order_by(Card.front_md)
    )
    return list(rows.scalars())


async def workspace_for(db: AsyncSession, notebook: Notebook) -> Workspace:
    subject = await db.get(Subject, notebook.subject_id)
    assert subject is not None
    workspace = await db.get(Workspace, subject.workspace_id)
    assert workspace is not None
    return workspace


async def test_cards_arrive_studyable(
    db: AsyncSession, user: User, tmp_path: Path
) -> None:
    """Imported cards are the learner's own, so nothing waits for approval.

    AI drafts are inert until approved. These are cards someone has been
    reviewing for years — withholding them would be absurd.
    """
    notebook = await notebook_for(db, user)

    report = await import_anki(
        db,
        build(tmp_path, [{"flds": "ねこ\x1fcat"}]),
        owner_id=user.id,
        notebook_id=notebook.id,
    )

    assert report.added == 1
    card = (await cards_in(db, notebook))[0]
    assert card.front_md == "ねこ"
    assert card.origin is CardOrigin.USER
    assert card.approved_at is not None
    assert card.type is CardType.BASIC
    concept = await db.get(Concept, card.concept_id)
    assert concept is not None
    assert concept.name == "Default"
    assert concept.normalized_name == "default"
    assert concept.status is ConceptStatus.ACTIVE


async def test_deck_concepts_are_reused_only_inside_the_workspace(
    db: AsyncSession, user: User, tmp_path: Path
) -> None:
    first = await notebook_for(db, user)
    workspace = await workspace_for(db, first)
    second = await notebook_for(db, user, workspace=workspace)
    isolated = await notebook_for(db, user)

    candidate = Concept(
        owner_id=user.id,
        workspace_id=workspace.id,
        name="The Defaults",
        normalized_name=normalize_name("The Defaults"),
        aliases=[],
        source_chunk_ids=[],
        status=ConceptStatus.CANDIDATE,
    )
    db.add(candidate)
    await db.flush()

    deck = build(tmp_path, [{"flds": "q\x1fa"}])
    await import_anki(db, deck, owner_id=user.id, notebook_id=first.id)
    await import_anki(db, deck, owner_id=user.id, notebook_id=second.id)
    await import_anki(db, deck, owner_id=user.id, notebook_id=isolated.id)

    first_card = (await cards_in(db, first))[0]
    second_card = (await cards_in(db, second))[0]
    isolated_card = (await cards_in(db, isolated))[0]
    assert first_card.concept_id == candidate.id
    assert second_card.concept_id == candidate.id
    assert isolated_card.concept_id != candidate.id
    assert candidate.status is ConceptStatus.ACTIVE
    assert await db.scalar(select(func.count()).select_from(Concept)) == 2


async def test_full_hierarchical_paths_keep_equal_leaves_distinct(
    db: AsyncSession, user: User, tmp_path: Path
) -> None:
    notebook = await notebook_for(db, user)
    deck = build(
        tmp_path,
        [
            {"flds": "heart\x1fcardiology", "did": 1},
            {"flds": "cell\x1fbiology", "did": 2},
        ],
        decks={1: "Medicine::Common", 2: "Biology::Common"},
    )

    await import_anki(db, deck, owner_id=user.id, notebook_id=notebook.id)

    cards = await cards_in(db, notebook)
    concepts = {
        concept.id: concept for concept in (await db.scalars(select(Concept))).all()
    }
    assert len(concepts) == 2
    assert {concept.name for concept in concepts.values()} == {
        "Medicine::Common",
        "Biology::Common",
    }
    linked_names: set[str] = set()
    for card in cards:
        assert card.concept_id is not None
        linked_names.add(concepts[card.concept_id].normalized_name)
    assert linked_names == {
        "medicine common",
        "biology common",
    }


async def test_long_deck_paths_fit_without_truncation_collisions(
    db: AsyncSession, user: User, tmp_path: Path
) -> None:
    notebook = await notebook_for(db, user)
    shared_prefix = "A" * 240
    deck = build(
        tmp_path,
        [
            {"flds": "one\x1f1", "did": 1},
            {"flds": "two\x1f2", "did": 2},
        ],
        decks={
            1: f"{shared_prefix}::First",
            2: f"{shared_prefix}::Second",
        },
    )

    await import_anki(db, deck, owner_id=user.id, notebook_id=notebook.id)

    concepts = list((await db.scalars(select(Concept))).all())
    assert len(concepts) == 2
    assert all(len(concept.name) == 200 for concept in concepts)
    assert all(len(concept.normalized_name) == 200 for concept in concepts)
    assert len({concept.name for concept in concepts}) == 2
    assert len({concept.normalized_name for concept in concepts}) == 2
    assert all(
        concept.normalized_name == normalize_name(concept.normalized_name)
        for concept in concepts
    )
    assert all(
        concept.normalized_name == normalize_name(concept.name) for concept in concepts
    )


async def test_rejected_deck_concept_is_not_reactivated(
    db: AsyncSession, user: User, tmp_path: Path
) -> None:
    notebook = await notebook_for(db, user)
    workspace = await workspace_for(db, notebook)
    rejected = Concept(
        owner_id=user.id,
        workspace_id=workspace.id,
        name="Default",
        normalized_name="default",
        aliases=[],
        source_chunk_ids=[],
        status=ConceptStatus.REJECTED,
    )
    db.add(rejected)
    await db.flush()

    await import_anki(
        db,
        build(tmp_path, [{"flds": "q\x1fa"}]),
        owner_id=user.id,
        notebook_id=notebook.id,
    )

    card = (await cards_in(db, notebook))[0]
    assert card.concept_id == rejected.id
    assert rejected.status is ConceptStatus.REJECTED


async def test_merged_deck_concept_links_to_its_valid_target(
    db: AsyncSession, user: User, tmp_path: Path
) -> None:
    notebook = await notebook_for(db, user)
    workspace = await workspace_for(db, notebook)
    target = Concept(
        owner_id=user.id,
        workspace_id=workspace.id,
        name="Canonical topic",
        normalized_name="canonical topic",
        aliases=[],
        source_chunk_ids=[],
        status=ConceptStatus.ACTIVE,
    )
    db.add(target)
    await db.flush()
    merged = Concept(
        owner_id=user.id,
        workspace_id=workspace.id,
        name="Default",
        normalized_name="default",
        aliases=[],
        source_chunk_ids=[],
        status=ConceptStatus.MERGED,
        merged_into_id=target.id,
    )
    db.add(merged)
    await db.flush()

    await import_anki(
        db,
        build(tmp_path, [{"flds": "q\x1fa"}]),
        owner_id=user.id,
        notebook_id=notebook.id,
    )

    card = (await cards_in(db, notebook))[0]
    assert card.concept_id == target.id
    assert merged.status is ConceptStatus.MERGED
    assert merged.merged_into_id == target.id


async def test_the_anki_interval_becomes_the_schedule(
    db: AsyncSession, user: User, tmp_path: Path
) -> None:
    notebook = await notebook_for(db, user)

    await import_anki(
        db,
        build(
            tmp_path, [{"flds": "q\x1fa", "type": 2, "ivl": 90, "due": 300, "reps": 8}]
        ),
        owner_id=user.id,
        notebook_id=notebook.id,
    )

    card = (await cards_in(db, notebook))[0]
    schedule = await db.scalar(
        select(CardSchedule).where(CardSchedule.card_id == card.id)
    )
    assert schedule is not None
    assert schedule.state is CardState.REVIEW
    assert schedule.stability == 90.0
    assert schedule.reps == 8
    assert schedule.due_at.date() == CREATED.date() + timedelta(days=300)
    # Never reviewed *here*, and the review log's value is that everything in it
    # actually happened.
    assert schedule.last_review_at is None


async def test_an_unstudied_card_starts_new(
    db: AsyncSession, user: User, tmp_path: Path
) -> None:
    notebook = await notebook_for(db, user)

    await import_anki(
        db,
        build(tmp_path, [{"flds": "q\x1fa", "type": 0}]),
        owner_id=user.id,
        notebook_id=notebook.id,
    )

    card = (await cards_in(db, notebook))[0]
    schedule = await db.scalar(
        select(CardSchedule).where(CardSchedule.card_id == card.id)
    )
    assert schedule is not None
    assert schedule.state is CardState.NEW
    assert schedule.reps == 0


async def test_imported_card_reviews_feed_its_deck_mastery(
    db: AsyncSession, user: User, tmp_path: Path
) -> None:
    notebook = await notebook_for(db, user)
    await import_anki(
        db,
        build(tmp_path, [{"flds": "q\x1fa"}], decks={1: "Knowledge::Topic"}),
        owner_id=user.id,
        notebook_id=notebook.id,
    )
    card = (await cards_in(db, notebook))[0]
    assert card.concept_id is not None

    outcome = await record_review(db, card.id, owner_id=user.id, rating=Rating.GOOD)

    mastery = await db.scalar(
        select(ConceptMastery).where(ConceptMastery.concept_id == card.concept_id)
    )
    assert outcome.mastery is not None
    assert mastery is not None
    assert mastery.mastery == pytest.approx(outcome.mastery)


# ── Importing the same deck twice ────────────────────────────────────────────


async def test_reimporting_does_not_duplicate(
    db: AsyncSession, user: User, tmp_path: Path
) -> None:
    notebook = await notebook_for(db, user)
    deck = build(tmp_path, [{"flds": "q\x1fa"}, {"flds": "b\x1f2"}])

    first = await import_anki(db, deck, owner_id=user.id, notebook_id=notebook.id)
    second = await import_anki(db, deck, owner_id=user.id, notebook_id=notebook.id)

    assert first.added == 2
    assert second.added == 0
    assert second.unchanged == 2
    assert (
        await db.scalar(
            select(func.count()).select_from(Card).where(Card.notebook_id == notebook.id)
        )
        == 2
    )
    assert await db.scalar(select(func.count()).select_from(CardSchedule)) == 2
    assert await db.scalar(select(func.count()).select_from(Concept)) == 1


async def test_reimporting_leaves_an_existing_schedule_alone(
    db: AsyncSession, user: User, tmp_path: Path
) -> None:
    """The card has been studied here since the first import.

    A second import must not drag it back to where the file says it was — that
    is real progress destroyed by a routine action, and it would be discovered
    weeks later as "the scheduling feels wrong".
    """
    notebook = await notebook_for(db, user)
    deck = build(tmp_path, [{"flds": "q\x1fa", "type": 2, "ivl": 10}])

    await import_anki(db, deck, owner_id=user.id, notebook_id=notebook.id)
    card = (await cards_in(db, notebook))[0]
    schedule = await db.scalar(
        select(CardSchedule).where(CardSchedule.card_id == card.id)
    )
    assert schedule is not None

    # Studied here: stability grows well past what the file claims.
    schedule.stability = 400.0
    schedule.reps = 25
    await db.flush()

    await import_anki(db, deck, owner_id=user.id, notebook_id=notebook.id)

    await db.refresh(schedule)
    assert schedule.stability == 400.0
    assert schedule.reps == 25


async def test_reimport_backfills_a_legacy_null_link_without_touching_schedule(
    db: AsyncSession, user: User, tmp_path: Path
) -> None:
    notebook = await notebook_for(db, user)
    card = Card(
        owner_id=user.id,
        notebook_id=notebook.id,
        concept_id=None,
        type=CardType.BASIC,
        front_md="q",
        back_md="a",
        origin=CardOrigin.USER,
        approved_at=CREATED,
    )
    db.add(card)
    await db.flush()
    schedule = CardSchedule(
        owner_id=user.id,
        card_id=card.id,
        due_at=CREATED + timedelta(days=90),
        last_review_at=CREATED + timedelta(days=2),
        stability=400.0,
        difficulty=3.25,
        reps=25,
        lapses=4,
        state=CardState.REVIEW,
    )
    db.add(schedule)
    await db.flush()
    before = (
        schedule.id,
        schedule.due_at,
        schedule.last_review_at,
        schedule.stability,
        schedule.difficulty,
        schedule.reps,
        schedule.lapses,
        schedule.state,
    )

    report = await import_anki(
        db,
        build(tmp_path, [{"flds": "q\x1fa", "type": 2, "ivl": 10}]),
        owner_id=user.id,
        notebook_id=notebook.id,
    )

    await db.flush()
    await db.refresh(card)
    await db.refresh(schedule)
    assert report.added == 0
    assert report.unchanged == 1
    assert card.concept_id is not None
    assert before == (
        schedule.id,
        schedule.due_at,
        schedule.last_review_at,
        schedule.stability,
        schedule.difficulty,
        schedule.reps,
        schedule.lapses,
        schedule.state,
    )
    assert await db.scalar(select(func.count()).select_from(Card)) == 1
    assert await db.scalar(select(func.count()).select_from(CardSchedule)) == 1


async def test_reimport_preserves_a_curated_concept_link(
    db: AsyncSession, user: User, tmp_path: Path
) -> None:
    notebook = await notebook_for(db, user)
    deck = build(tmp_path, [{"flds": "q\x1fa"}])
    await import_anki(db, deck, owner_id=user.id, notebook_id=notebook.id)
    card = (await cards_in(db, notebook))[0]
    workspace = await workspace_for(db, notebook)
    curated = Concept(
        owner_id=user.id,
        workspace_id=workspace.id,
        name="Curated topic",
        normalized_name="curated topic",
        aliases=[],
        source_chunk_ids=[],
        status=ConceptStatus.ACTIVE,
    )
    db.add(curated)
    await db.flush()
    card.concept_id = curated.id
    await db.flush()

    report = await import_anki(db, deck, owner_id=user.id, notebook_id=notebook.id)

    await db.refresh(card)
    assert report.added == 0
    assert report.unchanged == 1
    assert card.concept_id == curated.id


async def test_a_deck_containing_the_same_card_twice_adds_it_once(
    db: AsyncSession, user: User, tmp_path: Path
) -> None:
    notebook = await notebook_for(db, user)

    report = await import_anki(
        db,
        build(
            tmp_path,
            [
                {"flds": "q\x1fa", "did": 1},
                {"flds": " Q \x1f A ", "did": 2},
            ],
            decks={1: "First", 2: "Second"},
        ),
        owner_id=user.id,
        notebook_id=notebook.id,
    )

    assert report.added == 1
    card = (await cards_in(db, notebook))[0]
    concept = await db.get(Concept, card.concept_id)
    assert concept is not None
    assert concept.name == "First"
    assert await db.scalar(select(func.count()).select_from(Concept)) == 1


async def test_first_duplicate_is_chosen_by_anki_card_id(
    db: AsyncSession, user: User, tmp_path: Path
) -> None:
    notebook = await notebook_for(db, user)

    await import_anki(
        db,
        build(
            tmp_path,
            [
                {"card_id": 20, "flds": "q\x1fa", "did": 1},
                {"card_id": 10, "flds": " Q \x1f A ", "did": 2},
            ],
            decks={1: "Later", 2: "Earlier"},
        ),
        owner_id=user.id,
        notebook_id=notebook.id,
    )

    card = (await cards_in(db, notebook))[0]
    concept = await db.get(Concept, card.concept_id)
    assert concept is not None
    assert concept.name == "Earlier"


async def test_concurrent_imports_serialize_cards_and_create_one_concept(
    db: AsyncSession, tmp_path: Path
) -> None:
    """Use independent connections so PostgreSQL locks and conflicts are real."""
    assert db.bind is not None  # The regular fixture preserves local DB skip policy.
    engine = create_async_engine(db.bind.engine.url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    owner_id: uuid.UUID | None = None

    try:
        async with sessions() as setup:
            owner = User(
                email=f"concurrent-{uuid.uuid4()}@example.com",
                password_hash="unused",
                display_name="Concurrent importer",
                settings={},
            )
            setup.add(owner)
            await setup.flush()
            owner_id = owner.id
            shared = await OwnedRepository(setup, Workspace, owner.id).create(
                title="Concurrent", slug=f"concurrent-{uuid.uuid4().hex[:8]}"
            )
            same_notebook = await notebook_for(setup, owner, workspace=shared)
            first_notebook = await notebook_for(setup, owner, workspace=shared)
            second_notebook = await notebook_for(setup, owner, workspace=shared)
            await setup.commit()

        same_deck = build(tmp_path, [{"flds": "same\x1fcard"}])

        async def run_import(data: bytes, notebook_id: uuid.UUID) -> ImportReport:
            async with sessions() as session:
                report = await import_anki(
                    session, data, owner_id=owner.id, notebook_id=notebook_id
                )
                await session.commit()
                return report

        same_reports = await asyncio.gather(
            run_import(same_deck, same_notebook.id),
            run_import(same_deck, same_notebook.id),
        )
        assert sorted((report.added, report.unchanged) for report in same_reports) == [
            (0, 1),
            (1, 0),
        ]

        first_deck = build(
            tmp_path,
            [{"flds": "first\x1fcard"}],
            decks={1: "Atomic Concept"},
        )
        second_deck = build(
            tmp_path,
            [{"flds": "second\x1fcard"}],
            decks={1: "Atomic Concept"},
        )
        await asyncio.gather(
            run_import(first_deck, first_notebook.id),
            run_import(second_deck, second_notebook.id),
        )

        async with sessions() as check:
            assert (
                await check.scalar(
                    select(func.count())
                    .select_from(Card)
                    .where(Card.notebook_id == same_notebook.id)
                )
                == 1
            )
            assert (
                await check.scalar(
                    select(func.count())
                    .select_from(CardSchedule)
                    .join(Card, Card.id == CardSchedule.card_id)
                    .where(Card.notebook_id == same_notebook.id)
                )
                == 1
            )
            assert (
                await check.scalar(
                    select(func.count())
                    .select_from(Concept)
                    .where(
                        Concept.workspace_id == shared.id,
                        Concept.normalized_name == "atomic concept",
                    )
                )
                == 1
            )
    finally:
        if owner_id is not None:
            async with sessions() as cleanup:
                await cleanup.execute(delete(User).where(User.id == owner_id))
                await cleanup.commit()
        await engine.dispose()


async def test_import_cannot_cross_notebook_ownership(
    db: AsyncSession, user: User, other_user: User, tmp_path: Path
) -> None:
    notebook = await notebook_for(db, user)

    with pytest.raises(NoResultFound):
        await import_anki(
            db,
            build(tmp_path, [{"flds": "q\x1fa"}]),
            owner_id=other_user.id,
            notebook_id=notebook.id,
        )

    assert await db.scalar(select(func.count()).select_from(Card)) == 0
    assert await db.scalar(select(func.count()).select_from(Concept)) == 0


async def test_the_same_deck_in_another_notebook_is_a_separate_import(
    db: AsyncSession, user: User, tmp_path: Path
) -> None:
    """Notebooks are how someone separates material; sharing cards across them
    silently would merge two things they deliberately kept apart."""
    first = await notebook_for(db, user)
    second = await notebook_for(db, user)
    deck = build(tmp_path, [{"flds": "q\x1fa"}])

    await import_anki(db, deck, owner_id=user.id, notebook_id=first.id)
    report = await import_anki(db, deck, owner_id=user.id, notebook_id=second.id)

    assert report.added == 1


async def test_the_report_is_checkable_against_the_deck(
    db: AsyncSession, user: User, tmp_path: Path
) -> None:
    notebook = await notebook_for(db, user)

    report = await import_anki(
        db,
        build(
            tmp_path,
            [
                {"flds": "a\x1f1", "type": 2, "ivl": 30},
                {"flds": "b\x1f2"},
                {"flds": 'c\x1f<img src="x.png">'},
            ],
        ),
        owner_id=user.id,
        notebook_id=notebook.id,
    )

    assert report.added == 2
    assert report.scheduled == 1
    assert sum(report.skipped.values()) == 1
    assert "2 cards added" in report.summary()
