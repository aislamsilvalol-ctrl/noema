"""Sabelia in shadow: recorded beside the Professor's decision, never acted on.

The engine has earned a benchmark on a public dataset, not a place in a
lesson. This module is the honest middle step: when ``NOEMA_SABELIA_URL``
points at a running Sabelia service, every turn sends that learner's recent
evidence and asks what the engine would recommend; the answer goes into the
turn's decision record under ``shadow`` and is read by nobody. The
Professor's own router decides the move exactly as before.

Three rules hold it in place:

* **Off unless configured.** No URL, or no export secret, and every call
  returns ``None`` without touching the network.
* **Never a failure path.** Timeouts, connection errors, bad payloads and
  slow responses are swallowed and logged; the caller gets ``None``.
  The budget is a few hundred milliseconds, not a retry policy.
* **Pseudonymous.** The engine sees ``u_<hmac>`` and educational
  quantities. No name, no e-mail, no text: the same boundary the export
  keeps (``noema.services.learning_export``).

When enough shadow turns have accumulated, ``scripts/shadow-eval.py``
compares the two on the product's own exported events. Until that comparison
favours the engine, this is all it does.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

import httpx

from noema.core.config import Settings
from noema.core.logging import get_logger
from noema.services.learning_export import pseudonym

log = get_logger(__name__)

#: How much recent evidence is sent. A lesson's working set, not a history.
MAX_EVENTS = 400


@dataclass(frozen=True, slots=True)
class ShadowResult:
    """What the engine said, and how long it took to say it."""

    model: str
    action: str
    concept: str | None
    reasons: list[str]
    recall: float | None
    mastery: float | None
    events: int
    latency_ms: int

    def as_record(self) -> dict[str, Any]:
        return {
            "engine": "sabelia",
            "model": self.model,
            "action": self.action,
            "concept": self.concept,
            "reasons": self.reasons,
            "recall": self.recall,
            "mastery": self.mastery,
            "events": self.events,
            "latency_ms": self.latency_ms,
        }


def enabled(settings: Settings) -> bool:
    return bool(settings.noema_sabelia_url and settings.noema_export_secret)


def _events_payload(student_id: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mastery events → LearningEvent v1, the shape the engine reads.

    Kept in this module rather than shared with the export because the export
    writes files and this writes a request body; both speak the same schema
    and neither copies text.
    """
    events: list[dict[str, Any]] = []
    for row in rows[-MAX_EVENTS:]:
        graded = row["kind"] in {"quiz", "check", "flashcard", "assessment"}
        events.append(
            {
                "schema_version": 1,
                "event_id": str(row["id"]),
                "student_id": student_id,
                "concept_id": row["concept_id"] or f"name:{row['concept_name']}",
                "item_id": row["item_id"],
                "timestamp": row["created_at"].timestamp(),
                "event_type": "answer" if graded else "exposure",
                "correct": (row["score"] >= 0.6) if graded else None,
                "score": row["score"],
                "elapsed_ms": row["elapsed_ms"],
                "difficulty": row["difficulty"],
                "confidence": row["confidence"],
                "source": "noema",
            }
        )
    return events


async def ask(
    settings: Settings,
    user_id: uuid.UUID,
    rows: list[dict[str, Any]],
    *,
    client: httpx.AsyncClient | None = None,
) -> ShadowResult | None:
    """Send the learner's recent evidence and return the engine's recommendation.

    ``rows`` are plain dicts of mastery-event columns, already loaded by the
    caller — this function opens no database session and holds no ORM object,
    so a slow service cannot pin a connection.
    """
    if not enabled(settings) or not rows:
        return None
    student_id = pseudonym(settings.noema_export_secret, user_id)
    budget = max(0.05, settings.noema_sabelia_timeout_ms / 1000)
    base = settings.noema_sabelia_url.rstrip("/")
    started = time.perf_counter()
    own = client is None
    client = client or httpx.AsyncClient(timeout=budget)
    try:
        posted = await client.post(
            f"{base}/events", json={"events": _events_payload(student_id, rows)}
        )
        posted.raise_for_status()
        response = await client.get(f"{base}/learner/{student_id}/recommend")
        response.raise_for_status()
        recommendation = response.json()
        state = (await client.get(f"{base}/learner/{student_id}/state")).json()
    except Exception as exc:  # every failure is the same failure: no shadow
        log.info("professor.shadow.unavailable", error=type(exc).__name__)
        return None
    finally:
        if own:
            await client.aclose()
    latency_ms = int((time.perf_counter() - started) * 1000)
    concept = recommendation.get("concept_id")
    concept_state = (state.get("concepts") or {}).get(concept) or {}
    return ShadowResult(
        model=str(state.get("model") or "unknown"),
        action=str(recommendation.get("action") or "unknown"),
        concept=concept,
        reasons=[str(r) for r in (recommendation.get("reasons") or [])][:6],
        recall=concept_state.get("recall"),
        mastery=concept_state.get("mastery"),
        events=int(state.get("events") or 0),
        latency_ms=latency_ms,
    )
