"""The Academic Source Registry reads OCW's own JSON and records licence and trust."""

from __future__ import annotations

import json
from pathlib import Path

from noema.academic.ocw import discover_course, lecture_links, parse_course, parse_lecture
from noema.academic.registry import (
    ContentType,
    Licence,
    Trust,
    licence_from_url,
    trust_for_url,
)

FIXTURES = Path(__file__).parent / "fixtures" / "ocw"
SLUG = "18-06-linear-algebra-spring-2010"


def _fetch(url: str) -> str:
    if url.endswith(f"/courses/{SLUG}/data.json"):
        return (FIXTURES / f"{SLUG}.data.json").read_text()
    if "/video_galleries/video-lectures/" in url:
        return (FIXTURES / "video-gallery.snippet.html").read_text()
    if url.endswith("lecture-1-the-geometry-of-linear-equations/data.json"):
        return (FIXTURES / "lecture-1.data.json").read_text()
    raise FileNotFoundError(url)  # every other lecture: not recorded → skipped


def test_licence_and_trust_are_read_not_assumed() -> None:
    assert (
        licence_from_url("https://creativecommons.org/licenses/by-nc-sa/4.0/")
        is Licence.cc_by_nc_sa_4
    )
    assert (
        licence_from_url("https://creativecommons.org/licenses/by-nc-sa/4.0")
        is Licence.cc_by_nc_sa_4
    )
    assert licence_from_url(None) is Licence.unknown
    assert licence_from_url("https://example.com/licence") is Licence.unknown
    assert trust_for_url("https://ocw.mit.edu/courses/x/") is Trust.official
    assert trust_for_url("https://ocw.mit.edu.evil.example/courses/x/") is Trust.unknown
    assert (
        Licence.cc_by_nc_sa_4.allows_derived_use
        and not Licence.unknown.allows_derived_use
    )


def test_course_record_from_ocw_json() -> None:
    course = parse_course(SLUG, json.loads((FIXTURES / f"{SLUG}.data.json").read_text()))
    assert course.university == "MIT" and course.department == "Mathematics"
    assert course.course_code == "18.06" and course.title == "Linear Algebra"
    assert course.instructors == ["Prof. Gilbert Strang"]
    assert course.term == "Spring" and course.year == "2010"
    assert course.topics == [["Mathematics", "Linear Algebra"]]
    assert "Lecture Videos" in course.resource_types
    assert course.trust is Trust.official


def test_gallery_links_keep_order_and_drop_duplicates() -> None:
    links = lecture_links((FIXTURES / "video-gallery.snippet.html").read_text())
    assert len(links) == 35
    assert links[0].endswith("/resources/lecture-1-the-geometry-of-linear-equations")
    assert len(set(links)) == len(links)


def test_lecture_record_carries_licence_captions_and_provenance() -> None:
    course = parse_course(SLUG, json.loads((FIXTURES / f"{SLUG}.data.json").read_text()))
    data = json.loads((FIXTURES / "lecture-1.data.json").read_text())
    lecture = parse_lecture(
        SLUG,
        f"/courses/{SLUG}/resources/lecture-1-the-geometry-of-linear-equations",
        data,
        order=1,
        course=course,
    )
    assert lecture.content_type is ContentType.lecture_video
    assert lecture.licence is Licence.cc_by_nc_sa_4 and lecture.trust is Trust.official
    assert lecture.usable
    assert lecture.youtube_id == "J7DzL2_Na80"
    kinds = {c.kind for c in lecture.captions}
    assert kinds == {"vtt", "transcript_pdf"}
    assert all(c.url.startswith("https://ocw.mit.edu/") for c in lecture.captions)
    assert lecture.order == 1 and lecture.course_code == "18.06"
    assert lecture.metadata["archive_url"].endswith("01.mp4")
    assert "linear equations" in lecture.metadata["description"].lower()


def test_discover_course_skips_lectures_it_cannot_read_and_never_invents() -> None:
    course = discover_course(SLUG, _fetch)
    assert course.title == "Linear Algebra"
    # only lecture 1 is recorded in the fixtures; the other 34 are not invented
    assert len(course.lectures) == 1 and course.lectures[0].order == 1
    assert course.lectures_with_captions == 1
    record = course.lectures[0].model_dump(mode="json")
    assert (
        record["url"]
        == f"https://ocw.mit.edu/courses/{SLUG}/resources/lecture-1-the-geometry-of-linear-equations/"
    )
    assert record["ingestion_status"] == "registered"
