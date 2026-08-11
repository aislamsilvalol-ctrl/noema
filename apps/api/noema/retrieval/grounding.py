"""Context assembly and citation enforcement.

Two jobs, both about trust:

* build the context block the model reasons over, clearly delimited and clearly
  labelled as *material*, never as instructions — a document can contain text aimed
  at the model, and during answering the model has no tools to reach for anyway;
* enforce citations on the way out. A sentence citing a block that was never
  supplied is dropped, because a tutor that invents a source is worse than no tutor:
  the learner encodes the invention.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from noema.retrieval.search import Retrieved

__all__ = [
    "Citation",
    "CitationFilter",
    "build_context",
    "citations_for",
]

CITATION = re.compile(r"\[(\d+)\]")

#: A sentence ends at .!? followed by whitespace, or at a newline. Buffering to this
#: granularity is what lets an invalid citation be caught before the user reads it.
SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n+")

#: Enough context to answer without burying the question.
DEFAULT_TOKEN_BUDGET = 6_000
CHARS_PER_TOKEN = 4


@dataclass(frozen=True, slots=True)
class Citation:
    number: int
    chunk_id: str
    source_id: str
    location: str
    excerpt: str


def build_context(
    results: Sequence[Retrieved], token_budget: int = DEFAULT_TOKEN_BUDGET
) -> tuple[str, list[Retrieved]]:
    """Render numbered context blocks, and return the ones that actually fit.

    The returned list is what the citation filter validates against, so a block
    dropped for budget can never be cited.
    """
    blocks: list[str] = []
    included: list[Retrieved] = []
    used = 0

    for result in results:
        rendered = f"[{len(included) + 1}] {result.location}\n{result.content.strip()}"
        cost = len(rendered) // CHARS_PER_TOKEN
        if included and used + cost > token_budget:
            break
        blocks.append(rendered)
        included.append(result)
        used += cost

    return "\n\n".join(blocks), included


def citations_for(results: Sequence[Retrieved]) -> list[Citation]:
    return [
        Citation(
            number=index,
            chunk_id=str(result.chunk_id),
            source_id=str(result.source_id),
            location=result.location,
            excerpt=result.content.strip()[:280],
        )
        for index, result in enumerate(results, start=1)
    ]


@dataclass
class CitationFilter:
    """Streams text through, dropping sentences that cite unsupplied blocks.

    Buffers to the sentence rather than the token: a citation marker only becomes
    checkable once the sentence around it is complete. The cost is that output
    appears a sentence at a time, which is a fair price for never showing the user a
    fabricated source.
    """

    valid_numbers: frozenset[int]
    buffer: str = ""
    dropped: list[str] = field(default_factory=list)
    used: set[int] = field(default_factory=set)

    @classmethod
    def for_results(cls, results: Sequence[Retrieved]) -> CitationFilter:
        return cls(valid_numbers=frozenset(range(1, len(results) + 1)))

    def feed(self, text: str) -> str:
        """Accept streamed text; return whatever is now safe to show."""
        self.buffer += text
        return self._drain(final=False)

    def flush(self) -> str:
        """Emit whatever is left when the stream ends."""
        return self._drain(final=True)

    def _drain(self, *, final: bool) -> str:
        emitted: list[str] = []

        while True:
            match = SENTENCE_END.search(self.buffer)
            if match is None:
                break
            sentence, self.buffer = (
                self.buffer[: match.end()],
                self.buffer[match.end() :],
            )
            kept = self._check(sentence)
            if kept is not None:
                emitted.append(kept)

        if final and self.buffer:
            kept = self._check(self.buffer)
            self.buffer = ""
            if kept is not None:
                emitted.append(kept)

        return "".join(emitted)

    def _check(self, sentence: str) -> str | None:
        cited = {int(number) for number in CITATION.findall(sentence)}
        if not cited:
            return sentence

        invalid = cited - self.valid_numbers
        if invalid:
            self.dropped.append(sentence.strip())
            return None

        self.used.update(cited)
        return sentence


def used_citations(citations: Iterable[Citation], used: set[int]) -> list[Citation]:
    """Only the sources the answer actually leaned on reach the user."""
    return [citation for citation in citations if citation.number in used]
