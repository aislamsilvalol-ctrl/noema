"""Rank fusion, context assembly and citation enforcement.

All pure functions, so the behaviour that decides whether a user can trust an answer
is testable without a database or a model.
"""

from __future__ import annotations

import uuid

import pytest

from noema.retrieval.fusion import RRF_K, fuse, max_possible_score
from noema.retrieval.grounding import (
    CitationFilter,
    build_context,
    citations_for,
    used_citations,
)
from noema.retrieval.search import Retrieved

A, B, C, D = (uuid.uuid4() for _ in range(4))


def result(content: str = "text", title: str = "Boyd", score: float = 0.9) -> Retrieved:
    return Retrieved(
        chunk_id=uuid.uuid4(),
        source_id=uuid.uuid4(),
        content=content,
        heading_path=["Optimization"],
        page_from=12,
        page_to=12,
        source_title=title,
        score=score,
        found_by_both=True,
    )


# ── Fusion ────────────────────────────────────────────────────────────────────


def test_agreement_between_retrievers_wins() -> None:
    """A result both retrievers liked outranks one only a single retriever loved."""
    fused = fuse(dense=[A, B], sparse=[B, C])

    assert fused[0].chunk_id == B
    assert fused[0].found_by_both


def test_scores_ignore_the_incompatible_scales_and_use_rank() -> None:
    fused = {r.chunk_id: r.score for r in fuse(dense=[A], sparse=[B])}

    assert fused[A] == pytest.approx(1 / (RRF_K + 1))
    assert fused[A] == fused[B], "identical ranks must fuse to identical scores"


def test_a_single_retriever_still_returns_results() -> None:
    """Text-only search is what a notebook without embeddings falls back to."""
    fused = fuse(dense=[], sparse=[A, B])

    assert [r.chunk_id for r in fused] == [A, B]
    assert all(r.dense_rank is None for r in fused)
    assert not fused[0].found_by_both


def test_duplicates_within_one_list_count_once() -> None:
    fused = fuse(dense=[A, A, B], sparse=[])
    assert [r.chunk_id for r in fused] == [A, B]


def test_ordering_is_deterministic_for_tied_scores() -> None:
    first = fuse(dense=[A, B], sparse=[B, A])
    second = fuse(dense=[A, B], sparse=[B, A])
    assert [r.chunk_id for r in first] == [r.chunk_id for r in second]


def test_limit_truncates_after_ranking_not_before() -> None:
    fused = fuse(dense=[A, B, C], sparse=[D, C, B], limit=2)
    assert len(fused) == 2
    # C and B appear in both lists, so they must survive the cut over A and D.
    assert {r.chunk_id for r in fused} == {B, C}


def test_the_normalising_ceiling_matches_a_double_first_place() -> None:
    fused = fuse(dense=[A], sparse=[A])
    assert fused[0].score == pytest.approx(max_possible_score())


def test_k_must_be_positive() -> None:
    with pytest.raises(ValueError):
        fuse([A], [B], k=0)


# ── Context assembly ──────────────────────────────────────────────────────────


def test_context_blocks_are_numbered_from_one_with_their_location() -> None:
    context, included = build_context([result("First."), result("Second.")])

    assert context.startswith("[1] Boyd · p. 12 · Optimization")
    assert "[2]" in context
    assert len(included) == 2


def test_blocks_that_do_not_fit_the_budget_are_excluded_from_both_outputs() -> None:
    """A block dropped for budget must not be citable — it was never shown."""
    big = result("word " * 4000)
    context, included = build_context([result("Small."), big, big], token_budget=500)

    assert len(included) == 1
    assert context.count("[2]") == 0


def test_at_least_one_block_survives_however_large() -> None:
    context, included = build_context([result("word " * 10000)], token_budget=10)
    assert len(included) == 1
    assert context


def test_citations_carry_what_the_user_needs_to_check_the_claim() -> None:
    citations = citations_for([result("Gradient descent steps downhill.")])

    assert citations[0].number == 1
    assert "Boyd" in citations[0].location
    assert "Gradient descent" in citations[0].excerpt


# ── Citation enforcement ──────────────────────────────────────────────────────


def make_filter(blocks: int) -> CitationFilter:
    return CitationFilter.for_results([result() for _ in range(blocks)])


def test_valid_citations_pass_through() -> None:
    f = make_filter(2)
    out = f.feed("Gradient descent steps downhill [1]. It converges [2].") + f.flush()

    assert "[1]" in out and "[2]" in out
    assert f.dropped == []
    assert f.used == {1, 2}


def test_a_sentence_citing_a_block_that_was_never_supplied_is_dropped() -> None:
    """The whole trust model: an invented source never reaches the reader."""
    f = make_filter(2)
    out = f.feed("True claim [1]. Invented claim [7]. Another true one [2].") + f.flush()

    assert "Invented claim" not in out
    assert "True claim" in out and "Another true one" in out
    assert len(f.dropped) == 1
    assert f.used == {1, 2}


def test_uncited_sentences_are_left_alone() -> None:
    f = make_filter(1)
    out = f.feed("Let me explain. The gradient points uphill [1].") + f.flush()

    assert "Let me explain." in out


def test_text_arriving_split_across_tokens_is_still_checked() -> None:
    """The model streams a character at a time; the guarantee cannot depend on that."""
    f = make_filter(1)

    out = ""
    for character in "Fine [1]. Bogus [9]. Fine again [1].":
        out += f.feed(character)
    out += f.flush()

    assert "Bogus" not in out
    assert out.count("Fine") == 2


def test_a_trailing_sentence_without_punctuation_is_still_checked() -> None:
    f = make_filter(1)
    out = f.feed("An unfinished invented claim [4]") + f.flush()

    assert out == ""
    assert len(f.dropped) == 1


def test_nothing_is_emitted_before_a_sentence_completes() -> None:
    """Emitting early would show a claim before its citation could be validated."""
    f = make_filter(1)
    assert f.feed("A claim citing [9") == ""
    assert f.feed("]") == ""
    assert f.flush() == ""


def test_with_no_context_every_citation_is_invalid() -> None:
    f = make_filter(0)
    out = f.feed("Confidently cited [1].") + f.flush()

    assert out == ""
    assert len(f.dropped) == 1


def test_only_the_sources_actually_used_are_reported() -> None:
    citations = citations_for([result(), result(), result()])
    f = make_filter(3)
    f.feed("Only the second one is used [2].")
    f.flush()

    reported = used_citations(citations, f.used)
    assert [c.number for c in reported] == [2]
