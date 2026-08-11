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
        raise PromptNotFound(f"No prompt {path.name!r}. Available: {', '.join(available)}")

    raw = path.read_text(encoding="utf-8")
    meta: dict[str, Any] = {}
    match = FRONT_MATTER.match(raw)
    if match:
        for line in match.group(1).splitlines():
            if ":" in line:
                key, _, value = line.partition(":")
                meta[key.strip()] = value.strip()
        raw = raw[match.end() :]

    return Prompt(name=name, body=raw.strip(), meta=meta)


def tutor(mode: str) -> Prompt:
    return load(f"tutor.{mode}")
