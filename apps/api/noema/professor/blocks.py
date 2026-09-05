"""Learning blocks, found and validated on the server.

The model may place a fenced block — ```` ```noema:<tool> ```` with one JSON
object — inside a reply. The client used to find these with a regex over the
streamed text. Now the server does: `BlockFilter` holds back the fence while
it arrives, validates the body against the tool's schema when it closes, and
hands back a `Block` the route emits as its own SSE event. The learner's
stream never contains the fence, a malformed block is dropped and logged
(never shown raw), and the interface draws blocks from events, not from
pattern-matching prose.

The filter is a sibling of `teaching_policy.SidecarFilter` and is applied
*after* it (the PEDAGOGY record is split off first).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from noema.core.logging import get_logger

log = get_logger(__name__)

__all__ = ["TOOLS", "Block", "BlockFilter", "validate_block"]

OPEN_RE = re.compile(r"```noema:([a-z_]+)[ \t]*\n")
#: The longest prefix that could still turn into an opening fence.
OPEN_PREFIX = "```noema:"
CLOSE = "\n```"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


def _texts(value: list[str], *, cap: int = 12) -> list[str]:
    return [v[:200] for v in value if v][:cap]


class LayersBlock(_Strict):
    title: str = ""
    above_label: str = ""
    above: list[str] = Field(default_factory=list)
    below_label: str = ""
    below: list[str] = Field(default_factory=list)
    note: str = ""

    @field_validator("above", "below")
    @classmethod
    def _cap(cls, v: list[str]) -> list[str]:
        return _texts(v)


class StepsBlock(_Strict):
    title: str = ""
    items: list[str] = Field(min_length=2)

    @field_validator("items")
    @classmethod
    def _cap(cls, v: list[str]) -> list[str]:
        return _texts(v)


class CompareBlock(_Strict):
    title: str = ""
    columns: list[str] = Field(min_length=2, max_length=4)
    rows: list[list[str]] = Field(min_length=1)

    @field_validator("rows")
    @classmethod
    def _cap(cls, v: list[list[str]]) -> list[list[str]]:
        return [[c[:200] for c in row][:4] for row in v][:10]


class QuizBlock(_Strict):
    question: str = Field(min_length=1)
    options: list[str] = Field(min_length=2, max_length=5)
    answer: int = Field(ge=0)
    explain: str = ""
    concept: str = ""

    @field_validator("options")
    @classmethod
    def _cap(cls, v: list[str]) -> list[str]:
        return [o[:240] for o in v]


class FlashcardBlock(_Strict):
    front: str = Field(min_length=1)
    back: str = Field(min_length=1)
    concept: str = ""


class CheckBlock(_Strict):
    """An open question the learner answers in their own words; the professor
    grades it in the next turn. The rubric never reaches the client."""

    question: str = Field(min_length=1)
    rubric: list[str] = Field(default_factory=list)
    concept: str = ""
    #: teach_back asks the learner to explain it as if to a beginner.
    kind: str = "check"

    @field_validator("rubric")
    @classmethod
    def _cap(cls, v: list[str]) -> list[str]:
        return _texts(v, cap=6)

    @field_validator("kind")
    @classmethod
    def _kind(cls, v: str) -> str:
        return v if v in ("check", "teach_back") else "check"


TOOLS: dict[str, type[_Strict]] = {
    "layers": LayersBlock,
    "steps": StepsBlock,
    "compare": CompareBlock,
    "quiz": QuizBlock,
    "flashcard": FlashcardBlock,
    "check": CheckBlock,
}

#: Fields the learner must not see; stripped from the public form of a block.
PRIVATE_FIELDS: dict[str, tuple[str, ...]] = {"check": ("rubric",)}


@dataclass(frozen=True, slots=True)
class Block:
    tool: str
    data: dict[str, Any]

    def public(self) -> dict[str, Any]:
        hidden = PRIVATE_FIELDS.get(self.tool, ())
        return {k: v for k, v in self.data.items() if k not in hidden}

    def as_record(self) -> dict[str, Any]:
        return {"tool": self.tool, "data": self.data}


def validate_block(tool: str, body: str) -> Block | None:
    """A validated block, or None (and a log line) when it cannot be one."""
    model = TOOLS.get(tool)
    if model is None:
        log.warning("professor.block_unknown_tool", tool=tool)
        return None
    try:
        raw = json.loads(body)
    except ValueError:
        log.warning("professor.block_malformed_json", tool=tool)
        return None
    if not isinstance(raw, dict):
        log.warning("professor.block_not_object", tool=tool)
        return None
    try:
        parsed = model.model_validate(raw)
    except ValidationError as exc:
        log.warning("professor.block_invalid", tool=tool, errors=exc.error_count())
        return None
    data = parsed.model_dump()
    if tool == "quiz" and data["answer"] >= len(data["options"]):
        log.warning("professor.block_quiz_answer_out_of_range", tool=tool)
        return None
    return Block(tool=tool, data=data)


@dataclass
class BlockFilter:
    """Split a streamed reply into prose and blocks.

    `feed(text)` returns `(visible, blocks)`: the prose safe to show and any
    block whose fence closed in this chunk. A partial tail that might be the
    start of an opening fence is held back until the next chunk settles it.
    Inside a fence nothing is shown; on the closing fence the body is
    validated. `flush()` releases a held tail and drops an unclosed fence.
    """

    blocks: list[Block] = field(default_factory=list)
    _pending: str = field(default="", repr=False)
    _tool: str | None = field(default=None, repr=False)
    _body: str = field(default="", repr=False)

    def feed(self, text: str) -> tuple[str, list[Block]]:
        out: list[str] = []
        found: list[Block] = []
        buffer = self._pending + text
        self._pending = ""

        while buffer:
            if self._tool is not None:
                end = buffer.find(CLOSE)
                if end == -1:
                    # Keep a tail that could be the start of the closing fence.
                    hold = _partial_suffix(buffer, CLOSE)
                    self._body += buffer[: len(buffer) - hold]
                    self._pending = buffer[len(buffer) - hold :]
                    buffer = ""
                    break
                self._body += buffer[:end]
                block = validate_block(self._tool, self._body)
                if block is not None:
                    self.blocks.append(block)
                    found.append(block)
                self._tool, self._body = None, ""
                buffer = buffer[end + len(CLOSE) :]
                # Swallow the newline that follows a closing fence so prose
                # does not start with a blank line.
                if buffer.startswith("\n"):
                    buffer = buffer[1:]
                continue

            match = OPEN_RE.search(buffer)
            if match:
                out.append(buffer[: match.start()])
                self._tool = match.group(1)
                self._body = ""
                buffer = buffer[match.end() :]
                continue

            hold = _partial_open(buffer)
            out.append(buffer[: len(buffer) - hold])
            self._pending = buffer[len(buffer) - hold :]
            buffer = ""

        return "".join(out), found

    def flush(self) -> str:
        if self._tool is not None:
            # The stream ended inside a fence: nothing to show, nothing to keep.
            log.warning("professor.block_unclosed", tool=self._tool)
            self._tool, self._body, self._pending = None, "", ""
            return ""
        visible, self._pending = self._pending, ""
        return visible


def _partial_suffix(buffer: str, marker: str) -> int:
    for size in range(min(len(marker) - 1, len(buffer)), 0, -1):
        if marker.startswith(buffer[-size:]):
            return size
    return 0


def _partial_open(buffer: str) -> int:
    """How much of the tail could still become ```` ```noema:<tool>\\n ````.

    Either a prefix of the literal opening, or the literal opening followed
    by a tool name that has not reached its newline yet.
    """
    index = buffer.rfind(OPEN_PREFIX)
    if index != -1:
        rest = buffer[index + len(OPEN_PREFIX) :]
        if "\n" not in rest and re.fullmatch(r"[a-z_]*[ \t]*", rest):
            return len(buffer) - index
    return _partial_suffix(buffer, OPEN_PREFIX)
