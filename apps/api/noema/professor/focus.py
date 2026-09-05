"""Focus mode (TDAH / ADHD-friendly learning): attention-aware delivery.

Nothing here diagnoses anything. The mode is a learner's preference — "more
interaction, shorter sessions, less padding" — and this module turns it into
three things the engine can act on:

- `CognitiveLoad`: how much one reply may carry (words, concepts, examples)
  and how often the learner is asked to do something. The chunk level adapts
  from product signals only: quick right answers widen the chunks, wrong
  answers and "não entendi" narrow them. It never sticks at five-word lines.
- `Pulse` (the AttentionPulseEngine): what the lesson can tell from product
  signals alone — time away, "me perdi", wrong streaks, long sittings — and
  what the router should do about it (reorient, welcome back, offer a pause).
- The `CuriosityParkingLot`: side questions kept for later instead of
  derailing the current objective, and offered back when the lesson closes.

The same depth, another rhythm. Content is never simplified; delivery is.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from noema.db.base import utcnow
from noema.db.models import LearningJourney, StudentConceptState, TeachingSession, User

__all__ = [
    "AWAY_AFTER",
    "CognitiveLoad",
    "Pulse",
    "adapt_focus_profile",
    "learning_mode",
    "load_for",
    "park_topic",
    "parked_topics",
    "pulse_for",
    "recap",
    "render_focus_directive",
    "unpark_topic",
]

#: Coming back after this long is "returning", not "continuing".
AWAY_AFTER = timedelta(hours=6)
#: A sitting this long earns an offer of a pause (never an interruption).
LONG_SESSION_TURNS = 40

MODES = ("normal", "focus")
CHUNK_LEVELS = {
    # words per reply · concepts · examples · ask every N teaching moves
    1: (90, 1, 1, 1),
    2: (160, 1, 1, 1),
    3: (260, 2, 2, 2),
}


def learning_mode(user: User) -> str:
    mode = str((user.settings or {}).get("learning_mode", "normal"))
    return mode if mode in MODES else "normal"


@dataclass(frozen=True, slots=True)
class CognitiveLoad:
    mode: str
    chunk_level: int
    max_words: int
    concepts: int
    examples: int
    ask_every: int
    #: Preferred sitting length in minutes, from the learner's settings.
    session_minutes: int

    @property
    def focus(self) -> bool:
        return self.mode == "focus"

    @property
    def max_tokens(self) -> int:
        # Words → tokens with room for a block and the PEDAGOGY record.
        return int(self.max_words * 1.6) + 450 if self.focus else 1900


def load_for(user: User, journey: LearningJourney) -> CognitiveLoad:
    mode = learning_mode(user)
    focus_profile = dict((journey.profile or {}).get("focus", {}))
    level = int(focus_profile.get("chunk_level", 1))
    level = max(1, min(3, level))
    words, concepts, examples, ask_every = CHUNK_LEVELS[level]
    minutes = int((user.settings or {}).get("session_minutes", 7))
    if mode != "focus":
        return CognitiveLoad(
            mode=mode,
            chunk_level=3,
            max_words=320,
            concepts=2,
            examples=2,
            ask_every=3,
            session_minutes=max(5, minutes),
        )
    return CognitiveLoad(
        mode=mode,
        chunk_level=level,
        max_words=words,
        concepts=concepts,
        examples=examples,
        ask_every=ask_every,
        session_minutes=max(3, min(15, minutes)),
    )


def adapt_focus_profile(
    profile: dict[str, Any], *, outcome: str, seconds_to_answer: float | None = None
) -> dict[str, Any]:
    """The chunk level after one showing. Pure; returns a new profile dict.

    `outcome`: "right" · "wrong" · "confused" · "lost". Two quick right
    answers in a row widen the chunks; any wrong, confused or lost narrows
    them. The pattern that worked is remembered by the compactor's
    `learner_patterns`, not here.
    """
    focus = dict(profile.get("focus", {}))
    level = max(1, min(3, int(focus.get("chunk_level", 1))))
    streak = int(focus.get("right_streak", 0))
    history = list(focus.get("recovery", []))
    if outcome == "right":
        quick = seconds_to_answer is None or seconds_to_answer < 45
        streak = streak + 1 if quick else streak
        if streak >= 2 and level < 3:
            level += 1
            streak = 0
    else:
        streak = 0
        if level > 1:
            level -= 1
        if outcome in ("lost", "confused"):
            history = [*history, outcome][-10:]
    focus.update({"chunk_level": level, "right_streak": streak, "recovery": history})
    updated = dict(profile)
    updated["focus"] = focus
    return updated


@dataclass(frozen=True, slots=True)
class Pulse:
    """What the product signals say about attention right now."""

    #: The learner pressed "me perdi".
    lost: bool = False
    #: Back after more than AWAY_AFTER since the last turn.
    returned: bool = False
    hours_away: float = 0.0
    #: The learner answered the welcome-back recall: remember · partly · forgot.
    recall: str = ""
    #: A side question worth parking (focus mode only).
    side_question: bool = False
    #: Many turns in one sitting: offer a pause, never force one.
    long_session: bool = False
    #: A parked topic the lesson can offer back now.
    offer_parked: str = ""


def pulse_for(
    session: TeachingSession,
    journey: LearningJourney,
    *,
    event_kind: str,
    event_answer: str,
    side_question: bool,
    closing: bool,
    last_turn_at: datetime | None = None,
    now: datetime | None = None,
) -> Pulse:
    """`last_turn_at` is the learner's previous turn — passed in by the route,
    which reads it before writing this turn (the row's own value is already
    "now" by the time the engine runs)."""
    now = now or utcnow()
    last = last_turn_at if last_turn_at is not None else session.last_turn_at
    away = 0.0
    if last is not None and session.turn_count > 1:
        if last.tzinfo is None:
            last = last.replace(tzinfo=now.tzinfo)
        away = (now - last).total_seconds() / 3600
    returned = away * 3600 > AWAY_AFTER.total_seconds() and event_kind not in (
        "recall",
        "lost",
    )
    parked = parked_topics(journey)
    return Pulse(
        lost=event_kind == "lost",
        returned=returned,
        hours_away=round(away, 1),
        recall=event_answer if event_kind == "recall" else "",
        side_question=side_question,
        long_session=session.turn_count >= LONG_SESSION_TURNS
        and session.turn_count % 20 == 0,
        offer_parked=parked[0]["topic"] if closing and parked else "",
    )


# ── the parking lot ───────────────────────────────────────────────────────


def parked_topics(journey: LearningJourney) -> list[dict[str, Any]]:
    return [
        t for t in list(journey.parked or []) if isinstance(t, dict) and t.get("topic")
    ]


def park_topic(
    journey: LearningJourney, topic: str, *, now: datetime | None = None
) -> None:
    topic = " ".join(topic.split())[:200]
    if not topic:
        return
    now = now or utcnow()
    kept = [t for t in parked_topics(journey) if t["topic"].lower() != topic.lower()]
    journey.parked = [*kept, {"topic": topic, "parked_at": now.isoformat()}][-12:]


def unpark_topic(journey: LearningJourney, topic: str) -> None:
    journey.parked = [
        t for t in parked_topics(journey) if t["topic"].lower() != topic.lower()
    ]


# ── the recap ("resume pra mim") ──────────────────────────────────────────


def recap(
    journey: LearningJourney, states: list[StudentConceptState], next_lessons: list[str]
) -> dict[str, Any]:
    """Ten-second recap from the state alone — no model call.

    YOU KNOW: concepts shown (mastered / learning). NOW: the current concept.
    NEXT: the lessons after this one.
    """
    know = [s.name for s in states if s.state in ("mastered", "learning")][:6]
    shaky = [s.name for s in states if s.state in ("uncertain", "needs_review")][:4]
    return {
        "know": know,
        "shaky": shaky,
        "now": journey.current_concept,
        "next": next_lessons[:2],
        "parked": [t["topic"] for t in parked_topics(journey)][:3],
    }


# ── the directive ─────────────────────────────────────────────────────────


def render_focus_directive(
    load: CognitiveLoad,
    pulse: Pulse,
    *,
    mission: str,
    session_concepts: list[str],
    done: list[str],
    current: str,
    communication: dict[str, Any] | None = None,
) -> str:
    """The FOCUS block of the turn directive. Delivery rules only."""
    lines = [
        "<FOCUS_MODE>",
        "The learner chose Focus mode: same depth, another rhythm. Deliver in "
        f"short bursts — at most ~{load.max_words} words this turn, {load.concepts} "
        f"concept{'s' if load.concepts > 1 else ''}, {load.examples} example"
        f"{'s' if load.examples > 1 else ''}. One thing at a time; the next thing "
        "only after they respond. Short lines, whitespace, a hook before the "
        "term. Never infantile, never slang for its own sake.",
    ]
    if mission:
        lines.append(f"Mission of this sitting: {mission}")
    if session_concepts:
        marks = []
        for name in session_concepts:
            if name in done:
                marks.append(f"● {name} ✓")
            elif name == current:
                marks.append(f"● {name} ← now")
            else:
                marks.append(f"○ {name}")
        lines.append("Session map (the learner sees this too): " + " · ".join(marks))
    if pulse.long_session:
        lines.append(
            "This has been a long sitting. If it fits, offer a pause in one line — "
            "an offer, never an instruction, never a health remark."
        )
    if pulse.offer_parked:
        lines.append(
            f"The learner parked a curiosity earlier: '{pulse.offer_parked}'. As the "
            "lesson closes, offer to pull that thread now — one line."
        )
    if communication:
        bits = [f"{k}: {v}" for k, v in communication.items() if v]
        if bits:
            lines.append(
                "How this learner likes to be talked to: " + "; ".join(bits) + "."
            )
    lines.append("</FOCUS_MODE>")
    return "\n".join(lines)


def communication_profile(journey: LearningJourney) -> dict[str, Any]:
    """StudentCommunicationProfile, as stored: educational preferences only."""
    raw = dict((journey.profile or {}).get("communication", {}))
    return {
        key: raw[key]
        for key in (
            "formality",
            "verbosity",
            "humor_tolerance",
            "explanation_depth",
            "interaction_frequency",
            "encouragement_preference",
        )
        if raw.get(key)
    }


def adapt_communication(profile: dict[str, Any], *, signal: str) -> dict[str, Any]:
    """Gradual: one nudge per clear signal, never a swing."""
    comm = dict(profile.get("communication", {}))
    if signal in ("confused", "lost"):
        comm["verbosity"] = "lower"
        comm["interaction_frequency"] = "higher"
    elif signal == "knows":
        comm["explanation_depth"] = "deeper"
    elif signal == "wants_depth":
        comm["explanation_depth"] = "deeper"
        comm["verbosity"] = "higher"
    elif signal == "tired":
        comm["encouragement_preference"] = "brief"
    updated = dict(profile)
    updated["communication"] = comm
    return updated


@dataclass
class FocusTurn:
    """Everything the engine computed about focus for one turn."""

    load: CognitiveLoad
    pulse: Pulse
    directive: str = ""
    extras: dict[str, Any] = field(default_factory=dict)
