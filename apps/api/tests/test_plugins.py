"""Third-party plugin discovery."""

from __future__ import annotations

from importlib.metadata import EntryPoint
from unittest.mock import MagicMock, patch

from noema.plugins import load_plugins

#: What a real plugin's registration call looks like from the outside — a
#: zero-argument callable at an importable dotted path. Its own test proves
#: importlib.metadata.EntryPoint can actually find and call it; every other
#: test in this file mocks the entry point itself, which only proves
#: load_plugins' own dispatch logic.
_calls: list[str] = []


def _real_plugin_target() -> None:
    _calls.append("registered")


def fake_entry_point(name: str, *, loader: object) -> MagicMock:
    point = MagicMock(name=name)
    point.name = name
    point.load.return_value = loader
    return point


def test_a_discovered_plugin_is_registered() -> None:
    register = MagicMock()
    point = fake_entry_point("gemini", loader=register)

    with patch("noema.plugins.entry_points", return_value=[point]):
        load_plugins()

    register.assert_called_once_with()


def test_every_discovered_plugin_is_registered() -> None:
    first, second = MagicMock(), MagicMock()
    points = [
        fake_entry_point("a", loader=first),
        fake_entry_point("b", loader=second),
    ]

    with patch("noema.plugins.entry_points", return_value=points):
        load_plugins()

    first.assert_called_once_with()
    second.assert_called_once_with()


def test_a_plugin_that_fails_to_import_does_not_stop_the_others() -> None:
    broken = fake_entry_point("broken", loader=None)
    broken.load.side_effect = ImportError("no module named noema_provider_broken")
    healthy_register = MagicMock()
    healthy = fake_entry_point("healthy", loader=healthy_register)

    with patch("noema.plugins.entry_points", return_value=[broken, healthy]):
        load_plugins()  # must not raise

    healthy_register.assert_called_once_with()


def test_a_plugin_whose_register_call_raises_does_not_stop_the_others() -> None:
    def exploding() -> None:
        raise RuntimeError("misconfigured")

    broken = fake_entry_point("broken", loader=exploding)
    healthy_register = MagicMock()
    healthy = fake_entry_point("healthy", loader=healthy_register)

    with patch("noema.plugins.entry_points", return_value=[broken, healthy]):
        load_plugins()  # must not raise

    healthy_register.assert_called_once_with()


def test_no_plugins_installed_is_not_an_error() -> None:
    with patch("noema.plugins.entry_points", return_value=[]):
        load_plugins()  # must not raise


def test_a_real_entry_point_actually_finds_and_calls_the_target() -> None:
    """Only this test exercises importlib.metadata's own loader — the exact
    resolution a real `[project.entry-points."noema.providers"]` line goes
    through, `entry_points()` discovery aside (mocked, same as every other
    test here — that half only proves *this repo's* packages are found, which
    is a statement about the environment, not about load_plugins)."""
    _calls.clear()
    point = EntryPoint(
        name="real",
        value="test_plugins:_real_plugin_target",
        group="noema.providers",
    )

    with patch("noema.plugins.entry_points", return_value=[point]):
        load_plugins()

    assert _calls == ["registered"]
