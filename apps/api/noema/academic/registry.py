"""The Academic Source Registry: records, licences and trust.

A record answers, for one piece of published university material: whose is
it, which course, which licence, may the pipeline use it automatically, and
where are the official captions and transcripts. Records are plain pydantic
models so they can be written as JSONL today and become table rows later
without changing their shape.

Trust is a decision, not a guess: ``official`` means the material came
from a domain or channel on the hand-maintained allow-list; ``verified``
means a person confirmed it; ``unknown`` never enters the automatic
pipeline. Licence is recorded per resource from the source's own
statement; ``unknown`` blocks derived use until resolved.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class Licence(StrEnum):
    cc_by_4 = "CC-BY-4.0"
    cc_by_nc_4 = "CC-BY-NC-4.0"
    cc_by_nc_sa_4 = "CC-BY-NC-SA-4.0"
    cc_by_sa_4 = "CC-BY-SA-4.0"
    terms_of_service = "terms-of-service"
    unknown = "unknown"

    @property
    def allows_derived_use(self) -> bool:
        """Derived, attributed, non-commercial knowledge may be built from it."""
        return self in {
            Licence.cc_by_4,
            Licence.cc_by_nc_4,
            Licence.cc_by_nc_sa_4,
            Licence.cc_by_sa_4,
        }


LICENCE_URLS: dict[str, Licence] = {
    "https://creativecommons.org/licenses/by-nc-sa/4.0/": Licence.cc_by_nc_sa_4,
    "https://creativecommons.org/licenses/by-nc/4.0/": Licence.cc_by_nc_4,
    "https://creativecommons.org/licenses/by-sa/4.0/": Licence.cc_by_sa_4,
    "https://creativecommons.org/licenses/by/4.0/": Licence.cc_by_4,
}


def licence_from_url(url: str | None) -> Licence:
    if not url:
        return Licence.unknown
    return LICENCE_URLS.get(url.strip().rstrip("/") + "/", Licence.unknown)


class Trust(StrEnum):
    official = "official"
    verified = "verified"
    unknown = "unknown"


class ContentType(StrEnum):
    lecture_video = "lecture_video"
    lecture_notes = "lecture_notes"
    slides = "slides"
    problem_set = "problem_set"
    transcript = "transcript"
    syllabus = "syllabus"
    course = "course"


#: Domains whose material is official by construction. A channel or domain
#: outside this list is `unknown` until a person verifies it.
OFFICIAL_DOMAINS: dict[str, str] = {
    "ocw.mit.edu": "MIT",
    "online.stanford.edu": "Stanford",
    "see.stanford.edu": "Stanford",
    "pll.harvard.edu": "Harvard",
    "cs50.harvard.edu": "Harvard",
}

#: Official YouTube channel ids (not names — names can be imitated).
OFFICIAL_YOUTUBE_CHANNELS: dict[str, str] = {
    "UCEBb1b_L6zDS3xTUrIALZOw": "MIT OpenCourseWare",
    "UC-EnprmCZ3OXyAoG7vjVNCA": "Stanford Online",
    "UCcAbgpvcj3hOqv8XyxDNvng": "Harvard University",
}


def trust_for_url(url: str) -> Trust:
    host = url.split("//", 1)[-1].split("/", 1)[0].lower()
    return Trust.official if host in OFFICIAL_DOMAINS else Trust.unknown


class CaptionResource(BaseModel):
    url: str
    language: str = "en"
    kind: str = Field(description="vtt | transcript_pdf | transcript_txt")


class SourceRecord(BaseModel):
    """One piece of material: a lecture video, a notes PDF, a course page."""

    source_id: str
    university: str
    department: str | None = None
    course_code: str | None = None
    course_title: str | None = None
    instructors: list[str] = Field(default_factory=list)
    content_type: ContentType
    title: str
    url: HttpUrl
    published_at: str | None = Field(
        default=None, description="Term/year as the source states it"
    )
    language: str = "en"
    licence: Licence = Licence.unknown
    trust: Trust = Trust.unknown
    #: Position inside the course when the source is one lecture of a series.
    order: int | None = None
    youtube_id: str | None = None
    captions: list[CaptionResource] = Field(default_factory=list)
    checksum: str | None = None
    ingestion_status: str = "registered"
    last_checked_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def usable(self) -> bool:
        """May the automatic pipeline derive knowledge from this record?"""
        return self.trust is Trust.official and self.licence.allows_derived_use


class CourseRecord(BaseModel):
    course_id: str
    university: str
    department: str | None
    course_code: str | None
    title: str
    instructors: list[str]
    url: HttpUrl
    term: str | None
    year: str | None
    level: list[str] = Field(default_factory=list)
    topics: list[list[str]] = Field(default_factory=list)
    licence: Licence = Licence.unknown
    trust: Trust = Trust.unknown
    resource_types: list[str] = Field(default_factory=list)
    lectures: list[SourceRecord] = Field(default_factory=list)

    @property
    def lectures_with_captions(self) -> int:
        return sum(1 for lecture in self.lectures if lecture.captions)
