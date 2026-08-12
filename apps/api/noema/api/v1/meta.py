"""What this deployment is.

The web app cannot know whether it is talking to a cloud instance or an air-gapped
one, and guessing produces the worst outcome: a button that is visible, clickable,
and fails. Local mode in particular has to be visible in the interface, because a
privacy guarantee nobody can see is a guarantee nobody trusts.

Unauthenticated on purpose. Nothing here is a secret — the sign-in page needs it
before there is anyone to authenticate, and the deployment's own mode is not
information an attacker gains anything from.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from noema.api.v1 import deps

router = APIRouter(prefix="/meta", tags=["meta"])


class MetaOut(BaseModel):
    mode: str
    #: True when no request may leave this machine. The API refuses to construct a
    #: network provider, and `docker-compose.local.yml` puts the containers on a
    #: network with no route out — belt and braces, because one of them is code.
    local: bool
    allow_signups: bool
    default_provider: str
    embedding_model: str
    version: str


@router.get("", response_model=MetaOut)
async def meta(settings: deps.SettingsDep) -> MetaOut:
    return MetaOut(
        mode=settings.noema_mode.value,
        local=settings.is_local_mode,
        allow_signups=settings.noema_allow_signups,
        default_provider=settings.noema_default_provider,
        embedding_model=settings.noema_embedding_model,
        version="0.1.0",
    )
