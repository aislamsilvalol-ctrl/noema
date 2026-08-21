"""Misconception correction, against a real database.

`_build`/`_spaced_enough` are covered as pure functions in `test_correction.py`.
What's tested here is the orchestration: `resolve_if_earned`'s query for what
counts as evidence (confident, correct, after the mistake, spaced apart), and
`build_drills`'s tenancy checks, its use of a real gateway response, and that a
malformed or failed model response degrades to nothing rather than crashing.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.errors import NotFound
from noema.db.base import utcnow
from noema.db.models import (
    Answer,
    Concept,
    ConceptStatus,
    Mistake,
    Notebook,
    Question,
    QuestionType,
    Subject,
    User,
    Workspace,
)
from noema.db.repository import OwnedRepository
from noema.providers.base import (
    Capabilities,
    ChatRequest,
    ChatResponse,
    EmbedRequest,
    EmbedResponse,
    HealthReport,
    ProviderError,
    StructuredRequest,
)
from noema.providers.gateway import AIGateway
from noema.study.correction import CONFIDENT, Drills, build_drills, resolve_if_earned

pytestmark = pytest.mark.asyncio


class FakeProvider:
    """A scripted ``AIProvider`` — see ``test_db_generation.py`` for why not
    ``MockProvider``: its schema-skeleton response isn't useful when the test
    needs to control exactly what comes back."""

    name = "fake"
    capabilities = Capabilities(structured_output="native")

    def __init__(self, responses: list[dict[str, Any] | Exception]) -> None:
        self._queue = list(responses)
        self.calls = 0

    async def structured(self, request: StructuredRequest) -> dict[str, Any]:
        self.calls += 1
        response = self._queue.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    async def chat(self, request: ChatRequest) -> ChatResponse:
        raise NotImplementedError

    def stream(self, request: ChatRequest) -> Any:
        raise NotImplementedError

    async def embed(self, request: EmbedRequest) -> EmbedResponse:
        raise NotImplementedError

    async def health(self) -> HealthReport:
        raise NotImplementedError


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
    db: AsyncSession, user: User, notebook: Notebook, concept: Concept | None
) -> Question:
    question = Question(
        owner_id=user.id,
        notebook_id=notebook.id,
        concept_id=concept.id if concept else None,
        type=QuestionType.MCQ,
        prompt="What fills the ventricles?",
        payload={"options": ["Diastole", "Systole"], "correct_index": 0},
    )
    db.add(question)
    await db.flush()
    return question


async def make_answer(
    db: AsyncSession,
    user: User,
    question: Question,
    concept: Concept | None,
    *,
    is_correct: bool,
    confidence: int,
    answered_at: Any = None,
) -> Answer:
    answer = Answer(
        owner_id=user.id,
        question_id=question.id,
        concept_id=concept.id if concept else None,
        response={"index": 0},
        is_correct=is_correct,
        confidence=confidence,
    )
    if answered_at is not None:
        answer.answered_at = answered_at
    db.add(answer)
    await db.flush()
    return answer


async def make_mistake(
    db: AsyncSession,
    user: User,
    question: Question,
    answer: Answer,
    concept: Concept | None,
    *,
    is_misconception: bool = True,
    resolved_at: Any = None,
    summary: str | None = "Thinks systole fills the ventricles.",
) -> Mistake:
    mistake = Mistake(
        owner_id=user.id,
        question_id=question.id,
        answer_id=answer.id,
        concept_id=concept.id if concept else None,
        confidence=answer.confidence,
        is_misconception=is_misconception,
        resolved_at=resolved_at,
        summary=summary,
    )
    db.add(mistake)
    await db.flush()
    return mistake


def drill_payload(*, belief: str = "Systole fills the ventricles.") -> dict[str, Any]:
    return {
        "belief": belief,
        "questions": [
            {
                "type": "mcq",
                "prompt": "Which phase fills the ventricles?",
                "options": ["Diastole", "Systole"],
                "correct_index": 0,
                "explanation": "Diastole is the filling phase.",
                "discriminates": "Filling versus ejection.",
            },
            {
                "type": "true_false",
                "prompt": "Systole is the filling phase.",
                "answer": False,
                "explanation": "Systole ejects; diastole fills.",
                "discriminates": "Direct contradiction of the misconception.",
            },
        ],
    }


# ---------------------------------------------------------------------------
# resolve_if_earned
# ---------------------------------------------------------------------------


async def test_no_concept_returns_zero_without_touching_the_database(
    db: AsyncSession, user: User
) -> None:
    assert await resolve_if_earned(db, None, owner_id=user.id) == 0


async def test_a_concept_with_no_open_mistakes_returns_zero(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    concept = await make_concept(db, user, notebook, "Cardiac Cycle")

    assert await resolve_if_earned(db, concept.id, owner_id=user.id) == 0


async def test_two_confident_correct_answers_spaced_apart_resolve_it(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    concept = await make_concept(db, user, notebook, "Cardiac Cycle")
    question = await make_question(db, user, notebook, concept)
    wrong = await make_answer(db, user, question, concept, is_correct=False, confidence=4)
    mistake = await make_mistake(db, user, question, wrong, concept)

    base = mistake.created_at
    await make_answer(
        db,
        user,
        question,
        concept,
        is_correct=True,
        confidence=CONFIDENT,
        answered_at=base + timedelta(minutes=1),
    )
    await make_answer(
        db,
        user,
        question,
        concept,
        is_correct=True,
        confidence=CONFIDENT,
        answered_at=base + timedelta(hours=21),
    )

    resolved = await resolve_if_earned(db, concept.id, owner_id=user.id)

    assert resolved == 1
    await db.refresh(mistake)
    assert mistake.resolved_at is not None


async def test_a_single_confident_correct_answer_does_not_resolve(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    concept = await make_concept(db, user, notebook, "Cardiac Cycle")
    question = await make_question(db, user, notebook, concept)
    wrong = await make_answer(db, user, question, concept, is_correct=False, confidence=4)
    mistake = await make_mistake(db, user, question, wrong, concept)
    await make_answer(db, user, question, concept, is_correct=True, confidence=CONFIDENT)

    resolved = await resolve_if_earned(db, concept.id, owner_id=user.id)

    assert resolved == 0
    await db.refresh(mistake)
    assert mistake.resolved_at is None


async def test_low_confidence_correct_answers_do_not_count(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    concept = await make_concept(db, user, notebook, "Cardiac Cycle")
    question = await make_question(db, user, notebook, concept)
    wrong = await make_answer(db, user, question, concept, is_correct=False, confidence=4)
    mistake = await make_mistake(db, user, question, wrong, concept)

    base = mistake.created_at
    await make_answer(
        db,
        user,
        question,
        concept,
        is_correct=True,
        confidence=CONFIDENT - 1,
        answered_at=base + timedelta(minutes=1),
    )
    await make_answer(
        db,
        user,
        question,
        concept,
        is_correct=True,
        confidence=CONFIDENT - 1,
        answered_at=base + timedelta(hours=21),
    )

    assert await resolve_if_earned(db, concept.id, owner_id=user.id) == 0


async def test_incorrect_answers_do_not_count_even_if_confident(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    concept = await make_concept(db, user, notebook, "Cardiac Cycle")
    question = await make_question(db, user, notebook, concept)
    wrong = await make_answer(db, user, question, concept, is_correct=False, confidence=4)
    mistake = await make_mistake(db, user, question, wrong, concept)

    base = mistake.created_at
    await make_answer(
        db,
        user,
        question,
        concept,
        is_correct=False,
        confidence=CONFIDENT,
        answered_at=base + timedelta(minutes=1),
    )
    await make_answer(
        db,
        user,
        question,
        concept,
        is_correct=False,
        confidence=CONFIDENT,
        answered_at=base + timedelta(hours=21),
    )

    assert await resolve_if_earned(db, concept.id, owner_id=user.id) == 0


async def test_answers_from_before_the_mistake_do_not_count(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    concept = await make_concept(db, user, notebook, "Cardiac Cycle")
    question = await make_question(db, user, notebook, concept)

    before = utcnow() - timedelta(days=5)
    await make_answer(
        db,
        user,
        question,
        concept,
        is_correct=True,
        confidence=CONFIDENT,
        answered_at=before,
    )
    await make_answer(
        db,
        user,
        question,
        concept,
        is_correct=True,
        confidence=CONFIDENT,
        answered_at=before + timedelta(hours=21),
    )

    wrong = await make_answer(db, user, question, concept, is_correct=False, confidence=4)
    mistake = await make_mistake(db, user, question, wrong, concept)

    assert await resolve_if_earned(db, concept.id, owner_id=user.id) == 0
    await db.refresh(mistake)
    assert mistake.resolved_at is None


async def test_an_already_resolved_mistake_is_left_alone(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    concept = await make_concept(db, user, notebook, "Cardiac Cycle")
    question = await make_question(db, user, notebook, concept)
    wrong = await make_answer(db, user, question, concept, is_correct=False, confidence=4)
    stamp = utcnow() - timedelta(days=1)
    mistake = await make_mistake(db, user, question, wrong, concept, resolved_at=stamp)

    base = mistake.created_at
    await make_answer(
        db,
        user,
        question,
        concept,
        is_correct=True,
        confidence=CONFIDENT,
        answered_at=base + timedelta(minutes=1),
    )
    await make_answer(
        db,
        user,
        question,
        concept,
        is_correct=True,
        confidence=CONFIDENT,
        answered_at=base + timedelta(hours=21),
    )

    assert await resolve_if_earned(db, concept.id, owner_id=user.id) == 0
    await db.refresh(mistake)
    assert mistake.resolved_at == stamp


async def test_a_mistake_not_flagged_as_a_misconception_is_ignored(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    concept = await make_concept(db, user, notebook, "Cardiac Cycle")
    question = await make_question(db, user, notebook, concept)
    wrong = await make_answer(db, user, question, concept, is_correct=False, confidence=4)
    mistake = await make_mistake(
        db, user, question, wrong, concept, is_misconception=False
    )

    base = mistake.created_at
    await make_answer(
        db,
        user,
        question,
        concept,
        is_correct=True,
        confidence=CONFIDENT,
        answered_at=base + timedelta(minutes=1),
    )
    await make_answer(
        db,
        user,
        question,
        concept,
        is_correct=True,
        confidence=CONFIDENT,
        answered_at=base + timedelta(hours=21),
    )

    assert await resolve_if_earned(db, concept.id, owner_id=user.id) == 0


async def test_only_the_mistakes_that_earned_it_are_counted(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    concept = await make_concept(db, user, notebook, "Cardiac Cycle")
    q1 = await make_question(db, user, notebook, concept)
    q2 = await make_question(db, user, notebook, concept)

    wrong1 = await make_answer(db, user, q1, concept, is_correct=False, confidence=4)
    earns_it = await make_mistake(db, user, q1, wrong1, concept)
    base = earns_it.created_at
    await make_answer(
        db,
        user,
        q1,
        concept,
        is_correct=True,
        confidence=CONFIDENT,
        answered_at=base + timedelta(minutes=1),
    )
    await make_answer(
        db,
        user,
        q1,
        concept,
        is_correct=True,
        confidence=CONFIDENT,
        answered_at=base + timedelta(hours=21),
    )

    # Evidence is scoped by concept, not by mistake — a mistake created after the
    # qualifying answers must not benefit from evidence that predates it.
    wrong2 = await make_answer(db, user, q2, concept, is_correct=False, confidence=4)
    stays_open = await make_mistake(db, user, q2, wrong2, concept)
    stays_open.created_at = base + timedelta(hours=22)
    await db.flush()

    resolved = await resolve_if_earned(db, concept.id, owner_id=user.id)

    assert resolved == 1
    await db.refresh(earns_it)
    await db.refresh(stays_open)
    assert earns_it.resolved_at is not None
    assert stays_open.resolved_at is None


# ---------------------------------------------------------------------------
# build_drills
# ---------------------------------------------------------------------------


async def test_build_drills_raises_not_found_for_a_missing_mistake(
    db: AsyncSession, user: User
) -> None:
    gateway = AIGateway(FakeProvider([]))
    with pytest.raises(NotFound):
        await build_drills(db, uuid.uuid4(), owner_id=user.id, gateway=gateway)


async def test_build_drills_raises_not_found_for_another_owners_mistake(
    db: AsyncSession, user: User, other_user: User, notebook: Notebook
) -> None:
    concept = await make_concept(db, user, notebook, "Cardiac Cycle")
    question = await make_question(db, user, notebook, concept)
    wrong = await make_answer(db, user, question, concept, is_correct=False, confidence=4)
    mistake = await make_mistake(db, user, question, wrong, concept)

    gateway = AIGateway(FakeProvider([]))
    with pytest.raises(NotFound):
        await build_drills(db, mistake.id, owner_id=other_user.id, gateway=gateway)


async def test_build_drills_raises_not_found_with_no_gateway_configured(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    concept = await make_concept(db, user, notebook, "Cardiac Cycle")
    question = await make_question(db, user, notebook, concept)
    wrong = await make_answer(db, user, question, concept, is_correct=False, confidence=4)
    mistake = await make_mistake(db, user, question, wrong, concept)

    with pytest.raises(NotFound):
        await build_drills(db, mistake.id, owner_id=user.id, gateway=None)


async def test_build_drills_stores_gradeable_questions_and_names_the_belief(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    concept = await make_concept(db, user, notebook, "Cardiac Cycle")
    question = await make_question(db, user, notebook, concept)
    wrong = await make_answer(db, user, question, concept, is_correct=False, confidence=4)
    mistake = await make_mistake(db, user, question, wrong, concept, summary=None)

    gateway = AIGateway(FakeProvider([drill_payload()]))
    drills = await build_drills(db, mistake.id, owner_id=user.id, gateway=gateway)

    assert drills.belief == "Systole fills the ventricles."
    assert len(drills.questions) == 2
    assert {q.type for q in drills.questions} == {
        QuestionType.MCQ,
        QuestionType.TRUE_FALSE,
    }
    await db.refresh(mistake)
    assert mistake.summary == "Systole fills the ventricles."


async def test_build_drills_drops_ungradeable_items_but_keeps_the_rest(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    concept = await make_concept(db, user, notebook, "Cardiac Cycle")
    question = await make_question(db, user, notebook, concept)
    wrong = await make_answer(db, user, question, concept, is_correct=False, confidence=4)
    mistake = await make_mistake(db, user, question, wrong, concept)

    payload = drill_payload()
    payload["questions"].append({"type": "essay", "prompt": "Explain everything."})
    payload["questions"].append("not even a dict")

    gateway = AIGateway(FakeProvider([payload]))
    drills = await build_drills(db, mistake.id, owner_id=user.id, gateway=gateway)

    assert len(drills.questions) == 2


async def test_build_drills_truncates_to_max_drills(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    concept = await make_concept(db, user, notebook, "Cardiac Cycle")
    question = await make_question(db, user, notebook, concept)
    wrong = await make_answer(db, user, question, concept, is_correct=False, confidence=4)
    mistake = await make_mistake(db, user, question, wrong, concept)

    payload = drill_payload()
    extra = dict(payload["questions"][1])
    payload["questions"] = [payload["questions"][0]] + [extra] * 5

    gateway = AIGateway(FakeProvider([payload]))
    drills = await build_drills(db, mistake.id, owner_id=user.id, gateway=gateway)

    assert len(drills.questions) == 3


async def test_build_drills_yields_nothing_on_a_provider_error_without_crashing(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    concept = await make_concept(db, user, notebook, "Cardiac Cycle")
    question = await make_question(db, user, notebook, concept)
    wrong = await make_answer(db, user, question, concept, is_correct=False, confidence=4)
    mistake = await make_mistake(
        db, user, question, wrong, concept, summary="Original summary."
    )

    gateway = AIGateway(
        FakeProvider([ProviderError("down", provider="fake", retryable=False)])
    )
    drills = await build_drills(db, mistake.id, owner_id=user.id, gateway=gateway)

    assert drills == Drills(belief="", questions=[])
    await db.refresh(mistake)
    assert mistake.summary == "Original summary."


async def test_an_empty_belief_leaves_the_existing_summary_in_place(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    concept = await make_concept(db, user, notebook, "Cardiac Cycle")
    question = await make_question(db, user, notebook, concept)
    wrong = await make_answer(db, user, question, concept, is_correct=False, confidence=4)
    mistake = await make_mistake(
        db, user, question, wrong, concept, summary="Original summary."
    )

    gateway = AIGateway(FakeProvider([drill_payload(belief="")]))
    await build_drills(db, mistake.id, owner_id=user.id, gateway=gateway)

    await db.refresh(mistake)
    assert mistake.summary == "Original summary."
