"""The weights a given learner is scheduled with.

Stored on the user rather than in a table of their own: it is one small record per
person, written a few times a year, and read on every review. A row that is always
fetched with the user might as well be part of the user.

Falling back to the defaults is not a failure mode — it is the correct answer until
there is enough history to earn something better.
"""

from __future__ import annotations

from typing import Any

from noema.core.logging import get_logger
from noema.db.models import User
from noema.engines import fsrs

log = get_logger(__name__)

__all__ = ["fitted_weights", "store_weights"]

SETTINGS_KEY = "fsrs"


def fitted_weights(user: User) -> fsrs.Weights:
    """This learner's weights, or the defaults.

    Anything malformed is ignored rather than raised on. A corrupted settings blob
    should cost someone the personalisation, not the ability to review a card.
    """
    stored = (user.settings or {}).get(SETTINGS_KEY)
    if not isinstance(stored, dict):
        return fsrs.DEFAULT_WEIGHTS

    weights = stored.get("weights")
    if (
        not isinstance(weights, list)
        or len(weights) != len(fsrs.DEFAULT_WEIGHTS)
        or not all(isinstance(w, int | float) for w in weights)
    ):
        if weights is not None:
            log.warning("fsrs.weights_malformed", user_id=str(user.id))
        return fsrs.DEFAULT_WEIGHTS

    return tuple(float(w) for w in weights)


def store_weights(user: User, weights: fsrs.Weights, meta: dict[str, Any]) -> None:
    """Record a fit, with what it was measured against.

    The metadata is kept so the learner can be told why their schedule changed, and
    so a later fit can be compared with this one rather than with a memory of it.
    """
    settings = dict(user.settings or {})
    settings[SETTINGS_KEY] = {"weights": list(weights), **meta}
    # Reassigned rather than mutated in place: SQLAlchemy does not notice a JSONB
    # dict that was edited under it, and the fit would be silently lost.
    user.settings = settings
