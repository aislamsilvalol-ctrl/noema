"""The account's own security: its password and the devices signed in to it.

Cookie session only: an API token is for integrations and can neither change
the password nor end sessions. Every mutation carries the CSRF check.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, status

from noema.api.v1 import deps
from noema.api.v1.schemas import (
    ActiveSessionOut,
    ChangePasswordRequest,
    ConfirmPasswordRequest,
    MfaCodeRequest,
    MfaDisableRequest,
    MfaSetupOut,
    MfaStatusOut,
    RecoveryCodesOut,
    RevokedOut,
)
from noema.core.errors import Unauthorized
from noema.db.models import Session, User
from noema.services.auth import AuthService
from noema.services.mfa import MfaService

router = APIRouter(
    prefix="/me/security", tags=["security"], dependencies=[Depends(deps.require_csrf)]
)


async def _current(
    request: Request, db: deps.SessionDep, settings: deps.SettingsDep
) -> tuple[User, Session]:
    token = request.cookies.get(deps.SESSION_COOKIE)
    if not token:
        raise Unauthorized("Not authenticated.")
    return await AuthService(db, settings).resolve(token)


def describe_device(user_agent: str) -> tuple[str, str]:
    """Browser and OS from a user agent, and nothing more precise than that.

    Order matters: Edge and Opera also say "Chrome", Chrome also says "Safari".
    Unknown is said as unknown rather than guessed.
    """
    ua = user_agent
    if "Edg/" in ua:
        browser = "Edge"
    elif "OPR/" in ua or "Opera" in ua:
        browser = "Opera"
    elif "Firefox/" in ua:
        browser = "Firefox"
    elif "Chrome/" in ua or "CriOS/" in ua:
        browser = "Chrome"
    elif "Safari/" in ua:
        browser = "Safari"
    else:
        browser = ""
    if "iPhone" in ua or "iPad" in ua:
        os = "iOS"
    elif "Android" in ua:
        os = "Android"
    elif "Mac OS X" in ua or "Macintosh" in ua:
        os = "macOS"
    elif "Windows" in ua:
        os = "Windows"
    elif "Linux" in ua:
        os = "Linux"
    else:
        os = ""
    return browser, os


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    db: deps.SessionDep,
    settings: deps.SettingsDep,
) -> None:
    """Change the password. Every other device is signed out; this one stays."""
    user, session = await _current(request, db, settings)
    await AuthService(db, settings).change_password(
        user,
        payload.current_password,
        payload.new_password,
        keep_family=session.family_id,
    )


@router.get("/sessions", response_model=list[ActiveSessionOut])
async def sessions(
    request: Request, db: deps.SessionDep, settings: deps.SettingsDep
) -> list[ActiveSessionOut]:
    user, current = await _current(request, db, settings)
    out = []
    for item in await AuthService(db, settings).active_sessions(user):
        browser, os = describe_device(item.user_agent)
        out.append(
            ActiveSessionOut(
                id=item.family_id,
                browser=browser,
                os=os,
                started_at=item.started_at,
                last_active_at=item.last_active_at,
                current=item.family_id == current.family_id,
            )
        )
    return out


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def end_session(
    session_id: uuid.UUID,
    request: Request,
    db: deps.SessionDep,
    settings: deps.SettingsDep,
) -> None:
    user, _ = await _current(request, db, settings)
    await AuthService(db, settings).revoke_session(user, session_id)


@router.post("/sessions/revoke-others", response_model=RevokedOut)
async def end_other_sessions(
    request: Request, db: deps.SessionDep, settings: deps.SettingsDep
) -> RevokedOut:
    user, current = await _current(request, db, settings)
    revoked = await AuthService(db, settings).revoke_other_sessions(
        user, current.family_id
    )
    return RevokedOut(revoked=revoked)


# ── Two-step verification ───────────────────────────────────────────────────


@router.get("/mfa", response_model=MfaStatusOut)
async def mfa_status(
    request: Request, db: deps.SessionDep, settings: deps.SettingsDep
) -> MfaStatusOut:
    user, _ = await _current(request, db, settings)
    mfa = MfaService(db, None)
    return MfaStatusOut(
        enabled=await mfa.enabled(user.id),
        recovery_codes_left=await mfa.recovery_codes_left(user.id),
    )


@router.post("/mfa/setup", response_model=MfaSetupOut)
async def mfa_setup(
    payload: ConfirmPasswordRequest,
    request: Request,
    db: deps.SessionDep,
    settings: deps.SettingsDep,
) -> MfaSetupOut:
    """A secret to scan. Nothing is protected until the first code confirms it."""
    user, _ = await _current(request, db, settings)
    AuthService(db, settings).confirm_password(user, payload.password)
    setup = await MfaService(db, deps.get_secret_box(settings)).begin(user)
    return MfaSetupOut(secret=setup.secret, uri=setup.uri, qr_svg=setup.qr_svg)


@router.post("/mfa/confirm", response_model=RecoveryCodesOut)
async def mfa_confirm(
    payload: MfaCodeRequest,
    request: Request,
    db: deps.SessionDep,
    settings: deps.SettingsDep,
) -> RecoveryCodesOut:
    """The first code turns it on. The recovery codes are shown this once."""
    user, _ = await _current(request, db, settings)
    codes = await MfaService(db, deps.get_secret_box(settings)).confirm(
        user, payload.code
    )
    return RecoveryCodesOut(recovery_codes=codes)


@router.post("/mfa/disable", status_code=status.HTTP_204_NO_CONTENT)
async def mfa_disable(
    payload: MfaDisableRequest,
    request: Request,
    db: deps.SessionDep,
    settings: deps.SettingsDep,
) -> None:
    """Off needs both: the password and a current code (or a recovery code)."""
    user, _ = await _current(request, db, settings)
    AuthService(db, settings).confirm_password(user, payload.password)
    await MfaService(db, deps.get_secret_box(settings)).disable(user, payload.code)


@router.post("/mfa/recovery-codes", response_model=RecoveryCodesOut)
async def mfa_recovery_codes(
    payload: ConfirmPasswordRequest,
    request: Request,
    db: deps.SessionDep,
    settings: deps.SettingsDep,
) -> RecoveryCodesOut:
    """Ten new codes; the old ones stop working."""
    user, _ = await _current(request, db, settings)
    AuthService(db, settings).confirm_password(user, payload.password)
    codes = await MfaService(db, deps.get_secret_box(settings)).regenerate_codes(user)
    return RecoveryCodesOut(recovery_codes=codes)
