"""Tests for agent.ingest.db config — asserts the spec matches docs/SCHEMA.md.

No live cluster: only the pure collection/index/natural-key specs and the
no-URI guard are exercised here. Connection behaviour is validated with creds.
"""
from __future__ import annotations

import pytest

from agent.ingest import db


def _index_by_name(models, name):
    for m in models:
        if m.document.get("name") == name:
            return m.document
    return None


def test_timeseries_configs_match_schema():
    assert db.TIMESERIES["filings_form4"] == {
        "timeField": "transaction_ts",
        "metaField": "meta",
        "granularity": "hours",
    }
    assert db.TIMESERIES["prices"] == {
        "timeField": "ts",
        "metaField": "ticker",
        "granularity": "hours",
    }


def test_unique_natural_key_indexes_exist():
    uniques = {
        "filings_13f": "uq_accession",
        "wsb_posts": "uq_post",
        "papers": "uq_paper",
        "normalized_signals": "uq_ticker_date",
        "divergence_library": "uq_pattern",
    }
    for coll, idx_name in uniques.items():
        doc = _index_by_name(db.INDEXES[coll], idx_name)
        assert doc is not None, f"{coll} missing {idx_name}"
        assert doc.get("unique") is True


def test_natural_keys_exclude_timeseries():
    # Time-series collections can't have unique indexes → not upsert targets.
    assert "filings_form4" not in db.NATURAL_KEYS
    assert "prices" not in db.NATURAL_KEYS
    assert db.NATURAL_KEYS["normalized_signals"] == ["ticker", "as_of_date"]


def test_every_collection_is_specified():
    collections = set(db.INDEXES) | set(db.TIMESERIES)
    assert collections == {
        "filings_13f", "filings_form4", "wsb_posts", "prices",
        "papers", "normalized_signals", "divergence_library",
    }


def test_get_client_requires_uri(monkeypatch):
    monkeypatch.delenv("MONGODB_URI", raising=False)
    with pytest.raises(RuntimeError, match="MONGODB_URI"):
        db.get_client()


def test_upsert_many_empty_is_noop():
    assert db.upsert_many(None, "papers", []) == 0   # returns before touching db
