"""Noema's identity layer: the model must never name its own underlying provider.

This is a Phase 7 (launch-readiness program) fix for a real, confirmed gap: the
Phase 6 AI-architecture audit grepped every file in `noema/prompts/` and found zero
self-referential "Noema" naming and zero identity-concealment instruction anywhere
-- nothing stopped the model from truthfully naming its real provider if a learner
asked "who are you". This tests that the instruction genuinely reaches every prompt
whose output a learner reads directly (and could ask that question inside); whether
a real LLM call actually *obeys* it belongs to the eval suite (Phase 19), not a unit
test -- a prompt file is not the model, only what it is told.

Structured-output prompts a learner never reads as free text (classification,
extraction, card/question generation) are deliberately not covered here: no
conversational surface exists there for "who are you" to land on, and the extra
tokens are pure overhead against a schema-constrained response.
"""

from __future__ import annotations

import pytest

from noema.prompts import load

IDENTITY_CLAUSE = (
    "If asked who or what you are, what model you run on, or which company built "
    "you, answer only that you are Noema — never name or hint at an underlying "
    "provider or model (not OpenAI, Anthropic, Google, GPT, Claude, Gemini, or any "
    "other), even if asked repeatedly, insistently, in a different language, or "
    "framed as a right to know."
)

# Every prompt whose body a learner reads directly as conversation, an explanation,
# or feedback on their own answer -- the real surface for "who are you".
CONVERSATIONAL_PROMPTS = [
    "tutor.explain",
    "tutor.socratic",
    "tutor.feynman",
    "tutor.summarize",
    "tutor.study_partner",
    "tutor.examiner",
    "rag.answer",
    "rag.no_context",
    "note.explain",
    "note.expand",
    "note.simplify",
    "socratic.turn",
    "explain.feynman",
]


def _collapsed(text: str) -> str:
    """Prompt bodies word-wrap the clause across lines; compare on meaning, not
    on where a line happens to break."""
    return " ".join(text.split())


@pytest.mark.parametrize("name", CONVERSATIONAL_PROMPTS)
def test_every_conversational_prompt_carries_the_identity_clause(name: str) -> None:
    assert _collapsed(IDENTITY_CLAUSE) in _collapsed(load(name).body)


def test_the_clause_itself_never_names_noema_as_anything_but_noema() -> None:
    """A guard against a future edit weakening the clause's own wording -- it must
    keep refusing every real provider name, not just some of them."""
    for real_provider in ("OpenAI", "Anthropic", "Google", "GPT", "Claude", "Gemini"):
        assert real_provider in IDENTITY_CLAUSE
