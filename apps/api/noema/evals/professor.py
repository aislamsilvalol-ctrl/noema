"""Measuring the Professor: scripted learners, deterministic checks, a judge.

`noema.evals` measures retrieval. This measures the tutor itself — the part a
learner actually talks to — with the scenarios in
`evals/professor_scenarios.json`: a beginner, someone who is ahead, someone
confused, a wrong quiz answer, "me guia", a long session and so on, each a
short scripted conversation with what every turn must show.

Three layers, cheapest first:

* **Router cases** (`router_cases`) — for every scripted turn, the signal the
  regexes must (or must not) read and the move `decide()` must pick in a
  stated situation. Pure functions, no model, no database: this is what CI
  runs (`tests/test_professor_router_eval.py`).
* **Deterministic checks** (`check_turn`) — on a live run: the move the
  router actually chose, the reply's language, its length, "Sim" where it
  belongs and nowhere else, a closing question when one is due, steps when
  steps were asked for, a forbidden answer when "guide me" was said.
* **The judge** (`judge`) — an economy-tier structured call scoring every
  reply 1-5 on correctness, clarity, pedagogy, difficulty fit, continuity and
  non-repetition.

`run_scenario` drives the real engine in-process, the way `POST /ai/professor`
does (session found or started, learner turn written, `prepare`, `stream`,
lifecycle facts), and reads tokens and cost per turn from `ai_usage`.
`scripts/eval_professor.py` is the command line around it.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from collections.abc import AsyncIterator, Callable, Iterable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.config import Settings
from noema.db.models import AIUsage, TeachingTurn, User
from noema.professor.language import detect_language
from noema.prompts import load
from noema.providers.base import (
    AIProvider,
    ChatRequest,
    Message,
    Role,
    StreamEvent,
    StructuredRequest,
    TaskClass,
)
from noema.providers.gateway import AIGateway
from noema.services.credentials import CredentialService
from noema.services.professor import BuildProvider

__all__ = [
    "CRITERIA",
    "SCENARIOS",
    "Meter",
    "RouterCase",
    "ScenarioResult",
    "TurnResult",
    "check_turn",
    "detect_language",
    "judge",
    "load_scenarios",
    "render_report",
    "router_cases",
    "run_scenario",
    "usd_for",
]

SCENARIOS = Path(__file__).resolve().parents[4] / "evals" / "professor_scenarios.json"

CRITERIA: tuple[str, ...] = (
    "correctness",
    "clarity",
    "pedagogy",
    "difficulty_fit",
    "continuity",
    "non_repetition",
)

#: USD per million tokens (input, cached input, output), longest prefix wins.
#: Claude rows match `model_tier_configs` (migration 0014); OpenAI rows are
#: OpenAI's published prices — the fallback runs on its own default model,
#: which no tier row names, so `ai_usage.cost_cents` is 0 for it.
PRICES: dict[str, tuple[float, float, float]] = {
    "claude-haiku-4-5": (1.00, 0.10, 5.00),
    "claude-sonnet-5": (2.00, 0.20, 10.00),
    "claude-opus-5": (5.00, 0.50, 25.00),
    "gpt-4.1-mini": (0.40, 0.10, 1.60),
    "gpt-4.1-nano": (0.10, 0.025, 0.40),
    "gpt-4.1": (2.00, 0.50, 8.00),
    "gpt-4o-mini": (0.15, 0.075, 0.60),
    "gpt-4o": (2.50, 1.25, 10.00),
    "text-embedding-3-small": (0.02, 0.02, 0.0),
    "text-embedding-3-large": (0.13, 0.13, 0.0),
}


def load_scenarios(path: Path | None = None) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((path or SCENARIOS).read_text(encoding="utf-8"))
    return loaded


# ── Router cases (CI) ─────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class RouterCase:
    scenario: str
    turn: int
    text: str
    #: pattern · classifier · awaiting · first_turn · event
    via: str
    signal: str
    situation: dict[str, Any]
    moves: tuple[str, ...]
    strategy: str = ""

    @property
    def id(self) -> str:
        return f"{self.scenario}-{self.turn}"


def router_cases(scenarios: dict[str, Any] | None = None) -> list[RouterCase]:
    scenarios = scenarios or load_scenarios()
    cases: list[RouterCase] = []
    for scenario in scenarios["scenarios"]:
        for index, turn in enumerate(scenario["turns"], start=1):
            router = turn.get("router")
            if not router:
                continue
            cases.append(
                RouterCase(
                    scenario=scenario["id"],
                    turn=index,
                    text=turn.get("learner", ""),
                    via=router["via"],
                    signal=router["signal"],
                    situation=dict(router.get("situation") or {}),
                    moves=tuple(router["moves"]),
                    strategy=router.get("strategy", ""),
                )
            )
    return cases


# ── Deterministic checks ──────────────────────────────────────────────────

_WORD = re.compile(r"[a-zà-öø-ÿ]+", re.IGNORECASE)


def _strip_code(text: str) -> str:
    return re.sub(r"```.*?```|`[^`]*`", " ", text, flags=re.DOTALL)


def word_count(text: str) -> int:
    return len(_strip_code(text).split())


_YES = re.compile(
    r"^\W*(sim|yes|s[ií]|exato|exatamente|isso mesmo|correto|certo)\b", re.I
)


def opens_with_yes(text: str) -> bool:
    return bool(_YES.match(text.strip()))


def first_sentence(text: str) -> str:
    body = text.strip()
    match = re.search(r"(?<=[.!?])\s|\n", body)
    return body[: match.start()] if match else body


def ends_with_question(text: str, blocks: Sequence[dict[str, Any]]) -> bool:
    if any(b.get("tool") in ("quiz", "check") for b in blocks):
        return True
    tail = _strip_code(text).strip().rstrip("*_ )\"'»”")
    return tail.endswith("?") or "?" in tail[-160:].split("\n")[-1]


_STEP_LINE = re.compile(r"^\s*(\d+[.)]|passo \d|step \d|paso \d)", re.I | re.M)


def has_steps(text: str, blocks: Sequence[dict[str, Any]]) -> bool:
    if any(b.get("tool") == "steps" for b in blocks):
        return True
    return len(_STEP_LINE.findall(text)) >= 2


def overlap(a: str, b: str, n: int = 5) -> float:
    """Share of `a`'s word n-grams that also appear in `b`."""

    def grams(text: str) -> set[tuple[str, ...]]:
        words = [w.lower() for w in _WORD.findall(text)]
        return {tuple(words[i : i + n]) for i in range(len(words) - n + 1)}

    mine = grams(a)
    return len(mine & grams(b)) / len(mine) if mine else 0.0


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class TurnResult:
    index: int
    learner: str
    reply: str = ""
    move: str = ""
    signal: str = ""
    strategy: str = ""
    reason: str = ""
    situation: dict[str, Any] = field(default_factory=dict)
    skipped_ahead: bool = False
    position_before: tuple[int, int] = (0, 0)
    position_after: tuple[int, int] = (0, 0)
    concept_before: str = ""
    concept_after: str = ""
    #: The PEDAGOGY record the engine parsed from the reply (None: none came).
    pedagogy: dict[str, Any] | None = None
    blocks: list[dict[str, Any]] = field(default_factory=list)
    event: dict[str, Any] | None = None
    error: str = ""
    first_token_s: float = 0.0
    total_s: float = 0.0
    #: Every model call of the turn, metered from the provider's response.
    usage: list[dict[str, Any]] = field(default_factory=list)
    #: What `ai_usage` recorded for the same turn, for comparison.
    recorded: dict[str, Any] = field(default_factory=dict)
    checks: list[Check] = field(default_factory=list)
    scores: dict[str, int] = field(default_factory=dict)
    note: str = ""

    @property
    def cost_usd(self) -> float:
        return sum(float(u["cost_usd"]) for u in self.usage)

    @property
    def tokens(self) -> int:
        return sum(
            int(u["prompt_tokens"]) + int(u["completion_tokens"]) for u in self.usage
        )


