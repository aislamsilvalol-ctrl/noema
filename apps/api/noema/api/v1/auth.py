"""Authentication endpoints."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response, status

from noema.api.v1 import deps
from noema.api.v1.schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    MfaAnswerRequest,
    MfaChallengeOut,
    RegisterRequest,
    ResetPasswordRequest,
    SessionOut,
    UserOut,
    VerifyEmailRequest,
)
from noema.core.errors import RateLimited, Unauthorized
from noema.services.auth import AuthService, IssuedSession
from noema.services.email_verification import (
    EmailVerification,
    send_verification_email,
)
from noema.services.login_guard import (
    RESET_COOLDOWN_SECONDS,
    LoginGuard,
    PasswordResetCooldown,
    VerificationResendCooldown,
)
from noema.services.mfa import MfaService
from noema.services.security_notice import notify

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookies(
    response: Response, issued: IssuedSession, secure: bool, max_age: int
) -> None:
    response.set_cookie(
        deps.SESSION_COOKIE,
        issued.refresh_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=max_age,
        path="/",
    )
    # Readable by the client on purpose: the SPA echoes it back in the CSRF header.
    # The httpOnly session cookie is what actually authenticates.
    response.set_cookie(
        deps.CSRF_COOKIE,
        issued.csrf_token,
        httponly=False,
        secure=secure,
        samesite="lax",
        max_age=max_age,
        path="/",
    )


@router.post("/register", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    db: deps.SessionDep,
    settings: deps.SettingsDep,
    background: BackgroundTasks,
) -> SessionOut:
    service = AuthService(db, settings)
    user = await service.register(
        payload.email,
        payload.password,
        payload.display_name,
        attribution=payload.attribution.cleaned() if payload.attribution else None,
    )
    issued = await service.issue_session(
        user,
        user_agent=request.headers.get("user-agent"),
        ip=request.client.host if request.client else None,
    )
    # The token row commits with the account; only the email waits for the
    # response. A mail provider that is down or unconfigured cannot fail a
    # registration -- the banner and its resend button cover that case.
    # Only when mail can reach them: from a test sender the link would never
    # arrive, and the app does not ask for a confirmation it cannot deliver.
    if settings.email_reaches_anyone:
        token = await EmailVerification(db, settings).issue(user)
        background.add_task(send_verification_email, settings, user.email, token)
    _set_session_cookies(
        response,
        issued,
        settings.noema_secure_cookies,
        settings.refresh_token_ttl_seconds,
    )
    return SessionOut(
        user=UserOut.model_validate(user),
        csrf_token=issued.csrf_token,
        expires_at=issued.expires_at,
    )


@router.post("/login", response_model=SessionOut | MfaChallengeOut)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: deps.SessionDep,
    settings: deps.SettingsDep,
) -> SessionOut | MfaChallengeOut:
    service = AuthService(db, settings)
    # `scope.get`, not `request.app`: a request built without an application
    # (a route called directly) has no limiter state to find, and no guard.
    app = request.scope.get("app")
    guard = LoginGuard(getattr(getattr(app, "state", None), "redis", None))
    wait = await guard.retry_after(payload.email)
    if wait:
        # Same words whether the account exists or not: the pause is keyed on
        # the address typed, so it says nothing about who is registered.
        raise RateLimited(
            "Too many wrong passwords for this account. "
            f"Try again in {max(wait // 60, 1)} minutes, or reset your password.",
            retry_after=wait,
        )
    try:
        user = await service.authenticate(payload.email, payload.password)
    except Unauthorized:
        await guard.failed(payload.email)
        raise
    mfa = MfaService(db, None)
    if await mfa.enabled(user.id):
        # Half of signing in. No session, no cookie: a challenge that only a
        # code from the account's authenticator (or a recovery code) redeems.
        return MfaChallengeOut(challenge=await mfa.open_challenge(user))
    issued = await service.issue_session(
        user,
        user_agent=request.headers.get("user-agent"),
        ip=request.client.host if request.client else None,
    )
    _set_session_cookies(
        response,
        issued,
        settings.noema_secure_cookies,
        settings.refresh_token_ttl_seconds,
    )
    return SessionOut(
        user=UserOut.model_validate(user),
        csrf_token=issued.csrf_token,
        expires_at=issued.expires_at,
    )


@router.post("/mfa", response_model=SessionOut)
async def answer_mfa(
    payload: MfaAnswerRequest,
    request: Request,
    response: Response,
    db: deps.SessionDep,
    settings: deps.SettingsDep,
) -> SessionOut:
    """The second step of a sign-in: a challenge and a code become a session."""
    user = await MfaService(db, deps.get_secret_box(settings)).answer_challenge(
        payload.challenge, payload.code
    )
    service = AuthService(db, settings)
    issued = await service.issue_session(
        user,
        user_agent=request.headers.get("user-agent"),
        ip=request.client.host if request.client else None,
    )
    _set_session_cookies(
        response,
        issued,
        settings.noema_secure_cookies,
        settings.refresh_token_ttl_seconds,
    )
    return SessionOut(
        user=UserOut.model_validate(user),
        csrf_token=issued.csrf_token,
        expires_at=issued.expires_at,
    )


@router.post("/refresh", response_model=SessionOut)
async def refresh(
    request: Request,
    response: Response,
    db: deps.SessionDep,
    settings: deps.SettingsDep,
) -> SessionOut:
    token = request.cookies.get(deps.SESSION_COOKIE)
    if not token:
        raise Unauthorized("No session.")

    issued = await AuthService(db, settings).refresh(
        token,
        user_agent=request.headers.get("user-agent"),
        ip=request.client.host if request.client else None,
    )
    _set_session_cookies(
        response,
        issued,
        settings.noema_secure_cookies,
        settings.refresh_token_ttl_seconds,
    )
    return SessionOut(
        user=UserOut.model_validate(issued.user),
        csrf_token=issued.csrf_token,
        expires_at=issued.expires_at,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request, response: Response, db: deps.SessionDep, settings: deps.SettingsDep
) -> None:
    token = request.cookies.get(deps.SESSION_COOKIE)
    if token:
        await AuthService(db, settings).logout(token)
    response.delete_cookie(deps.SESSION_COOKIE, path="/")
    response.delete_cookie(deps.CSRF_COOKIE, path="/")


@router.get("/me", response_model=UserOut)
async def me(user: deps.CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.post("/forgot-password", status_code=status.HTTP_204_NO_CONTENT)
async def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    db: deps.SessionDep,
    settings: deps.SettingsDep,
) -> None:
    """Always 204, whether or not the email belongs to a real account.

    `AuthService.request_password_reset` already enforces this at the service
    layer -- this route exists only to make it plain that the *route* itself
    must never branch on the result, or the one guarantee that matters here
    (a stranger cannot learn which emails have accounts) leaks right back in
    at the HTTP layer.

    The same goes for the cooldown: a throttled address gets the same silent
    204, keyed on what was typed, so it says nothing about who is registered.
    """
    app = request.scope.get("app")
    cooldown = PasswordResetCooldown(getattr(getattr(app, "state", None), "redis", None))
    if not await cooldown.claim(payload.email):
        return
    await AuthService(db, settings).request_password_reset(payload.email)


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    payload: ResetPasswordRequest,
    background: BackgroundTasks,
    db: deps.SessionDep,
    settings: deps.SettingsDep,
) -> None:
    email = await AuthService(db, settings).reset_password(
        payload.token, payload.new_password
    )
    background.add_task(notify, settings, email, "password_reset")


@router.post("/verify-email", status_code=status.HTTP_204_NO_CONTENT)
async def verify_email(
    payload: VerifyEmailRequest, db: deps.SessionDep, settings: deps.SettingsDep
) -> None:
    """Opening the link. No session needed: the email was opened on whatever
    device the inbox is on, which is often not the one that signed up."""
    await EmailVerification(db, settings).verify(payload.token)


@router.post(
    "/verify-email/resend",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(deps.require_csrf)],
)
async def resend_verification(
    request: Request,
    user: deps.CurrentUser,
    background: BackgroundTasks,
    db: deps.SessionDep,
    settings: deps.SettingsDep,
) -> None:
    """Another link, for the signed-in account. Nothing to do once verified."""
    if user.email_verified_at is not None:
        return
    app = request.scope.get("app")
    cooldown = VerificationResendCooldown(
        getattr(getattr(app, "state", None), "redis", None)
    )
    if not await cooldown.claim(user.id):
        raise RateLimited(
            "A verification email went out a few minutes ago. Check your inbox "
            "(and spam), then try again in a few minutes.",
            retry_after=RESET_COOLDOWN_SECONDS,
        )
    token = await EmailVerification(db, settings).issue(user)
    background.add_task(send_verification_email, settings, user.email, token)
