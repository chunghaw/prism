"""Tests for the static behavioural-finance corpus (agent.ingest.papers_seed)."""
from __future__ import annotations

import datetime

from agent.ingest.papers_seed import load_papers


def test_corpus_loads_and_validates():
    papers = load_papers()
    assert len(papers) >= 15                      # ≥ the bare-minimum 12 in DATA_SOURCES.md
    # every entry is a valid Paper (load_papers would have raised otherwise)
    assert all(p.title and p.authors and p.abstract for p in papers)


def test_paper_ids_are_unique():
    ids = [p.paper_id for p in load_papers()]
    assert len(ids) == len(set(ids))


def test_known_anchors_present_and_accurate():
    by_id = {p.paper_id: p for p in load_papers()}
    bo = by_id["barber-odean-2000"]
    assert bo.year == 2000 and bo.venue == "Journal of Finance"
    assert "Barber, Brad M." in bo.authors
    # the insider routine-vs-opportunistic paper that justifies our 10b5-1 flag
    assert "cohen-malloy-pomorski-2012" in by_id


def test_every_paper_has_tags_and_pattern():
    for p in load_papers():
        assert p.bias_tags, f"{p.paper_id} missing bias_tags"
        assert p.pattern_explained, f"{p.paper_id} missing pattern_explained"
        assert 1970 <= p.year <= datetime.date.today().year
        assert p.embedding is None                # embeddings added by the Week-2 Vertex pass