@dataclass
class ScenarioResult:
    id: str
    title: str
    language: str
    turns: list[TurnResult] = field(default_factory=list)
    verdict: str = ""
    top_issue: str = ""
    judge_cost_usd: float = 0.0

    @property
    def checks(self) -> list[Check]:
        return [c for t in self.turns for c in t.checks]

    @property
    def cost_usd(self) -> float:
        return sum(t.cost_usd for t in self.turns) + self.judge_cost_usd

    def mean(self, criterion: str) -> float | None:
        values = [t.scores[criterion] for t in self.turns if criterion in t.scores]
        return sum(values) / len(values) if values else None


def check_turn(
    expect: dict[str, Any],
    turn: TurnResult,
    *,
    defaults: dict[str, Any] | None = None,
    earlier: Sequence[str] = (),
) -> list[Check]:
    """Every deterministic expectation of one turn, checked."""
    defaults = defaults or {}
    checks: list[Check] = []
    text = turn.reply
    if turn.error:
        return [Check("reply", False, turn.error)]
    if not text.strip():
        return [Check("reply", False, "empty reply")]

    moves = expect.get("moves")
    if moves:
        checks.append(Check("move", turn.move in moves, f"{turn.move} ∉ {moves}"))
    signals = expect.get("signals")
    if signals:
        checks.append(
            Check("signal", turn.signal in signals, f"{turn.signal} ∉ {signals}")
        )
    if "strategy" in expect:
        checks.append(
            Check(
                "strategy",
                turn.strategy == expect["strategy"],
                f"{turn.strategy} ≠ {expect['strategy']}",
            )
        )
    if "strategy_not" in expect:
        checks.append(
            Check(
                "strategy",
                turn.strategy not in expect["strategy_not"],
                f"{turn.strategy} repeated",
            )
        )
    lang = expect.get("lang")
    if lang:
        seen = detect_language(text)
        checks.append(Check("language", seen in (lang, ""), f"replied in {seen}"))

    words = word_count(text)
    low = int(expect.get("min_words", defaults.get("min_words", 0)))
    high = int(expect.get("max_words", defaults.get("max_words", 10_000)))
    checks.append(
        Check("length", low <= words <= high, f"{words} words ∉ [{low}, {high}]")
    )

    if "opens_with_yes" in expect:
        wanted = bool(expect["opens_with_yes"])
        checks.append(
            Check(
                "sim",
                opens_with_yes(text) == wanted,
                f"opens with {first_sentence(text)[:60]!r}",
            )
        )
    if "ends_with_question" in expect:
        wanted = bool(expect["ends_with_question"])
        checks.append(
            Check(
                "ends_with_question",
                ends_with_question(text, turn.blocks) == wanted,
                f"ends with {_strip_code(text).strip()[-80:]!r}",
            )
        )
    lowered = text.lower()
    if "contains_any" in expect:
        options = expect["contains_any"]
        checks.append(
            Check(
                "contains",
                any(o.lower() in lowered for o in options),
                f"none of {options}",
            )
        )
    if "first_sentence_contains" in expect:
        options = expect["first_sentence_contains"]
        head = first_sentence(text).lower()
        checks.append(
            Check(
                "answer_first",
                any(o.lower() in head for o in options),
                f"first sentence {first_sentence(text)[:100]!r}",
            )
        )
    for phrase in expect.get("not_contains", []):
        checks.append(
            Check("forbidden", phrase.lower() not in lowered, f"says {phrase!r}")
        )
    for pattern in expect.get("not_regex", []):
        found = re.search(pattern, _strip_code(text))
        checks.append(
            Check(
                "forbidden", found is None, f"matches {found.group(0)!r}" if found else ""
            )
        )
    if expect.get("numbered_steps"):
        checks.append(Check("steps", has_steps(text, turn.blocks), "no numbered steps"))
    tools = {b.get("tool") for b in turn.blocks}
    if "blocks_any" in expect:
        wanted_tools = set(expect["blocks_any"])
        checks.append(
            Check(
                "block",
                bool(tools & wanted_tools),
                f"blocks {sorted(str(t) for t in tools)}",
            )
        )
    if "blocks_none" in expect:
        unwanted = set(expect["blocks_none"])
        checks.append(
            Check(
                "block",
                not tools & unwanted,
                f"blocks {sorted(str(t) for t in tools & unwanted)}",
            )
        )
    if expect.get("position_advanced"):
        checks.append(
            Check(
                "moved_on",
                turn.skipped_ahead or turn.position_after != turn.position_before,
                f"still at lesson {turn.position_after}",
            )
        )
    if expect.get("stays"):
        # Checking a guess is not proof of being ahead: no lesson skipped.
        checks.append(
            Check(
                "stays",
                not turn.skipped_ahead and turn.position_after == turn.position_before,
                f"skipped from lesson {turn.position_before} to {turn.position_after}",
            )
        )
    if expect.get("moves_on"):
        # The next concept or the next lesson: either is moving on.
        checks.append(
            Check(
                "moved_on",
                turn.skipped_ahead
                or turn.position_after != turn.position_before
                or turn.concept_after != turn.concept_before,
                f"still on {turn.concept_after!r} at lesson {turn.position_after}",
            )
        )
    for i, previous in enumerate(earlier, start=1):
        share = overlap(text, previous)
        if share > 0.35:
            checks.append(
                Check("repetition", False, f"{share:.0%} of 5-grams repeat turn {i}")
            )
            break
    if turn.move in ("teach", "advance", "example", "answer"):
        # Paraphrase escapes the n-gram check: the same term defined again,
        # in new words, is the repetition a learner actually notices.
        # Defined here and before; or named in bold after two definitions
        # already ("**term**" carried into an example is fine once).
        counts: dict[str, int] = {}
        for previous in earlier:
            for term in defined_terms(previous):
                counts[term] = counts.get(term, 0) + 1
        again = sorted(
            (defined_terms(text) & counts.keys())
            | {t for t in bold_terms(text) if counts.get(t, 0) >= 2}
        )
        if again:
            checks.append(Check("redefinition", False, f"defines {again} again"))
    return checks


