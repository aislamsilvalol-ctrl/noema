"""Telling the account holder when something about their account's safety changed.

A password changed, a reset used, two-step verification turned on or off: if
it was them, the email is a receipt; if it was not, it is the only warning
they get, with the way back in the same message.

Sent after the response, as a background task, and never allowed to fail the
change itself: a slow or unconfigured mail provider must not undo a password
change. Portuguese only, the same known limitation as the reset email.
"""

from __future__ import annotations

from typing import Literal

from noema.core.config import Settings
from noema.core.logging import get_logger
from noema.services.email import send_email

log = get_logger(__name__)

Event = Literal["password_changed", "password_reset", "mfa_enabled", "mfa_disabled"]

_WHAT: dict[str, tuple[str, str]] = {
    "password_changed": (
        "Sua senha do Noema foi trocada",
        "A senha da sua conta foi trocada, e os outros dispositivos foram desconectados.",
    ),
    "password_reset": (
        "Sua senha do Noema foi redefinida",
        "A senha da sua conta foi redefinida por um link de recuperação, "
        "e todos os dispositivos foram desconectados.",
    ),
    "mfa_enabled": (
        "Verificação em duas etapas ativada",
        "A verificação em duas etapas foi ativada na sua conta.",
    ),
    "mfa_disabled": (
        "Verificação em duas etapas desativada",
        "A verificação em duas etapas foi desativada na sua conta.",
    ),
}


def _html(what: str, reset_link: str) -> str:
    return f"""
    <p>{what}</p>
    <p>Se foi você, não precisa fazer nada.</p>
    <p>Se não foi você, <a href="{reset_link}">redefina sua senha agora</a>
    e depois, em Configurações, Segurança, desconecte os dispositivos
    que não reconhece.</p>
    """


async def notify(settings: Settings, email: str, event: Event) -> None:
    subject, what = _WHAT[event]
    try:
        await send_email(
            settings,
            to=email,
            subject=subject,
            html=_html(what, f"{settings.web_origin()}/forgot-password"),
        )
    except Exception as exc:
        log.warning("security.notice_failed", notice=event, error=type(exc).__name__)
