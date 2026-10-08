"""Which language a piece of text is in, by function words.

The eval reads the tutor's replies with it; the engine reads the learner's
messages with it, so the turn directive can name the language to answer in
(2026-10-07 eval: "What does the mitochondria actually do?", asked in a
Portuguese course, was answered in Portuguese while the directive only said
"the language of the learner's latest message").

A heuristic, not a model: pt, es and en are told apart by the small words
every sentence carries. Short messages ("ok", "I don't get it.") rarely carry
two of them, and then nothing is claimed.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

__all__ = ["LANGUAGE_NAMES", "detect_language", "reply_language"]

LANGUAGE_NAMES: dict[str, str] = {"pt": "Portuguese", "es": "Spanish", "en": "English"}

#: Function words that tell the three apart. Words the languages share
#: ("para", "porque", "está", "o") are left out: a Portuguese reply full of
#: "o valor ... para" once read as Spanish.
_MARKERS: dict[str, frozenset[str]] = {
    "pt": frozenset(
        [
            "não",
            "você",
            "é",
            "do",
            "da",
            "dos",
            "das",
            "em",
            "um",
            "uma",
            "com",
            "isso",
            "são",
            "então",
            "mas",
            "muito",
            "pra",
            "seu",
            "sua",
            "já",
            "ao",
        ]
    ),
    "es": frozenset(
        [
            "el",
            "la",
            "los",
            "las",
            "y",
            "del",
            "con",
            "es",
            "muy",
            "pero",
            "qué",
            "cómo",
            "usted",
            "tú",
            "aquí",
            "su",
            "ya",
            "lo",
            "un",
            "una",
            "eso",
        ]
    ),
    "en": frozenset(
        [
            "the",
            "is",
            "and",
            "you",
            "of",
            "to",
            "in",
            "that",
            "it",
            "what",
            "this",
            "with",
            "for",
            "are",
            "your",
            "be",
            "when",
            "or",
            "so",
            "can",
            "how",
        ]
    ),
}
_WORD = re.compile(r"[a-zà-öø-ÿ]+", re.IGNORECASE)
_CODE = re.compile(r"```.*?```|`[^`]*`", re.DOTALL)


def detect_language(text: str, *, min_words: int = 6) -> str:
    """pt / es / en, or "" when there is too little to tell.

    Two marker words at least, and more of them than any other language has:
    a tie is not a reading.
    """
    words = [w.lower() for w in _WORD.findall(_CODE.sub(" ", text))]
    if len(words) < min_words:
        return ""
    scores = sorted(
        ((sum(w in markers for w in words), lang) for lang, markers in _MARKERS.items()),
        reverse=True,
    )
    (best, lang), (second, _) = scores[0], scores[1]
    return lang if best >= 2 and best > second else ""


def reply_language(latest: str, earlier: Iterable[str] = ()) -> str:
    """The language the tutor should answer in: the latest learner message's
    when it is clear, else the most recent earlier message that was, else ""
    (the caller then falls back to the course's language).

    `earlier` is the learner's previous messages, newest first.
    """
    for text in (latest, *earlier):
        found = detect_language(text, min_words=3)
        if found:
            return found
    return ""
