"""Two-step verification, end to end through the sign-in routes.

The properties that make it worth having: a right password alone opens
nothing, a code works once, a recovery code works once, a challenge dies
after five wrong guesses even for the right code, and turning it off needs
both the password and a code.
"""

from __future__ import annotations

import os
import time

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request
from starlette.responses import Response

from noema.api.v1.auth import answer_mfa, login
from noema.api.v1.schemas import (
    LoginRequest,
    MfaAnswerRequest,
    MfaChallengeOut,
    SessionOut,
)
from noema.core import totp
from noema.core.config import Settings
from noema.core.crypto import SecretBox
from noema.core.errors import Unauthorized, WrongPassword
from noema.db.models import User
from noema.services.auth import AuthService
from noema.services.mfa import CHALLENGE_ATTEMPTS, RECOVERY_CODES, MfaService

pytestmark = pytest.mark.asyncio

PASSWORD = "correct-horse-battery"
KEY = os.urandom(32)


def bare_request() -> Request:
    return Request(
        {
            "type": "http",
            "headers": [],
            "client": ("10.0.0.1", 1),
            "method": "POST",
            "path": "/",
        }
    )


def mfa_settings(settings: Settings) -> Settings:
    import base64

    return settings.model_copy(
        update={"noema_master_key": base64.b64encode(KEY).decode()}
    )


async def enrolled(
    db: AsyncSession, settings: Settings, email: str
) -> tuple[User, str, list[str]]:
    user = await AuthService(db, settings).register(email, PASSWORD, "Ana")
    mfa = MfaService(db, SecretBox(KEY))
    setup = await mfa.begin(user)
    codes = await mfa.confirm(user, totp.code_at(setup.secret, time.time()))
    return user, setup.secret, codes


async def challenge_for(db: AsyncSession, settings: Settings, email: str) -> str:
    response = Response()
    out = await login(
        LoginRequest(email=email, password=PASSWORD),
        bare_request(),
        response,
        db,
        settings,
    )
    assert isinstance(out, MfaChallengeOut)
    assert "set-cookie" not in response.headers  # half a sign-in is no session
    return out.challenge


async def test_setup_turns_on_with_a_first_code_and_hands_out_recovery_codes(
    db: AsyncSession, settings: Settings
) -> None:
    user, _, codes = await enrolled(db, settings, "setup@example.com")

    assert await MfaService(db, None).enabled(user.id)
    assert len(codes) == RECOVERY_CODES == len(set(codes))
    assert await MfaService(db, None).recovery_codes_left(user.id) == RECOVERY_CODES


async def test_a_right_password_alone_opens_nothing_and_a_code_finishes_it(
    db: AsyncSession, settings: Settings
) -> None:
    settings = mfa_settings(settings)
    _, secret, _ = await enrolled(db, settings, "login@example.com")

    challenge = await challenge_for(db, settings, "login@example.com")
    # The enrolment code used this step; the next step's code is the fresh one.
    code = totp.code_at(secret, time.time() + totp.STEP_SECONDS)
    response = Response()
    out = await answer_mfa(
        MfaAnswerRequest(challenge=challenge, code=code),
        bare_request(),
        response,
        db,
        settings,
    )

    assert isinstance(out, SessionOut)
    assert "set-cookie" in response.headers

    again = await challenge_for(db, settings, "login@example.com")
    with pytest.raises(WrongPassword):  # the same code, seen once, is spent
        await answer_mfa(
            MfaAnswerRequest(challenge=again, code=code),
            bare_request(),
            Response(),
            db,
            settings,
        )


async def test_a_recovery_code_works_once(db: AsyncSession, settings: Settings) -> None:
    settings = mfa_settings(settings)
    _, _, codes = await enrolled(db, settings, "recovery@example.com")

    first = await challenge_for(db, settings, "recovery@example.com")
    await answer_mfa(
        MfaAnswerRequest(challenge=first, code=codes[0].upper()),
        bare_request(),
        Response(),
        db,
        settings,
    )

    second = await challenge_for(db, settings, "recovery@example.com")
    with pytest.raises(WrongPassword):
        await answer_mfa(
            MfaAnswerRequest(challenge=second, code=codes[0]),
            bare_request(),
            Response(),
            db,
            settings,
        )


async def test_a_challenge_dies_after_five_wrong_guesses_even_for_the_right_code(
    db: AsyncSession, settings: Settings
) -> None:
    settings = mfa_settings(settings)
    _, secret, _ = await enrolled(db, settings, "guess@example.com")
    challenge = await challenge_for(db, settings, "guess@example.com")

    for _ in range(CHALLENGE_ATTEMPTS):
        with pytest.raises(WrongPassword):
            await answer_mfa(
                MfaAnswerRequest(challenge=challenge, code="000000"),
                bare_request(),
                Response(),
                db,
                settings,
            )

    right = totp.code_at(secret, time.time() + totp.STEP_SECONDS)
    with pytest.raises(Unauthorized):
        await answer_mfa(
            MfaAnswerRequest(challenge=challenge, code=right),
            bare_request(),
            Response(),
            db,
            settings,
        )


async def test_turning_it_off_needs_a_code(db: AsyncSession, settings: Settings) -> None:
    user, _, codes = await enrolled(db, settings, "off@example.com")
    mfa = MfaService(db, SecretBox(KEY))

    with pytest.raises(WrongPassword):
        await mfa.disable(user, "123456")
    assert await mfa.enabled(user.id)

    await mfa.disable(user, codes[1])
    assert not await mfa.enabled(user.id)


async def test_a_sealed_secret_does_not_open_for_another_user(
    db: AsyncSession, settings: Settings
) -> None:
    """The user id is the associated data: a row copied across accounts is dead."""
    ana, _, _ = await enrolled(db, settings, "ana-mfa@example.com")
    bea = await AuthService(db, settings).register("bea-mfa@example.com", PASSWORD, "Bea")
    mfa = MfaService(db, SecretBox(KEY))
    factor = await mfa.factor(ana.id)
    assert factor is not None

    with pytest.raises(Exception, match="decrypt"):
        mfa._secret(bea, factor)
