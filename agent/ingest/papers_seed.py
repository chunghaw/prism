"""Static behavioural-finance corpus seed (docs/DATA_SOURCES.md §5).

Citation-accurate metadata for the papers Prism cites when it explains a detected
divergence. The corpus is **static** for the hackathon — seed once. Embeddings are
added later by the Vertex AI pass (Week 2). ``abstract`` fields are faithful one-to-
two-sentence summaries of each paper's thesis, not verbatim journal abstracts.
"""
from __future__ import annotations

import json
from pathlib import Path

from agent.schemas import Paper

_DATA = Path(__file__).resolve().parent / "data" / "papers.json"


def load_papers() -> list[Paper]:
    """Parse + validate the curated corpus into ``Paper`` models."""
    raw = json.loads(_DATA.read_text(encoding="utf-8"))
    return [Paper(**p) for p in raw]


def seed_papers(db) -> int:
    """Upsert the corpus into the ``papers`` collection (idempotent). Returns rows written."""
    from agent.ingest.db import upsert_many

    papers = [p.model_dump() for p in load_papers()]
    return upsert_many(db, "papers", papers)