_BOLD = re.compile(r"\*\*([^*\n]{2,60})\*\*")
_DEFINED = re.compile(
    r"\*\*([^*\n]{2,60})\*\*,?\s+(?:é|são|is|are|es|son)\b", re.IGNORECASE
)


def bold_terms(text: str) -> set[str]:
    return {m.group(1).strip().lower() for m in _BOLD.finditer(text)}


def defined_terms(text: str) -> set[str]:
    """Terms the reply defines: "**term** é …" / "**term** is …"."""
    return {m.group(1).strip().lower() for m in _DEFINED.finditer(text)}


# ── Cost ──────────────────────────────────────────────────────────────────


def usd_for(model: str, prompt: int, cached: int, completion: int) -> float:
    """Published price of the model that answered; 0 for one not listed."""
    name = model.lower()
    key = next(
        (k for k in sorted(PRICES, key=len, reverse=True) if name.startswith(k)), None
    )
    if key is None:
        return 0.0
    fresh_rate, cached_rate, out_rate = PRICES[key]
    cached = max(0, min(cached, prompt))
    return (
        (prompt - cached) * fresh_rate + cached * cached_rate + completion * out_rate
    ) / 1_000_000


@dataclass(frozen=True, slots=True)
class Call:
    provider: str
    model: str
    kind: str
    prompt_tokens: int
    cached_tokens: int
    completion_tokens: int

    @property
    def cost_usd(self) -> float:
        return usd_for(
            self.model, self.prompt_tokens, self.cached_tokens, self.completion_tokens
        )


