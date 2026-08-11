"""Concept resolution, DAG validation and extraction parsing.

Pure functions, and the ones that decide whether the knowledge graph is a usable
map or a pile of near-duplicates.
"""

from __future__ import annotations

import pytest

from noema.db.models import EdgeKind
from noema.knowledge.extraction import parse_extraction
from noema.knowledge.resolution import (
    Decision,
    normalize_name,
    resolve,
    would_create_cycle,
)

# ── Normalisation ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Chain Rule", "chain rule"),
        ("chain rule", "chain rule"),
        ("The Chain Rule", "chain rule"),
        ("chain-rule", "chain rule"),
        ("Chain  Rule.", "chain rule"),
        ("Derivatives", "derivative"),
        ("Matrices", "matrice"),  # crude, but consistently crude
        ("Gradients", "gradient"),
        ("Séries de Fourier", "series de fourier"),
    ],
)
def test_meaningless_differences_are_folded(raw: str, expected: str) -> None:
    assert normalize_name(raw) == expected


def test_meaningful_differences_are_preserved() -> None:
    """Over-eager normalisation would merge concepts a learner must tell apart."""
    assert normalize_name("gradient descent") != normalize_name(
        "stochastic gradient descent"
    )
    assert normalize_name("derivative") != normalize_name("partial derivative")


def test_words_that_only_look_plural_survive() -> None:
    assert normalize_name("Analysis") == "analysis"
    assert normalize_name("Basis") == "basis"
    assert normalize_name("Stress") == "stress"


def test_an_empty_name_normalises_to_nothing() -> None:
    assert normalize_name("   ...  ") == ""


# ── Resolution ────────────────────────────────────────────────────────────────


def test_an_identical_name_merges_whatever_the_embedding_says() -> None:
    match = resolve("The Chain Rule", [("c1", "chain rule", 0.10)])

    assert match.decision is Decision.MERGE
    assert match.target_id == "c1"


def test_a_near_identical_embedding_merges() -> None:
    match = resolve("Backprop", [("c1", "backpropagation", 0.95)])

    assert match.decision is Decision.MERGE
    assert match.target_id == "c1"


def test_an_ambiguous_similarity_asks_a_human() -> None:
    """Auto-merging a maybe is how two distinct ideas silently collapse into one."""
    match = resolve("Gradient", [("c1", "gradient descent", 0.85)])

    assert match.decision is Decision.REVIEW
    assert match.target_id == "c1"


def test_a_distinct_concept_is_created() -> None:
    match = resolve("Fourier Transform", [("c1", "gradient descent", 0.20)])
    assert match.decision is Decision.CREATE


def test_the_first_concept_in_an_empty_workspace_is_created() -> None:
    assert resolve("Chain Rule", []).decision is Decision.CREATE


def test_the_closest_neighbour_decides_not_the_first_one_listed() -> None:
    match = resolve(
        "Backprop",
        [("far", "fourier transform", 0.10), ("near", "backpropagation", 0.96)],
    )
    assert match.target_id == "near"


# ── Cycles ────────────────────────────────────────────────────────────────────


def test_a_direct_reversal_is_a_cycle() -> None:
    assert would_create_cycle([("a", "b")], src="b", dst="a")


def test_an_indirect_reversal_is_a_cycle() -> None:
    """A is a prerequisite of B, B of C — so C cannot be a prerequisite of A."""
    assert would_create_cycle([("a", "b"), ("b", "c")], src="c", dst="a")


def test_a_concept_cannot_be_its_own_prerequisite() -> None:
    assert would_create_cycle([], src="a", dst="a")


def test_an_ordinary_chain_is_allowed() -> None:
    assert not would_create_cycle([("a", "b")], src="b", dst="c")


def test_a_diamond_is_not_a_cycle() -> None:
    """Two paths to the same concept is normal in a curriculum, not a loop."""
    edges = [("a", "b"), ("a", "c")]
    assert not would_create_cycle(edges, src="b", dst="d")
    assert not would_create_cycle([*edges, ("b", "d")], src="c", dst="d")


def test_cycle_detection_terminates_on_an_already_cyclic_graph() -> None:
    """Defensive: a cycle that predates this check must not hang the walk."""
    assert would_create_cycle([("a", "b"), ("b", "a")], src="b", dst="a")


# ── Extraction parsing ────────────────────────────────────────────────────────


def payload(**concept: object) -> dict[str, object]:
    base = {
        "name": "Backpropagation",
        "definition": "Computes gradients via the chain rule.",
        "difficulty": 0.7,
        "prerequisites": ["Chain Rule"],
        "relations": [],
    }
    return {"concepts": [{**base, **concept}]}


def test_a_well_formed_response_parses() -> None:
    concepts = parse_extraction(payload(), ["chunk-1"])

    assert len(concepts) == 1
    assert concepts[0].name == "Backpropagation"
    assert concepts[0].prerequisites == ["Chain Rule"]
    assert concepts[0].source_chunk_ids == ["chunk-1"]


def test_a_concept_naming_itself_as_its_own_prerequisite_is_cleaned() -> None:
    """Models emit this often enough to be worth handling rather than validating."""
    concepts = parse_extraction(
        payload(prerequisites=["backpropagation", "Chain Rule"]), ["c1"]
    )
    assert concepts[0].prerequisites == ["Chain Rule"]


def test_difficulty_is_clamped_and_defaulted() -> None:
    assert parse_extraction(payload(difficulty=5), ["c1"])[0].difficulty == 1.0
    assert parse_extraction(payload(difficulty=-2), ["c1"])[0].difficulty == 0.0
    assert parse_extraction(payload(difficulty="hard"), ["c1"])[0].difficulty == 0.5


def test_unnamed_concepts_are_dropped() -> None:
    assert parse_extraction(payload(name="   "), ["c1"]) == []


def test_long_fields_are_bounded() -> None:
    concepts = parse_extraction(payload(name="x" * 5000, definition="y" * 5000), ["c1"])
    assert len(concepts[0].name) <= 200
    assert len(concepts[0].definition) <= 600


def test_prerequisites_stated_as_relations_are_ignored() -> None:
    """Prerequisites arrive through their own field, in one direction only.

    Accepting them here too would let the model state the relation whichever way it
    prefers, and a reversed prerequisite sends the learner through the material
    backwards.
    """
    concepts = parse_extraction(
        payload(relations=[{"target": "Calculus", "kind": "prerequisite_of"}]), ["c1"]
    )
    assert concepts[0].relations == []


def test_unknown_relation_kinds_are_dropped() -> None:
    concepts = parse_extraction(
        payload(
            relations=[
                {"target": "Calculus", "kind": "invented_by"},
                {"target": "Optimization", "kind": "part_of"},
            ]
        ),
        ["c1"],
    )
    assert [r.kind for r in concepts[0].relations] == [EdgeKind.PART_OF]


def test_duplicate_prerequisites_are_collapsed() -> None:
    concepts = parse_extraction(
        payload(prerequisites=["Chain Rule", "Chain Rule"]), ["c1"]
    )
    assert concepts[0].prerequisites == ["Chain Rule"]


def test_a_malformed_response_yields_nothing_rather_than_half_importing() -> None:
    assert parse_extraction({}, ["c1"]) == []
    assert parse_extraction({"concepts": "not a list"}, ["c1"]) == []
    assert parse_extraction({"concepts": [None, 42]}, ["c1"]) == []


def test_the_batch_size_is_bounded() -> None:
    many = {"concepts": [{"name": f"Concept {i}"} for i in range(500)]}
    assert len(parse_extraction(many, ["c1"])) <= 25
