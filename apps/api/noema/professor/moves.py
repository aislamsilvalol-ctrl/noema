"""The Professor Router: what this turn is *for*, decided before the model speaks.

Twelve moves (the brief's list). A move is chosen from three things, in this
order of authority:

1. **What just happened** — a quiz was answered, an assessment was submitted,
   a check was asked last turn. These are facts the code knows; no model is
   asked.
2. **What the learner said** — cheap, language-aware signals ("não entendi",
   "já sei", "me testa", "resume") read from the message itself. A regex is
   not understanding, so these only fire on unambiguous phrasings; anything
   else is classified by an economy-tier structured call, failing safe to
   TEACH.
3. **Where the lesson is** — a checkpoint is due, three teaching moves passed
   without a check, the learner is wrong twice on the same concept, an
   assessment left concepts to correct.

The result is a `Decision`: the move, the strategy to try (the switching
ladder lives here, not in the prompt), the cost tier, and Mino's state — the
last derived from the move, never from the model's words. Everything in this
module is pure; the one model call is behind `classify()`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from noema.core.logging import get_logger
from noema.db.models import ModelTier
from noema.prompts import load
from noema.providers.base import (
    Message,
    ProviderError,
    Role,
    StructuredRequest,
    TaskClass,
)
from noema.providers.gateway import AIGateway

log = get_logger(__name__)

__all__ = [
    "Decision",
    "Move",
    "Signal",
    "Situation",
    "classify",
    "decide",
    "mino_state_for",
    "next_strategy",
    "read_signal",
]


class Move(StrEnum):
    TEACH = "teach"
    QUESTION = "question"
    CORRECT = "correct"
    REVIEW = "review"
    EXAMPLE = "example"
    PRACTICE = "practice"
    FLASHCARD = "flashcard"
    QUIZ = "quiz"
    EXAM = "exam"
    MOTIVATE = "motivate"
    SUMMARIZE = "summarize"
    ADVANCE = "advance"


class Signal(StrEnum):
    """What the learner's message shows, as far as the code can tell."""

    NEUTRAL = "neutral"
    CONFUSED = "confused"
    KNOWS = "knows"
    WANTS_EXAMPLE = "wants_example"
    WANTS_PRACTICE = "wants_practice"
    WANTS_EXAM = "wants_exam"
    WANTS_SUMMARY = "wants_summary"
    WANTS_DEPTH = "wants_depth"
    WANTS_FLASHCARDS = "wants_flashcards"
    ANSWERING = "answering"
    RIGHT = "right"
    WRONG = "wrong"
    OFF_TOPIC = "off_topic"
    TIRED = "tired"


#: The order strategies are tried when one did not land. Each step is a
#: genuinely different way in, which is the whole point of switching.
STRATEGY_LADDER: tuple[str, ...] = (
    "definition",
    "analogy",
    "scenario",
    "worked_example",
    "contrast",
    "prerequisite",
    "socratic",
)

#: Tier per move. Teaching and correcting are where quality is bought;
#: summarising and motivating are not.
MOVE_TIER: dict[Move, ModelTier] = {
    Move.TEACH: ModelTier.STANDARD,
    Move.QUESTION: ModelTier.STANDARD,
    Move.CORRECT: ModelTier.PREMIUM,
    Move.REVIEW: ModelTier.STANDARD,
    Move.EXAMPLE: ModelTier.STANDARD,
    Move.PRACTICE: ModelTier.STANDARD,
    Move.FLASHCARD: ModelTier.ECONOMY,
    Move.QUIZ: ModelTier.STANDARD,
    Move.EXAM: ModelTier.ECONOMY,
    Move.MOTIVATE: ModelTier.ECONOMY,
    Move.SUMMARIZE: ModelTier.STANDARD,
    Move.ADVANCE: ModelTier.STANDARD,
}

#: Mino's state per move. The character shows what the professor is doing;
#: the model's text has no say in it.
MOVE_MINO: dict[Move, str] = {
    Move.TEACH: "teaching",
    Move.QUESTION: "questioning",
    Move.CORRECT: "correcting",
    Move.REVIEW: "reviewing",
    Move.EXAMPLE: "teaching",
    Move.PRACTICE: "questioning",
    Move.FLASHCARD: "writing",
    Move.QUIZ: "questioning",
    Move.EXAM: "exam",
    Move.MOTIVATE: "happy",
    Move.SUMMARIZE: "teaching",
    Move.ADVANCE: "teaching",
}

