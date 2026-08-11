"""The intermediate representation every parser produces.

One shape for every input format, so chunking, embedding and citation are written
once. Adding a format means writing a parser to this IR and nothing else — which is
the contribution path ``CONTRIBUTING.md`` advertises.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

__all__ = ["Block", "BlockKind", "ParsedDocument"]


class BlockKind(StrEnum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST_ITEM = "list_item"
    CODE = "code"
    TABLE = "table"
    QUOTE = "quote"
    CAPTION = "caption"


@dataclass(frozen=True, slots=True)
class Block:
    """One structural unit of a document.

    ``page`` and ``timestamp`` are the citation anchors: a claim in an answer has to
    point back at a place a human can open and check.
    """

    kind: BlockKind
    text: str
    level: int = 0  # heading depth; 0 for everything else
    page: int | None = None
    timestamp: float | None = None  # seconds, for transcripts
    language: str | None = None  # for code blocks

    def __post_init__(self) -> None:
        if self.kind is BlockKind.HEADING and not 1 <= self.level <= 6:
            raise ValueError(f"heading level must be 1-6, got {self.level}")


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    blocks: list[Block]
    metadata: dict[str, Any] = field(default_factory=dict)
    page_count: int | None = None

    @property
    def text(self) -> str:
        return "\n\n".join(block.text for block in self.blocks)

    @property
    def is_empty(self) -> bool:
        return not any(block.text.strip() for block in self.blocks)
