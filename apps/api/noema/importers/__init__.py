"""Bringing a learner's existing material in.

Someone with ten thousand Anki cards and four years of scheduling history will
not retype them, and should not have to. An import that arrives is worth more
than any feature that only works on material created here.

Importers are pure: bytes in, plain dataclasses out, no database and no network.
The persistence step is separate and boring on purpose — parsing someone else's
file format is where the surprises live, and surprises belong somewhere they can
be tested without a Postgres.
"""

from __future__ import annotations

__all__ = ["anki"]
