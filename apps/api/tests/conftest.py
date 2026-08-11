from __future__ import annotations

import base64
import os

import pytest

# Settings are read at import time, so the environment has to be set before any
# noema module is imported.
os.environ.setdefault("NOEMA_ENV", "test")
os.environ.setdefault("NOEMA_MASTER_KEY", base64.b64encode(b"0" * 32).decode())
os.environ.setdefault("NOEMA_SESSION_SECRET", base64.b64encode(b"1" * 32).decode())
os.environ.setdefault("NOEMA_DEFAULT_PROVIDER", "mock")


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> None:
    from noema.core.config import get_settings

    get_settings.cache_clear()
