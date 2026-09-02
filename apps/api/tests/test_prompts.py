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

Phase 8 (Prompt Architecture) centralized this: the clause is injected once by
`noema.prompts.load()`, not pasted into each `.md` file -- the first version of
this was 13 hand-duplicated copies, which is exactly the maintenance problem this
module's own docstring exists to prevent. These tests import the real constants
from `noema.prompts` rather than re-declaring them, so a future wording change is
verified against itself, not against a second, possibly-stale copy.
"""

from __future__ import annotations

import pytest

from noema.prompts import CONVERSATIONAL_PROMPTS, IDENTITY_CLAUSE, PROMPT_DIR, load


def _collapsed(text: str) -> str:
    """Prompt bodies word-wrap the clause across lines; compare on meaning, not
    on where a line happens to break."""
    return " ".join(text.split())


@pytest.mark.parametrize("name", sorted(CONVERSATIONAL_PROMPTS))
def test_every_conversational_prompt_carries_the_identity_clause(name: str) -> None:
    assert _collapsed(IDENTITY_CLAUSE) in _collapsed(load(name).body)


@pytest.mark.parametrize("name", sorted(CONVERSATIONAL_PROMPTS))
def test_the_clause_is_injected_not_duplicated_in_the_source_file(name: str) -> None:
    """Proves centralization actually happened -- the .md file itself must not
    contain a second, hand-pasted copy of the clause `load()` already injects."""
    raw = (PROMPT_DIR / f"{name}.v1.md").read_text(encoding="utf-8")
    assert "who or what you are" not in raw.lower()


def test_structured_output_prompts_are_not_given_the_identity_clause() -> None:
    """The exclusion is deliberate, not an oversight -- confirmed against real
    prompts a learner never reads as free text, not just asserted."""
    for name in ("professor.classify_intent", "generate.cards", "generate.questions"):
        assert name not in CONVERSATIONAL_PROMPTS
        assert _collapsed(IDENTITY_CLAUSE) not in _collapsed(load(name).body)


def test_the_clause_itself_never_names_noema_as_anything_but_noema() -> None:
    """A guard against a future edit weakening the clause's own wording -- it must
    keep refusing every real provider name, not just some of them."""
    for real_provider in ("OpenAI", "Anthropic", "Google", "GPT", "Claude", "Gemini"):
        assert real_provider in IDENTITY_CLAUSE


def test_every_conversational_prompt_name_actually_resolves_to_a_real_file() -> None:
    """Guards the other direction -- a typo'd name in CONVERSATIONAL_PROMPTS would
    otherwise silently exclude a prompt from the identity layer forever."""
    for name in CONVERSATIONAL_PROMPTS:
        assert (PROMPT_DIR / f"{name}.v1.md").exists()