#: The legacy `intent` label the client already maps to a "thinking…" line.
MOVE_INTENT: dict[Move, str] = {
    Move.TEACH: "explain",
    Move.QUESTION: "quiz_me",
    Move.CORRECT: "explain",
    Move.REVIEW: "explain",
    Move.EXAMPLE: "explain",
    Move.PRACTICE: "quiz_me",
    Move.FLASHCARD: "create_flashcard",
    Move.QUIZ: "quiz_me",
    Move.EXAM: "create_exam",
    Move.MOTIVATE: "explain",
    Move.SUMMARIZE: "summarize",
    Move.ADVANCE: "deepen",
}


@dataclass(frozen=True, slots=True)
class Situation:
    """What the router knows before reading the message."""

    #: The move chosen last turn ("" on a first turn).
    last_move: str = ""
    #: Consecutive wrong showings on the current concept.
    wrong_streak: int = 0
    #: Teaching moves since the learner was last asked to show something.
    since_check: int = 0
    #: The strategy used last on this concept.
    last_strategy: str = "definition"
    #: A checkpoint is due (enough concepts since the last one, at a boundary).
    checkpoint_due: bool = False
    #: Concepts an assessment just found weak.
    remediation: tuple[str, ...] = ()
    #: A structured learning event arrived with the message.
    event_kind: str = ""
    event_correct: bool | None = None
    #: First message of a journey.
    first_turn: bool = False
    #: Whether assessments are switched on for this deployment.
    assessments_enabled: bool = True
    #: Concepts once mastered and not shown for a while (needs_review).
    review_due: tuple[str, ...] = ()
    #: The current concept has enough evidence to be explained back.
    teach_back_due: bool = False


@dataclass(frozen=True, slots=True)
class Decision:
    move: Move
    signal: Signal
    strategy: str
    tier: ModelTier
    mino: str
    #: Why — one short phrase, for the turn record and the logs.
    reason: str
    #: Concepts to correct first, when the move is CORRECT after an assessment.
    remediation: tuple[str, ...] = ()
    #: Whether the reply must end with a check the learner can answer.
    require_check: bool = False
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def intent(self) -> str:
        return MOVE_INTENT[self.move]


# ── Signals from the message ──────────────────────────────────────────────

