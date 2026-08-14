"""Measuring retrieval and refusal against a labelled corpus.

The claim this project makes about answers — that they cite the page they came
from, and that a question the material does not answer is refused rather than
invented — is only worth as much as a number that would fall if it stopped being
true. Unit tests prove the citation filter drops an uncited sentence; they cannot
say whether the right chunk was found in the first place.

Two metrics, both computed from the same labelled file:

* **Recall@k** — for a question the corpus does answer, is the chunk that answers
  it among the results.
* **Refusal rate** — for a question it does not answer, does retrieval come back
  empty. This is the one that decays silently: loosen a similarity floor to fix a
  missed match and refusals quietly become nearest-paragraph guesses.

Run with the mock embedder, which is a real bag-of-words model rather than noise,
so the numbers mean something in CI. A run against a hosted embedder scores the
same corpus and can be compared directly.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from noema.db.models import (
    Chunk,
    Notebook,
    Source,
    SourceKind,
    SourceStatus,
    Subject,
    Workspace,
)
from noema.db.repository import OwnedRepository
from noema.providers.base import EmbedRequest
from noema.providers.gateway import AIGateway
from noema.retrieval.search import RetrievalSettings, retrieve

__all__ = ["Report", "load_corpus", "run"]

CORPUS = Path(__file__).resolve().parents[4] / "evals" / "retrieval.json"


@dataclass(frozen=True, slots=True)
class Report:
    recall_at_k: float
    refusal_rate: float
    answerable: int
    unanswerable: int
    #: Queries whose answering chunk was not retrieved, and unanswerable ones that
    #: returned something anyway. Named, because "0.83" tells you nothing about
    #: what to fix.
    missed: list[str]
    false_answers: list[str]

    def summary(self) -> str:
        return (
            f"recall@k {self.recall_at_k:.0%} over {self.answerable} answerable "
            f"queries; refused {self.refusal_rate:.0%} of {self.unanswerable} "
            f"unanswerable ones"
        )


def load_corpus(path: Path | None = None) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((path or CORPUS).read_text(encoding="utf-8"))
    return loaded


async def run(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    gateway: AIGateway,
    embedding_model: str | None = None,
    corpus: dict[str, Any] | None = None,
) -> Report:
    """Ingest the corpus, run every query, and score what came back."""
    corpus = corpus or load_corpus()
    chunk_labels = await _ingest(session, corpus, owner_id, gateway, embedding_model)

    hits = 0
    answerable = 0
    refusals = 0
    unanswerable = 0
    missed: list[str] = []
    false_answers: list[str] = []

    for query in corpus["queries"]:
        results = await retrieve(
            session,
            query["text"],
            owner_id=owner_id,
            gateway=gateway,
            embedding_model=embedding_model,
            settings=RetrievalSettings(),
        )
        labels = {chunk_labels.get(r.chunk_id) for r in results}

        if query["answerable"]:
            answerable += 1
            if query["expect"] in labels:
                hits += 1
            else:
                missed.append(query["text"])
        else:
            unanswerable += 1
            if results:
                false_answers.append(query["text"])
            else:
                refusals += 1

    return Report(
        recall_at_k=hits / answerable if answerable else 0.0,
        refusal_rate=refusals / unanswerable if unanswerable else 0.0,
        answerable=answerable,
        unanswerable=unanswerable,
        missed=missed,
        false_answers=false_answers,
    )


async def _ingest(
    session: AsyncSession,
    corpus: dict[str, Any],
    owner_id: uuid.UUID,
    gateway: AIGateway,
    embedding_model: str | None,
) -> dict[uuid.UUID, str]:
    """Store the corpus as chunks and embed them, returning id → label.

    Written directly rather than through the ingestion pipeline: the corpus is
    already chunked by hand, and running it through the chunker would measure the
    chunker instead of retrieval. Parsing has its own tests.
    """
    workspace = await OwnedRepository(session, Workspace, owner_id).create(
        title="Evals", slug=f"evals-{uuid.uuid4().hex[:8]}"
    )
    subject = await OwnedRepository(session, Subject, owner_id).create(
        workspace_id=workspace.id, title="Evals", slug="evals"
    )
    notebook = await OwnedRepository(session, Notebook, owner_id).create(
        subject_id=subject.id, title="Evals", slug="evals", retrieval_settings={}
    )

    labels: dict[uuid.UUID, str] = {}

    for document in corpus["documents"]:
        source = await OwnedRepository(session, Source, owner_id).create(
            notebook_id=notebook.id,
            kind=SourceKind.MD,
            original_filename=f"{document['id']}.md",
            byte_size=0,
            status=SourceStatus.READY,
        )

        texts = [chunk["text"] for chunk in document["chunks"]]
        vectors = (
            await gateway.embed(EmbedRequest(texts=texts, model=embedding_model))
        ).vectors

        for ordinal, (chunk, vector) in enumerate(
            zip(document["chunks"], vectors, strict=True)
        ):
            row = await OwnedRepository(session, Chunk, owner_id).create(
                source_id=source.id,
                notebook_id=notebook.id,
                ordinal=ordinal,
                content=chunk["text"],
                token_count=len(chunk["text"].split()),
                heading_path=[document["title"]],
                embedding=list(vector),
                embedding_model=embedding_model or "mock",
            )
            labels[row.id] = chunk["id"]

    await session.flush()
    return labels