class Meter:
    """Every model call's tokens, read from the provider's own response.

    Independent of `ai_usage` on purpose: until 2026-10-08 the gateway wrote
    structured calls with no tokens and a stream answered by a fallback with
    model "unknown", and a second count is how that was seen. The eval
    instruments each provider it builds — `_post` for chat, structured and
    embeddings, `stream` for the tutor's reply — and the report sets the
    two side by side.
    """

    def __init__(self) -> None:
        self.calls: list[Call] = []
        self._taken = 0

    def take(self) -> list[Call]:
        fresh = self.calls[self._taken :]
        self._taken = len(self.calls)
        return fresh

    def wrap(self, build: BuildProvider) -> BuildProvider:
        async def built(
            name: str, settings: Settings, credentials: CredentialService | None
        ) -> AIProvider:
            return self.instrument(await build(name, settings, credentials))

        return built

    def instrument(self, provider: AIProvider) -> AIProvider:
        if getattr(provider, "_eval_metered", False):
            return provider
        name = provider.name
        default_model = str(getattr(provider, "model", ""))
        post = getattr(provider, "_post", None)
        if post is not None:

            async def metered_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
                data: dict[str, Any] = await post(path, payload)
                usage = data.get("usage") or {}
                details = usage.get("prompt_tokens_details") or {}
                self.calls.append(
                    Call(
                        name,
                        str(data.get("model") or payload.get("model") or ""),
                        path.strip("/").split("/")[-1],
                        int(usage.get("prompt_tokens", usage.get("input_tokens", 0))),
                        int(
                            details.get("cached_tokens", 0)
                            or usage.get("cache_read_input_tokens", 0)
                        ),
                        int(
                            usage.get("completion_tokens", usage.get("output_tokens", 0))
                        ),
                    )
                )
                return data

            setattr(provider, "_post", metered_post)  # noqa: B010
        stream = provider.stream

        async def metered_stream(request: ChatRequest) -> AsyncIterator[StreamEvent]:
            async for event in stream(request):
                if event.done and event.usage:
                    self.calls.append(
                        Call(
                            name,
                            event.model or request.model or default_model,
                            "stream",
                            event.usage.prompt_tokens,
                            event.usage.cached_tokens,
                            event.usage.completion_tokens,
                        )
                    )
                yield event

        setattr(provider, "stream", metered_stream)  # noqa: B010
        setattr(provider, "_eval_metered", True)  # noqa: B010
        return provider


def call_view(call: Call) -> dict[str, Any]:
    return {**asdict(call), "cost_usd": round(call.cost_usd, 6)}