_PATTERNS: tuple[tuple[Signal, re.Pattern[str]], ...] = (
    (
        Signal.CONFUSED,
        re.compile(
            r"\b(n[aã]o entendi|nao entendi|n[aã]o t[oô] entendendo|confus[oa]|"
            r"i don'?t (get|understand)|didn'?t (get|understand)|not following|"
            r"no entiendo|no lo entiendo|explica de outro jeito|"
            r"explain (it )?differently|de novo)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Signal.KNOWS,
        re.compile(
            r"\b(isso eu j[aá] sei|j[aá] sei|j[aá] conhe[cç]o|eu sei isso|"
            r"i (already )?know (this|that)|already know|ya (lo )?s[eé]|"
            r"pode pular|skip (this|that)|pula essa)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Signal.WANTS_EXAM,
        re.compile(
            r"\b(prova|simulado|exame|exam|test me (properly|for real))\b", re.IGNORECASE
        ),
    ),
    (
        Signal.WANTS_PRACTICE,
        re.compile(
            r"\b(me testa|me teste|quiz|quero praticar|exerc[ií]cio|pratica|"
            r"test me|practice|quiero practicar|pregúntame|pergunta pra mim)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Signal.WANTS_FLASHCARDS,
        re.compile(r"\b(flashcards?|cart[oõ]es|cards?)\b", re.IGNORECASE),
    ),
    (
        Signal.WANTS_SUMMARY,
        re.compile(
            r"\b(resum[ea]|resumo|summar(y|ize|ise)|tl;?dr|recap)\b", re.IGNORECASE
        ),
    ),
    (
        Signal.WANTS_EXAMPLE,
        re.compile(
            r"\b(exemplo|d[aá] um exemplo|example|ejemplo|na pr[aá]tica)\b", re.IGNORECASE
        ),
    ),
    (
        Signal.WANTS_DEPTH,
        re.compile(
            r"\b(aprofund|mais a fundo|mais detalhe|vai al[eé]m|go deeper|"
            r"more (depth|detail)|profundiza|deepen)",
            re.IGNORECASE,
        ),
    ),
    (
        Signal.TIRED,
        re.compile(
            r"\b(cansad[oa]|t[oô] cansado|desist|chega por hoje|i'?m tired|"
            r"give up|enough for today)\b",
            re.IGNORECASE,
        ),
    ),
)


def read_signal(message: str) -> Signal:
    """The signal an unambiguous message carries, or NEUTRAL.

    Order matters: "não entendi o exemplo" is confusion, not a request for an
    example, so CONFUSED is tested first; "me testa numa prova" is an exam,
    so EXAM precedes PRACTICE.
    """
    text = " ".join(message.split())
    for signal, pattern in _PATTERNS:
        if pattern.search(text):
            return signal
    return Signal.NEUTRAL


# ── Strategy switching ────────────────────────────────────────────────────


def next_strategy(current: str) -> str:
    """The next rung after `current`; wraps to the analogy, never back to the
    definition that already failed."""
    if current not in STRATEGY_LADDER:
        return "analogy"
    index = STRATEGY_LADDER.index(current)
    following = STRATEGY_LADDER[index + 1 :] or STRATEGY_LADDER[1:2]
    return following[0]


# ── The decision ──────────────────────────────────────────────────────────


def decide(
    signal: Signal,
    situation: Situation,
    *,
    check_after_moves: int = 3,
) -> Decision:
    """Choose the move. Pure; every rule is one `if` a reader can argue with."""
    s = situation

    # 1. Facts about what just happened outrank anything the message says.
    if s.event_kind == "assessment":
        if s.remediation:
            return _decision(
                Move.CORRECT,
                signal,
                next_strategy(s.last_strategy),
                "an assessment left concepts to correct",
                remediation=s.remediation,
            )
        return _decision(Move.ADVANCE, Signal.RIGHT, s.last_strategy, "assessment passed")

    if s.event_kind in ("quiz", "check", "flashcard") and s.event_correct is not None:
        if s.event_correct:
            return _decision(
                Move.ADVANCE,
                Signal.RIGHT,
                s.last_strategy,
                "the check landed — confirm briefly and raise the level",
            )
        strategy = next_strategy(s.last_strategy)
        if s.wrong_streak >= 2:
            return _decision(
                Move.CORRECT,
                Signal.WRONG,
                strategy,
                "wrong again on the same concept — step back to the prerequisite",
                extras={"concerned": True},
            )
        return _decision(
            Move.CORRECT, Signal.WRONG, strategy, "wrong — name the misconception, switch"
        )

    if s.last_move in (Move.QUESTION.value, Move.QUIZ.value, Move.PRACTICE.value) and (
        signal is Signal.NEUTRAL
    ):
        # A question was asked; a message that is not a request is an answer.
        return _decision(
            Move.CORRECT,
            Signal.ANSWERING,
            s.last_strategy,
            "grading the answer to last turn's question",
            require_check=False,
        )

    # 2. What the learner asked for, when they asked plainly.
    if signal is Signal.CONFUSED:
        strategy = next_strategy(s.last_strategy)
        extras = {"concerned": s.wrong_streak >= 2}
        return _decision(
            Move.CORRECT, signal, strategy, "lost — a different way in", extras=extras
        )
    if signal is Signal.KNOWS:
        return _decision(
            Move.ADVANCE, signal, s.last_strategy, "already knows — skip ahead"
        )
    if signal is Signal.WANTS_EXAM:
        if s.assessments_enabled:
            return _decision(Move.EXAM, signal, s.last_strategy, "asked for an exam")
        return _decision(Move.QUIZ, signal, s.last_strategy, "asked for an exam (quiz)")
    if signal is Signal.WANTS_PRACTICE:
        return _decision(Move.QUIZ, signal, s.last_strategy, "asked to be tested")
    if signal is Signal.WANTS_FLASHCARDS:
        return _decision(Move.FLASHCARD, signal, s.last_strategy, "asked for cards")
    if signal is Signal.WANTS_SUMMARY:
        return _decision(Move.SUMMARIZE, signal, "summary", "asked for a summary")
    if signal is Signal.WANTS_EXAMPLE:
        return _decision(Move.EXAMPLE, signal, "worked_example", "asked for an example")
    if signal is Signal.WANTS_DEPTH:
        return _decision(Move.ADVANCE, signal, s.last_strategy, "asked to go deeper")
    if signal is Signal.TIRED:
        return _decision(
            Move.MOTIVATE, signal, "summary", "tired — close the loop kindly"
        )

    # 3. Where the lesson is.
    if s.remediation and s.last_move != Move.CORRECT.value:
        return _decision(
            Move.CORRECT,
            signal,
            next_strategy(s.last_strategy),
            "weak concepts still open from the last assessment",
            remediation=s.remediation,
        )
    if s.checkpoint_due and s.assessments_enabled and s.last_move != Move.EXAM.value:
        return _decision(Move.EXAM, signal, s.last_strategy, "checkpoint due")
    if s.first_turn:
        return _decision(
            Move.TEACH,
            signal,
            "definition",
            "first contact — one idea, one example, then find out where they are",
            require_check=True,
        )
    if s.review_due and s.last_move not in (Move.REVIEW.value, Move.CORRECT.value):
        return _decision(
            Move.REVIEW,
            signal,
            s.last_strategy,
            "a mastered concept has gone quiet — retrieve it before moving on",
            remediation=s.review_due,
            require_check=True,
        )
    if s.since_check >= check_after_moves:
        if s.teach_back_due:
            return _decision(
                Move.QUESTION,
                signal,
                s.last_strategy,
                "the concept has landed twice — have them teach it back",
                require_check=True,
                extras={"teach_back": True},
            )
        return _decision(
            Move.QUESTION,
            signal,
            s.last_strategy,
            "several explanations without a check",
            require_check=True,
        )
    return _decision(Move.TEACH, signal, s.last_strategy, "continue the lesson")


def _decision(
    move: Move,
    signal: Signal,
    strategy: str,
    reason: str,
    *,
    remediation: tuple[str, ...] = (),
    require_check: bool = False,
    extras: dict[str, Any] | None = None,
) -> Decision:
    extras = extras or {}
    return Decision(
        move=move,
        signal=signal,
        strategy=strategy,
        tier=MOVE_TIER[move],
        mino=mino_state_for(move, concerned=bool(extras.get("concerned"))),
        reason=reason,
        remediation=remediation,
        require_check=require_check,
        extras=extras,
    )


def mino_state_for(move: Move, *, concerned: bool = False) -> str:
    if concerned and move is Move.CORRECT:
        return "concerned"
    return MOVE_MINO[move]


# ── The one model call ────────────────────────────────────────────────────

ROUTE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "signal": {"type": "string", "enum": [s.value for s in Signal]},
    },
    "required": ["signal"],
}


async def classify(
    gateway: AIGateway, message: str, *, model: str | None, context: str = ""
) -> Signal:
    """Read the signal of a message the patterns could not settle.

    Economy tier, one enum out. Any failure is NEUTRAL — the lesson simply
    continues, which was the right answer before this call existed.
    """
    prompt = load("professor.route")
    user = f"<CONTEXT>\n{context}\n</CONTEXT>\n\n{message}" if context else message
    try:
        payload = await gateway.structured(
            StructuredRequest(
                messages=[
                    Message(role=Role.SYSTEM, content=prompt.body),
                    Message(role=Role.USER, content=user),
                ],
                json_schema=ROUTE_SCHEMA,
                task=TaskClass.CLASSIFY_INTENT,
                model=model,
                metadata={"feature": "professor.route"},
            )
        )
        return Signal(str(payload["signal"]))
    except (ProviderError, KeyError, ValueError) as exc:
        log.warning("professor.route_failed", error=str(exc))
        return Signal.NEUTRAL
