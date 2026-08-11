"""Chunking decides citation quality, so it gets tested on behaviour, not shape."""

from __future__ import annotations

import pytest

from noema.ingestion.chunking import (
    ChunkSettings,
    chunk_document,
    estimate_tokens,
)
from noema.ingestion.ir import Block, BlockKind, ParsedDocument


def doc(*blocks: Block) -> ParsedDocument:
    return ParsedDocument(blocks=list(blocks))


def heading(text: str, level: int = 1) -> Block:
    return Block(kind=BlockKind.HEADING, text=text, level=level)


def para(text: str, page: int | None = None) -> Block:
    return Block(kind=BlockKind.PARAGRAPH, text=text, page=page)


def test_a_document_without_headings_still_chunks() -> None:
    chunks = chunk_document(doc(para("One idea."), para("Another idea.")))
    assert len(chunks) == 1
    assert "One idea." in chunks[0].content


def test_headings_become_the_chunk_boundary() -> None:
    chunks = chunk_document(
        doc(
            heading("Optimization"),
            para("We minimise a loss."),
            heading("Gradient Descent", level=2),
            para("Step downhill."),
        )
    )

    assert len(chunks) == 2
    assert chunks[0].heading_path == ["Optimization"]
    assert chunks[1].heading_path == ["Optimization", "Gradient Descent"]


def test_the_heading_path_is_embedded_but_not_stored() -> None:
    """A chunk saying 'it converges' is unretrievable without its context."""
    chunks = chunk_document(
        doc(
            heading("Optimization"),
            heading("Convergence", level=2),
            para("It converges when the step size is small enough."),
        )
    )

    chunk = chunks[0]
    assert chunk.content == "It converges when the step size is small enough."
    assert chunk.embedding_text().startswith("Optimization > Convergence")
    assert chunk.content in chunk.embedding_text()


def test_a_sibling_heading_pops_the_path() -> None:
    chunks = chunk_document(
        doc(
            heading("Calculus"),
            heading("Derivatives", level=2),
            para("Rate of change."),
            heading("Integrals", level=2),
            para("Area under a curve."),
        )
    )

    assert chunks[0].heading_path == ["Calculus", "Derivatives"]
    assert chunks[1].heading_path == ["Calculus", "Integrals"]


def test_oversized_sections_are_split_with_overlap() -> None:
    long_paragraphs = [para(f"Paragraph {i}. " + "word " * 60) for i in range(12)]
    settings = ChunkSettings(max_tokens=200, min_tokens=20, overlap_ratio=0.2)

    chunks = chunk_document(doc(heading("Long"), *long_paragraphs), settings)

    assert len(chunks) > 1
    assert all(chunk.token_count <= settings.max_tokens * 1.3 for chunk in chunks)
    # Overlap means the tail of one chunk reappears at the head of the next, so a
    # claim spanning the boundary survives in at least one chunk whole. These
    # paragraphs are each larger than the overlap budget, which is exactly the case
    # where naive paragraph-level overlap silently gives up.
    for i in range(len(chunks) - 1):
        tail_sentence = chunks[i].content.strip().split(". ")[-1][:40]
        assert tail_sentence in chunks[i + 1].content, (
            f"no overlap between chunk {i} and {i + 1}"
        )


def test_code_blocks_are_never_split_mid_structure() -> None:
    code = Block(
        kind=BlockKind.CODE,
        text="\n".join(f"line_{i} = {i}" for i in range(200)),
        language="python",
    )
    chunks = chunk_document(
        doc(heading("Example"), code), ChunkSettings(max_tokens=100, min_tokens=20)
    )

    fenced = [c for c in chunks if "```" in c.content]
    assert fenced, "the code block disappeared"
    for chunk in fenced:
        assert chunk.content.count("```") % 2 == 0, "a fence was split in half"


def test_tiny_chunks_are_merged_into_their_neighbour() -> None:
    """A four-word chunk matches everything and means nothing."""
    chunks = chunk_document(
        doc(
            heading("Notes"),
            para("A reasonably substantial paragraph. " * 20),
            para("Short."),
        ),
        ChunkSettings(max_tokens=500, min_tokens=50),
    )

    assert all(chunk.token_count >= 20 for chunk in chunks)


def test_runts_are_not_merged_across_headings() -> None:
    chunks = chunk_document(
        doc(heading("First"), para("Tiny."), heading("Second"), para("Also tiny."))
    )
    assert [c.heading_path for c in chunks] == [["First"], ["Second"]]


def test_page_anchors_survive_into_chunks() -> None:
    chunks = chunk_document(
        doc(heading("Chapter"), para("Start.", page=4), para("End.", page=6))
    )
    assert chunks[0].page_from == 4
    assert chunks[0].page_to == 6


def test_ordinals_are_contiguous_after_merging() -> None:
    chunks = chunk_document(
        doc(
            heading("A"),
            para("x " * 400),
            heading("B"),
            para("Tiny."),
            heading("C"),
            para("y " * 400),
        ),
        ChunkSettings(max_tokens=120, min_tokens=30),
    )
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))


def test_empty_documents_produce_no_chunks() -> None:
    assert chunk_document(doc()) == []
    assert chunk_document(doc(para("   "))) == []


def test_settings_reject_nonsense() -> None:
    with pytest.raises(ValueError):
        ChunkSettings(max_tokens=100, min_tokens=200)
    with pytest.raises(ValueError):
        ChunkSettings(overlap_ratio=0.9)


def test_token_estimate_scales_with_length() -> None:
    assert estimate_tokens("") == 1
    assert estimate_tokens("a" * 400) > estimate_tokens("a" * 40)
