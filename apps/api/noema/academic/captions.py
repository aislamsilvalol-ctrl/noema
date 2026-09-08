"""Captions → cues → sentences → segments, with timestamps kept all the way.

Phase 2 of `docs/academic-knowledge-engine.md`. A lecture's official ``.vtt``
is parsed into cues, the cues are joined into sentences that remember when
they were said, and the sentences are cut into topic segments. Nothing here
summarises, rewrites or interprets: a segment is the lecturer's own words with
a start and an end, and the timestamps are what later lets a claim be checked
against the moment it came from.

Segmentation is lexical cohesion (Hearst's TextTiling, 1997): a boundary goes
where the vocabulary on the left stops resembling the vocabulary on the right.
It needs no model, which is why Phase 2 starts here — an embedding-based
segmentation can replace `segment` later without changing what it returns.

The quality flag is the honest part. Automatic speech recognition mangles
mathematics ("x squared" arrives as "x squared", but also as "expert"), drops
sentence ends, and repeats itself; a segment that looks like that is marked
and is meant to be reviewed before anything is extracted from it.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field

#: A cue's timing line: 00:00:12.345 --> 00:00:15.678 (hours optional).
_TIMING = re.compile(
    r"(?:(\d+):)?(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*(?:(\d+):)?(\d{2}):(\d{2})[.,](\d{3})"
)
_TAGS = re.compile(r"</?[cvbiu][^>]*>|<\d{2}:\d{2}:\d{2}\.\d{3}>")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"[a-z][a-z'-]+")

#: Words that carry no topic. Deliberately short: a longer list starts
#: deciding what a lecture is about, which is not this function's job.
_STOPWORDS = """a an and are as at be been but by can could do does for from get go had
    has have he her here his how i if in into is it its just like make me my no not of on
    one or our out say see she so some than that the their them then there these they this
    to too up us was we were what when where which who will with would you your
    ok okay right well now thing things kind sort lot"""
STOPWORDS = frozenset(_STOPWORDS.split())

#: Signs the transcript itself is unreliable, not that the lecture was.
FILLER = frozenset({"um", "uh", "er", "ah", "hmm", "mmm"})

#: Words a lecturer says instead of writing a symbol.
_MATH_SPEECH = """squared cubed sqrt root times equals equal plus minus divided over
    matrix matrices vector vectors column columns row rows determinant
    transpose inverse eigenvalue eigenvalues eigenvector eigenvectors
    zero one two three four five six seven eight nine ten"""
MATH_SPEECH = frozenset(_MATH_SPEECH.split())

#: Above this share of spoken-mathematics words, the text is standing in for
#: notation. Calibrated on MIT 18.06: 0.065 is that course's median segment,
#: 0.12 its top fifth — a mathematics lecture is not suspicious for being one.
MATH_DENSITY = 0.12


@dataclass(frozen=True, slots=True)
class Cue:
    start_ms: int
    end_ms: int
    text: str


@dataclass(frozen=True, slots=True)
class Sentence:
    start_ms: int
    end_ms: int
    text: str

    @property
    def words(self) -> list[str]:
        return _WORD.findall(self.text.lower())


@dataclass(slots=True)
class Segment:
    """A stretch of one lecture: its words, when they were said, how trustworthy."""

    index: int
    start_ms: int
    end_ms: int
    text: str
    sentences: int
    quality: list[str] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        """No blocking quality problem — short segments are kept, flagged."""
        return "empty" not in self.quality

    def as_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "text": self.text,
            "sentences": self.sentences,
            "quality": self.quality,
        }


def _ms(hours: str | None, minutes: str, seconds: str, millis: str) -> int:
    return (
        int(hours or 0) * 3_600_000
        + int(minutes) * 60_000
        + int(seconds) * 1000
        + int(millis)
    )


def parse_vtt(source: str) -> list[Cue]:
    """WebVTT (and SRT, whose only difference here is the comma) → cues.

    Rolling captions repeat the previous line as the next cue's first line;
    the repetition is dropped so a sentence is not counted twice.
    """
    cues: list[Cue] = []
    lines = source.replace("\r\n", "\n").split("\n")
    i = 0
    while i < len(lines):
        match = _TIMING.search(lines[i])
        if not match:
            i += 1
            continue
        start = _ms(match.group(1), match.group(2), match.group(3), match.group(4))
        end = _ms(match.group(5), match.group(6), match.group(7), match.group(8))
        i += 1
        body: list[str] = []
        while i < len(lines) and lines[i].strip() and not _TIMING.search(lines[i]):
            body.append(_TAGS.sub("", lines[i]).strip())
            i += 1
        text = " ".join(part for part in body if part)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        if cues and text == cues[-1].text:
            continue
        if cues and cues[-1].text.endswith(text):  # rolling repeat
            continue
        cues.append(Cue(start_ms=start, end_ms=max(end, start), text=text))
    return cues


def sentences(cues: list[Cue]) -> list[Sentence]:
    """Cues → sentences that keep the timing of the words they contain.

    A caption breaks where the screen is full, not where the lecturer stops
    talking, so the cues are joined and re-split on sentence ends; a sentence
    starts when its first cue starts and ends when its last cue ends. Speech
    with no punctuation at all (some automatic captions) is split on long
    pauses instead, so a segment never becomes one unbroken block.
    """
    if not cues:
        return []
    joined = " ".join(cue.text for cue in cues)
    if _SENTENCE_END.search(joined) is None:
        return _split_on_pauses(cues)
    # walk the cues alongside the sentence split, so each sentence knows which
    # cues it came from without re-aligning by string search
    spans: list[Sentence] = []
    cue_index = 0
    consumed = 0  # characters of the current cue already used
    for part in _SENTENCE_END.split(joined):
        part = part.strip()
        if not part:
            continue
        need = len(part)
        start_cue = cue_index
        while need > 0 and cue_index < len(cues):
            available = len(cues[cue_index].text) - consumed
            if available > need:
                consumed += need + 1
                need = 0
            else:
                need -= available + 1
                cue_index += 1
                consumed = 0
        # `consumed == 0` means the walk stepped past the cue that held the
        # sentence's last character; the sentence ends in that cue, not in the
        # next one, and a timestamp that points one cue late is a timestamp
        # that cannot be checked against the video
        last_used = (
            cue_index - 1 if consumed == 0 and cue_index > start_cue else cue_index
        )
        end_cue = max(start_cue, min(last_used, len(cues) - 1))
        spans.append(
            Sentence(
                start_ms=cues[start_cue].start_ms,
                end_ms=cues[end_cue].end_ms,
                text=part,
            )
        )
    return spans


def _split_on_pauses(cues: list[Cue], gap_ms: int = 1500) -> list[Sentence]:
    out: list[Sentence] = []
    buffer: list[Cue] = []
    for cue in cues:
        if buffer and cue.start_ms - buffer[-1].end_ms > gap_ms:
            out.append(_join(buffer))
            buffer = []
        buffer.append(cue)
    if buffer:
        out.append(_join(buffer))
    return out


def _join(cues: list[Cue]) -> Sentence:
    return Sentence(
        start_ms=cues[0].start_ms,
        end_ms=cues[-1].end_ms,
        text=" ".join(cue.text for cue in cues),
    )


def _cosine(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    shared = set(left) & set(right)
    if not shared:
        return 0.0
    dot = sum(left[word] * right[word] for word in shared)
    norm = math.sqrt(sum(v * v for v in left.values())) * math.sqrt(
        sum(v * v for v in right.values())
    )
    return dot / norm if norm else 0.0


def _content(sentence: Sentence) -> Counter[str]:
    return Counter(word for word in sentence.words if word not in STOPWORDS)


def segment(
    spans: list[Sentence],
    *,
    window: int = 6,
    min_sentences: int = 8,
    max_sentences: int = 40,
) -> list[Segment]:
    """Cut a lecture where its vocabulary changes, never mid-sentence.

    ``window`` sentences on each side of every candidate boundary are compared;
    a boundary is kept where the similarity dips below the mean minus half a
    standard deviation (TextTiling's own threshold), and `min_sentences` keeps
    the pieces from becoming paragraphs. Boundaries are chosen before the
    length rules apply, so a long segment is one that really does keep talking
    about the same thing.
    """
    if not spans:
        return []
    if len(spans) <= min_sentences:
        return [_segment(0, spans)]
    scores: list[tuple[int, float]] = []
    for boundary in range(1, len(spans)):
        left: Counter[str] = Counter()
        right: Counter[str] = Counter()
        for s in spans[max(0, boundary - window) : boundary]:
            left.update(_content(s))
        for s in spans[boundary : boundary + window]:
            right.update(_content(s))
        scores.append((boundary, _cosine(left, right)))
    values = [value for _, value in scores]
    mean = sum(values) / len(values)
    sd = math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))
    threshold = mean - sd / 2
    cuts: list[int] = []
    for index, (boundary, value) in enumerate(scores):
        if value > threshold:
            continue
        # a local minimum only: a dip is one boundary, not a run of them
        before = scores[index - 1][1] if index else math.inf
        after = scores[index + 1][1] if index + 1 < len(scores) else math.inf
        if value > before or value > after:
            continue
        if cuts and boundary - cuts[-1] < min_sentences:
            continue
        if boundary < min_sentences or len(spans) - boundary < min_sentences:
            continue
        cuts.append(boundary)

    segments: list[Segment] = []
    start = 0
    for cut in [*cuts, len(spans)]:
        piece = spans[start:cut]
        while len(piece) > max_sentences:  # a segment nobody would read
            segments.append(_segment(len(segments), piece[:max_sentences]))
            piece = piece[max_sentences:]
        if piece:
            segments.append(_segment(len(segments), piece))
        start = cut
    return segments


def _segment(index: int, spans: list[Sentence]) -> Segment:
    text = " ".join(s.text for s in spans).strip()
    words = [word for s in spans for word in s.words]
    quality: list[str] = []
    if not text:
        quality.append("empty")
    if len(spans) < 3:
        quality.append("short")
    if words and sum(1 for w in words if w in FILLER) / len(words) > 0.02:
        quality.append("disfluent")
    if words and len(set(words)) / len(words) < 0.35:
        quality.append("repetitive")
    if not re.search(r"[.!?]", text):
        quality.append("unpunctuated")
    if words and sum(1 for w in words if w in MATH_SPEECH) / len(words) > MATH_DENSITY:
        # Spoken mathematics survives transcription badly ("x squared" and
        # "expert" are the same sound to a recogniser), and the board carries
        # what the words do not. A mention is not the signal — a segment that
        # is mostly spoken formula is, so this is a density and its threshold
        # was read off MIT 18.06: the top fifth of its segments, where the
        # words really are standing in for notation.
        quality.append("spoken_math")
    return Segment(
        index=index,
        start_ms=spans[0].start_ms,
        end_ms=spans[-1].end_ms,
        text=text,
        sentences=len(spans),
        quality=quality,
    )


def segments_for(vtt: str, **kwargs: int) -> list[Segment]:
    """The whole path, for a caller that has the caption file and wants pieces."""
    return segment(sentences(parse_vtt(vtt)), **kwargs)
