"""The last gate before a word reaches the learner.

The prompt hands the model its context in tagged sections (`<COURSE>`,
`<KNOWLEDGE_STATE>`, `<TURN_DIRECTIVE>` …). A model that echoes one would
show the learner the machinery: their mastery scores, the router's reason,
the rules. `LeakFilter` removes any such section, or a stray tag, from the
stream before it is shown. The `<PEDAGOGY>` record is not its business: the
sidecar filter, which runs first, takes it out and keeps it.

Like the other stream filters, a tail that might be the start of a tag is
held back one chunk, never lost.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

__all__ = ["INTERNAL_TAGS", "LeakFilter"]

#: Every section name the prompt builders use. A new section is added here
#: in the same change that adds it to a prompt.
INTERNAL_TAGS: tuple[str, ...] = (
    "ACTIVE_SESSION",
    "ASSESSMENT_RESULTS",
    "CONTEXT",
    "COURSE",
    "FOCUS_MODE",
    "KNOWLEDGE_STATE",
    "LEARNING_MEMORY",
    "LESSON",
    "MATERIALS",
    "RUBRIC",
    "SYSTEM",
    "TRANSCRIPT",
    "TURN_DIRECTIVE",
)

_TAG = re.compile(r"<(/?)(" + "|".join(INTERNAL_TAGS) + r")>")
_CANDIDATES = tuple(f"<{name}>" for name in INTERNAL_TAGS) + tuple(
    f"</{name}>" for name in INTERNAL_TAGS
)


def _held_tail(buffer: str) -> int:
    """Length of a tail that is a proper prefix of some tag, else 0."""
    start = buffer.rfind("<")
    if start == -1:
        return 0
    tail = buffer[start:]
    if any(tag.startswith(tail) and tag != tail for tag in _CANDIDATES):
        return len(tail)
    return 0


@dataclass
class LeakFilter:
    #: Characters removed, for the turn's log line.
    dropped: int = 0
    _pending: str = field(default="", repr=False)
    #: The section being skipped, "" when outside one.
    _inside: str = field(default="", repr=False)

    def feed(self, text: str) -> str:
        buffer = self._pending + text
        self._pending = ""
        out: list[str] = []
        while buffer:
            if self._inside:
                close = f"</{self._inside}>"
                end = buffer.find(close)
                if end == -1:
                    # Keep only what could still be the start of the close tag.
                    hold = 0
                    for size in range(min(len(close) - 1, len(buffer)), 0, -1):
                        if close.startswith(buffer[-size:]):
                            hold = size
                            break
                    self.dropped += len(buffer) - hold
                    self._pending = buffer[len(buffer) - hold :]
                    return "".join(out)
                self.dropped += end + len(close)
                buffer = buffer[end + len(close) :]
                self._inside = ""
                continue
            match = _TAG.search(buffer)
            if match is None:
                hold = _held_tail(buffer)
                out.append(buffer[: len(buffer) - hold])
                self._pending = buffer[len(buffer) - hold :]
                return "".join(out)
            out.append(buffer[: match.start()])
            self.dropped += len(match.group(0))
            if not match.group(1):
                self._inside = match.group(2)
            buffer = buffer[match.end() :]
        return "".join(out)

    def flush(self) -> str:
        """The stream ended. An unclosed section stays hidden; a held tail
        that never became a tag is released."""
        held, self._pending = self._pending, ""
        if self._inside:
            self.dropped += len(held)
            return ""
        return held
