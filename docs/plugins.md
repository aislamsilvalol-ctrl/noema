# NOEMA — Plugins

`CONTRIBUTING.md` describes adding an AI provider as "one file plus a registry line" — and
that story has always been true only for a file living inside this repo. Plugins are the
same story for a provider that lives in its own pip-installed package instead: nothing in
NOEMA's own source changes, or needs to, to pick it up.

Only **AI providers** are a plugin extension point today. Importers, exporters, question
generators and themes are still direct contributions to this repo — see the "Plugin SDK"
line in `ROADMAP.md`. `noema/providers/registry.py`'s `register()`/`create()` shape is the
template widening that would follow.

## Writing a provider plugin

1. Implement `AIProvider` (`noema/providers/base.py`) in your own package, exactly as a
   built-in provider does — see `docs/ai-providers.md` for the interface and
   `noema/providers/mock.py` for the smallest real example.
2. Write a zero-argument `register()` function that calls
   `noema.providers.registry.register(name)` the same way a built-in provider's own module
   does:

   ```python
   # noema_provider_example/__init__.py
   from noema.providers.registry import register
   from .provider import ExampleProvider

   def register() -> None:
       register("example")(lambda **kwargs: ExampleProvider(**kwargs))
   ```

3. Declare it in your package's `pyproject.toml`:

   ```toml
   [project.entry-points."noema.providers"]
   example = "noema_provider_example:register"
   ```

4. `pip install` your package alongside NOEMA. `register()` runs once, at API startup,
   after every built-in provider is already registered — a plugin can shadow a built-in
   name if it means to, but a built-in's own startup never depends on one.

Your provider is then selectable anywhere a provider name is: `NOEMA_DEFAULT_PROVIDER`,
a notebook's per-task override, a user's own preference.

## What isn't yours to change

**Local mode.** `LOCAL_PROVIDERS` in `noema/providers/registry.py` is a frozenset hardcoded
in this repo — the set of providers allowed to run with no network route out. A plugin has
no way to add itself to it. An installed provider plugin is simply unavailable in local
mode by default, the same as any built-in provider nobody has vetted for that guarantee.
This is deliberate: the promise a local install makes is enforced by code that a plugin
cannot reach, not by trusting every plugin author to have made it honestly.

## What happens when a plugin is broken

A plugin that fails to import, or whose `register()` raises, is logged
(`plugin.load_failed`, with the plugin's name and which extension-point group it declared)
and skipped. One broken third-party package must not be able to stop the deployment from
starting, or take a working built-in provider down with it — which is also why plugins load
strictly after the built-ins, never interleaved with them.

## Verifying a plugin loaded

```
docker compose logs api | grep plugin.loaded
```

or, from Python, once your package is installed:

```python
from importlib.metadata import entry_points
list(entry_points(group="noema.providers"))
```

If your plugin isn't there, the entry-point declaration in your `pyproject.toml` didn't
reach installed metadata — reinstall (`pip install -e .` picks up a `pyproject.toml` change
immediately; a prebuilt wheel does not, and needs rebuilding).
