"""Shared FastAPI dependencies: current user, CSRF, gateway construction."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.config import Settings, get_settings
from noema.core.crypto import SecretBox
from noema.core.errors import Forbidden, Unauthorized
from noema.db.base import get_session
from noema.db.models import User
from noema.providers import (  # noqa: F401 — registers providers
    anthropic,
    mock,
    ollama,
    openai,
)
from noema.providers.base import AIProvider, TaskClass
from noema.providers.gateway import AIGateway
from noema.providers.registry import Router, create
from noema.services.auth import AuthService
from noema.services.credentials import CredentialService

SESSION_COOKIE = "noema_session"
CSRF_HEADER = "x-csrf-token"
CSRF_COOKIE = "noema_csrf"

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(
    request: Request, db: SessionDep, settings: SettingsDep
) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise Unauthorized("Not authenticated.")

    user, _ = await AuthService(db, settings).resolve(token)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_csrf(request: Request, db: SessionDep, settings: SettingsDep) -> None:
    """Double-submit check on cookie-authenticated mutations.

    The header value must match the token bound to the session record, not merely
    the cookie — otherwise any subdomain able to set cookies could forge a pair.
    """
    if request.method in SAFE_METHODS:
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


async def get_gateway(
    user: CurrentUser,
    db: SessionDep,
    settings: SettingsDep,
    box: SecretBoxDep,
    router: RouterDep,
) -> AIGateway:
    credentials = CredentialService(db, box, user.id)
    route = router.resolve(TaskClass.TUTOR_CHAT)
    primary = await build_provider(route.provider, settings, credentials)

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

    return AIGateway(primary, record_usage=UsageWriter(db, user.id), budget=budget)


GatewayDep = Annotated[AIGateway, Depends(get_gateway)]
