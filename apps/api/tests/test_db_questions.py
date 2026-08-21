"""Generating and answering questions, against a real database.

``parse_questions`` is covered as a pure function in ``test_questions.py``. What's
tested here is the wiring: chunks become a real gateway call and get stored with
the right filters (an open question with no rubric is unstorable, not just
unparseable), and answering routes to deterministic or semantic grading, records
a mistake when it's wrong, and flags a confident wrong answer as a misconception
candidate.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.errors import NotFound
from noema.db.models import (
    Chunk,
    Concept,
    ConceptStatus,
    Grader,
    Mistake,
    Notebook,
    Question,
    QuestionType,
    Source,
    SourceKind,
    SourceStatus,
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
from noema.study.questions import (
    BATCH_SIZE,
    MISCONCEPTION_CONFIDENCE,
    answer_question,
    generate_questions,
)

pytestmark = pytest.mark.asyncio


class FakeProvider:
    """A scripted ``AIProvider`` — see ``test_db_generation.py`` for why not
    ``MockProvider``."""

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


def mcq_payload(*, prompt: str = "Q", concept: str = "") -> dict[str, Any]:
    return {
        "questions": [
            {
                "type": "mcq",
                "difficulty": "medium",
                "prompt": prompt,
                "concept": concept,
                "options": ["Right", "Wrong"],
                "correct_index": 0,
                "explanation": "",
            }
        ]
    }


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


async def make_chunks(
    db: AsyncSession, user: User, notebook: Notebook, count: int
) -> list[Chunk]:
    source = await OwnedRepository(db, Source, user.id).create(
        notebook_id=notebook.id,
        kind=SourceKind.MD,
        original_filename="notes.md",
        byte_size=0,
        status=SourceStatus.READY,
    )
    chunks = []
    for i in range(count):
        chunk = await OwnedRepository(db, Chunk, user.id).create(
            source_id=source.id,
            notebook_id=notebook.id,
            ordinal=i,
            content=f"Passage {i} about organelles.",
            token_count=5,
            heading_path=[],
        )
        chunks.append(chunk)
    await db.flush()
    return chunks


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
    db: AsyncSession,
    user: User,
    notebook: Notebook,
    *,
    concept: Concept | None = None,
    question_type: QuestionType = QuestionType.MCQ,
    payload: dict[str, Any] | None = None,
    rubric: dict[str, Any] | None = None,
) -> Question:
    question = Question(
        owner_id=user.id,
        notebook_id=notebook.id,
        concept_id=concept.id if concept else None,
        type=question_type,
        prompt="What fills the ventricles?",
        payload=payload or {"options": ["Diastole", "Systole"], "correct_index": 0},
        rubric=rubric,
    )
    db.add(question)
    await db.flush()
    return question


# ---------------------------------------------------------------------------
# generate_questions
# ---------------------------------------------------------------------------


async def test_a_notebook_with_no_chunks_produces_no_questions(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    provider = FakeProvider([ProviderError("should not be called", provider="fake")])
    gateway = AIGateway(provider)

    questions = await generate_questions(
        db, notebook.id, owner_id=user.id, gateway=gateway
    )

    assert questions == []
    assert provider.calls == 0


async def test_generated_questions_are_stored_with_ai_origin(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    await make_chunks(db, user, notebook, 2)
    gateway = AIGateway(FakeProvider([mcq_payload(prompt="What fills the ventricles?")]))

    questions = await generate_questions(
        db, notebook.id, owner_id=user.id, gateway=gateway
    )

    assert len(questions) == 1
    assert questions[0].type is QuestionType.MCQ
    assert questions[0].notebook_id == notebook.id
    assert questions[0].owner_id == user.id


async def test_a_provider_error_on_one_batch_does_not_abort_the_rest(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    await make_chunks(db, user, notebook, BATCH_SIZE + 1)
    provider = FakeProvider(
        [
            ProviderError("rate limited", provider="fake", retryable=False),
            mcq_payload(prompt="From batch two"),
        ]
    )
    gateway = AIGateway(provider)

    questions = await generate_questions(
        db, notebook.id, owner_id=user.id, gateway=gateway
    )

    assert provider.calls == 2
    assert len(questions) == 1
    assert questions[0].prompt == "From batch two"


async def test_an_open_question_with_no_rubric_is_not_stored(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    """Parsing keeps it (storage's call, not parsing's); storage drops it."""
    await make_chunks(db, user, notebook, 1)
    payload = {
        "questions": [
            {
                "type": "open",
                "difficulty": "medium",
                "prompt": "Explain the chain rule.",
                "concept": "",
                "explanation": "",
            }
        ]
    }
    gateway = AIGateway(FakeProvider([payload]))

    questions = await generate_questions(
        db, notebook.id, owner_id=user.id, gateway=gateway
    )

    assert questions == []


async def test_a_question_is_linked_to_a_matching_concept(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    concept = await make_concept(db, user, notebook, "Mitochondria")
    await make_chunks(db, user, notebook, 1)
    gateway = AIGateway(FakeProvider([mcq_payload(concept="Mitochondria")]))

    questions = await generate_questions(
        db, notebook.id, owner_id=user.id, gateway=gateway
    )

    assert questions[0].concept_id == concept.id


async def test_a_question_with_no_matching_concept_has_no_concept_id(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    await make_chunks(db, user, notebook, 1)
    gateway = AIGateway(FakeProvider([mcq_payload(concept="Nonexistent Concept")]))

    questions = await generate_questions(
        db, notebook.id, owner_id=user.id, gateway=gateway
    )

    assert questions[0].concept_id is None


async def test_limit_caps_how_many_questions_are_stored(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    await make_chunks(db, user, notebook, 1)
    payload = {
        "questions": [
            {
                "type": "mcq",
                "difficulty": "medium",
                "prompt": f"Q{i}",
                "concept": "",
                "options": ["Right", "Wrong"],
                "correct_index": 0,
            }
            for i in range(3)
        ]
    }
    gateway = AIGateway(FakeProvider([payload]))

    questions = await generate_questions(
        db, notebook.id, owner_id=user.id, gateway=gateway, limit=2
    )

    assert len(questions) == 2


# ---------------------------------------------------------------------------
# answer_question
# ---------------------------------------------------------------------------


async def test_answer_question_raises_not_found_for_a_missing_question(
    db: AsyncSession, user: User
) -> None:
    with pytest.raises(NotFound):
        await answer_question(db, uuid.uuid4(), {}, owner_id=user.id)


async def test_answer_question_raises_not_found_for_another_owners_question(
    db: AsyncSession, user: User, other_user: User, notebook: Notebook
) -> None:
    question = await make_question(db, user, notebook)

    with pytest.raises(NotFound):
        await answer_question(db, question.id, {}, owner_id=other_user.id)


async def test_a_correct_mcq_answer_is_graded_deterministically_with_no_mistake(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    question = await make_question(db, user, notebook)

    answer = await answer_question(db, question.id, {"choice": 0}, owner_id=user.id)

    assert answer.is_correct is True
    assert answer.grader is Grader.DETERMINISTIC
    assert (
        await db.scalar(select(Mistake).where(Mistake.question_id == question.id))
    ) is None


async def test_an_incorrect_mcq_answer_records_a_mistake(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    question = await make_question(db, user, notebook)

    answer = await answer_question(db, question.id, {"choice": 1}, owner_id=user.id)

    assert answer.is_correct is False
    mistake = await db.scalar(select(Mistake).where(Mistake.question_id == question.id))
    assert mistake is not None


async def test_a_confident_wrong_answer_is_flagged_as_a_misconception(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    question = await make_question(db, user, notebook)

    await answer_question(
        db,
        question.id,
        {"choice": 1},
        owner_id=user.id,
        confidence=MISCONCEPTION_CONFIDENCE,
    )

    mistake = await db.scalar(select(Mistake).where(Mistake.question_id == question.id))
    assert mistake is not None
    assert mistake.is_misconception is True


async def test_an_unconfident_wrong_answer_is_not_a_misconception(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    question = await make_question(db, user, notebook)

    await answer_question(db, question.id, {"choice": 1}, owner_id=user.id, confidence=1)

    mistake = await db.scalar(select(Mistake).where(Mistake.question_id == question.id))
    assert mistake is not None
    assert mistake.is_misconception is False


async def test_negative_elapsed_ms_is_clamped_to_zero(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    question = await make_question(db, user, notebook)

    answer = await answer_question(
        db, question.id, {"choice": 0}, owner_id=user.id, elapsed_ms=-500
    )

    assert answer.elapsed_ms == 0


async def test_an_open_answer_with_no_gateway_self_grades_as_incorrect(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    question = await make_question(
        db,
        user,
        notebook,
        question_type=QuestionType.OPEN,
        payload={},
        rubric={"points": ["x"]},
    )

    answer = await answer_question(
        db,
        question.id,
        {"text": "The chain rule differentiates compositions."},
        owner_id=user.id,
    )

    assert answer.is_correct is False
    assert answer.grader is Grader.SELF
    assert answer.feedback is not None
    assert "grade yourself" in answer.feedback["feedback"]


async def test_an_open_answer_with_no_text_is_ungraded_without_calling_the_gateway(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    question = await make_question(
        db,
        user,
        notebook,
        question_type=QuestionType.OPEN,
        payload={},
        rubric={"points": ["x"]},
    )
    provider = FakeProvider([ProviderError("should not be called", provider="fake")])
    gateway = AIGateway(provider)

    answer = await answer_question(
        db, question.id, {"text": "   "}, owner_id=user.id, gateway=gateway
    )

    assert answer.is_correct is False
    assert provider.calls == 0


async def test_an_open_answer_is_graded_semantically_when_a_gateway_is_configured(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    question = await make_question(
        db,
        user,
        notebook,
        question_type=QuestionType.OPEN,
        payload={},
        rubric={"points": ["x"]},
    )
    gateway = AIGateway(
        FakeProvider(
            [{"score": 0.9, "missing": [], "errors": [], "feedback": "Solid answer."}]
        )
    )

    answer = await answer_question(
        db,
        question.id,
        {"text": "The chain rule differentiates compositions."},
        owner_id=user.id,
        gateway=gateway,
    )

    assert answer.is_correct is True
    assert answer.grader is Grader.AI
    assert answer.score == 0.9


async def test_a_low_scoring_open_answer_is_incorrect_and_recorded_as_a_mistake(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    question = await make_question(
        db,
        user,
        notebook,
        question_type=QuestionType.OPEN,
        payload={},
        rubric={"points": ["x"]},
    )
    gateway = AIGateway(
        FakeProvider(
            [
                {
                    "score": 0.3,
                    "missing": ["the direction"],
                    "errors": [],
                    "feedback": "Partial.",
                }
            ]
        )
    )

    answer = await answer_question(
        db, question.id, {"text": "Something vague."}, owner_id=user.id, gateway=gateway
    )

    assert answer.is_correct is False
    mistake = await db.scalar(select(Mistake).where(Mistake.question_id == question.id))
    assert mistake is not None


async def test_a_grading_provider_error_degrades_to_a_self_grade(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    question = await make_question(
        db,
        user,
        notebook,
        question_type=QuestionType.OPEN,
        payload={},
        rubric={"points": ["x"]},
    )
    gateway = AIGateway(
        FakeProvider([ProviderError("down", provider="fake", retryable=False)])
    )

    answer = await answer_question(
        db, question.id, {"text": "An answer."}, owner_id=user.id, gateway=gateway
    )

    assert answer.is_correct is False
    assert answer.grader is Grader.SELF
    assert answer.feedback is not None
    assert "unavailable" in answer.feedback["feedback"]


async def test_answering_a_question_linked_to_a_concept_does_not_crash(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    """Exercises the resolve_if_earned / recompute_for_review side effects."""
    concept = await make_concept(db, user, notebook, "Mitochondria")
    question = await make_question(db, user, notebook, concept=concept)

    answer = await answer_question(db, question.id, {"choice": 0}, owner_id=user.id)

    assert answer.concept_id == concept.id
