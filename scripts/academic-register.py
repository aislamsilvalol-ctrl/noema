#!/usr/bin/env python
"""Register an MIT OpenCourseWare course and its lecture videos in the Academic Source Registry.

    apps/api/.venv/bin/python scripts/academic-register.py --ocw 18-06-linear-algebra-spring-2010 --out registry/mit-18-06.jsonl

Reads OCW's own data.json documents (course, gallery, one per lecture) and
writes one JSON line per record: the course first, then each lecture with
its licence, trust, YouTube id and the official caption and transcript
URLs. Nothing else is fetched: no video, no transcript. This is Phase 1 of
docs/academic-knowledge-engine.md — knowing exactly what would be used,
under which licence, before anything is used.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from noema.academic.ocw import discover_course, http_fetch  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ocw", required=True, help="OCW course slug, e.g. 18-06-linear-algebra-spring-2010")
    parser.add_argument("--gallery", default="video-lectures")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    course = discover_course(args.ocw, http_fetch, gallery=args.gallery)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as f:
        f.write(course.model_copy(update={"lectures": []}).model_dump_json() + "\n")
        for lecture in course.lectures:
            f.write(lecture.model_dump_json() + "\n")
    usable = sum(1 for lecture in course.lectures if lecture.usable)
    print(
        f"{course.university} {course.course_code} — {course.title}: {len(course.lectures)} lectures, "
        f"{course.lectures_with_captions} with official captions, {usable} usable under their licence → {out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