async def recorded_usage(
    db: AsyncSession, owner_id: uuid.UUID, seen: set[uuid.UUID]
) -> dict[str, Any]:
    """What `ai_usage` wrote for this owner since the last read — kept beside
    the meter's numbers, so the gap between them stays visible."""
    rows = [
        r
        for r in await db.scalars(select(AIUsage).where(AIUsage.owner_id == owner_id))
        if r.id not in seen
    ]
    seen.update(r.id for r in rows)
    return {
        "rows": len(rows),
        "failed": sum(not r.succeeded for r in rows),
        "tokens": sum(r.prompt_tokens + r.completion_tokens for r in rows),
        "cost_usd": round(sum(r.cost_cents for r in rows) / 100, 6),
        "models": sorted({f"{r.provider}/{r.model}" for r in rows}),
    }


# ── The live driver ───────────────────────────────────────────────────────

#: Builds the engine for one turn: (db, user) -> ProfessorEngine.
EngineFactory = Callable[[AsyncSession, User], Any]


def parse_sse(chunk: bytes | str) -> list[tuple[str, dict[str, Any]]]:
    text = chunk.decode() if isinstance(chunk, bytes) else chunk
    events: list[tuple[str, dict[str, Any]]] = []
    for frame in text.strip("\n").split("\n\n"):
        lines = frame.split("\n")
        if len(lines) < 2:
            continue
        events.append(
            (
                lines[0].removeprefix("event: "),
                json.loads(lines[1].removeprefix("data: ")),
            )
        )
    return events


async def run_scenario(
    db: AsyncSession,
    *,
    user: User,
    scenario: dict[str, Any],
    engine_for: EngineFactory,
    meter: Meter,
    defaults: dict[str, Any] | None = None,
) -> ScenarioResult:
    """Play one scripted learner through the real engine, turn by turn.

    `engine_for` must build the engine on providers `meter` instruments
    (`meter.wrap(build_provider)`, `meter.instrument(...)` for the default
    gateway), or the turns come back with no cost."""
    from noema.professor.engine import LearningEvent
    from noema.services import learning_events
    from noema.services.teaching_session import TeachingSessions

    result = ScenarioResult(scenario["id"], scenario["title"], scenario["language"])
    seen: set[uuid.UUID] = set()
    meter.take()
    sessions = TeachingSessions(db, user.id)
    session_id: uuid.UUID | None = None

    for index, spec in enumerate(scenario["turns"], start=1):
        text = spec.get("learner", "")
        event: LearningEvent | None = None
        if spec.get("event"):
            event, text = await _scripted_event(db, user.id, session_id, spec["event"])
        turn = TurnResult(index=index, learner=text)
        turn.event = asdict(event) if event else None

        resumed = await sessions.start_or_resume(
            session_id=session_id, notebook_id=None, learning_goal=text
        )
        session = resumed.session
        session_id = session.id
        previous_turn_at = session.last_turn_at
        await sessions.record_learner(session, text)
        await db.commit()

        engine = engine_for(db, user)
        started = time.perf_counter()
        try:
            prepared = await engine.prepare(
                session=session,
                question=text,
                created=resumed.created,
                notebook_id=None,
                grounded_wanted=False,
                event=event,
                previous_turn_at=previous_turn_at,
            )
            await db.commit()
            journey = prepared.journey
            turn.move = prepared.decision.move.value
            turn.signal = prepared.decision.signal.value
            turn.strategy = prepared.decision.strategy
            turn.reason = prepared.decision.reason
            turn.skipped_ahead = prepared.skipped_ahead
            turn.situation = {
                k: v
                for k, v in asdict(prepared.situation).items()
                if v not in ("", False, 0, (), None)
            }
            # Where the previous turn left the journey: a skip inside
            # `prepare` has already moved it by now.
            turn.position_before = (
                result.turns[-1].position_after if result.turns else (0, 0)
            )
            turn.position_after = (journey.current_module, journey.current_lesson)
            turn.concept_before = result.turns[-1].concept_after if result.turns else ""
            text_parts: list[str] = []
            async for chunk in engine.stream(prepared, session=session, question=text):
                for name, data in parse_sse(chunk):
                    if name == "token":
                        if not text_parts:
                            turn.first_token_s = time.perf_counter() - started
                        text_parts.append(data["text"])
                    elif name == "block":
                        turn.blocks.append({"tool": data["tool"], "data": data["data"]})
                    elif name == "move":
                        turn.move = data["move"]
                    elif name == "error":
                        turn.error = str(data.get("message", "error"))
            turn.reply = "".join(text_parts)
            await learning_events.after_professor_turn(db, user.id, session.id)
            await db.commit()
            await db.refresh(journey)
            turn.position_after = (journey.current_module, journey.current_lesson)
            turn.concept_after = journey.current_concept or ""
            written = await db.scalar(
                select(TeachingTurn.pedagogy)
                .where(
                    TeachingTurn.session_id == session.id,
                    TeachingTurn.owner_id == user.id,
                )
                .order_by(TeachingTurn.created_at.desc())
                .limit(1)
            )
            turn.pedagogy = written if isinstance(written, dict) else None
        except Exception as exc:  # one broken turn is a finding, not a crash
            await db.rollback()
            turn.error = f"{type(exc).__name__}: {exc}"[:300]
        turn.total_s = time.perf_counter() - started
        turn.usage = [call_view(c) for c in meter.take()]
        turn.recorded = await recorded_usage(db, user.id, seen)
        turn.checks = check_turn(
            spec.get("expect", {}),
            turn,
            defaults=defaults,
            earlier=[t.reply for t in result.turns],
        )
        result.turns.append(turn)
    return result


