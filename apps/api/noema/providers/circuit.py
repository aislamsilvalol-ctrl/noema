"""Per-provider circuit breakers.

Retries handle a provider that blips. They make an outage worse: with three
attempts and backoff, every lesson turn during an upstream outage waits through
the whole retry ladder before reaching the fallback, and keeps hammering a
service that is already down. A breaker remembers: after enough consecutive
failures it opens, calls skip that provider and go straight to the next one in
the chain, and after a cooldown one probe call is let through to see whether
it recovered.

In-process on purpose. Each API process learns about an outage from its own
calls within a few seconds; sharing state through Redis would add a dependency
to the path that exists to survive dependencies failing.

Only failures that say the *service* is unhealthy count: timeouts, transport
errors, 429 and 5xx. A 400 or 401 means the provider answered — and with BYOK
it may be one learner's bad key, which must not switch the provider off for
everyone else.

One exception reads like a 400 and is an outage: the deployment's account is
out of credit (``CreditExhausted``). Nothing sent to that provider can succeed
until someone pays, so the circuit opens on the first one and stays open for
``billing_cooldown_seconds`` (10 minutes by default) instead of the usual 30
seconds. The gateway does not record it against a BYOK provider, for the
reason above.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import httpx

from noema.providers.base import CreditExhausted, ProviderError


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True, slots=True)
class BreakerPolicy:
    #: Consecutive counted failures that open the circuit...
    failure_threshold: int = 5
    #: ...when they all fall within this many seconds.
    window_seconds: float = 60.0
    #: How long an open circuit refuses before letting one probe through.
    cooldown_seconds: float = 30.0
    #: How long an out-of-credit provider is left alone before one probe.
    #: Topping up the account is a human action; probing every 30 seconds
    #: would only add a failed call to every half minute of lessons.
    billing_cooldown_seconds: float = 600.0


def counts_as_outage(exc: BaseException) -> bool:
    """Whether a failure says the provider itself is unhealthy."""
    if isinstance(exc, TimeoutError | CreditExhausted):
        return True
    if not isinstance(exc, ProviderError):
        return False
    if exc.status is not None:
        return exc.status == 429 or exc.status >= 500
    # No status: either the request never got an HTTP answer (transport) or
    # the answer was unusable (malformed JSON). Only the first is an outage.
    return isinstance(exc.__cause__, httpx.TransportError | TimeoutError) or bool(
        getattr(exc, "timed_out", False)
    )


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        policy: BreakerPolicy | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.name = name
        self.policy = policy or BreakerPolicy()
        self._clock = clock
        self._lock = threading.Lock()
        self._state = CircuitState.CLOSED
        self._failures: list[float] = []
        self._opened_at: float | None = None
        self._cooldown = self.policy.cooldown_seconds
        self._probe_in_flight = False
        self.last_error: str | None = None
        self.last_failure_at: float | None = None
        self.opened_total = 0

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._current_state()

    def _current_state(self) -> CircuitState:
        if (
            self._state is CircuitState.OPEN
            and self._opened_at is not None
            and self._clock() - self._opened_at >= self._cooldown
        ):
            self._state = CircuitState.HALF_OPEN
            self._probe_in_flight = False
        return self._state

    def allow(self) -> bool:
        """May a call go to this provider now? A half-open circuit admits one."""
        with self._lock:
            state = self._current_state()
            if state is CircuitState.CLOSED:
                return True
            if state is CircuitState.HALF_OPEN and not self._probe_in_flight:
                self._probe_in_flight = True
                return True
            return False

    def record_success(self) -> None:
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failures.clear()
            self._opened_at = None
            self._probe_in_flight = False

    def record_failure(self, exc: BaseException) -> None:
        """Record the outcome of a call that failed. Failures that do not count
        as an outage say the provider answered, which is a success here."""
        if not counts_as_outage(exc):
            self.record_success()
            return
        with self._lock:
            now = self._clock()
            self.last_error = _error_class(exc)
            self.last_failure_at = time.time()
            if isinstance(exc, CreditExhausted):
                self._open(now, cooldown=self.policy.billing_cooldown_seconds)
                return
            if self._current_state() is CircuitState.HALF_OPEN:
                self._open(now)
                return
            horizon = now - self.policy.window_seconds
            self._failures = [t for t in self._failures if t >= horizon]
            self._failures.append(now)
            if len(self._failures) >= self.policy.failure_threshold:
                self._open(now)

    def release(self) -> None:
        """A call that ended in neither verdict (our own bug, a cancellation):
        let the next caller probe instead of holding the circuit forever."""
        with self._lock:
            self._probe_in_flight = False

    def _open(self, now: float, *, cooldown: float | None = None) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = now
        self._cooldown = self.policy.cooldown_seconds if cooldown is None else cooldown
        self._probe_in_flight = False
        self._failures.clear()
        self.opened_total += 1

    def snapshot(self) -> dict[str, Any]:
        """For the admin ops view: state and error *class*, never a message."""
        with self._lock:
            state = self._current_state()
            retry_in = None
            if state is CircuitState.OPEN and self._opened_at is not None:
                retry_in = max(
                    0.0,
                    self._cooldown - (self._clock() - self._opened_at),
                )
            return {
                "provider": self.name,
                "state": state.value,
                "recent_failures": len(self._failures),
                "last_error": self.last_error,
                "last_failure_at": self.last_failure_at,
                "opened_total": self.opened_total,
                "retry_in_seconds": retry_in,
            }


def _error_class(exc: BaseException) -> str:
    if isinstance(exc, CreditExhausted):
        return "credit_exhausted"
    if isinstance(exc, TimeoutError) or getattr(exc, "timed_out", False):
        return "timeout"
    status = getattr(exc, "status", None)
    if status is not None:
        return f"http_{status}"
    cause = exc.__cause__
    return type(cause).__name__ if cause is not None else type(exc).__name__


_breakers: dict[str, CircuitBreaker] = {}
_registry_lock = threading.Lock()
_policy = BreakerPolicy()


def configure_breakers(policy: BreakerPolicy) -> None:
    """The policy every breaker uses, existing ones included. Called once at
    startup with the deployment's settings."""
    global _policy
    with _registry_lock:
        _policy = policy
        for breaker in _breakers.values():
            breaker.policy = policy


def breaker_for(provider: str) -> CircuitBreaker:
    """The process-wide breaker for a provider name."""
    with _registry_lock:
        breaker = _breakers.get(provider)
        if breaker is None:
            breaker = _breakers[provider] = CircuitBreaker(provider, _policy)
        return breaker


def all_breakers() -> list[CircuitBreaker]:
    with _registry_lock:
        return list(_breakers.values())


def reset_breakers() -> None:
    """Tests only: forget every provider's history."""
    global _policy
    with _registry_lock:
        _breakers.clear()
        _policy = BreakerPolicy()
