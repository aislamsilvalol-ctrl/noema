"""OpenAI's strict mode, and the schemas NOEMA writes for everyone."""

from __future__ import annotations

from typing import Any

from noema.professor.curriculum import PLAN_SCHEMA
from noema.professor.intent import GOAL_SCHEMA
from noema.providers.openai import strict_schema, without_nulls

SCHEMA = {
    "type": "object",
    "properties": {
        "subject": {"type": "string"},
        "level": {"type": "string", "enum": ["a", "b"]},
        "tags": {
            "type": "array",
            "items": {"type": "object", "properties": {"t": {"type": "string"}}},
        },
    },
    "required": ["subject"],
}


def _objects(node: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(node, dict):
        if node.get("type") == "object" or "properties" in node:
            found.append(node)
        for value in node.values():
            found += _objects(value)
    elif isinstance(node, list):
        for item in node:
            found += _objects(item)
    return found


def test_every_object_is_closed_and_lists_every_property() -> None:
    for schema in (SCHEMA, GOAL_SCHEMA, PLAN_SCHEMA):
        for obj in _objects(strict_schema(schema)):
            assert obj["additionalProperties"] is False
            assert set(obj["required"]) == set(obj.get("properties", {}))


def test_optional_fields_become_nullable_and_required_ones_do_not() -> None:
    out = strict_schema(SCHEMA)
    assert out["properties"]["subject"] == {"type": "string"}
    assert out["properties"]["level"]["type"] == ["string", "null"]
    assert None in out["properties"]["level"]["enum"]


def test_the_original_is_left_untouched() -> None:
    strict_schema(SCHEMA)
    assert "additionalProperties" not in SCHEMA


def test_nulls_from_strict_mode_come_back_as_absent_fields() -> None:
    assert without_nulls({"a": 1, "b": None, "c": [{"d": None, "e": 2}]}) == {
        "a": 1,
        "c": [{"e": 2}],
    }
