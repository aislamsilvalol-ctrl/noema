"""Markdown, plain text and CSV parsers.

Pure Python, no third-party dependencies, so these run everywhere and are the
reference for what a parser has to produce.
"""

from __future__ import annotations

import csv
import io
import re
from typing import Any

from noema.ingestion.ir import Block, BlockKind, ParsedDocument

ATX_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
SETEXT_UNDERLINE = re.compile(r"^(=+|-+)\s*$")
LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*)$")
FENCE = re.compile(r"^```(\w*)\s*$")
QUOTE = re.compile(r"^>\s?(.*)$")

#: Beyond this, a CSV is data to summarise rather than prose to read.
CSV_SAMPLE_ROWS = 20


def parse_markdown(text: str) -> ParsedDocument:
    blocks: list[Block] = []
    lines = text.replace("\r\n", "\n").split("\n")
    buffer: list[str] = []
    index = 0

    def flush() -> None:
        joined = "\n".join(buffer).strip()
        if joined:
            blocks.append(Block(kind=BlockKind.PARAGRAPH, text=joined))
        buffer.clear()

    while index < len(lines):
        line = lines[index]

        fence = FENCE.match(line)
        if fence:
            flush()
            language = fence.group(1) or None
            index += 1
            code: list[str] = []
            while index < len(lines) and not lines[index].startswith("```"):
                code.append(lines[index])
                index += 1
            blocks.append(
                Block(kind=BlockKind.CODE, text="\n".join(code), language=language)
            )
            index += 1
            continue

        heading = ATX_HEADING.match(line)
        if heading:
            flush()
            blocks.append(
                Block(
                    kind=BlockKind.HEADING,
                    text=heading.group(2).strip(),
                    level=len(heading.group(1)),
                )
            )
            index += 1
            continue

        # Setext: a line of text underlined by === or ---.
        if (
            index + 1 < len(lines)
            and line.strip()
            and SETEXT_UNDERLINE.match(lines[index + 1])
            and not buffer
        ):
            level = 1 if lines[index + 1].startswith("=") else 2
            blocks.append(Block(kind=BlockKind.HEADING, text=line.strip(), level=level))
            index += 2
            continue

        item = LIST_ITEM.match(line)
        if item:
            flush()
            blocks.append(Block(kind=BlockKind.LIST_ITEM, text=item.group(1).strip()))
            index += 1
            continue

        quote = QUOTE.match(line)
        if quote:
            flush()
            blocks.append(Block(kind=BlockKind.QUOTE, text=quote.group(1).strip()))
            index += 1
            continue

        if not line.strip():
            flush()
        else:
            buffer.append(line)
        index += 1

    flush()
    return ParsedDocument(blocks=blocks, metadata=_markdown_metadata(blocks))


def parse_text(text: str) -> ParsedDocument:
    """Plain text: paragraphs only, no structure invented that is not there."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text.replace("\r\n", "\n"))]
    blocks = [
        Block(kind=BlockKind.PARAGRAPH, text=paragraph)
        for paragraph in paragraphs
        if paragraph
    ]
    return ParsedDocument(blocks=blocks)


def parse_csv(text: str) -> ParsedDocument:
    """A CSV becomes a schema summary plus a sample.

    Emitting one chunk per row would flood retrieval with near-identical vectors and
    tell the model nothing about the table's shape.
    """
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return ParsedDocument(blocks=[])

    header, *data = rows
    blocks: list[Block] = [
        Block(kind=BlockKind.HEADING, text="Columns", level=2),
        Block(
            kind=BlockKind.PARAGRAPH,
            text=f"{len(data)} rows with columns: " + ", ".join(header),
        ),
    ]

    if data:
        sample = data[:CSV_SAMPLE_ROWS]
        table = [", ".join(header), *[", ".join(row) for row in sample]]
        blocks.append(Block(kind=BlockKind.HEADING, text="Sample rows", level=2))
        blocks.append(Block(kind=BlockKind.TABLE, text="\n".join(table)))

    return ParsedDocument(
        blocks=blocks,
        metadata={"columns": header, "row_count": len(data)},
    )


def _markdown_metadata(blocks: list[Block]) -> dict[str, Any]:
    title = next(
        (b.text for b in blocks if b.kind is BlockKind.HEADING and b.level == 1), None
    )
    return {"title": title} if title else {}
