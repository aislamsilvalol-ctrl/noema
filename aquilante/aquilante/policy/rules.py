"""A rule-and-score policy, deliberately.

Version 0 of the policy is rules over the learner state with an explicit
score per candidate action and structured reason codes. It is what a
careful teacher would do with the same numbers, and it is the baseline any
learned policy (a contextual bandit, later) must beat on *learning*
outcomes — not on engagement. Nothing here rewards time in app, streaks or
message counts.

Actions
-------
DIAGNOSTIC   the model is unsure what the learner knows: ask a cheap, informative question first
REVIEW       recall on a known concept is predicted to have dropped
LEARN        introduce the next concept whose prerequisites are in place
EXPLAIN      a recent failure on a concept that is being learned: another route to the idea
PRACTICE     the concept is learning-but-not-yet-stable: a graded question
CHALLENGE    everything in scope is mastered and stable: a harder item or a connection
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Action(StrEnum):
    diagnostic = "DIAGNOSTIC"
    review = "REVIEW"
    learn = "LEARN"
    explain = "EXPLAIN"
    practice = "PRACTICE"
    challenge = "CHALLENGE"


@dataclass
class Recommendation:
    action: Action
    concept_id: str | None
    score: float
    reasons: list[str] = field(default_factory=list)
    alternatives: list[tuple[str, str | None, float]] = field(default_factory=list)
    suggested_difficulty: float | None = None

    def as_dict(self) -> dict:
        return {
            "action": self.action.value,
            "concept_id": self.concept_id,
            "score": round(self.score, 4),
            "reasons": self.reasons,
            "suggested_difficulty": self.suggested_difficulty,
            "alternatives": [(a, c, round(s, 4)) for a, c, s in self.alternatives],
        }


# thresholds, named so the reasons can cite them
UNCERTAIN = 0.35  # confidence below this → we do not trust the mastery estimate
RECALL_DUE = 0.75  # predicted recall below this → review
MASTERED = 0.8
LEARNING = 0.45


def recommend(
    states: dict[str, dict],
    *,
    prerequisites: dict[str, list[str]] | None = None,
    in_scope: list[str] | None = None,
) -> Recommendation:
    """``states``: concept_id → {mastery, confidence, recall, days_since, attempts, last_correct, wrong_streak}.

    ``prerequisites``: concept → list of prerequisite concept ids.
    ``in_scope``: the concepts the current curriculum allows (defaults to all known + all in prerequisites).
    """
    prerequisites = prerequisites or {}
    scope = list(in_scope or sorted(set(states) | set(prerequisites)))
    candidates: list[Recommendation] = []

    def st(c: str) -> dict:
        return states.get(
            c,
            {
                "mastery": 0.0,
                "confidence": 0.0,
                "recall": 0.0,
                "days_since": None,
                "attempts": 0,
                "last_correct": None,
                "wrong_streak": 0,
            },
        )

    for c in scope:
        s = st(c)
        m, conf, recall = s["mastery"], s["confidence"], s["recall"]
        attempts = s.get("attempts", 0)
        prereqs = prerequisites.get(c, [])
        weak_prereqs = [p for p in prereqs if st(p)["mastery"] < LEARNING and st(p)["attempts"] > 0]
        unknown_prereqs = [p for p in prereqs if st(p)["attempts"] == 0]

        if attempts > 0 and conf < UNCERTAIN:
            candidates.append(
                Recommendation(
                    Action.diagnostic,
                    c,
                    0.9 - conf,
                    [
                        f"confidence_low:{conf:.2f}<{UNCERTAIN}",
                        f"attempts:{attempts}",
                        f"mastery_unreliable:{m:.2f}",
                    ],
                    suggested_difficulty=0.5,
                )
            )
        if attempts > 0 and m >= LEARNING and recall < RECALL_DUE:
            reasons = [f"recall_predicted:{recall:.2f}<{RECALL_DUE}"]
            if s.get("days_since") is not None:
                reasons.append(f"days_since_practice:{s['days_since']:.1f}")
            candidates.append(
                Recommendation(
                    Action.review,
                    c,
                    0.6 + (RECALL_DUE - recall),
                    reasons,
                    suggested_difficulty=min(0.7, max(0.3, m)),
                )
            )
        if attempts > 0 and m < MASTERED and s.get("wrong_streak", 0) >= 2:
            candidates.append(
                Recommendation(
                    Action.explain,
                    c,
                    0.7 + 0.05 * min(s["wrong_streak"], 4),
                    [
                        f"wrong_streak:{s['wrong_streak']}",
                        f"mastery:{m:.2f}",
                        *[f"prerequisite_weak:{p}" for p in weak_prereqs],
                    ],
                    suggested_difficulty=0.3,
                )
            )
        if (
            attempts > 0
            and LEARNING <= m < MASTERED
            and recall >= RECALL_DUE
            and conf >= UNCERTAIN
            and s.get("wrong_streak", 0) < 2
        ):
            candidates.append(
                Recommendation(
                    Action.practice,
                    c,
                    0.5 + (MASTERED - m),
                    [f"mastery_learning:{m:.2f}", f"confidence:{conf:.2f}"],
                    suggested_difficulty=min(0.8, m + 0.15),
                )
            )
        if attempts == 0 and not weak_prereqs and not unknown_prereqs:
            ready = sum(1 for p in prereqs if st(p)["mastery"] >= MASTERED)
            candidates.append(
                Recommendation(
                    Action.learn,
                    c,
                    0.45 + 0.05 * ready,
                    ["not_started", *[f"prerequisite_ready:{p}" for p in prereqs]],
                    suggested_difficulty=0.35,
                )
            )

    if not candidates:
        stable = [c for c in scope if st(c)["mastery"] >= MASTERED]
        if stable:
            best = max(stable, key=lambda c: st(c)["recall"])
            return Recommendation(
                Action.challenge,
                best,
                0.4,
                ["all_in_scope_mastered", f"strongest_recall:{best}"],
                suggested_difficulty=0.8,
            )
        return Recommendation(
            Action.learn,
            scope[0] if scope else None,
            0.3,
            ["no_evidence_yet"],
            suggested_difficulty=0.35,
        )

    candidates.sort(key=lambda r: -r.score)
    top = candidates[0]
    top.alternatives = [(r.action.value, r.concept_id, r.score) for r in candidates[1:4]]
    return top
