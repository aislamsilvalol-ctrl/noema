"""Shared FastAPI dependencies: current user, CSRF, gateway construction."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.config import Settings, get_settings
from noema.core.crypto import SecretBox
from noema.core.errors import Forbidden, ProviderUnavailable, Unauthorized
from noema.core.logging import get_logger
from noema.db.base import get_session
from noema.db.models import User
from noema.providers import (  # noqa: F401 — registers providers
    anthropic,
    mock,
    ollama,
    openai,
)
from noema.providers.base import AIProvider, ProviderError, TaskClass
from noema.providers.cache import EmbeddingCache
from noema.providers.gateway import AIGateway
from noema.providers.registry import Router, create
from noema.services.auth import AuthService
from noema.services.credentials import CredentialService
from noema.services.tokens import resolve_token

log = get_logger(__name__)

SESSION_COOKIE = "noema_session"
CSRF_HEADER = "x-csrf-token"
CSRF_COOKIE = "noema_csrf"
AUTHORIZATION_HEADER = "authorization"
BEARER_PREFIX = "bearer "

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

SettingsDep = Annotated[Settings, Depends(get_settings)]

# Committed *before* the response is sent (FastAPI's "function" scope). Every
# endpoint that answers with JSON uses this one, so a client can read what it
# just wrote the moment it has the status code -- see issue #22.
SessionDep = Annotated[AsyncSession, Depends(get_session, scope="function")]

# Kept open until the response body has been fully written ("request" scope):
# only for routes that return a StreamingResponse whose generator still reads
# or writes through the session (usage rows, teaching turns, ingestion polls).
# A stream route must take its user and gateway from the Stream* variants
# below so everything in that request shares this one session.
StreamSessionDep = Annotated[AsyncSession, Depends(get_session, scope="request")]


def _is_bearer_request(request: Request) -> bool:
    return request.headers.get(AUTHORIZATION_HEADER, "").lower().startswith(BEARER_PREFIX)


async def _resolve_session_user(
    request: Request, db: SessionDep, settings: SettingsDep
) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise Unauthorized("Not authenticated.")

    user, _ = await AuthService(db, settings).resolve(token)
    return user


async def _current_user(request: Request, db: AsyncSession, settings: Settings) -> User:
    """The caller, from a session cookie or a bearer API token — either is valid.

    A token's scope is checked right here, once, from the request method alone:
    ``read`` for a safe method, ``write`` otherwise. Centralising it here means a
    route added later is scoped by construction, not by whoever remembers to add
    the check to it.
    """
    if _is_bearer_request(request):
        header = request.headers[AUTHORIZATION_HEADER]
        secret = header[len(BEARER_PREFIX) :].strip()
        user, scopes = await resolve_token(db, secret)
        required = "read" if request.method in SAFE_METHODS else "write"
        # "write" implies "read" (see noema/services/tokens.py's SCOPES comment) —
        # a write-only token still has to be able to GET what it might change.
        allowed = required in scopes or (required == "read" and "write" in scopes)
        if not allowed:
            raise Forbidden(f"This token does not have '{required}' access.")
        return user

    return await _resolve_session_user(request, db, settings)


async def get_current_user(
    request: Request, db: SessionDep, settings: SettingsDep
) -> User:
    return await _current_user(request, db, settings)


async def get_stream_user(
    request: Request, db: StreamSessionDep, settings: SettingsDep
) -> User:
    """`get_current_user` on the stream-scoped session (see StreamSessionDep)."""
    return await _current_user(request, db, settings)


CurrentUser = Annotated[User, Depends(get_current_user)]
StreamUser = Annotated[User, Depends(get_stream_user)]


async def get_session_user(
    request: Request, db: SessionDep, settings: SettingsDep
) -> User:
    """Cookie-session only, no bearer token accepted.

    For the endpoints that manage tokens themselves — minting a new token with
    an existing one is a recursive-credential problem nobody has hit yet, so it
    stays out of scope rather than being half-solved.
    """
    return await _resolve_session_user(request, db, settings)


SessionUser = Annotated[User, Depends(get_session_user)]


async def get_admin_user(
    user: SessionUser, db: SessionDep, settings: SettingsDep
) -> User:
    """Cookie session only (an API token can never reach admin data) and the
    caller's email must be in ``NOEMA_ADMIN_EMAILS`` -- no admin-role column,
    no bootstrap problem. This is deliberately the minimal real gate for
    business/cost data, not a role system.
    """
    allowed = {
        email.strip().lower()
        for email in settings.noema_admin_emails.split(",")
        if email.strip()
    }
    if user.email.lower() not in allowed:
        raise Forbidden("Admin access required.")
    # An admin account sees every learner's usage and the business's numbers:
    # a password alone is not enough to hold that. Checked here, on every
    # admin request, so turning the factor off closes the door at once.
    from noema.services.mfa import MfaService

    if not await MfaService(db, None).enabled(user.id):
        raise Forbidden(
            "Admin access needs two-step verification. "
            "Turn it on in Settings, under Security, then come back."
        )
    return user


AdminUser = Annotated[User, Depends(get_admin_user)]


async def require_csrf(request: Request, db: SessionDep, settings: SettingsDep) -> None:
    """Double-submit check on cookie-authenticated mutations.

    The header value must match the token bound to the session record, not merely
    the cookie — otherwise any subdomain able to set cookies could forge a pair.

    A bearer token is not cookie-based, so a browser cannot be tricked into
    sending one on a forged request the way it can a cookie — CSRF does not
    apply, and `get_current_user` enforces that token's own scope instead.
    """
    if request.method in SAFE_METHODS or _is_bearer_request(request):
        return

    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise Unauthorized("Not authenticated.")

    submitted = request.headers.get(CSRF_HEADER)
    if not submitted:
        raise Forbidden("Missing CSRF token.")

    _, session = await AuthService(db, settings).resolve(token)
    from noema.core.security import constant_time_equals

    if not constant_time_equals(submitted, session.csrf_token):
        raise Forbidden("Invalid CSRF token.")


def get_secret_box(settings: SettingsDep) -> SecretBox:
    return SecretBox.from_base64(settings.noema_master_key)


SecretBoxDep = Annotated[SecretBox, Depends(get_secret_box)]


def get_router(settings: SettingsDep) -> Router:
    task_models = {
        task: model
        for task, model in {
            TaskClass.TUTOR_CHAT: settings.noema_model_tutor,
            TaskClass.EXTRACT_CONCEPTS: settings.noema_model_extract,
            TaskClass.GRADE_OPEN_ANSWER: settings.noema_model_grade,
            TaskClass.SUMMARIZE: settings.noema_model_summarize,
        }.items()
        if model
    }
    return Router(
        default_provider=settings.noema_default_provider,
        task_models=task_models,
        embedding_provider=settings.noema_embedding_provider,
    )


RouterDep = Annotated[Router, Depends(get_router)]


async def build_provider(
    name: str, settings: Settings, credentials: CredentialService | None
) -> AIProvider:
    """Instantiate a provider, preferring the user's own key over the deployment's."""
    user_key = await credentials.reveal_for_gateway(name) if credentials else None

    if name == "ollama":
        return create(
            "ollama",
            local_mode=settings.is_local_mode,
            base_url=settings.ollama_base_url,
            embed_model=settings.noema_embedding_model,
        )
    if name == "mock":
        return create(
            "mock",
            local_mode=settings.is_local_mode,
            dimensions=settings.noema_embedding_dim,
        )
    if name == "anthropic":
        return create(
            "anthropic",
            local_mode=settings.is_local_mode,
            api_key=user_key or settings.anthropic_api_key,
        )
    if name == "openai":
        return create(
            "openai",
            local_mode=settings.is_local_mode,
            api_key=user_key or settings.openai_api_key,
            embed_model=settings.noema_embedding_model,
        )
    return create(name, local_mode=settings.is_local_mode, api_key=user_key or "")


# The order a second opinion is asked in when the resolved provider fails.
# Hosted providers only: `ollama` is reachable in local mode, where it is the
# default anyway, and `mock` exists for tests.
_FALLBACK_ORDER = ("anthropic", "openai", "gemini", "openrouter")


def _has_deployment_key(name: str, settings: Settings) -> bool:
    return bool(getattr(settings, f"{name}_api_key", ""))


async def _fallback_chain(
    primary: str, settings: Settings, credentials: CredentialService | None
) -> list[AIProvider]:
    """Every other provider this deployment (or this learner) has a key for.

    A key configured beside the default exists to be used: when the default
    answers "your credit balance is too low" — a 400, so the gateway does not
    retry it — the lesson should continue on the next provider rather than end
    in "try again in a moment", which would never come true. Building a
    provider is cheap and local; a candidate whose key is missing or malformed
    raises here and is simply left out of the chain.
    """
    stored: set[str] = set()
    if credentials is not None:
        try:
            stored = {c.provider for c in await credentials.list()}
        except Exception:  # a BYOK read must not take the tutor down
            stored = set()

    chain: list[AIProvider] = []
    for name in _FALLBACK_ORDER:
        if name == primary:
            continue
        if name not in stored and not _has_deployment_key(name, settings):
            continue
        try:
            chain.append(await build_provider(name, settings, credentials))
        except Exception as exc:  # an unusable key is not an outage
            log.info("gateway.fallback_skipped", provider=name, error=str(exc))
    return chain


async def _gateway(
    request: Request,
    user: User,
    db: AsyncSession,
    settings: Settings,
    box: SecretBox,
    router: Router,
) -> AIGateway:
    credentials = CredentialService(db, box, user.id)
    route = router.resolve(TaskClass.TUTOR_CHAT)
    try:
        primary = await build_provider(route.provider, settings, credentials)
    except ProviderError as exc:
        # A ProviderError raised here (e.g. no deployment key and no BYOK key
        # configured for the resolved provider) is not a NoemaError, so it would
        # otherwise fall through FastAPI dependency resolution as a bare 500 with
        # no honest message -- the same catch-and-translate pattern socratic.py
        # and feynman.py already use around their own gateway calls.
        log.warning("gateway.unavailable", provider=route.provider, error=str(exc))
        raise ProviderUnavailable(f"The AI provider is unavailable: {exc}") from exc

    from noema.services.usage import DailyBudget, UsageWriter

    # A budget of zero means "no ceiling configured". Reading it as "allow nothing"
    # would turn an unset environment variable into an AI outage.
    budget = (
        DailyBudget(
            db,
            user.id,
            settings.noema_ai_daily_token_budget,
            reserve=settings.noema_ai_interactive_reserve,
        )
        if settings.noema_ai_daily_token_budget > 0
        else None
    )

    # The app's own Redis connection, not a new one per request. Absent in tests
    # that build the app without a lifespan, which is exactly when a cache should
    # not be involved anyway.
    cache = EmbeddingCache(
        getattr(request.app.state, "redis", None),
        ttl_days=settings.noema_embedding_cache_ttl_days,
    )

    fallbacks = await _fallback_chain(route.provider, settings, credentials)
    if fallbacks:
        log.debug(
            "gateway.chain",
            primary=route.provider,
            fallbacks=[p.name for p in fallbacks],
        )

    return AIGateway(
        primary,
        fallbacks,
        record_usage=UsageWriter(db, user.id),
        budget=budget,
        embeddings=cache,
    )


async def get_gateway(
    request: Request,
    user: CurrentUser,
    db: SessionDep,
    settings: SettingsDep,
    box: SecretBoxDep,
    router: RouterDep,
) -> AIGateway:
    return await _gateway(request, user, db, settings, box, router)


async def get_stream_gateway(
    request: Request,
    user: StreamUser,
    db: StreamSessionDep,
    settings: SettingsDep,
    box: SecretBoxDep,
    router: RouterDep,
) -> AIGateway:
    """`get_gateway` whose usage writer outlives the response headers: the
    stream records tokens after the last event, on the stream-scoped session."""
    return await _gateway(request, user, db, settings, box, router)


GatewayDep = Annotated[AIGateway, Depends(get_gateway)]
StreamGatewayDep = Annotated[AIGateway, Depends(get_stream_gateway)]
