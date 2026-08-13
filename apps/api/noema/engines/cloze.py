"""Cloze deletions, as a pure text transform.

`The {{c1::diastole}} fills the ventricles and the {{c2::systole}} empties them.`
becomes two cards, each hiding one deletion and showing the rest. Two cards, not
one with two blanks: recalling "diastole" tells you nothing about whether they can
recall "systole", and scheduling them together would let a known half carry an
unknown one indefinitely.

Deletions sharing a number are hidden together — `c1` twice in a sentence is one
idea appearing twice, and blanking only one of them gives the answer away.

Pure by design: no database, no clock, no IO. The scheduling and storage decisions
belong to the caller; this only knows what a card should say.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["ClozeCard", "expand", "has_deletions"]

#: `{{c1::answer}}` or `{{c1::answer::hint}}`. The hint is Anki's convention and
#: costs nothing to support, since decks get imported from there.
PATTERN = re.compile(r"\{\{c(\d+)::(.+?)(?:::(.+?))?\}\}", re.DOTALL)

#: What a hidden deletion looks like on the front of a card.
BLANK = "[…]"


@dataclass(frozen=True, slots=True)
class ClozeCard:
    #: 1 for c1, 2 for c2 — kept so the caller can order the cards the way the
    #: text reads rather than the order a set happened to iterate in.
    number: int
    front: str
    back: str


def has_deletions(text: str) -> bool:
    return PATTERN.search(text) is not None


def expand(text: str) -> list[ClozeCard]:
    """One card per deletion number, in the order they first appear.

    Returns nothing for text with no deletions: a "cloze" card with no blank is a
    basic card that would grade itself correct forever, and silently making one is
    worse than making none.
    """
    numbers: list[int] = []
    for match in PATTERN.finditer(text):
        number = int(match.group(1))
        if number not in numbers:
            numbers.append(number)

    return [
        ClozeCard(number=n, front=_front(text, n), back=_back(text, n)) for n in numbers
    ]


def _front(text: str, target: int) -> str:
    """The text with ``target`` blanked and every other deletion revealed.

    Revealed rather than blanked: the other deletions are context this card is
    entitled to, and blanking them turns one question into a puzzle with several
    unknowns.
    """

    def render(match: re.Match[str]) -> str:
        if int(match.group(1)) != target:
            return match.group(2)
        hint = match.group(3)
        return f"{BLANK}({hint})" if hint else BLANK

    return PATTERN.sub(render, text).strip()


def _back(text: str, target: int) -> str:
    """What was hidden. Repeated deletions of the same number join with a comma."""
    answers = [
        match.group(2).strip()
        for match in PATTERN.finditer(text)
        if int(match.group(1)) == target
    ]
    return ", ".join(dict.fromkeys(answers))