async def _scripted_event(
    db: AsyncSession,
    owner_id: uuid.UUID,
    session_id: uuid.UUID | None,
    spec: dict[str, Any],
) -> tuple[Any, str]:
    """A quiz click on the latest quiz Mino asked: the wrong (or right)
    option, chosen by its answer key. Without a quiz, a typed wrong answer."""
    from noema.professor.engine import LearningEvent

    quiz: dict[str, Any] | None = None
    if session_id is not None:
        turns = list(
            await db.scalars(
                select(TeachingTurn)
                .where(
                    TeachingTurn.session_id == session_id,
                    TeachingTurn.owner_id == owner_id,
                )
                .order_by(TeachingTurn.created_at.desc())
                .limit(4)
            )
        )
        for row in turns:
            for record in row.blocks or []:
                if isinstance(record, dict) and record.get("tool") == "quiz":
                    quiz = dict(record.get("data") or {})
                    break
            if quiz:
                break
    if not quiz or not quiz.get("options"):
        return None, "Acho que a resposta é a primeira opção."
    options = [str(o) for o in quiz["options"]]
    key = int(quiz.get("answer", 0))
    wanted_right = spec.get("pick") == "right"
    chosen = options[key] if wanted_right else options[(key + 1) % len(options)]
    event = LearningEvent(
        kind="quiz",
        correct=wanted_right,
        question=str(quiz.get("question", ""))[:600],
        chosen=chosen[:300],
    )
    return event, chosen


# ── The judge ─────────────────────────────────────────────────────────────

JUDGE_PROMPT_VERSION = 1


def judge_schema(turns: int) -> dict[str, Any]:
    score = {"type": "integer", "minimum": 1, "maximum": 5}
    return {
        "type": "object",
        "properties": {
            "turns": {
                "type": "array",
                "minItems": turns,
                "maxItems": turns,
                "items": {
                    "type": "object",
                    "properties": {
                        "turn": {"type": "integer"},
                        **dict.fromkeys(CRITERIA, score),
                        "note": {"type": "string"},
                    },
                    "required": ["turn", *CRITERIA, "note"],
                },
            },
            "verdict": {"type": "string", "enum": ["pass", "fail"]},
            "top_issue": {"type": "string"},
        },
        "required": ["turns", "verdict", "top_issue"],
    }


def render_conversation(scenario: dict[str, Any], result: ScenarioResult) -> str:
    lines = [f"SCENARIO: {scenario['title']}", f"FOCUS: {scenario['judge_focus']}", ""]
    for turn in result.turns:
        learner = turn.learner
        if turn.event:
            learner = f"[clicked quiz option] {learner}"
        lines.append(f"LEARNER (turn {turn.index}): {learner}")
        blocks = "".join(
            f"\n[{b['tool']} block: {json.dumps(b['data'], ensure_ascii=False)[:400]}]"
            for b in turn.blocks
        )
        lines.append(
            f"TUTOR (turn {turn.index}, move={turn.move}): {turn.reply.strip()}{blocks}"
        )
        lines.append("")
    return "\n".join(lines)


