"""Sending a learner's material back out.

The mirror of `noema.importers`: someone who came in with an Anki deck should be
able to leave with one too, review history included, and open it in Anki without
a plugin. Exporters are pure in the same way importers are — plain dataclasses in,
bytes out, no database and no network — for the same reason: the format is where
the surprises live, and surprises belong somewhere they can be tested without a
Postgres.
"""

from __future__ import annotations

__all__ = ["anki"]
