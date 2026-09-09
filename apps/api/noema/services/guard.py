"""Noema Guard: safety classification for a conversational turn.

Not a keyword blocklist that blindly refuses a topic -- a student of
medicine, chemistry, history, cybersecurity, or psychology can legitimately
need to discuss poisons, explosives, extremism, or exploits, and a naive
``if text.includes(word)`` filter would block all of that along with the
genuinely dangerous requests. See
``noema/prompts/guard.classify_content.v1.md`` for the actual judgment call
being asked for.

The cost shape is deliberate and was a real decision, not a default: a free,
substring-based heuristic runs on every single message. The overwhelming
majority match nothing and return ``SAFE`` at zero cost. Only a message that
touches one of a handful of dual-use topics escalates to a real LLM
classification (economy tier, structured output) -- this bounds the
per-message cost this layer adds to every conversational turn, forever, in
production. Calling an LLM on every message was considered and rejected
specifically for that reason.

Scope cut, stated plainly rather than silently: only ``ALLOW`` and ``BLOCK``
have real behavior wired today. A message classified ``RESTRICTED`` is
allowed and logged, not answered with a softened, context-constrained
response yet -- Focus Mode's ``<FOCUS_MODE>`` directive block
(``noema/professor/focus.py``) is the proven prompt-injection pattern a
later phase should copy for that. ``RiskLevel.BLOCKED`` (a hard,
heuristic-only, zero-tolerance category with no legitimate educational
framing to weigh -- the kind of content a real purpose-built classifier
exists for, not a hand-rolled keyword list) is likewise reserved in the
schema but not populated by this phase's heuristic; building or integrating
that classifier is real, separate, deliberately deferred work, not an
oversight.

Gated by ``settings.noema_guard_enabled`` (default off) -- disabled,
``evaluate()`` returns ``ALLOW`` before the heuristic even runs, so turning
this off is provably zero-cost and zero-behavior-change, not just "less."

Not to be confused with `sabelia/` (a separate, unrelated top-level Python
package: a learner-modeling ML research engine run in shadow mode via
``noema_sabelia_url``, see ``noema/services/professor.py`` neighbours).
Nothing in this module imports or depends on it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.config import Settings
from noema.core.logging import get_logger
from noema.db.models import RiskLevel, SafetyAction, SafetyEvent
from noema.prompts import load
from noema.providers.base import (
    Message,
    ProviderError,
    Role,
    StructuredRequest,
    TaskClass,
)
from noema.providers.gateway import AIGateway

log = get_logger(__name__)

#: Dual-use topics a bare keyword match cannot resolve on its own -- each one
#: escalates to a real classification call rather than deciding anything by
#: itself. Phrases, not single words: single words like "gun" or "drug" alone
#: appear constantly in ordinary academic writing and would escalate nearly
#: every history/chemistry/medicine conversation, defeating the point of a
#: free pre-filter. Bilingual (PT/EN) since the product serves both.
#:
#: A starting set, not a claim of completeness -- ``SafetyEvent`` rows are
#: exactly the observability this is meant to be tuned against over time.
_ESCALATE_PHRASES: dict[str, tuple[str, ...]] = {
    "self_harm": (
        "kill myself",
        "want to die",
        "end my life",
        "how to overdose",
        "me matar",
        "quero morrer",
        "tirar minha vida",
        "acabar com minha vida",
        "suicídio",
        "suicidio",
    ),
    "weapons_explosives": (
        "make a bomb",
        "build a bomb",
        "build an explosive",
        "synthesize an explosive",
        "3d print a gun",
        "fazer uma bomba",
        "construir uma bomba",
        "fabricar explosivo",
        "construir uma arma",
    ),
    "drugs_synthesis": (
        "synthesize meth",
        "make methamphetamine",
        "cook meth",
        "synthesize fentanyl",
        "sintetizar metanfetamina",
        "produzir droga sintética",
        "produzir droga sintetica",
        "fabricar droga",
    ),
    "malware_hacking": (
        "write ransomware",
        "write a virus to infect",
        "ddos attack script",
        "keylogger to steal",
        "exploit for cve",
        "invadir o sistema de",
        "invadir a conta de",
        "criar um vírus para",
        "criar um virus para",
    ),
    "extremism_violence": (
        "plan an attack on",
        "how to join isis",
        "mass shooting plan",
        "planejar um ataque",
        "atentado contra",
        "atirar em",
    ),
}

_GUARD_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "risk_level": {
            "type": "string",
            "enum": ["safe", "sensitive", "restricted", "high_risk"],
        },
        "category": {"type": "string"},
    },
    "required": ["risk_level", "category"],
}

#: What Noema Guard actually does about each risk level, in this phase --
#: see the module docstring's scope cut. SAFE is never logged at all (the
#: caller short-circuits before reaching this map); the rest are.
_POLICY: dict[RiskLevel, SafetyAction] = {
    RiskLevel.SAFE: SafetyAction.ALLOW,
    RiskLevel.SENSITIVE: SafetyAction.ALLOW,
    RiskLevel.RESTRICTED: SafetyAction.ALLOW,
    RiskLevel.HIGH_RISK: SafetyAction.BLOCK,
    RiskLevel.BLOCKED: SafetyAction.BLOCK,
}

#: Shown to the student instead of a generation when Guard blocks a turn.
#: Deliberately not preachy or clinical -- matches Mino's own "don't sound
#: like customer support" tone (``noema/prompts/mino.persona.v1.md``).
BLOCKED_MESSAGE = (
    "Não posso ajudar com esse pedido específico. Se o que você quer é "
    "entender o assunto por outro ângulo -- teoria, contexto, história, "
    "prevenção -- me pergunta assim que eu ajudo."
)


@dataclass(frozen=True, slots=True)
class GuardDecision:
    risk_level: RiskLevel
    action: SafetyAction
    category: str
    escalated: bool

    @property
    def blocks_generation(self) -> bool:
        return self.action is SafetyAction.BLOCK


def _heuristic_category(message: str) -> str | None:
    lowered = message.lower()
    for category, phrases in _ESCALATE_PHRASES.items():
        if any(phrase in lowered for phrase in phrases):
            return category
    return None


class NoemaGuard:
    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self._db = db
        self._settings = settings

    async def evaluate(
        self,
        message: str,
        *,
        user_id: uuid.UUID,
        gateway: AIGateway,
        model: str | None,
    ) -> GuardDecision:
        if not self._settings.noema_guard_enabled:
            return GuardDecision(RiskLevel.SAFE, SafetyAction.ALLOW, "none", False)

        category = _heuristic_category(message)
        if category is None:
            return GuardDecision(RiskLevel.SAFE, SafetyAction.ALLOW, "none", False)

        risk_level, resolved_category = await self._classify(
            message, gateway=gateway, model=model, hint=category
        )
        action = _POLICY[risk_level]

        if risk_level is not RiskLevel.SAFE:
            self._db.add(
                SafetyEvent(
                    user_id=user_id,
                    category=resolved_category,
                    risk_level=risk_level,
                    action=action,
                    escalated=True,
                )
            )
            await self._db.flush()

        return GuardDecision(risk_level, action, resolved_category, True)

    async def _classify(
        self, message: str, *, gateway: AIGateway, model: str | None, hint: str
    ) -> tuple[RiskLevel, str]:
        """Fails safe to SENSITIVE, not SAFE or HIGH_RISK.

        A classification failure must not silently wave through something the
        heuristic already flagged (SAFE), nor block a real student's turn on
        every transient provider hiccup (HIGH_RISK) -- the least disruptive
        real option is "allow, but log it."
        """
        prompt = load("guard.classify_content")
        try:
            payload = await gateway.structured(
                StructuredRequest(
                    messages=[
                        Message(role=Role.SYSTEM, content=prompt.body),
                        Message(role=Role.USER, content=message),
                    ],
                    json_schema=_GUARD_SCHEMA,
                    task=TaskClass.MODERATE_CONTENT,
                    model=model,
                )
            )
            return RiskLevel(payload["risk_level"]), str(payload["category"])
        except (ProviderError, KeyError, ValueError) as exc:
            log.warning("guard.classify_failed", error=str(exc), hint=hint)
            return RiskLevel.SENSITIVE, hint
