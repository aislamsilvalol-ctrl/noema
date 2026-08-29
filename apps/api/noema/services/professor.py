"""Professor Noema: decides what a message needs, not what mode a button picked.

Manual mode selection (``ChatIn.mode``) still exists and `POST /ai/chat` is
untouched — this is an additive orchestration layer, not a replacement. It answers
one question per turn: *what is this message actually asking for*, then dispatches
to whatever already handles that (the existing tutor-chat stream, question
generation, card generation), each with the cost tier the action deserves.

Classification itself always runs on the economy tier — it is a cheap, structured,
one-token-out decision, and paying a premium price to decide which model to use
next would defeat the point of tiering at all.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.logging import get_logger
from noema.db.models import ModelTier
from noema.prompts import load
from noema.providers.base import (
    AIProvider,
    Message,
    ProviderError,
    Role,
    StructuredRequest,
    TaskClass,
)
from noema.providers.gateway import AIGateway
from noema.services.pricing import PricingService

if TYPE_CHECKING:
    from noema.core.config import Settings
    from noema.services.credentials import CredentialService

#: Same shape as ``noema.api.v1.deps.build_provider`` — passed in rather than
#: imported directly to avoid a cycle (``deps.py`` is the FastAPI-layer home
#: for provider construction; this module stays layer-agnostic underneath it).
BuildProvider = Callable[
    [str, "Settings", "CredentialService | None"], Awaitable[AIProvider]
]

log = get_logger(__name__)


class Intent(StrEnum):
    """What the student's message is actually asking for.

    Six, not the spec's full sixteen — each of these already has a real,
    working, tested backend action to dispatch to (tutor chat, question
    generation, card generation, exam mode). Extending this list is extending
    real capability, not just adding a label a message can be sorted into;
    the rest of the spec's modes wait for the phase that builds their
    dispatch target.
    """

    EXPLAIN = "explain"
    DEEPEN = "deepen"
    SUMMARIZE = "summarize"
    QUIZ_ME = "quiz_me"
    CREATE_FLASHCARD = "create_flashcard"
    CREATE_EXAM = "create_exam"


#: The tier each intent's *main* action deserves. Classification itself is
#: always economy, regardless of what it decides — see the module docstring.
#: CREATE_EXAM never actually calls a model (``start_exam`` only picks
#: already-generated questions at random) — economy here is just the honest
#: "cheapest available" default for a `plan()` lookup that has to resolve to
#: something, not a cost decision that matters.
INTENT_TIER: dict[Intent, ModelTier] = {
    Intent.EXPLAIN: ModelTier.STANDARD,
    Intent.DEEPEN: ModelTier.PREMIUM,
    Intent.SUMMARIZE: ModelTier.STANDARD,
    Intent.QUIZ_ME: ModelTier.STANDARD,
    Intent.CREATE_FLASHCARD: ModelTier.STANDARD,
    Intent.CREATE_EXAM: ModelTier.ECONOMY,
}

INTENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": [i.value for i in Intent],
        }
    },
    "required": ["intent"],
}


async def classify_intent(
    gateway: AIGateway, message: str, *, model: str | None
) -> Intent:
    """Classify a message, failing safe to :attr:`Intent.EXPLAIN`.

    A classification failure — the provider errors, returns something outside
    the schema, or times out — must never block the student's actual message.
    Falling back to the same behaviour the product had before this orchestrator
    existed is the correct failure mode, not a 500.
    """
    prompt = load("professor.classify_intent")
    try:
        payload = await gateway.structured(
            StructuredRequest(
                messages=[
                    Message(role=Role.SYSTEM, content=prompt.body),
                    Message(role=Role.USER, content=message),
                ],
                json_schema=INTENT_SCHEMA,
                task=TaskClass.CLASSIFY_INTENT,
                model=model,
            )
        )
        return Intent(payload["intent"])
    except (ProviderError, KeyError, ValueError) as exc:
        log.warning("professor.classify_failed", error=str(exc))
        return Intent.EXPLAIN


@dataclass(frozen=True, slots=True)
class TieredCall:
    """A gateway ready to call, and the specific model it should use.

    ``model`` is ``None`` when the tier has no pricing row yet or its provider
    could not be built (missing credentials, disabled in local mode) — the
    caller passes that straight through as ``ChatRequest.model``/
    ``StructuredRequest.model``, and ``None`` there means "use the provider's
    own default," the same graceful fallback every other caller already gets.
    """

    gateway: AIGateway
    model: str | None


async def tiered_gateway(
    tier: ModelTier,
    *,
    db: AsyncSession,
    default_gateway: AIGateway,
    build_provider: BuildProvider,
    settings: Settings,
    credentials: CredentialService | None,
) -> TieredCall:
    """Resolve a cost tier to a gateway and model, falling back honestly.

    ``default_gateway`` is the caller's already-built gateway (the same one an
    un-tiered call would use) — every failure path here returns it unchanged,
    so a missing price row, an unconfigured provider, or local mode disallowing
    a tier's provider degrades to ordinary untiered behaviour instead of a 500.
    """
    config = await PricingService(db).tier_config(tier)
    if config is None:
        return TieredCall(default_gateway, None)

    try:
        provider: AIProvider = await build_provider(
            config.provider, settings, credentials
        )
    except Exception as exc:
        log.warning(
            "professor.tier_provider_unavailable",
            tier=tier.value,
            provider=config.provider,
            error=str(exc),
        )
        return TieredCall(default_gateway, None)

    tiered = AIGateway(
        provider,
        retry=default_gateway.retry,
        record_usage=default_gateway.record_usage,
        budget=default_gateway.budget,
        embeddings=default_gateway.embeddings,
    )
    return TieredCall(tiered, config.model)


@dataclass(frozen=True, slots=True)
class DispatchPlan:
    """What to actually do with a classified intent, resolved once per turn."""

    intent: Intent
    task: TaskClass
    mode: str
    call: TieredCall


async def plan(
    intent: Intent,
    *,
    db: AsyncSession,
    default_gateway: AIGateway,
    build_provider: BuildProvider,
    settings: Settings,
    credentials: CredentialService | None,
) -> DispatchPlan:
    tier = INTENT_TIER[intent]
    call = await tiered_gateway(
        tier,
        db=db,
        default_gateway=default_gateway,
        build_provider=build_provider,
        settings=settings,
        credentials=credentials,
    )
    task = {
        Intent.EXPLAIN: TaskClass.TUTOR_CHAT,
        Intent.DEEPEN: TaskClass.TUTOR_CHAT,
        Intent.SUMMARIZE: TaskClass.SUMMARIZE,
        Intent.QUIZ_ME: TaskClass.GENERATE_QUESTIONS,
        Intent.CREATE_FLASHCARD: TaskClass.GENERATE_CARDS,
        # Nearest real classification for logging/consistency; start_exam()
        # never actually calls dispatch.call.gateway.
        Intent.CREATE_EXAM: TaskClass.GENERATE_QUESTIONS,
    }[intent]
    # Both EXPLAIN and DEEPEN stream the same "explain" prompt; DEEPEN's only
    # difference is the escalated tier resolved above, not different wording —
    # a genuinely different "go deeper" prompt is a reasonable future refinement,
    # not a gap this phase needs to close to be real and useful.
    mode = "summarize" if intent is Intent.SUMMARIZE else "explain"
    return DispatchPlan(intent=intent, task=task, mode=mode, call=call)


NEEDS_NOTEBOOK: frozenset[Intent] = frozenset(
    {Intent.QUIZ_ME, Intent.CREATE_FLASHCARD, Intent.CREATE_EXAM}
)


def needs_notebook_material(intent: Intent, notebook_id: uuid.UUID | None) -> bool:
    """Whether this intent needs a notebook with ingested material to act on.

    ``generate_questions``/``generate_cards`` already return an empty list for a
    notebook with no chunks — this only catches the *no notebook at all* case,
    the one situation those functions cannot degrade from since they require an
    id to query against.
    """
    return intent in NEEDS_NOTEBOOK and notebook_id is None
