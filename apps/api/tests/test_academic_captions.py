"""Captions keep their timestamps, and acquisition obeys the licence.

The fixture is written here rather than taken from a lecture: the cache of a
real transcript is private by design, and a test file is the wrong place to
redistribute one.
"""

from __future__ import annotations

import json
from pathlib import Path

from noema.academic.acquire import acquire, caption_for
from noema.academic.captions import parse_vtt, segment, segments_for, sentences
from noema.academic.registry import (
    CaptionResource,
    ContentType,
    Licence,
    SourceRecord,
    Trust,
)

VTT = """WEBVTT

1
00:00:01.000 --> 00:00:04.000
Okay. Today we begin with the geometry

2
00:00:04.000 --> 00:00:07.500
of linear equations. Two equations,

3
00:00:07.500 --> 00:00:11.000
two unknowns. That is the row picture.

4
00:00:11.000 --> 00:00:14.000
<c.colorWhite>The column picture is different.</c>
"""


def record(**kwargs: object) -> SourceRecord:
    base: dict[str, object] = {
        "source_id": "mit-ocw:course:lecture-1",
        "university": "MIT",
        "content_type": ContentType.lecture_video,
        "title": "Lecture 1",
        "url": "https://ocw.mit.edu/courses/course/resources/lecture-1/",
        "licence": Licence.cc_by_nc_sa_4,
        "trust": Trust.official,
        "captions": [
            CaptionResource(url="https://ocw.mit.edu/x.vtt", kind="vtt"),
            CaptionResource(url="https://ocw.mit.edu/x.pdf", kind="transcript_pdf"),
        ],
    }
    return SourceRecord.model_validate({**base, **kwargs})


def test_cues_carry_their_timing_and_lose_their_markup() -> None:
    cues = parse_vtt(VTT)
    assert len(cues) == 4
    assert cues[0].start_ms == 1000 and cues[0].end_ms == 4000
    assert cues[3].text == "The column picture is different."
    assert cues[1].start_ms == 4000


def test_a_sentence_spans_the_cues_it_was_split_across() -> None:
    spans = sentences(parse_vtt(VTT))
    texts = [s.text for s in spans]
    assert texts[0] == "Okay."
    assert "geometry of linear equations." in texts[1]
    # the sentence starts in cue 1 and ends in cue 2, and says so
    assert spans[1].start_ms == 1000 and spans[1].end_ms == 7500
    assert all(s.end_ms >= s.start_ms for s in spans)


def test_rolling_repeats_are_dropped() -> None:
    rolling = """WEBVTT

00:00:01.000 --> 00:00:03.000
the row picture

00:00:03.000 --> 00:00:05.000
the row picture
"""
    assert len(parse_vtt(rolling)) == 1


def test_captions_without_punctuation_still_split() -> None:
    unpunctuated = "WEBVTT\n\n" + "\n\n".join(
        f"00:00:{i * 10:02d}.000 --> 00:00:{i * 10 + 2:02d}.000\nword{i} and more"
        for i in range(6)
    )
    spans = sentences(parse_vtt(unpunctuated))
    assert len(spans) > 1  # split on the pauses, not left as one block


def test_segments_are_cut_where_the_vocabulary_changes() -> None:
    # each line differs — identical consecutive cues are dropped as rolling
    # repeats, which is right for captions and wrong for a fixture
    first = [
        f"The row picture draws equation {i} as a line and asks where the lines meet."
        for i in range(10)
    ]
    second = [
        f"Eigenvalue {i} describes how a matrix stretches a vector along its direction."
        for i in range(10)
    ]
    cues = []
    for i, text in enumerate([*first, *second]):
        at = f"00:{i // 60:02d}:{i % 60:02d}"
        cues.append(f"{at}.000 --> {at}.500\n{text}")
    spans = sentences(parse_vtt("WEBVTT\n\n" + "\n\n".join(cues)))
    segments = segment(spans, window=4, min_sentences=4)
    assert len(segments) >= 2
    assert segments[0].end_ms <= segments[1].start_ms
    assert "row picture" in segments[0].text
    assert "Eigenvalue" in segments[-1].text
    assert all(s.sentences > 0 for s in segments)


def test_quality_flags_name_what_is_wrong() -> None:
    whole = segments_for(VTT)
    assert len(whole) == 1 and whole[0].usable
    assert whole[0].start_ms == 1000 and whole[0].end_ms == 14000

    def flags(body: str) -> set[str]:
        vtt = f"WEBVTT\n\n00:00:01.000 --> 00:00:09.000\n{body}\n"
        return set(segments_for(vtt)[0].quality)

    assert "short" in flags("One line only.")  # not a topic
    assert "spoken_math" in flags(
        "x squared plus y equals two times the vector minus one column."
    )
    # a mention is not the flag: this segment talks about a matrix, it does
    # not spell one out
    assert "spoken_math" not in flags(
        "A matrix is a table of numbers, and today we will look at what it "
        "does to the space around it, which is the part people remember."
    )
    assert "unpunctuated" in flags("so then we take the row and we look at it")
    assert "disfluent" in flags(
        "um so the uh row picture is um the one we want to see today alright"
    )
    assert "repetitive" in flags("Row row row row picture. Row row row row picture!")


def test_acquisition_skips_what_the_licence_does_not_allow(tmp_path: Path) -> None:
    calls: list[str] = []

    def fetch(url: str) -> str:
        calls.append(url)
        return VTT

    records = [
        record(),
        record(source_id="mit-ocw:course:lecture-2", licence=Licence.unknown),
        record(source_id="mit-ocw:course:lecture-3", trust=Trust.unknown),
        record(source_id="mit-ocw:course:lecture-4", captions=[]),
    ]
    results = acquire(records, tmp_path, fetch, pause=0)

    assert [r.status for r in results] == [
        "fetched",
        "skipped:licence",
        "skipped:trust",
        "skipped:no_captions",
    ]
    assert calls == ["https://ocw.mit.edu/x.vtt"]  # only the usable one
    written = json.loads((tmp_path / "manifest.jsonl").read_text().splitlines()[0])
    assert written["licence"] == "CC-BY-NC-SA-4.0" and written["trust"] == "official"
    assert written["checksum"].startswith("sha256:")
    assert (tmp_path / written["file"]).read_text() == VTT


def test_a_cached_lecture_is_not_fetched_twice(tmp_path: Path) -> None:
    calls: list[str] = []

    def fetch(url: str) -> str:
        calls.append(url)
        return VTT

    acquire([record()], tmp_path, fetch, pause=0)
    again = acquire([record()], tmp_path, fetch, pause=0)
    assert [r.status for r in again] == ["cached"]
    assert len(calls) == 1


def test_the_vtt_is_preferred_over_the_transcript_pdf() -> None:
    caption = caption_for(record())
    assert caption is not None and caption.kind == "vtt"
