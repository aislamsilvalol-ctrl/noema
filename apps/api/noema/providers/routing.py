"""Weighted interleaving between providers (``NOEMA_AI_ROUTING``).

Without a policy the gateway asks its primary first and the others only when
it fails. With one, each call picks its first provider by weight among the
ones whose circuit is not open, and the rest follow in weight order as the
fallback chain.

A call that carries a key (a teaching session, else the learner) always
lands on the same provider while that provider is healthy, so Mino keeps one
voice across a lesson. The choice is rendezvous hashing weighted by
``-ln(u)``: each provider draws a score from the key, the highest wins, and
over many keys a provider wins in proportion to its weight. Taking a provider
out (open circuit) only moves the keys it was winning; when it closes again
they move back and nobody else's do.
"""

from __future__ import annotations

import hashlib
import math
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from noema.providers.base import AIProvider

__all__ = ["RoutingPolicy"]


@dataclass(frozen=True, slots=True)
class RoutingPolicy:
    #: Provider name → weight, in the order the setting listed them.
    weights: tuple[tuple[str, float], ...]

    @classmethod
    def parse(cls, spec: str) -> RoutingPolicy | None:
        """``"anthropic:50,openai:50"`` → a policy; empty → None (no routing).

        A malformed entry raises: a typo in a deployment variable should stop
        the boot, not quietly send every lesson to one provider.
        """
        entries: list[tuple[str, float]] = []
        for raw in spec.split(","):
            item = raw.strip()
            if not item:
                continue
            name, sep, weight = item.partition(":")
            name = name.strip().lower()
            if not name or not sep:
                raise ValueError(f"NOEMA_AI_ROUTING entry {item!r} is not name:weight")
            try:
                value = float(weight)
            except ValueError as exc:
                raise ValueError(
                    f"NOEMA_AI_ROUTING weight for {name!r} is not a number"
                ) from exc
            if value < 0 or not math.isfinite(value):
                raise ValueError(f"NOEMA_AI_ROUTING weight for {name!r} must be >= 0")
            if any(n == name for n, _ in entries):
                raise ValueError(f"NOEMA_AI_ROUTING names {name!r} twice")
            entries.append((name, value))
        if not entries:
            return None
        return cls(tuple(entries))

    def weight(self, name: str) -> float:
        return next((w for n, w in self.weights if n == name), 0.0)

    def order(
        self,
        providers: Sequence[AIProvider],
        *,
        key: str | None,
        eligible: Callable[[AIProvider], bool],
        rng: random.Random | None = None,
    ) -> list[AIProvider]:
        """`providers` in the order this call should try them.

        Weight 0, or a provider the setting does not name, is never chosen
        first but stays in the chain as a last resort. When every weighted
        provider is out, the chain is plain weight order and the gateway's
        own circuit checks decide.
        """
        by_weight = sorted(
            providers,
            key=lambda p: -self.weight(p.name),  # stable: ties keep chain order
        )
        candidates = [p for p in by_weight if self.weight(p.name) > 0 and eligible(p)]
        if not candidates:
            return by_weight
        first = (
            _rendezvous(candidates, key, self.weight)
            if key
            else _weighted_random(candidates, self.weight, rng or _rng)
        )
        return [first, *(p for p in by_weight if p is not first)]


_rng = random.Random()  # noqa: S311 -- load spreading, not cryptography


def _weighted_random(
    candidates: Sequence[AIProvider],
    weight: Callable[[str], float],
    rng: random.Random,
) -> AIProvider:
    return rng.choices(list(candidates), weights=[weight(p.name) for p in candidates])[0]


def _rendezvous(
    candidates: Sequence[AIProvider], key: str, weight: Callable[[str], float]
) -> AIProvider:
    def score(provider: AIProvider) -> float:
        digest = hashlib.sha256(f"{key}\x00{provider.name}".encode()).digest()
        # Uniform in (0, 1), never 0 or 1, so the logarithm is finite and < 0.
        unit = (int.from_bytes(digest[:8], "big") + 1) / (2**64 + 1)
        return weight(provider.name) / -math.log(unit)

    return max(candidates, key=score)
