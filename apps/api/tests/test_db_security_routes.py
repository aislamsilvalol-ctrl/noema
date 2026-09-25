"""The account's own security: password, devices, and step-up.

What a stolen session must not be able to do alone (change the password,
export everything, delete the account), and what the owner must be able to
do from one device (see the others, end them).
"""

from __future__ import annotations

import pytest
from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request
from starlette.responses import Response

from noema.api.v1 import deps
from noema.api.v1.account import delete_account, export
from noema.api.v1.schemas import ChangePasswordRequest, ConfirmPasswordRequest
from noema.api.v1.security import (
    change_password,
    describe_device,
    end_other_sessions,
    end_session,
    sessions,
)
from noema.core import security
from noema.core.config import Settings
from noema.core.errors import NotFound, Unauthorized, WrongPassword
from noema.db.models import Session, User
from noema.services.auth import AuthService

pytestmark = pytest.mark.asyncio

PASSWORD = "correct-horse-battery"


def request_with(token: str) -> Request:
    return Request(
        {
            "type": "http",
            "headers": [(b"cookie", f"{deps.SESSION_COOKIE}={token}".encode())],
            "client": ("10.0.0.1", 1234),
            "method": "POST",
            "path": "/",
        }
    )


async def signed_in(
    db: AsyncSession, settings: Settings, email: str
) -> tuple[User, list[str]]:
    """A user with two devices: the token of each."""
    service = AuthService(db, settings)
    user = await service.register(email, PASSWORD, "Ana")
    laptop = await service.issue_session(
        user, user_agent="Mozilla (Macintosh) Chrome/1 Safari/1"
    )
    phone = await service.issue_session(user, user_agent="Mozilla (iPhone) Safari/1")
    return user, [laptop.refresh_token, phone.refresh_token]


async def test_changing_the_password_needs_the_old_one_and_signs_out_the_other_device(
    db: AsyncSession, settings: Settings
) -> None:
    user, (laptop, phone) = await signed_in(db, settings, "change@example.com")

    with pytest.raises(WrongPassword):
        await change_password(
            ChangePasswordRequest(
                current_password="wrong", new_password="a-new-long-passphrase"
            ),
            request_with(laptop),
            BackgroundTasks(),
            db,
            settings,
        )

    await change_password(
        ChangePasswordRequest(
            current_password=PASSWORD, new_password="a-new-long-passphrase"
        ),
        request_with(laptop),
        BackgroundTasks(),
        db,
        settings,
    )

    service = AuthService(db, settings)
    await service.resolve(laptop)  # this device stays signed in
    with pytest.raises(Unauthorized):
        await service.resolve(phone)
    assert security.verify_password("a-new-long-passphrase", user.password_hash)


async def test_the_device_list_names_each_device_and_marks_this_one(
    db: AsyncSession, settings: Settings
) -> None:
    _, (laptop, _) = await signed_in(db, settings, "list@example.com")

    listed = await sessions(request_with(laptop), db, settings)

    assert len(listed) == 2
    current = [s for s in listed if s.current]
    assert len(current) == 1 and current[0].os == "macOS"
    assert {s.os for s in listed} == {"macOS", "iOS"}


async def test_ending_other_sessions_keeps_this_one(
    db: AsyncSession, settings: Settings
) -> None:
    _, (laptop, phone) = await signed_in(db, settings, "others@example.com")

    out = await end_other_sessions(request_with(laptop), db, settings)

    assert out.revoked == 1
    service = AuthService(db, settings)
    await service.resolve(laptop)
    with pytest.raises(Unauthorized):
        await service.resolve(phone)


async def test_nobody_ends_a_session_that_is_not_theirs(
    db: AsyncSession, settings: Settings
) -> None:
    _, (mine, _) = await signed_in(db, settings, "mine@example.com")
    _, (theirs, _) = await signed_in(db, settings, "theirs@example.com")
    their_session = await db.scalar(
        select(Session).where(Session.refresh_token_hash == security.hash_token(theirs))
    )
    assert their_session is not None

    with pytest.raises(NotFound):
        await end_session(their_session.family_id, request_with(mine), db, settings)

    await AuthService(db, settings).resolve(theirs)


async def test_export_and_deletion_need_the_password(
    db: AsyncSession, settings: Settings, user: User
) -> None:
    user.password_hash = security.hash_password(PASSWORD)
    await db.flush()

    with pytest.raises(WrongPassword):
        await export(ConfirmPasswordRequest(password="wrong"), user, db, settings)
    with pytest.raises(WrongPassword):
        await delete_account(
            ConfirmPasswordRequest(password="wrong"), user, db, settings, Response()
        )
    assert user.deleted_at is None


def test_devices_are_described_without_guessing() -> None:
    assert describe_device(
        "Mozilla/5.0 (Windows NT 10.0) AppleWebKit Chrome/120 Safari/537 Edg/120"
    ) == ("Edge", "Windows")
    assert describe_device("Mozilla/5.0 (iPhone; CPU iPhone OS 17) Safari/604") == (
        "Safari",
        "iOS",
    )
    assert describe_device("curl/8") == ("", "")
