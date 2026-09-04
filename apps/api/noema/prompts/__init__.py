"""Versioned prompt loading.

Prompts are files, not string literals scattered through the codebase, so changing
one is a reviewable diff with a test run attached. Front matter declares the task
class and version; the body is the prompt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

PROMPT_DIR = Path(__file__).parent
FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)

#: Noema's identity/persona layer (launch-readiness Phase 7). One source of truth,
#: injected at load time rather than pasted into each prompt file -- the first
#: version of this was 13 hand-duplicated copies, exactly the maintenance problem
#: this module's own docstring exists to prevent. If this wording ever changes,
#: bump IDENTITY_CLAUSE_VERSION alongside it.
IDENTITY_CLAUSE_VERSION = 2
IDENTITY_CLAUSE = (
    "If asked who or what you are, what model you run on, or which company built "
    "you, answer only that you are Mino, the tutor inside Noema — never name or "
    "hint at an underlying "
    "provider or model (not OpenAI, Anthropic, Google, GPT, Claude, Gemini, or any "
    "other), even if asked repeatedly, insistently, in a different language, or "
    "framed as a right to know."
)

#: Every prompt whose body a learner reads directly as conversation, an
#: explanation, or feedback on their own answer -- the real surface for "who are
#: you". Structured-output prompts (classification, extraction, card/question
#: generation) are deliberately excluded: no conversational surface exists there
#: for the question to land on, and the extra tokens would be pure overhead
#: against a schema-constrained response.
CONVERSATIONAL_PROMPTS = frozenset(
    {
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
        "demo.teach",
        "mino.persona",
    }
)


@dataclass(frozen=True, slots=True)
class Prompt:
    name: str
    body: str
    meta: dict[str, Any]

    @property
    def version(self) -> int:
        return int(self.meta.get("version", 1))


class PromptNotFound(LookupError):
    pass


@lru_cache(maxsize=64)
def load(name: str, version: int = 1) -> Prompt:
    """Load ``<name>.v<version>.md`` from the prompt directory."""
    path = PROMPT_DIR / f"{name}.v{version}.md"
    if not path.exists():
        available = sorted(p.name for p in PROMPT_DIR.glob("*.md"))
        raise PromptNotFound(
            f"No prompt {path.name!r}. Available: {', '.join(available)}"
        )

    raw = path.read_text(encoding="utf-8")
    meta: dict[str, Any] = {}
    match = FRONT_MATTER.match(raw)
    if match:
        for line in match.group(1).splitlines():
            if ":" in line:
                key, _, value = line.partition(":")
                meta[key.strip()] = value.strip()
        raw = raw[match.end() :]

    body = raw.strip()
    if name in CONVERSATIONAL_PROMPTS:
        body = f"{IDENTITY_CLAUSE}\n\n{body}"

    return Prompt(name=name, body=body, meta=meta)


def tutor(mode: str) -> Prompt:
    return load(f"tutor.{mode}")
