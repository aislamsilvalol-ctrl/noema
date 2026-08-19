"""Third-party extension points, via Python's own packaging metadata.

A plugin is an ordinary pip-installed package that declares itself under one of
the groups in `PLUGIN_GROUPS`, in its own `pyproject.toml` — nothing in NOEMA's
source changes to pick it up, which is the same "no import list to maintain"
guarantee `noema.providers.registry` already gives a provider defined inside
this repo, extended to one that is not::

    [project.entry-points."noema.providers"]
    gemini = "noema_provider_gemini:register"

`register` is called with no arguments, once, at startup, and is expected to
call `noema.providers.registry.register(...)` itself — the exact call a
built-in provider already makes from `noema/providers/<name>.py`. Nothing
about being a plugin is special; it is a provider that happens to live in its
own package.

**A plugin cannot open a hole in local mode.** `noema.providers.registry
.LOCAL_PROVIDERS` — the frozenset of providers allowed to run with no network
route out — is closed over names hardcoded in this repo. A plugin has no way
to add itself to it, so an installed provider plugin is simply unavailable
in local mode by default, the same as any other provider nobody has vetted
for that guarantee.

A plugin that fails to import or raises during registration is logged and
skipped — one broken third-party package must not stop the deployment from
starting. This is also why plugins load after the built-in providers: a
plugin failure can never take a working provider down with it.

Importers, exporters, question generators and themes are still direct
contributions to this repo, not yet pip-installable plugins — see the
"Plugin SDK" line in ROADMAP.md for what widening this to cover them would
take. `noema.providers.registry`'s existing `register()`/`create()` shape is
the template either would follow.
"""

from __future__ import annotations

from importlib.metadata import entry_points

from noema.core.logging import get_logger

log = get_logger(__name__)

__all__ = ["PLUGIN_GROUPS", "load_plugins"]

#: Every extension point NOEMA currently opens to a third-party package.
PLUGIN_GROUPS = ("noema.providers",)


def load_plugins() -> None:
    """Discover and register every installed plugin. Call once, at startup."""
    for group in PLUGIN_GROUPS:
        for entry_point in entry_points(group=group):
            try:
                register = entry_point.load()
                register()
            except Exception:
                log.exception("plugin.load_failed", group=group, name=entry_point.name)
            else:
                log.info("plugin.loaded", group=group, name=entry_point.name)
