"""The only path from feature code to a model.

Handles retries, timeouts, provider fallback, token accounting and budget guarding.
Feature code asks the gateway for an answer; it never learns which vendor produced
one, except through the ``model`` field it can show the user.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, replace
from typing import Any, Protocol

from noema.core.errors import QuotaExceeded
from noema.core.logging import get_logger
from noema.providers.base import (
    AIProvider,
    ChatRequest,
    ChatResponse,
    EmbedRequest,
    EmbedResponse,
    ProviderError,
    StreamEvent,
    StructuredRequest,
    TaskClass,
    Usage,
)
from noema.providers.cache import EmbeddingCache

log = get_logger(__name__)

#: Per task class, because grading a long open answer and summarising a chunk have
#: nothing in common except that they both call a model.
TIMEOUTS: dict[TaskClass, float] = {
    TaskClass.TUTOR_CHAT: 120.0,
    TaskClass.EXTRACT_CONCEPTS: 90.0,
    TaskClass.GENERATE_CARDS: 90.0,
    TaskClass.GENERATE_QUESTIONS: 90.0,
    TaskClass.GRADE_OPEN_ANSWER: 60.0,
    TaskClass.SUMMARIZE: 45.0,
    TaskClass.EMBED: 120.0,
    TaskClass.CLASSIFY_INTENT: 15.0,
}


class UsageRecorder(Protocol):
    async def __call__(
        self, *, provider: str, model: str, task: TaskClass, usage: Usage, succeeded: bool
    ) -> None: ...


class BudgetGuard(Protocol):
    async def remaining_tokens(self) -> int: ...

    @property
    def reserved_tokens(self) -> int:
        """Tokens held back for work a human is waiting on."""
        ...


#: Tasks a person is sitting in front of. These keep running until the budget is
#: genuinely gone; everything else stops at the reserve line. A runaway generation
#: loop should cost you tomorrow's card drafts, not the ability to ask a question
#: about the chapter you are reading right now.
INTERACTIVE_TASKS = frozenset(
    {
        TaskClass.TUTOR_CHAT,
        TaskClass.GRADE_OPEN_ANSWER,
        TaskClass.SUMMARIZE,
        TaskClass.CLASSIFY_INTENT,
    }
)


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    attempts: int = 3
    base_delay: float = 0.5
    max_delay: float = 8.0

    def delay(self, attempt: int) -> float:
        """Exponential backoff with full jitter — synchronised retries are worse
        than the original failure."""
        capped = min(self.base_delay * 2**attempt, self.max_delay)
        return random.uniform(0, capped)  # noqa: S311 — jitter, not cryptography


class AIGateway:
    def __init__(
        self,
        primary: AIProvider,
        fallbacks: Sequence[AIProvider] = (),
        *,
        retry: RetryPolicy | None = None,
        record_usage: UsageRecorder | None = None,
        budget: BudgetGuard | None = None,
        embeddings: EmbeddingCache | None = None,
    ) -> None:
        self.primary = primary
        self.fallbacks = list(fallbacks)
        self.retry = retry or RetryPolicy()
        self._record_usage = record_usage
        self._budget = budget
        self._embeddings = embeddings

    @property
    def chain(self) -> list[AIProvider]:
        return [self.primary, *self.fallbacks]

    @property
    def record_usage(self) -> UsageRecorder | None:
        return self._record_usage

    @property
    def budget(self) -> BudgetGuard | None:
        return self._budget

    @property
    def embeddings(self) -> EmbeddingCache | None:
        return self._embeddings

    async def chat(self, request: ChatRequest) -> ChatResponse:
        await self._check_budget(request.task)
        response, provider = await self._attempt(
            lambda p: p.chat(request), request.task, request.model
        )
        await self._log_usage(
            provider, response.model, request.task, response.usage, True
        )
        return response

    async def stream(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        """Streams from the first provider that accepts the request.

        Fallback applies only before the first token: once the user is reading a
        partial answer, silently switching models would splice two different voices
        into one response.
        """
        await self._check_budget(request.task)
        last_error: ProviderError | None = None

        for provider in self.chain:
            iterator = provider.stream(request)
            try:
                first = await asyncio.wait_for(
                    anext(iterator), timeout=self._timeout(request.task)
                )
            except (ProviderError, TimeoutError) as exc:
                last_error = self._as_provider_error(exc, provider)
                log.warning("stream.start_failed", provider=provider.name, error=str(exc))
                continue

            yield first
            async for event in iterator:
                if event.done and event.usage:
                    await self._log_usage(
                        provider, request.model or "", request.task, event.usage, True
                    )
                yield event
            return

        raise last_error or ProviderError("no provider available", provider="gateway")

    async def embed(self, request: EmbedRequest) -> EmbedResponse:
        """Embed, through the cache when there is one.

        Deliberately *before* the budget check: a vector that is already known
        costs nothing, and refusing to hand it back would be a ceiling on work
        nobody is paying for. The provider call inside still checks.

        The cache is skipped when the request names no model. Without a model name
        the provider picks its own default, and a key that does not identify the
        model would survive a change of it and return the wrong vectors.
        """
        if self._embeddings is not None and request.model:
            return await self._embeddings.embed(
                request.texts,
                model=request.model,
                fetch=lambda texts: self._embed_uncached(
                    EmbedRequest(texts=texts, model=request.model)
                ),
            )
        return await self._embed_uncached(request)

    async def _embed_uncached(self, request: EmbedRequest) -> EmbedResponse:
        await self._check_budget(TaskClass.EMBED)
        response, provider = await self._attempt(
            lambda p: p.embed(request), TaskClass.EMBED, request.model
        )
        await self._log_usage(
            provider, response.model, TaskClass.EMBED, response.usage, True
        )
        return response

    async def structured(self, request: StructuredRequest) -> dict[str, Any]:
        """Schema-constrained call. Nothing is persisted before this validates."""
        await self._check_budget(request.task)
        result, _ = await self._attempt(
            lambda p: p.structured(request), request.task, request.model
        )
        return result

    async def _attempt[T](
        self,
        call: Callable[[AIProvider], Awaitable[T]],
        task: TaskClass,
        model: str | None,
    ) -> tuple[T, AIProvider]:
        last_error: Exception | None = None

        for provider in self.chain:
            for attempt in range(self.retry.attempts):
                try:
                    result = await asyncio.wait_for(
                        call(provider), timeout=self._timeout(task)
                    )
                except ProviderError as exc:
                    last_error = exc
                    if not exc.retryable:
                        # A 400 is our bug. Retrying it wastes time and hides it.
                        break
                except TimeoutError as exc:
                    last_error = exc
                except Exception as exc:
                    last_error = exc
                    break
                else:
                    return result, provider

                if attempt < self.retry.attempts - 1:
                    await asyncio.sleep(self.retry.delay(attempt))

            log.warning(
                "provider.exhausted",
                provider=provider.name,
                task=task.value,
                error=str(last_error),
            )

        await self._log_usage(self.primary, model or "", task, Usage(), False)
        raise self._as_provider_error(last_error, self.primary)

    def _timeout(self, task: TaskClass) -> float:
        return TIMEOUTS.get(task, 60.0)

    async def _check_budget(self, task: TaskClass) -> None:
        """Stop batch work early so interactive work survives.

        BYOK means a runaway loop spends the user's own money, so the ceiling has to
        bite — but it should degrade rather than switch the product off.
        """
        if self._budget is None:
            return

        remaining = await self._budget.remaining_tokens()
        if task in INTERACTIVE_TASKS:
            if remaining > 0:
                return
            raise QuotaExceeded(
                "The daily AI token budget is used up. It resets on a rolling "
                "24-hour window; everything already in your library still works.",
                task=task.value,
                remaining_tokens=remaining,
            )

        if remaining <= self._budget.reserved_tokens:
            raise QuotaExceeded(
                "Generation is paused: the daily AI token budget is nearly used up "
                "and the rest is reserved for asking questions and grading answers. "
                "Nothing already generated is affected.",
                task=task.value,
                remaining_tokens=remaining,
                reserved_tokens=self._budget.reserved_tokens,
            )

    async def _log_usage(
        self, provider: AIProvider, model: str, task: TaskClass, usage: Usage, ok: bool
    ) -> None:
        if self._record_usage is None:
            return
        await self._record_usage(
            provider=provider.name, model=model, task=task, usage=usage, succeeded=ok
        )

    @staticmethod
    def _as_provider_error(exc: Exception | None, provider: AIProvider) -> ProviderError:
        if isinstance(exc, ProviderError):
            return exc
        if isinstance(exc, TimeoutError):
            return ProviderError(
                f"{provider.name} timed out", provider=provider.name, retryable=True
            )
        return ProviderError(
            str(exc) if exc else "unknown provider failure", provider=provider.name
        )


def with_model(request: ChatRequest, model: str | None) -> ChatRequest:
    return replace(request, model=model) if model else request
