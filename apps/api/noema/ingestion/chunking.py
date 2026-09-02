"""Structure-aware chunking.

Chunk boundaries decide citation quality far more than the embedding model does. A
chunk that starts mid-argument retrieves badly and cites worse, so the splitter
follows the document's own structure first and falls back to token windows only
when a section is genuinely too large.

Pure functions over the IR — no I/O, no model calls, so the behaviour is fully
testable against fixture documents.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from noema.ingestion.ir import Block, BlockKind, ParsedDocument

__all__ = ["Chunk", "ChunkSettings", "chunk_document", "estimate_tokens"]

#: Rough token estimate. Deliberately not a tokenizer: the exact count only needs to
#: be good enough to keep chunks inside a model's window, and a real tokenizer would
#: tie chunking to one provider's vocabulary.
CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


@dataclass(frozen=True, slots=True)
class ChunkSettings:
    max_tokens: int = 512
    min_tokens: int = 100
    overlap_ratio: float = 0.15

    def __post_init__(self) -> None:
        if self.min_tokens >= self.max_tokens:
            raise ValueError("min_tokens must be below max_tokens")
        if not 0 <= self.overlap_ratio < 0.5:
            raise ValueError("overlap_ratio must be in [0, 0.5)")


@dataclass(frozen=True, slots=True)
class Chunk:
    content: str
    ordinal: int
    heading_path: list[str] = field(default_factory=list)
    page_from: int | None = None
    page_to: int | None = None

    @property
    def token_count(self) -> int:
        return estimate_tokens(self.content)

    def embedding_text(self) -> str:
        """What actually gets embedded.

        The heading path is prepended here and *only* here. "It converges when the
        step size is small enough" is unretrievable alone; prefixed with
        `Optimization > Gradient Descent > Convergence` it is findable. The stored
        content stays clean so citations quote the source, not our scaffolding.
        """
        if not self.heading_path:
            return self.content
        return " > ".join(self.heading_path) + "\n\n" + self.content


def chunk_document(
    document: ParsedDocument, settings: ChunkSettings | None = None
) -> list[Chunk]:
    """Split a parsed document into embeddable chunks."""
    settings = settings or ChunkSettings()
    chunks: list[Chunk] = []

    for section_path, blocks in _sections(document.blocks):
        text = _render(blocks)
        if not text.strip():
            continue

        pages = [b.page for b in blocks if b.page is not None]
        page_from = min(pages) if pages else None
        page_to = max(pages) if pages else None

        for piece in _split_to_size(text, blocks, settings):
            chunks.append(
                Chunk(
                    content=piece,
                    ordinal=len(chunks),
                    heading_path=list(section_path),
                    page_from=page_from,
                    page_to=page_to,
                )
            )

    return _merge_runts(chunks, settings)


def _sections(blocks: list[Block]) -> list[tuple[tuple[str, ...], list[Block]]]:
    """Group blocks under their heading path."""
    sections: list[tuple[tuple[str, ...], list[Block]]] = []
    path: list[str] = []
    current: list[Block] = []

    for block in blocks:
        if block.kind is BlockKind.HEADING:
            if current:
                sections.append((tuple(path), current))
                current = []
            # A level-2 heading replaces everything from level 2 down.
            path = path[: block.level - 1]
            while len(path) < block.level - 1:
                path.append("")
            path.append(block.text.strip())
        else:
            current.append(block)

    if current:
        sections.append((tuple(path), current))
    return [(tuple(p for p in path if p), blocks) for path, blocks in sections]


def _render(blocks: list[Block]) -> str:
    parts: list[str] = []
    for block in blocks:
        if block.kind is BlockKind.CODE:
            fence = f"```{block.language or ''}".rstrip()
            parts.append(f"{fence}\n{block.text}\n```")
        elif block.kind is BlockKind.LIST_ITEM:
            parts.append(f"- {block.text}")
        elif block.kind is BlockKind.QUOTE:
            parts.append(f"> {block.text}")
        else:
            parts.append(block.text)
    return "\n\n".join(parts).strip()


def _split_to_size(text: str, blocks: list[Block], settings: ChunkSettings) -> list[str]:
    """Split an oversized section on paragraph boundaries, with overlap."""
    if estimate_tokens(text) <= settings.max_tokens:
        return [text]

    # Code and tables are never split mid-structure: half a function or half a table
    # is worse than an oversized chunk.
    if any(b.kind in {BlockKind.CODE, BlockKind.TABLE} for b in blocks):
        atomic = _render(blocks).split("\n\n")
    else:
        # A section with no blank-line breaks at all -- a wall of text, a pasted
        # transcript -- collapses to one "paragraph" the size of the whole section.
        # Split anything still oversized before packing, or nothing downstream ever
        # gets a chance to bound this chunk's size.
        atomic = [
            piece
            for paragraph in _paragraphs(text)
            for piece in _split_oversized_paragraph(paragraph, settings.max_tokens)
        ]

    pieces: list[str] = []
    current: list[str] = []
    budget = settings.max_tokens
    overlap_tokens = int(settings.max_tokens * settings.overlap_ratio)

    for paragraph in atomic:
        candidate = [*current, paragraph]
        if current and estimate_tokens("\n\n".join(candidate)) > budget:
            pieces.append("\n\n".join(current))
            current = [*_tail(current, overlap_tokens), paragraph]
        else:
            current = candidate

    if current:
        pieces.append("\n\n".join(current))
    return pieces


def _paragraphs(text: str) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return paragraphs or [text]


SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def _split_oversized_paragraph(paragraph: str, max_tokens: int) -> list[str]:
    """A last-resort fallback below paragraph-boundary granularity.

    Only reached when a single paragraph (already the whole section, in the
    no-blank-lines case) is itself larger than a whole chunk. Packs sentences up
    to the budget first; a single sentence that is *still* oversized (no terminal
    punctuation anywhere, e.g. a giant unbroken transcript line) falls through to
    `_hard_split`. Every piece this returns is guaranteed at or under max_tokens --
    context assembly's own budget depends on no chunk ever exceeding it.
    """
    if estimate_tokens(paragraph) <= max_tokens:
        return [paragraph]

    pieces: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            pieces.append(" ".join(current))

    for sentence in (s for s in SENTENCE_END.split(paragraph.strip()) if s):
        if estimate_tokens(sentence) > max_tokens:
            flush()
            current.clear()
            pieces.extend(_hard_split(sentence, max_tokens))
            continue
        candidate = [*current, sentence]
        if current and estimate_tokens(" ".join(candidate)) > max_tokens:
            flush()
            current = [sentence]
        else:
            current = candidate

    flush()
    return pieces or [paragraph]


def _hard_split(text: str, max_tokens: int) -> list[str]:
    """The true last resort -- no sentence boundary to split on either.

    Packs whitespace-separated words up to the budget; a single "word" that is
    itself still oversized (no spaces at all -- one giant unbroken blob) is cut on
    a fixed character window as the final fallback.
    """
    window = max(1, max_tokens * CHARS_PER_TOKEN)
    pieces: list[str] = []
    current: list[str] = []

    for word in text.split():
        if estimate_tokens(word) > max_tokens:
            if current:
                pieces.append(" ".join(current))
                current = []
            pieces.extend(word[i : i + window] for i in range(0, len(word), window))
            continue
        candidate = [*current, word]
        if current and estimate_tokens(" ".join(candidate)) > max_tokens:
            pieces.append(" ".join(current))
            current = [word]
        else:
            current = candidate

    if current:
        pieces.append(" ".join(current))

    return pieces or [text[i : i + window] for i in range(0, len(text), window)] or [text]


def _tail(paragraphs: list[str], overlap_tokens: int) -> list[str]:
    """The trailing text that fits in the overlap budget.

    Overlap exists so a claim split across a boundary is still retrievable from at
    least one chunk in full. Whole paragraphs are preferred, but dense prose has
    paragraphs larger than the whole budget — and falling back to "no overlap"
    exactly where the text is densest would drop the guarantee where it matters
    most. So the last paragraph contributes its trailing sentences instead.
    """
    if overlap_tokens <= 0 or not paragraphs:
        return []

    tail: list[str] = []
    total = 0
    for paragraph in reversed(paragraphs):
        tokens = estimate_tokens(paragraph)
        if total + tokens > overlap_tokens:
            break
        tail.insert(0, paragraph)
        total += tokens

    if tail:
        return tail

    return _sentence_tail(paragraphs[-1], overlap_tokens)


def _sentence_tail(paragraph: str, overlap_tokens: int) -> list[str]:
    sentences = SENTENCE_END.split(paragraph.strip())
    tail: list[str] = []
    total = 0

    for sentence in reversed(sentences):
        tokens = estimate_tokens(sentence)
        if tail and total + tokens > overlap_tokens:
            break
        tail.insert(0, sentence)
        total += tokens
        if total >= overlap_tokens:
            break

    joined = " ".join(tail).strip()
    if not joined:
        return []

    # A single "sentence" by this regex's definition can still be larger than the
    # whole overlap budget -- a run-on with no terminal punctuation, or (since the
    # chunking-oversized-paragraph fallback below can hand this function a piece
    # with no punctuation at all) an entire hard-split fragment. Cap to the
    # trailing characters the budget actually allows rather than including it
    # whole, which would silently blow past overlap_tokens.
    window = max(1, overlap_tokens * CHARS_PER_TOKEN)
    if len(joined) > window:
        joined = joined[-window:].strip()
    return [joined] if joined else []


def _merge_runts(chunks: list[Chunk], settings: ChunkSettings) -> list[Chunk]:
    """Fold tiny chunks into their neighbour under the same heading.

    A four-word chunk matches everything and means nothing; it pollutes retrieval
    with a high-similarity, zero-information hit.
    """
    merged: list[Chunk] = []

    for chunk in chunks:
        previous = merged[-1] if merged else None
        fits = (
            previous is not None
            and chunk.token_count < settings.min_tokens
            and previous.heading_path == chunk.heading_path
            and previous.token_count + chunk.token_count <= settings.max_tokens
        )
        if fits and previous is not None:
            merged[-1] = Chunk(
                content=f"{previous.content}\n\n{chunk.content}",
                ordinal=previous.ordinal,
                heading_path=previous.heading_path,
                page_from=previous.page_from,
                page_to=chunk.page_to or previous.page_to,
            )
        else:
            merged.append(
                Chunk(
                    content=chunk.content,
                    ordinal=len(merged),
                    heading_path=chunk.heading_path,
                    page_from=chunk.page_from,
                    page_to=chunk.page_to,
                )
            )

    return merged
