"""PATCH schemas type every field ``X | None = None`` purely so the field can
be left out of a request — ``exclude_unset=True`` at the call site is what
actually tells "omitted" apart from "sent as null". Some of those fields back
a ``NOT NULL`` column (a notebook/note always has a title, a card always has
front/back text); sending one of those as an explicit JSON ``null`` used to
reach the database as an unhandled ``IntegrityError`` — a raw 500 — instead of
a clean validation error. These tests pin the rejection at the schema layer,
and confirm the genuinely-nullable fields on the same models are untouched.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from noema.api.v1.schemas import NotebookUpdate, NoteUpdate
from noema.api.v1.study import CardUpdate


def test_notebook_update_rejects_an_explicit_null_title() -> None:
    with pytest.raises(ValidationError, match="title"):
        NotebookUpdate(title=None)


def test_notebook_update_rejects_an_explicit_null_retrieval_settings() -> None:
    with pytest.raises(ValidationError, match="retrieval_settings"):
        NotebookUpdate(retrieval_settings=None)


def test_notebook_update_still_allows_clearing_genuinely_nullable_fields() -> None:
    update = NotebookUpdate(description=None, ai_provider_override=None)

    assert update.description is None
    assert update.ai_provider_override is None


def test_notebook_update_allows_omitting_every_field() -> None:
    update = NotebookUpdate()

    assert "title" not in update.model_fields_set
    assert "retrieval_settings" not in update.model_fields_set


def test_note_update_rejects_an_explicit_null_title() -> None:
    with pytest.raises(ValidationError, match="title"):
        NoteUpdate(title=None)


def test_note_update_rejects_an_explicit_null_content_md() -> None:
    with pytest.raises(ValidationError, match="content_md"):
        NoteUpdate(content_md=None)


def test_note_update_still_allows_clearing_content_json() -> None:
    update = NoteUpdate(content_json=None)

    assert update.content_json is None


def test_card_update_rejects_an_explicit_null_front_md() -> None:
    with pytest.raises(ValidationError, match="front_md"):
        CardUpdate(front_md=None)


def test_card_update_rejects_an_explicit_null_back_md() -> None:
    with pytest.raises(ValidationError, match="back_md"):
        CardUpdate(back_md=None)


def test_card_update_still_allows_unlinking_its_concept() -> None:
    update = CardUpdate(concept_id=None)

    assert update.concept_id is None


def test_card_update_allows_a_normal_partial_edit() -> None:
    concept_id = uuid.uuid4()

    update = CardUpdate(front_md="New question?", concept_id=concept_id)

    assert update.front_md == "New question?"
    assert update.concept_id == concept_id
    assert "back_md" not in update.model_fields_set
