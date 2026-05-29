"""MongoDB Atlas client + collection/index setup for Prism (implements docs/SCHEMA.md).

Connection comes from ``MONGODB_URI`` / ``MONGODB_DATABASE`` in the environment
(.env) — nothing is hardcoded. The collection, index, and natural-key specs are
plain data so they can be asserted in tests without a live cluster; only
:func:`get_client`, :func:`ensure_collections`, and the write helpers touch Atlas.
"""
from __future__ import annotations

import os
from typing import Any, Iterable, Mapping

from pymongo import ASCENDING, DESCENDING, IndexModel, MongoClient, UpdateOne

DB_NAME = os.environ.get("MONGODB_DATABASE", "prism")

# Time-series collections MUST be created explicitly before first insert
# (you can't convert a standard collection later). See SCHEMA.md §2, §4.
TIMESERIES: dict[str, dict[str, str]] = {
    "filings_form4": {"timeField": "transaction_ts", "metaField": "meta", "granularity": "hours"},
    "prices": {"timeField": "ts", "metaField": "ticker", "granularity": "hours"},
}

# Standard b-tree indexes per collection (vector + Atlas Search indexes are created
# in the Atlas UI / via search-index commands — see SCHEMA.md).
INDEXES: dict[str, list[IndexModel]] = {
    "filings_13f": [
        IndexModel([("accession_number", ASCENDING)], unique=True, name="uq_accession"),
        IndexModel([("quarter", ASCENDING), ("positions.ticker", ASCENDING)], name="quarter_ticker"),
        IndexModel([("fund_cik", ASCENDING), ("quarter", ASCENDING)], name="fund_quarter"),
    ],
    "filings_form4": [
        IndexModel([("meta.ticker", ASCENDING), ("transaction_ts", DESCENDING)], name="ticker_ts"),
    ],
    "wsb_posts": [
        IndexModel([("post_id", ASCENDING)], unique=True, name="uq_post"),
        IndexModel([("tickers", ASCENDING), ("created_utc", DESCENDING)], name="tickers_created"),
    ],
    "prices": [
        IndexModel([("ticker", ASCENDING), ("ts", DESCENDING)], name="ticker_ts"),
    ],
    "papers": [
        IndexModel([("paper_id", ASCENDING)], unique=True, name="uq_paper"),
    ],
    "normalized_signals": [
        IndexModel([("ticker", ASCENDING), ("as_of_date", ASCENDING)], unique=True, name="uq_ticker_date"),
    ],
    "divergence_library": [
        IndexModel([("pattern_id", ASCENDING)], unique=True, name="uq_pattern"),
        IndexModel([("ticker", ASCENDING), ("as_of_date", DESCENDING)], name="ticker_date"),
    ],
}

# Natural keys for idempotent upsert (re-ingestion must not duplicate).
# Time-series collections (filings_form4, prices) are append-only; dedupe is the
# ingestor's job (accession-seen set for Form 4; (ticker, ts) guard for prices).
NATURAL_KEYS: dict[str, list[str]] = {
    "filings_13f": ["accession_number"],
    "wsb_posts": ["post_id"],
    "papers": ["paper_id"],
    "normalized_signals": ["ticker", "as_of_date"],
    "divergence_library": ["pattern_id"],
}


def get_client(uri: str | None = None) -> MongoClient:
    uri = uri or os.environ.get("MONGODB_URI")
    if not uri:
        raise RuntimeError("MONGODB_URI not set (add it to .env)")
    return MongoClient(uri, appname="prism")


def get_db(client: MongoClient | None = None):
    return (client or get_client())[DB_NAME]


def ensure_collections(db) -> None:
    """Create time-series collections (if missing) and all b-tree indexes. Idempotent."""
    existing = set(db.list_collection_names())
    for name, ts in TIMESERIES.items():
        if name not in existing:
            db.create_collection(name, timeseries=ts)
    for name, models in INDEXES.items():
        if models:
            db[name].create_indexes(models)


def upsert_many(db, collection: str, docs: Iterable[Mapping[str, Any]], *, key: list[str] | None = None) -> int:
    """Idempotent bulk upsert on the collection's natural key. Returns rows written."""
    key = key or NATURAL_KEYS[collection]
    ops = [UpdateOne({k: d[k] for k in key}, {"$set": dict(d)}, upsert=True) for d in docs]
    if not ops:
        return 0
    res = db[collection].bulk_write(ops, ordered=False)
    return (res.upserted_count or 0) + (res.modified_count or 0)


def insert_timeseries(db, collection: str, docs: list[Mapping[str, Any]]) -> int:
    """Append rows to a time-series collection (no unique index possible)."""
    if collection not in TIMESERIES:
        raise ValueError(f"{collection} is not a time-series collection")
    if not docs:
        return 0
    return len(db[collection].insert_many(list(docs)).inserted_ids)