async def judge(
    gateway: AIGateway,
    scenario: dict[str, Any],
    result: ScenarioResult,
    *,
    model: str | None,
) -> None:
    """Score every reply of `result` in place. A judge failure leaves the
    scores empty and says so in `top_issue`; the deterministic checks stand."""
    prompt = load("eval.judge_professor", JUDGE_PROMPT_VERSION)
    try:
        payload = await gateway.structured(
            StructuredRequest(
                messages=[
                    Message(role=Role.SYSTEM, content=prompt.body),
                    Message(
                        role=Role.USER, content=render_conversation(scenario, result)
                    ),
                ],
                json_schema=judge_schema(len(result.turns)),
                task=TaskClass.GRADE_OPEN_ANSWER,
                model=model,
                max_tokens=3000,
                metadata={"feature": "eval.judge"},
            )
        )
    except Exception as exc:
        result.top_issue = f"judge failed: {type(exc).__name__}: {exc}"[:300]
        return
    by_index = {int(t.get("turn", 0)): t for t in payload.get("turns", [])}
    for position, turn in enumerate(result.turns):
        graded = by_index.get(turn.index) or (
            payload["turns"][position] if position < len(payload["turns"]) else None
        )
        if not graded:
            continue
        turn.scores = {c: int(graded[c]) for c in CRITERIA if c in graded}
        turn.note = str(graded.get("note", ""))
    result.verdict = str(payload.get("verdict", ""))
    result.top_issue = str(payload.get("top_issue", ""))


# ── The report ────────────────────────────────────────────────────────────


def _fmt(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f}"


def _excerpt(text: str, limit: int = 420) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[:limit] + " …"


def overall(results: Iterable[ScenarioResult], criterion: str) -> float | None:
    values = [
        t.scores[criterion] for r in results for t in r.turns if criterion in t.scores
    ]
    return sum(values) / len(values) if values else None


def _evidenced(turns: Iterable[TurnResult]) -> int:
    return sum(bool(t.pedagogy and t.pedagogy.get("mastery_evidence")) for t in turns)


def render_report(results: Sequence[ScenarioResult], meta: dict[str, Any]) -> str:
    """The markdown report: summary tables first, failures, then transcripts."""
    checks = [c for r in results for c in r.checks]
    passed = sum(c.passed for c in checks)
    turns = [t for r in results for t in r.turns]
    cost = sum(r.cost_usd for r in results)
    out: list[str] = [
        f"# Professor eval — {meta.get('date', '')}",
        "",
        f"Revision `{meta.get('revision', '')}`. {len(results)} scenarios, "
        f"{len(turns)} learner turns, driven in-process through `ProfessorEngine` "
        f"against a fresh local database with the production provider routing "
        f"({meta.get('routing', '')}). Judge: {meta.get('judge', '')}.",
        "",
        f"Prompt versions: {meta.get('prompts', '')}.",
        "",
        f"**Deterministic checks: {passed}/{len(checks)} passed.** "
        f"**Total cost: ${cost:.4f}** "
        f"(tutor ${sum(t.cost_usd for t in turns):.4f}, judge "
        f"${sum(r.judge_cost_usd for r in results):.4f}). "
        f"Models that answered (calls): {meta.get('models', '')}.",
        "",
        f"Cost is metered from each provider response and priced at published "
        f"rates; for comparison, {meta.get('ai_usage', '')}.",
        "",
        *(
            [
                f"PEDAGOGY records parsed: {sum(t.pedagogy is not None for t in turns)}"
                f"/{len(turns)} replies; with mastery evidence: {_evidenced(turns)}.",
                "",
            ]
            if meta.get("pedagogy_captured")
            else []
        ),
        *([f"Note: {meta['rescored']}.", ""] if meta.get("rescored") else []),
        "## Per criterion (judge, 1 to 5, mean over all replies)",
        "",
        "| " + " | ".join(CRITERIA) + " |",
        "|" + "---|" * len(CRITERIA),
        "| " + " | ".join(_fmt(overall(results, c)) for c in CRITERIA) + " |",
        "",
        "## Per scenario",
        "",
        "| scenario | turns | checks | "
        + " | ".join(c.replace("_", " ") for c in CRITERIA)
        + " | verdict | avg latency | cost |",
        "|" + "---|" * (len(CRITERIA) + 6),
    ]
    for r in results:
        ok = sum(c.passed for c in r.checks)
        latency = sum(t.total_s for t in r.turns) / max(len(r.turns), 1)
        out.append(
            f"| {r.id} | {len(r.turns)} | {ok}/{len(r.checks)} | "
            + " | ".join(_fmt(r.mean(c)) for c in CRITERIA)
            + f" | {r.verdict or '—'} | {latency:.1f} s | ${r.cost_usd:.4f} |"
        )

    out += ["", "## Router decisions per turn", ""]
    out.append("| scenario | turn | learner | signal | move | strategy | checks failed |")
    out.append("|---|---|---|---|---|---|---|")
    for r in results:
        for t in r.turns:
            failed = ", ".join(c.name for c in t.checks if not c.passed) or "—"
            learner = _excerpt(t.learner, 60).replace("|", "\\|")
            out.append(
                f"| {r.id} | {t.index} | {learner} | {t.signal} | {t.move} | "
                f"{t.strategy} | {failed} |"
            )

    out += ["", "## Failed deterministic checks", ""]
    failures = [
        (r, t, c) for r in results for t in r.turns for c in t.checks if not c.passed
    ]
    if not failures:
        out.append("None.")
    for r, t, c in failures:
        out.append(f"- **{r.id} · turn {t.index} · {c.name}** — {c.detail}")

    out += ["", "## Judge: scenario verdicts and top issues", ""]
    for r in results:
        out.append(f"- **{r.id}** ({r.verdict or '—'}): {r.top_issue or '—'}")

    out += ["", "## Lowest-scored replies", ""]
    scored = [
        (min(t.scores.values()), r, t) for r in results for t in r.turns if t.scores
    ]
    for low, r, t in sorted(scored, key=lambda x: x[0])[:8]:
        if low >= 4:
            break
        worst = ", ".join(f"{k} {v}" for k, v in t.scores.items() if v == low)
        out += [
            f"### {r.id} · turn {t.index} ({worst})",
            "",
            f"> **Learner:** {_excerpt(t.learner, 200)}",
            ">",
            f"> **Mino ({t.move}):** {_excerpt(t.reply)}",
            "",
            f"Judge: {t.note}",
            "",
        ]

    out += ["", "## Transcripts", ""]
    for r in results:
        out += [f"### {r.id} — {r.title}", ""]
        for t in r.turns:
            usage = f"{t.tokens} tokens, ${t.cost_usd:.4f}"
            out += [
                f"**{t.index}. Learner:** {t.learner}",
                "",
                f"*{t.signal} → {t.move} ({t.strategy}); {t.reason}; "
                f"first token {t.first_token_s:.1f} s, total {t.total_s:.1f} s; {usage}*",
                "",
                "**Mino:** " + (_excerpt(t.reply, 1200) if t.reply else f"({t.error})"),
                "",
            ]
            if t.blocks:
                out.append(f"Blocks: {', '.join(b['tool'] for b in t.blocks)}")
                out.append("")
    return "\n".join(out) + "\n"


