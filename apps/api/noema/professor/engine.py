"""One turn of the Professor, composed.

`ProfessorEngine.prepare` does everything that happens before a token is
streamed: finds or starts the journey (goal → curriculum), records the
learning event the client sent, reads the signal, decides the move, runs the
move's pre-work (cards written, a checkpoint prepared), and assembles the
prompt under a token budget from *stored* state — the transcript the client
sent is not forwarded; the server's own turns are.

`ProfessorEngine.stream` streams the reply through three filters (PEDAGOGY
record, learning blocks, citations), emits structured events as it goes, and
after `done` writes the turn down, folds the record into the student model,
writes cards for what landed, and compacts the context when it has grown —
each on a session of its own, each optional in failure, so a lesson that was
taught is never lost to a step that could not run.

The system prompt is the same text on every turn of every lesson (persona +
mode + principles), so a provider's prompt cache keeps it warm; everything
that changes per turn rides in one directive message at the end.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Sequence
from dataclasses import asdict, dataclass, field, replace
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.config import Settings
from noema.core.errors import QuotaExceeded
from noema.core.logging import get_logger
from noema.db.base import utcnow
from noema.db.models import (
    Assessment,
    Card,
    ConceptState,
    JourneyStatus,
    LearningJourney,
    ModelTier,
    TeachingSession,
    TeachingTurn,
    TurnRole,
    User,
)
from noema.db.repository import OwnedRepository
from noema.knowledge.resolution import normalize_name
from noema.prompts import Prompt, load
from noema.providers.base import ChatRequest, Message, ProviderError, Role, TaskClass
from noema.providers.gateway import AIGateway
from noema.retrieval.grounding import (
    Citation,
    CitationFilter,
    citations_for,
    used_citations,
)
from noema.retrieval.search import Retrieved, retrieve
from noema.retrieval.search import has_material as notebook_has_material
from noema.services.credentials import CredentialService
from noema.services.professor import BuildProvider, TieredCall, tiered_gateway
from noema.services.teaching_evidence import record_conversational_evidence
from noema.services.teaching_policy import SidecarFilter, persona, principles
from noema.services.teaching_session import TeachingSessions, render_session
from noema.services.usage import UsageWriter

from . import assessment as assessments
from . import curriculum, flashcards
from .blocks import Block, BlockFilter
from .budget import ContextReport, TokenBudget, estimate, fit_transcript
from .checkpoint import checkpoint_due, run_checkpoint
from .intent import parse_goal
from .memory import (
    ContextCompactor,
    active_turns,
    render_handoff,
    render_memory,
    should_compact,
)
from .moves import Decision, Move, Signal, Situation, classify, decide, read_signal
from .student import REVIEW_AFTER, StudentModel

log = get_logger(__name__)

__all__ = ["LearningEvent", "Prepared", "ProfessorEngine", "journey_public", "sse"]

#: Verdicts the PEDAGOGY record may carry, as scores for the student model.
VERDICT_SCORES = {"understood": 1.0, "partial": 0.5, "misunderstood": 0.0}
#: Moves that count as "explaining without asking".
TEACHING_MOVES = frozenset(
    {Move.TEACH, Move.EXAMPLE, Move.ADVANCE, Move.SUMMARIZE, Move.MOTIVATE}
)


def sse(event: str, data: dict[str, Any]) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()


@dataclass(frozen=True, slots=True)
class LearningEvent:
    """What the interface reports happened since the last turn."""

    kind: str
    concept: str = ""
    correct: bool | None = None
    score: float | None = None
    question: str = ""
    chosen: str = ""
    assessment_id: uuid.UUID | None = None


@dataclass
class Prepared:
    journey: LearningJourney
    decision: Decision
    situation: Situation
    request: ChatRequest
    report: ContextReport
    system: Prompt
    call: TieredCall
    economy: TieredCall
    grounded: bool
    citations: list[Citation]
    cited: list[Retrieved]
    focus: str
    pre_events: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    assessment: Assessment | None = None
    cards: list[Card] = field(default_factory=list)


def journey_public(
    journey: LearningJourney, states: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    return {
        "id": str(journey.id),
        "subject": journey.subject,
        "objective": journey.objective,
        "level": journey.inferred_level,
        "status": journey.status,
        "plan": curriculum.public_plan(journey.plan),
        "current": {
            "module": journey.current_module,
            "lesson": journey.current_lesson,
            "concept": journey.current_concept,
        },
        "checkpoints": journey.checkpoints,
        "concepts": states or [],
    }


class ProfessorEngine:
    def __init__(
        self,
        db: AsyncSession,
        *,
        user: User,
        settings: Settings,
        gateway: AIGateway,
        credentials: CredentialService | None,
        build_provider: BuildProvider,
    ) -> None:
        self.db = db
        self.user = user
        self.settings = settings
        self.gateway = gateway
        self.credentials = credentials
        self.build_provider = build_provider
        self.budget = TokenBudget(transcript=settings.noema_professor_transcript_budget)

    # ── before the stream ─────────────────────────────────────────────────

    async def _tier(self, tier: ModelTier) -> TieredCall:
        return await tiered_gateway(
            tier,
            db=self.db,
            default_gateway=self.gateway,
            build_provider=self.build_provider,
            settings=self.settings,
            credentials=self.credentials,
        )

    async def prepare(
        self,
        *,
        session: TeachingSession,
        question: str,
        created: bool,
        notebook_id: uuid.UUID | None,
        grounded_wanted: bool,
        event: LearningEvent | None,
    ) -> Prepared:
        economy = await self._tier(ModelTier.ECONOMY)
        journey = await self._journey_for(session, question, economy)
        student = StudentModel(self.db, self.user.id, journey)
        position = curriculum.Position(journey.current_module, journey.current_lesson)
        lesson_concepts = curriculum.concepts_of_current_lesson(journey.plan, position)
        focus = journey.current_concept or (lesson_concepts[0] if lesson_concepts else "")

        # 1. What the interface says happened, written down before anything is decided.
        results_block = ""
        event_correct: bool | None = None
        if event is not None:
            event_correct = await self._record_event(
                event, journey, session, student, focus
            )
            if event.kind == "assessment" and event.assessment_id is not None:
                submitted = await self.db.scalar(
                    select(Assessment).where(
                        Assessment.id == event.assessment_id,
                        Assessment.owner_id == self.user.id,
                    )
                )
                if submitted is not None and submitted.status == "submitted":
                    results_block = assessments.render_results(submitted)

        # 2. The signal, then the move.
        first_turn = created and session.turn_count <= 1
        signal = read_signal(question)
        awaiting_answer = session.last_move in (
            Move.QUESTION.value,
            Move.QUIZ.value,
            Move.PRACTICE.value,
        )
        if (
            signal is Signal.NEUTRAL
            and event is None
            and not first_turn
            and not awaiting_answer
            and len(question) > 12
        ):
            signal = await classify(
                economy.gateway,
                question,
                model=economy.model,
                context=f"Subject: {journey.subject}. Current concept: {focus}. "
                f"Last move: {session.last_move or 'none'}.",
            )
        review_due, teach_back_due = await self._review_signals(student, focus)
        situation = Situation(
            review_due=review_due,
            teach_back_due=teach_back_due,
            last_move=session.last_move,
            wrong_streak=session.wrong_streak,
            since_check=session.since_check,
            last_strategy=session.strategy or "definition",
            checkpoint_due=checkpoint_due(
                journey,
                last_move=session.last_move,
                every_concepts=self.settings.noema_professor_checkpoint_every_concepts,
                enabled=self.settings.noema_professor_assessments_enabled,
            ),
            remediation=tuple(str(c) for c in journey.pending_remediation)[:4],
            event_kind=event.kind if event else "",
            event_correct=event_correct,
            first_turn=first_turn,
            assessments_enabled=self.settings.noema_professor_assessments_enabled,
        )
        decision = decide(
            signal,
            situation,
            check_after_moves=self.settings.noema_professor_check_after_moves,
        )

        # 3. The move's pre-work.
        prepared_events: list[tuple[str, dict[str, Any]]] = []
        assessment: Assessment | None = None
        cards: list[Card] = []
        turns = await active_turns(self.db, session, owner_id=self.user.id)

        if decision.move is Move.EXAM:
            outcome = await run_checkpoint(
                self.db,
                owner_id=self.user.id,
                journey=journey,
                session=session,
                turns=turns,
                gateway=economy.gateway,
                model=economy.model,
                keep=self.settings.noema_professor_keep_turns,
                fold_after=self.settings.noema_professor_fold_after_summaries,
                with_assessment=True,
                flashcards_enabled=self.settings.noema_professor_flashcards_enabled,
            )
            for name, data in ((e["event"], e["data"]) for e in outcome.events):
                prepared_events.append((name, data))
            if outcome.cards:
                prepared_events.append(("flashcards", _cards_public(outcome.cards)))
            assessment = outcome.assessment
            if assessment is None:
                # No paper could be written: check in conversation instead.
                decision = replace(decision, move=Move.QUIZ, mino="questioning")
            else:
                prepared_events.append(
                    ("checkpoint", assessments.public_view(assessment))
                )
            turns = await active_turns(self.db, session, owner_id=self.user.id)

        elif (
            decision.move is Move.FLASHCARD
            and self.settings.noema_professor_flashcards_enabled
        ):
            concept = focus or journey.subject
            cards = await flashcards.generate_for_concept(
                self.db,
                owner_id=self.user.id,
                journey=journey,
                concept=concept,
                context=_transcript_text(turns[-10:]),
                gateway=economy.gateway,
                model=economy.model,
            )
            if cards:
                prepared_events.append(("flashcards", _cards_public(cards)))
            else:
                decision = replace(decision, move=Move.TEACH, mino="teaching")

        elif decision.move is Move.ADVANCE and decision.signal is Signal.KNOWS:
            plan, next_position = curriculum.skip_lesson(journey.plan, position)
            journey.plan = plan
            if next_position is not None:
                journey.current_module = next_position.module
                journey.current_lesson = next_position.lesson
                new_concepts = curriculum.concepts_of_current_lesson(plan, next_position)
                journey.current_concept = new_concepts[0] if new_concepts else ""
                focus = journey.current_concept
                lesson_concepts = new_concepts
            await self.db.flush()

        # 4. The prompt, under budget, from stored state.
        call = await self._tier(decision.tier)
        results: list[Retrieved] = []
        grounded = notebook_id is not None and grounded_wanted
        has_material = True
        if grounded:
            results = await retrieve(
                self.db,
                question,
                owner_id=self.user.id,
                notebook_id=notebook_id,
                gateway=call.gateway,
                embedding_model=self.settings.noema_embedding_model,
            )
            if not results and notebook_id is not None:
                has_material = await notebook_has_material(
                    self.db, owner_id=self.user.id, notebook_id=notebook_id
                )
        from noema.api.v1.ai import _assemble

        system, context_block, cited = _assemble(
            "explain", grounded, results, has_material
        )
        citations = citations_for(cited)

        system_text = f"{persona().body}\n\n{system.body}\n\n{principles().body}"
        report = ContextReport(system=estimate(system_text))
        messages: list[Message] = [Message(role=Role.SYSTEM, content=system_text)]

        kept, dropped = fit_transcript(turns, self.budget.transcript)
        transcript = _as_messages(kept)
        messages += transcript
        report.transcript = sum(estimate(m.content) for m in transcript)
        report.transcript_turns = len(transcript)
        report.transcript_dropped = dropped
        report.message = estimate(question)

        if context_block:
            messages.append(
                Message(
                    role=Role.USER, content=f"<MATERIALS>\n{context_block}\n</MATERIALS>"
                )
            )
            report.materials = estimate(context_block)

        plan_block = curriculum.render_plan(
            journey.plan,
            curriculum.Position(journey.current_module, journey.current_lesson),
        )
        knowledge_block = await student.snapshot(focus=lesson_concepts)
        memory_block = await render_memory(
            self.db, owner_id=self.user.id, journey=journey, budget=self.budget.memory
        )
        session_block = render_session(session)
        report.student = estimate(knowledge_block) + estimate(plan_block)
        report.memory = estimate(memory_block)
        report.session = estimate(session_block)

        directive = self._directive(
            decision,
            journey=journey,
            focus=focus,
            plan_block=plan_block,
            knowledge_block=knowledge_block,
            memory_block=memory_block,
            session_block=session_block,
            results_block=results_block,
            cards=cards,
            assessment=assessment,
            compacted=session.compacted_through > 0,
        )
        messages.append(Message(role=Role.USER, content=directive))
        report.extras = {
            "directive": estimate(directive),
            "move": decision.move.value,
            "signal": decision.signal.value,
            "strategy": decision.strategy,
            "tier": decision.tier.value,
        }

        request = ChatRequest(
            messages=messages,
            task=TaskClass.TUTOR_CHAT,
            model=call.model,
            max_tokens=self.budget.response + 500,  # room for the PEDAGOGY record
            metadata={
                "feature": f"professor.{decision.move.value}",
                "session_id": str(session.id),
                "journey_id": str(journey.id),
                "move": decision.move.value,
                "strategy": decision.strategy,
                "grounded": grounded,
                "retrieved": len(cited),
                "prompt_version": system.version,
            },
        )
        session.last_move = decision.move.value
        session.strategy = decision.strategy[:48]
        journey.last_active_at = utcnow()
        # Once asked, not asked again for this concept; once reviewed, not
        # nagged about — notes are the cheapest durable flag the state has.
        if decision.extras.get("teach_back") and focus:
            state = await student.ensure(focus)
            state.notes = [*state.notes, "teach_back_asked"][-4:]
        if decision.move is Move.REVIEW:
            for name in decision.remediation:
                state = await student.ensure(name)
                state.notes = [*state.notes, "reviewed"][-4:]
        await self.db.flush()

        return Prepared(
            journey=journey,
            decision=decision,
            situation=situation,
            request=request,
            report=report,
            system=system,
            call=call,
            economy=economy,
            grounded=grounded,
            citations=citations,
            cited=cited,
            focus=focus,
            pre_events=prepared_events,
            assessment=assessment,
            cards=cards,
        )

    async def _journey_for(
        self, session: TeachingSession, question: str, economy: TieredCall
    ) -> LearningJourney:
        journeys = OwnedRepository(self.db, LearningJourney, self.user.id)
        if session.journey_id is not None:
            return await journeys.get(session.journey_id)

        goal = await parse_goal(
            economy.gateway, session.learning_goal or question, model=economy.model
        )
        # The same subject, already under way: continue it rather than start
        # a twin. Only active journeys, only the same notebook (or none).
        existing = await self.db.scalar(
            select(LearningJourney)
            .where(
                LearningJourney.owner_id == self.user.id,
                LearningJourney.status == JourneyStatus.ACTIVE.value,
                LearningJourney.notebook_id.is_(session.notebook_id)
                if session.notebook_id is None
                else LearningJourney.notebook_id == session.notebook_id,
            )
            .order_by(LearningJourney.last_active_at.desc().nulls_last())
            .limit(20)
        )
        journey: LearningJourney | None = None
        if existing is not None and normalize_name(existing.subject) == normalize_name(
            goal.subject
        ):
            journey = existing
        if journey is None:
            plan = await curriculum.build_plan(economy.gateway, goal, model=economy.model)
            first = curriculum.concepts_of_current_lesson(plan, curriculum.Position(0, 0))
            journey = await journeys.create(
                notebook_id=session.notebook_id,
                goal=(session.learning_goal or question).strip()[:4000],
                subject=goal.subject,
                objective=goal.objective,
                inferred_level=goal.inferred_level,
                desired_depth=goal.desired_depth,
                prerequisites=list(goal.prerequisites),
                plan=plan,
                current_module=0,
                current_lesson=0,
                current_concept=first[0] if first else goal.subject,
                profile={"language": goal.language} if goal.language else {},
                status=JourneyStatus.ACTIVE.value,
                concepts_since_checkpoint=0,
                checkpoints=0,
                pending_remediation=[],
                last_active_at=utcnow(),
            )
            log.info(
                "professor.journey_started",
                journey_id=str(journey.id),
                subject=goal.subject,
                parsed=goal.parsed,
                generated=plan.get("generated", False),
            )
        session.journey_id = journey.id
        if not session.subject:
            session.subject = journey.subject[:200]
        await self.db.flush()
        return journey

    async def _review_signals(
        self, student: StudentModel, focus: str
    ) -> tuple[tuple[str, ...], bool]:
        """What the knowledge state asks of the router.

        Review: concepts once mastered whose last showing is older than
        `REVIEW_AFTER` (computed at read time — the stored stage does not
        change by itself). Teach-back: the current concept has two strong
        showings and has not been explained back yet.
        """
        now = utcnow()
        due: list[str] = []
        teach_back = False
        for state in await student.states():
            stale = (
                state.state
                in (ConceptState.MASTERED.value, ConceptState.NEEDS_REVIEW.value)
                and state.last_evidence_at is not None
                and now - state.last_evidence_at > REVIEW_AFTER
            )
            if stale and "reviewed" not in state.notes:
                due.append(state.name)
            if (
                focus
                and state.normalized_name == normalize_name(focus)
                and state.strong_evidence_count >= 2
                and state.score >= 0.6
                and "teach_back_asked" not in state.notes
            ):
                teach_back = True
        return tuple(due[:3]), teach_back

    async def _record_event(
        self,
        event: LearningEvent,
        journey: LearningJourney,
        session: TeachingSession,
        student: StudentModel,
        focus: str,
    ) -> bool | None:
        """The interface's report of a quiz, a check or a flashcard, counted.

        Returns the correctness the router should see (None when the event
        carries no verdict — an open answer is graded by the reply itself).
        """
        concept = event.concept or focus or journey.subject
        if event.kind == "quiz" and event.correct is not None:
            await student.record(
                concept,
                kind="quiz",
                score=1.0 if event.correct else 0.0,
                detail={"question": event.question[:300], "chosen": event.chosen[:200]},
            )
            session.wrong_streak = 0 if event.correct else session.wrong_streak + 1
            session.since_check = 0
            await self.db.flush()
            return event.correct
        if event.kind == "assessment":
            session.since_check = 0
            await self.db.flush()
            return None
        if event.kind == "check":
            session.since_check = 0
            await self.db.flush()
        return None

    def _directive(
        self,
        decision: Decision,
        *,
        journey: LearningJourney,
        focus: str,
        plan_block: str,
        knowledge_block: str,
        memory_block: str,
        session_block: str,
        results_block: str,
        cards: Sequence[Card],
        assessment: Assessment | None,
        compacted: bool,
    ) -> str:
        """Everything that changes per turn, in one message at the end."""
        parts: list[str] = ["<TURN_DIRECTIVE>"]
        parts.append(load(f"move.{decision.move.value}").body)
        parts.append(f"Strategy for this turn: {decision.strategy}.")
        if focus:
            parts.append(f"Current concept: {focus}.")
        if decision.signal is Signal.ANSWERING:
            parts.append(
                "The learner's message is their answer to your last question. Grade it "
                "exactly (right / partly right / wrong), say why in one or two lines, "
                "then continue."
            )
        if decision.remediation and decision.move is Move.REVIEW:
            parts.append(
                "Concepts to bring back (retrieve, do not re-explain): "
                + ", ".join(decision.remediation)
                + "."
            )
        elif decision.remediation:
            parts.append("Correct these first: " + ", ".join(decision.remediation) + ".")
        if decision.extras.get("teach_back"):
            parts.append(
                'Ask for a teach-back: a `noema:check` block with "kind": "teach_back" '
                "on the current concept — have them explain it as if to a beginner."
            )
        if results_block:
            parts.append(f"<ASSESSMENT_RESULTS>\n{results_block}\n</ASSESSMENT_RESULTS>")
        if cards:
            parts.append(
                f"Cards saved ({len(cards)}): "
                + " | ".join(c.front_md[:80] for c in cards)
            )
        if assessment is not None:
            parts.append(
                f"Checkpoint prepared: '{assessment.title}', {len(assessment.questions)} "
                "questions on: "
                + ", ".join(sorted({q["concept"] for q in assessment.questions}))
            )
        if decision.require_check:
            parts.append("End this turn with a question the learner can answer.")
        parts.append("</TURN_DIRECTIVE>")

        if compacted:
            parts.append(
                "<CONTEXT>\n"
                + render_handoff(
                    journey=journey,
                    plan_block=plan_block,
                    knowledge_block=knowledge_block,
                    memory_block=memory_block,
                    session_block=session_block,
                )
                + "\n</CONTEXT>"
            )
        else:
            if plan_block:
                parts.append(f"<COURSE>\n{plan_block}\n</COURSE>")
            if knowledge_block:
                parts.append(f"<KNOWLEDGE_STATE>\n{knowledge_block}\n</KNOWLEDGE_STATE>")
            if memory_block:
                parts.append(f"<LEARNING_MEMORY>\n{memory_block}\n</LEARNING_MEMORY>")
            if session_block:
                parts.append(f"<ACTIVE_SESSION>\n{session_block}\n</ACTIVE_SESSION>")
        return "\n\n".join(parts)

    # ── the stream ─────────────────────────────────────────────────────────

    async def stream(
        self, prepared: Prepared, *, session: TeachingSession, question: str
    ) -> AsyncIterator[bytes]:
        decision = prepared.decision
        journey = prepared.journey
        student = StudentModel(self.db, self.user.id, journey)
        yield sse("journey", journey_public(journey, await student.public()))
        yield sse(
            "move",
            {
                "move": decision.move.value,
                "strategy": decision.strategy,
                "signal": decision.signal.value,
                "reason": decision.reason,
            },
        )
        yield sse("intent", {"intent": decision.intent})
        yield sse("mino", {"state": decision.mino})
        for name, data in prepared.pre_events:
            yield sse(name, data)
        if prepared.citations:
            yield sse("sources", {"citations": [asdict(c) for c in prepared.citations]})

        citation_filter = CitationFilter.for_results(prepared.cited)
        sidecar = SidecarFilter()
        blocks = BlockFilter()
        shown: list[str] = []
        emitted: list[Block] = []

        def _pass(text: str) -> tuple[str, list[Block]]:
            visible = sidecar.feed(text)
            if not visible:
                return "", []
            prose, found = blocks.feed(visible)
            safe = citation_filter.feed(prose) if prose else ""
            return safe, found

        try:
            async for event in prepared.call.gateway.stream(prepared.request):
                if event.delta:
                    safe, found = _pass(event.delta)
                    if safe:
                        shown.append(safe)
                        yield sse("token", {"text": safe})
                    for block in found:
                        emitted.append(block)
                        yield sse(
                            "block",
                            {
                                "tool": block.tool,
                                "data": block.public(),
                                "index": len(emitted) - 1,
                            },
                        )
                        if block.tool in ("quiz", "check"):
                            yield sse("mino", {"state": "questioning"})
                if event.done:
                    held = sidecar.flush()
                    prose, found = blocks.feed(held) if held else ("", [])
                    tail = (
                        citation_filter.feed(prose + blocks.flush())
                        + citation_filter.flush()
                    )
                    if tail:
                        shown.append(tail)
                        yield sse("token", {"text": tail})
                    for block in found:
                        emitted.append(block)
                        yield sse(
                            "block",
                            {
                                "tool": block.tool,
                                "data": block.public(),
                                "index": len(emitted) - 1,
                            },
                        )
                    usage = event.usage
                    yield sse(
                        "done",
                        {
                            "prompt_tokens": usage.prompt_tokens if usage else 0,
                            "completion_tokens": usage.completion_tokens if usage else 0,
                            "cached_tokens": usage.cached_tokens if usage else 0,
                            "grounded": prepared.grounded,
                            "used_citations": [
                                asdict(c)
                                for c in used_citations(
                                    prepared.citations, citation_filter.used
                                )
                            ],
                            "dropped_sentences": len(citation_filter.dropped),
                            "context": prepared.report.as_dict(),
                            "move": decision.move.value,
                        },
                    )
                    async for after in self._after(
                        prepared,
                        session_id=session.id,
                        content="".join(shown),
                        blocks=emitted,
                        pedagogy=sidecar.pedagogy(),
                        question=question,
                    ):
                        yield after
        except ProviderError as exc:
            log.warning("professor.stream_failed", provider=exc.provider, error=str(exc))
            yield sse("error", {"message": str(exc), "provider": exc.provider})
        except QuotaExceeded as exc:
            log.warning(
                "professor.stream_budget_exhausted", task=TaskClass.TUTOR_CHAT.value
            )
            yield sse("error", {"message": exc.detail})

    # ── after the stream ───────────────────────────────────────────────────

    async def _after(
        self,
        prepared: Prepared,
        *,
        session_id: uuid.UUID,
        content: str,
        blocks: Sequence[Block],
        pedagogy: dict[str, Any] | None,
        question: str,
    ) -> AsyncIterator[bytes]:
        """Write the turn, fold the record in, write cards, compact.

        On a session of its own, bound to the request's connection, committed
        explicitly — the pattern `_record_noema_turn` established after three
        writes assumed to land in the request scope did not. Each step is
        wrapped so a failure is logged, not raised into the stream.
        """
        if not content.strip() and not blocks:
            return
        decision = prepared.decision
        owner_id = self.user.id
        events: list[tuple[str, dict[str, Any]]] = []
        try:
            async with AsyncSession(
                bind=self.db.bind,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            ) as db:
                sessions = TeachingSessions(db, owner_id)
                session = await sessions.sessions.get(session_id)
                journey = await OwnedRepository(db, LearningJourney, owner_id).get(
                    prepared.journey.id
                )
                student = StudentModel(db, owner_id, journey)

                record = {
                    "move": decision.move.value,
                    "signal": decision.signal.value,
                    "strategy": decision.strategy,
                    "reason": decision.reason,
                    "context": prepared.report.as_dict(),
                }
                if pedagogy:
                    record.update(
                        {
                            k: pedagogy[k]
                            for k in ("situation", "next_action")
                            if k in pedagogy
                        }
                    )
                turn = await sessions.record_noema(
                    session,
                    content,
                    intent=decision.intent,
                    decision=record,
                    pedagogy=pedagogy,
                    blocks=[b.as_record() for b in blocks] or None,
                )

                # Bookkeeping the router reads next turn.
                asked = any(b.tool in ("quiz", "check") for b in blocks)
                if asked:
                    session.last_move = Move.QUESTION.value
                    session.since_check = 0
                elif decision.move in TEACHING_MOVES or decision.move is Move.CORRECT:
                    session.since_check += 1
                else:
                    session.since_check = 0

                # The PEDAGOGY record into the journey and the student model.
                if pedagogy:
                    await self._apply_pedagogy(
                        db, journey, session, student, pedagogy, turn, question
                    )
                    if pedagogy.get("mastery_evidence"):
                        state = await student.get(pedagogy["mastery_evidence"]["concept"])
                        if state is not None:
                            events.append(
                                (
                                    "mastery",
                                    {
                                        "concept": state.name,
                                        "state": state.state,
                                        "evidence": state.evidence_count,
                                    },
                                )
                            )
                elif prepared.focus:
                    await student.mark_introduced([prepared.focus])

                # Cards for a concept that just landed and has none.
                if self.settings.noema_professor_flashcards_enabled and pedagogy:
                    made = await self._auto_cards(
                        db, prepared, journey, student, pedagogy, session
                    )
                    if made:
                        events.append(("mino", {"state": "writing"}))
                        events.append(("flashcards", _cards_public(made)))

                # Compaction: technical, size-driven.
                turns = await active_turns(db, session, owner_id=owner_id)
                if should_compact(
                    turns,
                    after_tokens=self.settings.noema_professor_compact_after_tokens,
                    after_turns=self.settings.noema_professor_compact_after_turns,
                    keep=self.settings.noema_professor_keep_turns,
                    boundary=bool(pedagogy and pedagogy.get("next_action") == "move_on"),
                ):
                    compactor = ContextCompactor(
                        db,
                        owner_id=owner_id,
                        journey=journey,
                        session=session,
                        gateway=self._side_gateway(prepared, db),
                        model=prepared.economy.model,
                        keep=self.settings.noema_professor_keep_turns,
                        fold_after=self.settings.noema_professor_fold_after_summaries,
                    )
                    result = await compactor.compact(turns)
                    if result.archived_turns:
                        events.append(
                            (
                                "memory",
                                {
                                    "compacted_turns": result.archived_turns,
                                    "tokens_saved": result.tokens_saved,
                                    "folded": result.folded,
                                },
                            )
                        )

                journey.last_active_at = utcnow()
                await db.commit()
                events.append(
                    ("journey", journey_public(journey, await student.public()))
                )
        except Exception as exc:
            log.warning(
                "professor.after_turn_failed", session_id=str(session_id), error=str(exc)
            )
        for name, data in events:
            yield sse(name, data)
        if events:
            yield sse("mino", {"state": "idle"})

    def _side_gateway(self, prepared: Prepared, db: AsyncSession) -> AIGateway:
        """The economy provider, recording usage on the post-turn session."""
        return AIGateway(
            prepared.economy.gateway.primary,
            retry=prepared.economy.gateway.retry,
            record_usage=UsageWriter(db, self.user.id),
        )

    async def _apply_pedagogy(
        self,
        db: AsyncSession,
        journey: LearningJourney,
        session: TeachingSession,
        student: StudentModel,
        pedagogy: dict[str, Any],
        turn: TeachingTurn,
        question: str,
    ) -> None:
        concept = str(pedagogy.get("current_concept") or "").strip()
        if concept:
            journey.current_concept = concept[:200]
            await student.mark_introduced([concept])
        evidence = pedagogy.get("mastery_evidence")
        if isinstance(evidence, dict):
            score = VERDICT_SCORES.get(str(evidence.get("verdict")))
            name = str(evidence.get("concept", "")).strip()
            if score is not None and name:
                await student.record(
                    name,
                    kind="conversation",
                    score=score,
                    detail={
                        "strength": evidence.get("strength", "weak"),
                        "turn": str(turn.id),
                    },
                    turn_id=turn.id,
                    misconception=str(pedagogy.get("misconception") or "") or None,
                )
                session.wrong_streak = 0 if score >= 0.5 else session.wrong_streak + 1
                # The graph, when it knows the name (unchanged from V2).
                await record_conversational_evidence(
                    db,
                    owner_id=self.user.id,
                    session_id=session.id,
                    pedagogy=pedagogy,
                    learner_text=question,
                )
        resolved = str(pedagogy.get("misconception_resolved") or "").strip()
        if resolved:
            for state in await student.states():
                if resolved in state.misconceptions:
                    await student.resolve_misconception(state.name, resolved)

        # The lesson advances when every concept in it has been shown.
        position = curriculum.Position(journey.current_module, journey.current_lesson)
        concepts = curriculum.concepts_of_current_lesson(journey.plan, position)
        if concepts:
            states = {s.normalized_name: s for s in await student.states()}
            shown = [states.get(normalize_name(c)) for c in concepts]
            if all(
                s is not None and s.evidence_count >= 1 and s.score >= 0.6 for s in shown
            ):
                plan, next_position = curriculum.advance_lesson(journey.plan, position)
                journey.plan = plan
                if next_position is not None:
                    journey.current_module = next_position.module
                    journey.current_lesson = next_position.lesson
                    following = curriculum.concepts_of_current_lesson(plan, next_position)
                    journey.current_concept = following[0] if following else ""
                else:
                    journey.status = JourneyStatus.DONE.value
        await db.flush()

    async def _auto_cards(
        self,
        db: AsyncSession,
        prepared: Prepared,
        journey: LearningJourney,
        student: StudentModel,
        pedagogy: dict[str, Any],
        session: TeachingSession,
    ) -> list[Card]:
        """Cards when a concept was just shown understood and has none."""
        evidence = pedagogy.get("mastery_evidence")
        if not isinstance(evidence, dict):
            return []
        if evidence.get("verdict") != "understood":
            return []
        if evidence.get("strength") == "weak":
            return []
        name = str(evidence.get("concept", "")).strip()
        if not name:
            return []
        state = await student.get(name)
        if state is None or not flashcards.should_card(state, understood=True):
            return []
        turns = await active_turns(db, session, owner_id=self.user.id)
        return await flashcards.generate_for_concept(
            db,
            owner_id=self.user.id,
            journey=journey,
            concept=state.name,
            context=_transcript_text(turns[-8:]),
            gateway=self._side_gateway(prepared, db),
            model=prepared.economy.model,
        )


# ── helpers ────────────────────────────────────────────────────────────────


def _cards_public(cards: Sequence[Card]) -> dict[str, Any]:
    return {
        "cards": [
            {
                "id": str(c.id),
                "front": c.front_md,
                "back": c.back_md,
                "concept": c.concept_name or "",
            }
            for c in cards
        ],
        "count": len(cards),
    }


def _transcript_text(turns: Sequence[TeachingTurn]) -> str:
    return "\n".join(
        f"{'Learner' if t.role is TurnRole.LEARNER else 'Mino'}: {t.content.strip()}"
        for t in turns
    )


def _as_messages(turns: Sequence[TeachingTurn]) -> list[Message]:
    """Stored turns as chat messages: first one a learner's, consecutive
    same-role turns merged — what every provider accepts."""
    out: list[Message] = []
    for turn in turns:
        role = Role.USER if turn.role is TurnRole.LEARNER else Role.ASSISTANT
        if not out and role is Role.ASSISTANT:
            continue
        if out and out[-1].role is role:
            out[-1] = Message(role=role, content=f"{out[-1].content}\n\n{turn.content}")
        else:
            out.append(Message(role=role, content=turn.content))
    return out
