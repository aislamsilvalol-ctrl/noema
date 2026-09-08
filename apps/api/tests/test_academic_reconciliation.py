"""Reconciliation folds lectures together without folding away what they disagree on."""

from __future__ import annotations

from noema.academic.extraction import (
    Concept,
    Evidence,
    Extraction,
    Relation,
    RelationKind,
    Support,
)
from noema.academic.reconciliation import reconcile

APPROACHES = "The value a function approaches as the input approaches a point."
EPSILON_DELTA = "For every epsilon there is a delta keeping the distance under it."
HEADING = "Where the function is heading, whatever happens at the point itself."


def at(source: str, start: int = 0) -> Evidence:
    return Evidence(
        source_id=source, start_ms=start, end_ms=start + 60_000, segment=start // 60_000
    )


def concept(
    name: str,
    *,
    source: str,
    definition: str = "",
    difficulty: float = 0.5,
    support: Support = Support.source_supported,
    start: int = 0,
) -> Concept:
    return Concept(
        name=name,
        definition=definition,
        difficulty=difficulty,
        support=support,
        evidence=at(source, start),
    )


def extraction(
    source: str, *concepts: Concept, relations: list[Relation] | None = None
) -> Extraction:
    return Extraction(
        evidence=at(source),
        concepts=list(concepts),
        relations=relations or [],
    )


def test_the_same_concept_under_three_names_becomes_one_entry() -> None:
    atlas = reconcile(
        [
            extraction(
                "l1",
                concept(
                    "Eigenvalue",
                    source="l1",
                    definition="A scalar that scales its own vector.",
                ),
            ),
            extraction(
                "l2",
                concept(
                    "eigenvalues",
                    source="l2",
                    definition="A scalar that scales its own vector.",
                ),
            ),
            extraction(
                "l3",
                concept(
                    "Eigenvalue",
                    source="l3",
                    definition="A scalar that scales its own vector.",
                ),
            ),
        ]
    )

    assert len(atlas.concepts) == 1
    entry = atlas.concepts[0]
    assert entry.key == "eigenvalue"
    assert entry.name == "Eigenvalue"  # the form two lectures used
    assert entry.aliases == ["eigenvalues"]
    assert entry.lectures == {"l1", "l2", "l3"}


def test_confidence_counts_lectures_not_repetitions() -> None:
    one_lecture = reconcile(
        [
            extraction(
                "l1",
                *(concept("limit", source="l1", start=i * 60_000) for i in range(20)),
            )
        ]
    ).concepts[0]
    four_lectures = reconcile(
        [extraction(f"l{i}", concept("limit", source=f"l{i}")) for i in range(4)]
    ).concepts[0]

    assert len(one_lecture.mentions) == 20
    assert one_lecture.confidence < four_lectures.confidence
    assert four_lectures.confidence == 1.0


def test_a_concept_only_ever_inferred_stays_low_however_often_it_appears() -> None:
    atlas = reconcile(
        [
            extraction(
                f"l{i}",
                concept("Hilbert space", source=f"l{i}", support=Support.inferred),
            )
            for i in range(6)
        ]
    )
    entry = atlas.concepts[0]
    assert not entry.source_supported
    assert entry.confidence <= 0.3


def test_two_sources_defining_it_differently_is_recorded_not_resolved() -> None:
    atlas = reconcile(
        [
            extraction(
                "l1",
                concept(
                    "limit",
                    source="l1",
                    definition=APPROACHES,
                ),
            ),
            extraction(
                "l2",
                concept(
                    "limit",
                    source="l2",
                    definition=EPSILON_DELTA,
                ),
            ),
        ]
    )

    entry = atlas.concepts[0]
    assert len(entry.disagreements) == 1
    disagreement = entry.disagreements[0]
    assert {disagreement.left.source_id, disagreement.right.source_id} == {"l1", "l2"}
    # both wordings survive; neither was voted away
    assert disagreement.left.definition != disagreement.right.definition
    assert entry.definition in (
        disagreement.left.definition,
        disagreement.right.definition,
    )


def test_one_lecture_rephrasing_itself_is_not_a_disagreement() -> None:
    atlas = reconcile(
        [
            extraction(
                "l1",
                concept(
                    "limit",
                    source="l1",
                    definition="The value a function approaches at a point.",
                ),
                concept(
                    "limit",
                    source="l1",
                    definition=HEADING,
                    start=600_000,
                ),
            )
        ]
    )
    assert atlas.concepts[0].disagreements == []


def test_the_plan_says_merge_review_or_create_against_the_products_own_concepts() -> None:
    # what an embedding lookup would return, keyed by normalised name: the
    # pair's similarity, not one number reused for every candidate
    similarities = {
        "eigenvalue": [("concept-1", "eigenvalue", 0.99)],
        "singular value": [("concept-2", "singular value", 0.83)],
        "gram schmidt": [("concept-1", "eigenvalue", 0.11)],
    }

    atlas = reconcile(
        [
            extraction("l1", concept("Eigenvalues", source="l1")),
            extraction("l1", concept("singular values", source="l1", start=60_000)),
            extraction("l1", concept("Gram-Schmidt", source="l1", start=120_000)),
        ],
        nearest=lambda name: similarities.get(name, []),
    )

    plans = {c.key: (c.decision, c.target_id) for c in atlas.concepts}
    assert plans["eigenvalue"] == ("merge", "concept-1")
    assert plans["singular value"][0] in {"merge", "review"}
    assert plans["gram schmidt"][0] == "create"
    assert all(c.reason for c in atlas.concepts)


def test_edges_survive_only_between_concepts_the_atlas_has() -> None:
    relations = [
        Relation(
            source="Eigenvalue",
            target="determinant",
            kind=RelationKind.used_in,
            support=Support.source_supported,
            evidence=at("l1"),
        ),
        Relation(
            source="Eigenvalue",
            target="quantum mechanics",  # never extracted as a concept
            kind=RelationKind.used_in,
            support=Support.inferred,
            evidence=at("l1"),
        ),
    ]
    atlas = reconcile(
        [
            extraction(
                "l1",
                concept("Eigenvalue", source="l1"),
                concept("Determinant", source="l1"),
                relations=relations,
            ),
            extraction(
                "l2",
                concept("eigenvalue", source="l2"),
                concept("determinant", source="l2"),
                relations=[
                    Relation(
                        source="eigenvalue",
                        target="determinant",
                        kind=RelationKind.used_in,
                        support=Support.source_supported,
                        evidence=at("l2"),
                    )
                ],
            ),
        ]
    )

    assert [(e.source, e.target, e.kind) for e in atlas.edges] == [
        ("eigenvalue", "determinant", RelationKind.used_in)
    ]
    assert atlas.edges[0].lectures == ("l1", "l2")  # two lectures say so
    assert atlas.edges[0].source_supported


def test_a_generator_is_read_once_and_still_yields_edges() -> None:
    """The caller may stream a file; the edges pass must not find it empty."""
    items = (
        extraction(
            "l1",
            concept("Eigenvalue", source="l1"),
            concept("Determinant", source="l1"),
            relations=[
                Relation(
                    source="Eigenvalue",
                    target="Determinant",
                    kind=RelationKind.related_to,
                    support=Support.source_supported,
                    evidence=at("l1"),
                )
            ],
        )
        for _ in range(1)
    )
    atlas = reconcile(items)
    assert len(atlas.concepts) == 2 and len(atlas.edges) == 1