def as_json(results: Sequence[ScenarioResult], meta: dict[str, Any]) -> dict[str, Any]:
    def turn_json(t: TurnResult) -> dict[str, Any]:
        data = asdict(t)
        data["checks"] = [asdict(c) for c in t.checks]
        data["cost_usd"] = round(t.cost_usd, 6)
        return data

    return {
        "meta": meta,
        "criteria": {c: overall(results, c) for c in CRITERIA},
        "scenarios": [
            {
                "id": r.id,
                "title": r.title,
                "language": r.language,
                "verdict": r.verdict,
                "top_issue": r.top_issue,
                "judge_cost_usd": round(r.judge_cost_usd, 6),
                "cost_usd": round(r.cost_usd, 6),
                "means": {c: r.mean(c) for c in CRITERIA},
                "turns": [turn_json(t) for t in r.turns],
            }
            for r in results
        ],
    }


def from_json(data: dict[str, Any]) -> list[ScenarioResult]:
    """Results back from `as_json`, for rescoring without calling a model."""
    results: list[ScenarioResult] = []
    for s in data["scenarios"]:
        result = ScenarioResult(
            s["id"],
            s["title"],
            s["language"],
            verdict=s.get("verdict", ""),
            top_issue=s.get("top_issue", ""),
            judge_cost_usd=float(s.get("judge_cost_usd", 0.0)),
        )
        for t in s["turns"]:
            fields = {k: v for k, v in t.items() if k not in ("checks", "cost_usd")}
            fields["position_before"] = tuple(fields["position_before"])
            fields["position_after"] = tuple(fields["position_after"])
            turn = TurnResult(**fields)
            turn.checks = [Check(**c) for c in t["checks"]]
            result.turns.append(turn)
        results.append(result)
    return results


def rescore(
    results: Sequence[ScenarioResult], scenarios: dict[str, Any] | None = None
) -> None:
    """Run the deterministic checks again on stored replies — for a check
    that changed after a run, at no cost. Judge scores are kept."""
    scenarios = scenarios or load_scenarios()
    specs = {s["id"]: s for s in scenarios["scenarios"]}
    defaults = scenarios.get("defaults", {})
    for result in results:
        turns = specs[result.id]["turns"]
        for i, turn in enumerate(result.turns):
            if i and not turn.concept_before:
                turn.concept_before = result.turns[i - 1].concept_after
            turn.checks = check_turn(
                turns[i].get("expect", {}),
                turn,
                defaults=defaults,
                earlier=[t.reply for t in result.turns[:i]],
            )
