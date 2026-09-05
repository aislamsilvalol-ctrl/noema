"""AssessmentEngine: micro-quizzes and checkpoint exams inside a journey.

The professor decides *when* (checkpoint.py, moves.py); this module writes
the paper, grades it and says what to do about the result. Questions carry
their answers and rubrics in the row; `public_view` strips them before the
client sees the paper. Closed types are graded deterministically with the
same functions the notebook questions use; open answers go to the rubric
grader. Every graded question writes an `assessment` mastery event on its
concept, and concepts under 0.5 come back as the remediation list the router
turns into a correction turn — the loop the brief asks for.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.errors import Conflict, NotFound
from noema.core.logging import get_logger
from noema.db.base import utcnow
from noema.db.models import Assessment, LearningJourney, QuestionType
from noema.prompts import load
from noema.providers.base import (
    Message,
    ProviderError,
    Role,
    StructuredRequest,
    TaskClass,
)
from noema.providers.gateway import AIGateway
from noema.study.grading import grade_deterministic, is_gradeable_locally

from .student import StudentModel

log = get_logger(__name__)

__all__ = [
    "ASSESSMENT_SCHEMA",
    "create_assessment",
    "grade",
    "parse_questions",
    "public_view",
    "render_results",
    "submit",
]

ASSESSMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": [
                            "mcq",
                            "true_false",
                            "short",
                            "open",
                            "ordering",
                            "fill_blank",
                        ],
                    },
                    "prompt": {"type": "string"},
                    "concept": {"type": "string"},
                    "options": {"type": "array", "items": {"type": "string"}},
                    "correct_index": {"type": "integer", "minimum": 0},
                    "answer": {"type": "boolean"},
                    "accepted": {"type": "array", "items": {"type": "string"}},
                    "order": {"type": "array", "items": {"type": "string"}},
                    "rubric": {"type": "array", "items": {"type": "string"}},
                    "explanation": {"type": "string"},
                },
                "required": ["type", "prompt", "concept"],
            },
        },
    },
    "required": ["title", "questions"],
}

PRIVATE = ("correct_index", "answer", "accepted", "order", "rubric", "explanation")
MAX_QUESTIONS = {"micro": 3, "checkpoint": 6}
WEAK_BELOW = 0.5


async def create_assessment(
    db: AsyncSession,
    *,
    owner_id: uuid.UUID,
    journey: LearningJourney,
    session_id: uuid.UUID | None,
    kind: str,
    concepts: list[str],
    context: str,
    gateway: AIGateway,
    model: str | None,
    now: datetime | None = None,
) -> Assessment | None:
    """Write the paper. None when the model could not (the lesson goes on)."""
    now = now or utcnow()
    kind = kind if kind in MAX_QUESTIONS else "micro"
    prompt = load("professor.assessment")
    user = (
        f"Subject: {journey.subject}\n"
        f"Kind: {kind} ({MAX_QUESTIONS[kind]} questions at most)\n"
        f"Learner level: {journey.inferred_level}\n"
        f"Concepts to assess: {', '.join(concepts) or journey.subject}\n"
        f"Language: {journey.profile.get('language') or 'the language of the lesson'}\n\n"
        f"<LESSON>\n{context[:8000]}\n</LESSON>"
    )
    try:
        payload = await gateway.structured(
            StructuredRequest(
                messages=[
                    Message(role=Role.SYSTEM, content=prompt.body),
                    Message(role=Role.USER, content=user),
                ],
                json_schema=ASSESSMENT_SCHEMA,
                task=TaskClass.GENERATE_QUESTIONS,
                model=model,
                metadata={"feature": "professor.assessment"},
            )
        )
    except ProviderError as exc:
        log.warning("professor.assessment_failed", kind=kind, error=str(exc))
        return None

    questions = parse_questions(payload, limit=MAX_QUESTIONS[kind])
    if not questions:
        return None
    assessment = Assessment(
        owner_id=owner_id,
        journey_id=journey.id,
        session_id=session_id,
        kind=kind,
        status="open",
        title=_text(payload.get("title"))[:200] or journey.subject,
        questions=questions,
        responses=[],
        results={},
    )
    db.add(assessment)
    await db.flush()
    log.info("professor.assessment_created", kind=kind, questions=len(questions))
    return assessment


def parse_questions(payload: dict[str, Any], *, limit: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    raw = payload.get("questions")
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        kind = _text(item.get("type"))
        prompt = _text(item.get("prompt"))[:800]
        concept = _text(item.get("concept"))[:200]
        if not prompt or not concept:
            continue
        question: dict[str, Any] = {"type": kind, "prompt": prompt, "concept": concept}
        explanation = _text(item.get("explanation"))[:600]
        if explanation:
            question["explanation"] = explanation
        if kind == "mcq":
            options = _strings(item.get("options"))[:5]
            index = item.get("correct_index")
            if (
                len(options) < 2
                or not isinstance(index, int)
                or not 0 <= index < len(options)
            ):
                continue
            question.update(options=options, correct_index=index)
        elif kind == "true_false":
            if not isinstance(item.get("answer"), bool):
                continue
            question["answer"] = item["answer"]
        elif kind in ("short", "fill_blank"):
            accepted = _strings(item.get("accepted"))
            if not accepted:
                continue
            question["accepted"] = accepted
        elif kind == "ordering":
            order = _strings(item.get("order"))
            if len(order) < 3:
                continue
            question["order"] = order
        elif kind == "open":
            rubric = _strings(item.get("rubric"))
            if not rubric:
                continue
            question["rubric"] = rubric
        else:
            continue
        out.append(question)
        if len(out) >= limit:
            break
    return out


def public_view(assessment: Assessment) -> dict[str, Any]:
    """The paper without its answers. `ordering` shows the items shuffled."""
    questions = []
    for index, q in enumerate(assessment.questions):
        item = {k: v for k, v in q.items() if k not in PRIVATE}
        item["index"] = index
        if q["type"] == "ordering":
            items = list(q["order"])
            # Deterministic shuffle: sorted by text, never the answer's order.
            item["items"] = sorted(items, key=str.lower)
        questions.append(item)
    return {
        "id": str(assessment.id),
        "kind": assessment.kind,
        "status": assessment.status,
        "title": assessment.title,
        "questions": questions,
        "score": assessment.score,
        "results": assessment.results if assessment.status == "submitted" else {},
    }


def grade(question: dict[str, Any], response: Any) -> tuple[float, bool]:
    """A closed question's score, deterministically. Open questions return
    (-1, False) to say "ask the grader"."""
    kind = question["type"]
    if kind == "mcq":
        return (1.0, True) if response == question["correct_index"] else (0.0, False)
    if kind == "true_false":
        return (1.0, True) if response == question["answer"] else (0.0, False)
    if kind in ("short", "fill_blank"):
        qtype = QuestionType.FILL_BLANK
        if not is_gradeable_locally(qtype):
            return (0.0, False)
        result = grade_deterministic(
            qtype, {"accepted": question["accepted"]}, {"text": str(response or "")}
        )
        return (result.score, result.is_correct)
    if kind == "ordering":
        result = grade_deterministic(
            QuestionType.ORDERING,
            {"order": question["order"]},
            {"order": response if isinstance(response, list) else []},
        )
        return (result.score, result.is_correct)
    return (-1.0, False)


async def submit(
    db: AsyncSession,
    *,
    owner_id: uuid.UUID,
    journey: LearningJourney,
    assessment_id: uuid.UUID,
    responses: list[Any],
    gateway: AIGateway | None,
    model: str | None,
    now: datetime | None = None,
) -> Assessment:
    now = now or utcnow()
    assessment = await db.scalar(
        select(Assessment).where(
            Assessment.id == assessment_id,
            Assessment.owner_id == owner_id,
            Assessment.journey_id == journey.id,
        )
    )
    if assessment is None:
        raise NotFound("Assessment not found")
    if assessment.status == "submitted":
        raise Conflict("This assessment was already handed in.")

    student = StudentModel(db, owner_id, journey)
    per_question: list[dict[str, Any]] = []
    by_concept: dict[str, list[float]] = {}
    for index, question in enumerate(assessment.questions):
        response = responses[index] if index < len(responses) else None
        score, correct = grade(question, response)
        feedback = ""
        if score < 0:
            score, feedback = await _grade_open(question, response, gateway, model)
            correct = score >= 0.7
        per_question.append(
            {
                "index": index,
                "concept": question["concept"],
                "score": round(score, 3),
                "correct": correct,
                "feedback": feedback,
                "explanation": question.get("explanation", ""),
                "expected": _expected(question),
            }
        )
        by_concept.setdefault(question["concept"], []).append(score)
        await student.record(
            question["concept"],
            kind="assessment",
            score=score,
            detail={"assessment_id": str(assessment.id), "question": index},
            now=now,
        )

    concepts = [
        {
            "name": name,
            "score": round(sum(scores) / len(scores), 3),
            "verdict": "weak" if sum(scores) / len(scores) < WEAK_BELOW else "ok",
        }
        for name, scores in by_concept.items()
    ]
    weak = [c["name"] for c in concepts if c["verdict"] == "weak"]
    total = sum(q["score"] for q in per_question) / max(len(per_question), 1)

    assessment.responses = list(responses)
    assessment.results = {"questions": per_question, "concepts": concepts, "weak": weak}
    assessment.score = round(total, 3)
    assessment.status = "submitted"
    assessment.submitted_at = now
    journey.pending_remediation = weak
    journey.checkpoints += 1 if assessment.kind == "checkpoint" else 0
    if assessment.kind == "checkpoint":
        journey.last_checkpoint_at = now
        journey.concepts_since_checkpoint = 0
    await db.flush()
    log.info(
        "professor.assessment_submitted",
        kind=assessment.kind,
        score=assessment.score,
        weak=len(weak),
    )
    return assessment


async def _grade_open(
    question: dict[str, Any], response: Any, gateway: AIGateway | None, model: str | None
) -> tuple[float, str]:
    answer = str(response or "").strip()
    if not answer:
        return 0.0, ""
    if gateway is None:
        return 0.5, ""
    prompt = load("grade.open")
    try:
        payload = await gateway.structured(
            StructuredRequest(
                messages=[
                    Message(role=Role.SYSTEM, content=prompt.body),
                    Message(
                        role=Role.USER,
                        content=(
                            f"<QUESTION>\n{question['prompt']}\n</QUESTION>\n"
                            f"<RUBRIC>\n- "
                            + "\n- ".join(question["rubric"])
                            + "\n</RUBRIC>\n"
                            f"<ANSWER>\n{answer[:4000]}\n</ANSWER>"
                        ),
                    ),
                ],
                json_schema={
                    "type": "object",
                    "properties": {
                        "score": {"type": "number", "minimum": 0, "maximum": 1},
                        "feedback": {"type": "string"},
                    },
                    "required": ["score", "feedback"],
                },
                task=TaskClass.GRADE_OPEN_ANSWER,
                model=model,
                metadata={"feature": "professor.grade"},
            )
        )
        score = float(payload.get("score", 0.0))
        return max(0.0, min(1.0, score)), _text(payload.get("feedback"))[:400]
    except (ProviderError, TypeError, ValueError) as exc:
        log.warning("professor.grade_open_failed", error=str(exc))
        # Ungradeable is not wrong: partial credit, and the professor reads
        # the answer itself in the correction turn.
        return 0.5, ""


def _expected(question: dict[str, Any]) -> Any:
    kind = question["type"]
    if kind == "mcq":
        return question["options"][question["correct_index"]]
    if kind == "true_false":
        return question["answer"]
    if kind in ("short", "fill_blank"):
        return question["accepted"][0]
    if kind == "ordering":
        return question["order"]
    return None


def render_results(assessment: Assessment) -> str:
    """The results for the correction turn's prompt."""
    results = assessment.results or {}
    lines = [
        f"Assessment '{assessment.title}' ({assessment.kind}): "
        f"score {round((assessment.score or 0.0) * 100)}%."
    ]
    for q in results.get("questions", []):
        verdict = "right" if q["correct"] else "wrong"
        lines.append(
            f"- Q{q['index'] + 1} on {q['concept']}: {verdict} (score {q['score']})"
            + (
                f"; expected: {q['expected']}"
                if not q["correct"] and q["expected"]
                else ""
            )
            + (f"; grader: {q['feedback']}" if q.get("feedback") else "")
        )
    if results.get("weak"):
        lines.append("Weak concepts to correct first: " + ", ".join(results["weak"]))
    return "\n".join(lines)


def _strings(value: Any) -> list[str]:
    return [
        v.strip()[:300]
        for v in (value if isinstance(value, list) else [])
        if isinstance(v, str) and v.strip()
    ]


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""
