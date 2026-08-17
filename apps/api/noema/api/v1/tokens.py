"""Managing the public REST API's own credentials.

Minting and revoking a token is itself a cookie-authenticated action — `SessionUser`,
not `CurrentUser` — so a stolen token cannot be used to mint a longer-lived
replacement for itself. See `noema.api.v1.deps.get_session_user`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from noema.api.v1 import deps
from noema.core.errors import NotFound
from noema.services.tokens import create_token, list_tokens, revoke_token

router = APIRouter(
    prefix="/tokens", tags=["tokens"], dependencies=[Depends(deps.require_csrf)]
)


class TokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    scopes: list[Literal["read", "write"]] = Field(min_length=1)
    expires_at: datetime | None = None


class TokenOut(BaseModel):
    id: uuid.UUID
    name: str
    scopes: list[str]
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None


class TokenCreated(TokenOut):
    #: Present only in the response to the create call that generated it.
    secret: str


@router.post("", response_model=TokenCreated)
async def create_api_token(
    user: deps.SessionUser, db: deps.SessionDep, body: TokenCreate
) -> TokenCreated:
    """Issue a new API token. The secret is returned once and never again."""
    created = await create_token(
        db,
        owner_id=user.id,
        name=body.name,
        scopes=list(dict.fromkeys(body.scopes)),
        expires_at=body.expires_at,
    )
    return TokenCreated(
        id=created.token.id,
        name=created.token.name,
        scopes=created.token.scopes,
        created_at=created.token.created_at,
        expires_at=created.token.expires_at,
        last_used_at=created.token.last_used_at,
        secret=created.secret,
    )


@router.get("", response_model=list[TokenOut])
async def list_api_tokens(user: deps.SessionUser, db: deps.SessionDep) -> list[TokenOut]:
    tokens = await list_tokens(db, owner_id=user.id)
    return [
        TokenOut(
            id=token.id,
            name=token.name,
            scopes=token.scopes,
            created_at=token.created_at,
            expires_at=token.expires_at,
            last_used_at=token.last_used_at,
        )
        for token in tokens
    ]


@router.delete("/{token_id}", status_code=204)
async def revoke_api_token(
    token_id: uuid.UUID, user: deps.SessionUser, db: deps.SessionDep
) -> None:
    revoked = await revoke_token(db, owner_id=user.id, token_id=token_id)
    if not revoked:
        raise NotFound("Token not found")
