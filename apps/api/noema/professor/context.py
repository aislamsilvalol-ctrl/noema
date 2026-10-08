"""What the decision layer hands the tutor, as one object.

`prepare()` decides the move and gathers the state the tutor must see; this
module carries those parts and renders them into the single user message that
ends the prompt. Rendering is the only thing it does — the parts are built
elsewhere, and the text is the same as when the engine concatenated in place.

Of the fields the brief names (§230), these ride here under the names the
engine already uses: concept (`concept`), recommended strategy
(`decision.strategy`), recent errors / weak concepts (`decision.remediation`),
mastery and confidence (inside `knowledge_block`, rendered per concept by
`StudentModel.snapshot`). Three have no source in the engine yet and are
deliberately absent rather than faked: recommended difficulty, max new
concepts (only Focus mode has one, and it rides inside `focus_block`), and
hint policy.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from noema.db.models import Assessment, Card, LearningJourney
from noema.prompts import load

from .language import LANGUAGE_NAMES
from .memory import render_handoff
from .moves import STRATEGY_NOTES, Decision, Move, Signal

__all__ = ["MOVE_PROMPT_VERSIONS", "TeachingContext"]

#: Moves that explain something: these are told what is already defined.
_BUILDS_ON = frozenset(
    {Move.TEACH, Move.ADVANCE, Move.EXAMPLE, Move.ANSWER, Move.QUESTION}
)

#: The live version of each move's prompt. A prompt change is a new file
#: (`move.<name>.v<n>.md`) and a new number here, so the old text stays in
#: the tree and a response can be traced to the words that produced it.
MOVE_PROMPT_VERSIONS: dict[str, int] = {"correct": 3, "answer": 4}


def language_directive(journey: LearningJourney, reply_in: str = "") -> str:
    """Which language to answer in. Without it an English question, in an
    account whose other course is in Portuguese, got a Portuguese lesson
    (2026-09-28, production).

    `reply_in` is what `language.reply_language` read from the learner's own
    messages. When it names a language, that language is named outright: a
    rule plus a course hint ("reply in the language of the latest message.
    This course was asked for in pt.") was read as "reply in pt" (2026-10-07
    eval, an English question in a Portuguese course).
    """
    name = LANGUAGE_NAMES.get(reply_in, "")
    if name:
        return (
            f"Language: reply in {name} — the learner is writing in {name}, "
            "whatever language the course or the earlier turns were in."
        )
    course = str((journey.profile or {}).get("language") or "").strip()
    hint = f" This course was asked for in {course}." if course else ""
    return (
        "Language: reply in the language of the learner's latest message."
        f"{hint} Never switch language on your own."
    )


@dataclass(frozen=True, slots=True)
class TeachingContext:
    """Everything that changes per turn, typed, rendered once."""

    decision: Decision
    journey: LearningJourney
    #: The concept this turn is about; empty when the journey has none yet.
    concept: str
    plan_block: str
    knowledge_block: str
    memory_block: str
    session_block: str
    #: `assessments.render_results` of a paper just submitted, else empty.
    results_block: str = ""
    cards: Sequence[Card] = ()
    assessment: Assessment | None = None
    #: After a compaction the four state blocks fold into one `<CONTEXT>`.
    compacted: bool = False
    #: `render_focus_directive` output when Focus mode is on, else empty.
    focus_block: str = ""
    #: The language the learner is writing in (`language.reply_language`),
    #: "" when their messages do not say.
    reply_language: str = ""
    #: Concepts this session has already introduced. A teaching move on one
    #: of them builds on it instead of defining it again (2026-10-07 eval:
    #: the long session defined "estatística" four times).
    already_defined: Sequence[str] = ()
    #: The current lesson's concepts, as the plan names them: the names the
    #: PEDAGOGY record must use, or its evidence never meets the plan.
    lesson_concepts: Sequence[str] = ()

    def render(self) -> str:
        decision = self.decision
        parts: list[str] = ["<TURN_DIRECTIVE>"]
        move = decision.move.value
        parts.append(load(f"move.{move}", MOVE_PROMPT_VERSIONS.get(move, 1)).body)
        note = STRATEGY_NOTES.get(decision.strategy, "")
        parts.append(f"Strategy for this turn: {decision.strategy}. {note}".rstrip())
        if self.concept:
            parts.append(f"Current concept: {self.concept}.")
        parts.append(language_directive(self.journey, self.reply_language))
        if decision.signal is Signal.CONFUSED:
            parts.append(
                "The learner did not attempt an answer: they said they did not follow, "
                "or asked for another way. There is nothing to grade — do not say they "
                "tried, erred or got it wrong."
            )
        if decision.signal is Signal.ANSWERING and decision.extras.get("volunteered"):
            parts.append(
                "The learner stated a claim of their own; no question was open. Grade "
                "it exactly. If it is false, say so plainly in your first sentence, "
                "then give the correct idea and why, kindly. Never repeat the false "
                "claim as if it were true, and never explain it with its wrong reason."
            )
        elif decision.signal is Signal.ANSWERING:
            parts.append(
                "The learner's message is their answer to your last question. Grade it "
                "exactly (right / partly right / wrong), say why in one or two lines, "
                "then continue."
            )
        if decision.signal is Signal.WANTS_NEXT:
            parts.append(
                "The learner asked to move on. Start the current concept named above "
                "now; do not go back over the previous one beyond a single line."
            )
        defined = [c for c in self.already_defined if c]
        if defined and decision.move in _BUILDS_ON:
            parts.append(
                "Already introduced in this session: "
                + ", ".join(defined)
                + ". Do not define these again — the learner has the definition. "
                "Build on it (a one-line reminder at most), or go on to the next "
                "concept of the lesson."
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
        if self.results_block:
            parts.append(
                f"<ASSESSMENT_RESULTS>\n{self.results_block}\n</ASSESSMENT_RESULTS>"
            )
        if self.cards:
            parts.append(
                f"Cards saved ({len(self.cards)}): "
                + " | ".join(c.front_md[:80] for c in self.cards)
            )
        if self.assessment is not None:
            parts.append(
                f"Checkpoint prepared: '{self.assessment.title}', "
                f"{len(self.assessment.questions)} questions on: "
                + ", ".join(sorted({q["concept"] for q in self.assessment.questions}))
            )
        if decision.require_check:
            parts.append("End this turn with a question the learner can answer.")
        parts.append(self._record_reminder())
        parts.append("</TURN_DIRECTIVE>")

        if self.compacted:
            parts.append(
                "<CONTEXT>\n"
                + render_handoff(
                    journey=self.journey,
                    plan_block=self.plan_block,
                    knowledge_block=self.knowledge_block,
                    memory_block=self.memory_block,
                    session_block=self.session_block,
                )
                + "\n</CONTEXT>"
            )
        else:
            if self.plan_block:
                parts.append(f"<COURSE>\n{self.plan_block}\n</COURSE>")
            if self.knowledge_block:
                parts.append(
                    f"<KNOWLEDGE_STATE>\n{self.knowledge_block}\n</KNOWLEDGE_STATE>"
                )
            if self.memory_block:
                parts.append(
                    f"<LEARNING_MEMORY>\n{self.memory_block}\n</LEARNING_MEMORY>"
                )
            if self.session_block:
                parts.append(f"<ACTIVE_SESSION>\n{self.session_block}\n</ACTIVE_SESSION>")
        if self.focus_block:
            parts.append(self.focus_block)
        return "\n\n".join(parts)

    def _record_reminder(self) -> str:
        """The PEDAGOGY record, asked for where the model reads last.

        The rule sits in the system prompt, thousands of tokens up. Claude
        followed it there; gpt-4.1-mini, which served every reply of the
        2026-10-07 eval while Anthropic was out of credit, wrote no record on
        any of the 55 — so no mastery evidence, no `current_concept`, and a
        lesson that could never advance.
        """
        line = (
            "After your reply, on its own last line, append the "
            "<PEDAGOGY>{…}</PEDAGOGY> record exactly as your instructions describe."
        )
        names = [c for c in self.lesson_concepts if c]
        if names:
            line += (
                " Name concepts in it exactly as this lesson does: "
                + "; ".join(names)
                + "."
            )
        return line
