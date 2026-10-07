"""The request id: one string that ties a request's logs, AI usage rows and
background jobs together.

Accepted from an incoming ``X-Request-ID`` only when it looks like an id —
short, from a safe alphabet — because the value lands in every log line and a
caller-chosen string there is log injection. Anything else is replaced.
"""

from __future__ import annotations

import re
import uuid
from contextvars import ContextVar, Token
from typing import Any

import dramatiq
import structlog

REQUEST_ID_HEADER = "x-request-id"
_VALID = re.compile(r"[A-Za-z0-9._:-]{8,128}")

_request_id: ContextVar[str | None] = ContextVar("noema_request_id", default=None)


def accept_or_generate(incoming: str | None) -> str:
    """The caller's id if it is sane, a fresh UUID otherwise."""
    if incoming and _VALID.fullmatch(incoming):
        return incoming
    return str(uuid.uuid4())


def current_request_id() -> str | None:
    """The id of the request this code runs on behalf of, if any."""
    return _request_id.get()


def set_request_id(value: str | None) -> Token[str | None]:
    return _request_id.set(value)


def reset_request_id(token: Token[str | None]) -> None:
    _request_id.reset(token)


class RequestIdMiddleware(dramatiq.Middleware):
    """Carries the enqueuing request's id into the job that runs later.

    On enqueue (in the API process) the current id rides in the message's
    options; on processing (in the worker) it is bound into the log context
    and the context variable, so the job's logs and any AI usage rows it
    writes share the id of the request that started it. No call site changes:
    `ingest.send(...)` from a route is enough.
    """

    def before_enqueue(self, broker: dramatiq.Broker, message: Any, delay: int) -> None:
        request_id = current_request_id()
        if request_id and "request_id" not in message.options:
            message.options["request_id"] = request_id

    def before_process_message(self, broker: dramatiq.Broker, message: Any) -> None:
        request_id = message.options.get("request_id")
        if not isinstance(request_id, str) or not _VALID.fullmatch(request_id):
            request_id = None
        set_request_id(request_id)
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id, job=message.actor_name, message_id=message.message_id
        )

    def after_process_message(
        self,
        broker: dramatiq.Broker,
        message: Any,
        *,
        result: Any = None,
        exception: BaseException | None = None,
    ) -> None:
        set_request_id(None)
        structlog.contextvars.clear_contextvars()

    after_skip_message = after_process_message
