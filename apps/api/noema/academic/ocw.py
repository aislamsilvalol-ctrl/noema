"""MIT OpenCourseWare discovery: a course and its lecture videos, from OCW's own JSON.

OCW publishes, next to every course page, a machine-readable ``data.json``
(title, department numbers, instructors, term, year, level, topics,
resource types), and next to every resource page another ``data.json`` with
the licence URL, the YouTube id, the archive.org file and the official
captions (``.vtt``) and transcript (PDF) paths. This module reads those two
documents and the video gallery's anchor list, and nothing else: no video
is downloaded, no transcript is fetched here. The fetcher is injected so the
same code runs against recorded fixtures in tests and against the site in a
job.

Everything OCW publishes is CC BY-NC-SA 4.0 unless a resource says
otherwise; the licence is read from the resource, never assumed.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from noema.academic.registry import (
    CaptionResource,
    ContentType,
    CourseRecord,
    Licence,
    SourceRecord,
    Trust,
    licence_from_url,
)
from noema.core.logging import get_logger

log = get_logger(__name__)

OCW = "https://ocw.mit.edu"
Fetch = Callable[[str], str]

#: MIT department numbers → names, for the ones the pilot touches. Others
#: are recorded by number and resolved later.
DEPARTMENTS = {
    "6": "Electrical Engineering and Computer Science",
    "8": "Physics",
    "9": "Brain and Cognitive Sciences",
    "14": "Economics",
    "18": "Mathematics",
    "24": "Linguistics and Philosophy",
}

_LECTURE_LINK = re.compile(r'href="(/courses/[^/"]+/resources/[^"#?]+?)/?"')


def course_data_url(slug: str) -> str:
    return f"{OCW}/courses/{slug}/data.json"


def gallery_url(slug: str, gallery: str = "video-lectures") -> str:
    return f"{OCW}/courses/{slug}/video_galleries/{gallery}/"


def lecture_links(gallery_html: str) -> list[str]:
    """Resource paths in the order the gallery lists them, without duplicates."""
    seen: dict[str, None] = {}
    for path in _LECTURE_LINK.findall(gallery_html):
        seen.setdefault(path.rstrip("/"), None)
    return list(seen)


def parse_course(slug: str, data: dict[str, Any]) -> CourseRecord:
    numbers = [str(n) for n in data.get("department_numbers", [])]
    department = DEPARTMENTS.get(numbers[0]) if numbers else None
    return CourseRecord(
        course_id=f"mit-ocw:{slug}",
        university="MIT",
        department=department or (f"Course {numbers[0]}" if numbers else None),
        course_code=data.get("primary_course_number"),
        title=data.get("course_title") or data.get("title") or slug,
        instructors=[
            i.get("title")
            or f"{i.get('first_name', '')} {i.get('last_name', '')}".strip()
            for i in data.get("instructors", [])
        ],
        url=f"{OCW}/courses/{slug}/",
        term=data.get("term"),
        year=str(data["year"]) if data.get("year") else None,
        level=list(data.get("level", [])),
        topics=[list(t) for t in data.get("topics", [])],
        licence=Licence.cc_by_nc_sa_4,  # OCW's site-wide licence; resources restate it
        trust=Trust.official,
        resource_types=list(data.get("learning_resource_types", [])),
    )


def parse_lecture(
    slug: str, path: str, data: dict[str, Any], *, order: int, course: CourseRecord
) -> SourceRecord:
    video = data.get("video_files") or {}
    meta = data.get("video_metadata") or {}
    captions: list[CaptionResource] = []
    for c in video.get("video_captions_resources", []) or []:
        captions.append(
            CaptionResource(
                url=OCW + c["file"], language=c.get("language", "en"), kind="vtt"
            )
        )
    for t in video.get("video_transcript_resources", []) or []:
        kind = (
            "transcript_pdf" if t["file"].lower().endswith(".pdf") else "transcript_txt"
        )
        captions.append(
            CaptionResource(
                url=OCW + t["file"], language=t.get("language", "en"), kind=kind
            )
        )
    return SourceRecord(
        source_id=f"mit-ocw:{slug}:{path.rsplit('/', 1)[-1]}",
        university="MIT",
        department=course.department,
        course_code=course.course_code,
        course_title=course.title,
        instructors=course.instructors,
        content_type=ContentType.lecture_video,
        title=data.get("title") or path.rsplit("/", 1)[-1],
        url=f"{OCW}{path}/",
        published_at=" ".join(x for x in (course.term, course.year) if x) or None,
        licence=licence_from_url(data.get("license")),
        trust=Trust.official,
        order=order,
        youtube_id=meta.get("youtube_id") or None,
        captions=captions,
        metadata={
            "archive_url": video.get("archive_url"),
            "file_size": data.get("file_size"),
            "description": (data.get("content") or "")[:500],
            "resourcetype": data.get("resourcetype"),
        },
    )


def discover_course(
    slug: str, fetch: Fetch, *, gallery: str = "video-lectures"
) -> CourseRecord:
    """The course record with one SourceRecord per lecture video, from OCW's JSON."""
    course = parse_course(slug, json.loads(fetch(course_data_url(slug))))
    try:
        html = fetch(gallery_url(slug, gallery))
    except Exception:
        html = ""
    for order, path in enumerate(lecture_links(html), start=1):
        try:
            data = json.loads(fetch(f"{OCW}{path}/data.json"))
        except Exception as exc:
            # a lecture whose JSON cannot be read is left out, never invented
            log.warning("academic.ocw.lecture_unreadable", path=path, error=str(exc))
            continue
        if data.get("resourcetype") != "Video":
            continue
        course.lectures.append(
            parse_lecture(slug, path, data, order=order, course=course)
        )
    return course


def http_fetch(url: str) -> str:
    """The real fetcher: GET with a plain identifying user agent. Not used in tests."""
    import httpx

    response = httpx.get(
        url,
        timeout=30,
        follow_redirects=True,
        headers={
            "User-Agent": "noema-academic-registry/0.1 (+https://github.com/aislamsilvalol-ctrl/noema)"
        },
    )
    response.raise_for_status()
    return response.text
