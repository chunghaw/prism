"""SEC EDGAR 13F + Form 4 ingestion adapter — the thin network/Mongo edge.

This module is the *edge*: it performs the SEC fetch dance (submissions JSON ->
latest accession -> filing-dir ``index.json`` -> the ``.xml``) and persists the
results to MongoDB. All *parsing* stays in the pure cores
(:mod:`agent.tools.parse_13f`, :mod:`agent.tools.parse_form4`) — this file never
re-implements XML mapping. CUSIP -> ticker resolution and the ticker universe
come from :mod:`agent.tools.tickers`; collection/index/write helpers from
:mod:`agent.ingest.db`.

Network policy (docs/DATA_SOURCES.md): SEC requires a ``User-Agent`` header
(``SEC_USER_AGENT`` env, format "Name email@example.com") and limits to 10
req/sec — we throttle to ~7/sec to leave headroom for retries. Every HTTP call
goes through the single module-level seam :func:`_get`, so tests substitute the
committed fixtures with **no network and no credentials**.

Idempotency:
  * ``filings_13f`` is upserted on its natural key (accession number) via
    :func:`agent.ingest.db.upsert_many` — re-ingestion never duplicates.
  * ``filings_form4`` is a time-series collection (no unique index possible);
    we dedupe by accession number against the already-stored set before
    appending with :func:`agent.ingest.db.insert_timeseries`.
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Iterable, Optional

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from agent.ingest.db import insert_timeseries, upsert_many
from agent.schemas import Filing13F, Form4Transaction
from agent.tools.parse_13f import build_filing, parse_positions
from agent.tools.parse_form4 import parse_form4
from agent.tools.tickers import resolve_cusips

# --- endpoints (docs/DATA_SOURCES.md) ----------------------------------------
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik10}.json"
ARCHIVES_DIR_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nodash}"

# SEC allows 10 req/sec; 7/sec leaves headroom for tenacity retries.
_THROTTLE_SECONDS = 1.0 / 7.0
_throttle_lock = threading.Lock()
_last_request_at = 0.0


def _user_agent(ua: Optional[str]) -> str:
    """Resolve the SEC User-Agent: explicit arg wins, else ``SEC_USER_AGENT`` env."""
    ua = ua or os.environ.get("SEC_USER_AGENT")
    if not ua:
        raise RuntimeError(
            "SEC_USER_AGENT not set (format: 'Name email@example.com')"
        )
    return ua


def _throttle() -> None:
    """Block until at least ``_THROTTLE_SECONDS`` have passed since the last call."""
    global _last_request_at
    with _throttle_lock:
        wait = _THROTTLE_SECONDS - (time.monotonic() - _last_request_at)
        if wait > 0:
            time.sleep(wait)
        _last_request_at = time.monotonic()


@retry(
    retry=retry_if_exception_type(requests.RequestException),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=0.5, max=8),
    reraise=True,
)
def _get(url: str, ua: str) -> str:
    """Fetch ``url`` as text with the SEC ``User-Agent`` header (THE network seam).

    This is the *only* function in the module that touches the network. Tests
    monkeypatch it (or pass ``_get=...``) to return committed fixtures, so the
    rest of the adapter runs deterministically offline. Throttled to ~7 req/sec
    and retried with exponential backoff on transient request errors.
    """
    _throttle()
    resp = requests.get(
        url,
        headers={"User-Agent": ua, "Accept-Encoding": "gzip, deflate"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.text


# --- fetch-dance helpers (pure given ``_get``) -------------------------------
def _submissions(
    cik10: str, *, ua: str, _get: Callable[[str, str], str]
) -> dict:
    """Return a CIK's parsed submissions JSON (entity ``name`` + ``filings.recent``)."""
    return json.loads(_get(SUBMISSIONS_URL.format(cik10=cik10), ua))


def _iter_filings(
    recent: dict[str, list], form: str
) -> Iterable[tuple[str, str, str]]:
    """Yield ``(accession, filing_date, period_of_report)`` for matching ``form``.

    The submissions JSON stores filings as parallel columns; we zip them and
    filter by exact form type, preserving the SEC's newest-first ordering.
    """
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    dates = recent.get("filingDate", [])
    periods = recent.get("reportDate", [])
    for i, form_t in enumerate(forms):
        if form_t == form:
            yield (
                accessions[i],
                dates[i] if i < len(dates) else "",
                periods[i] if i < len(periods) else "",
            )


def _dir_filenames(
    cik_int: int, accession: str, *, ua: str, _get: Callable[[str, str], str]
) -> tuple[str, list[str]]:
    """Return the filing directory base URL and its file names (from ``index.json``)."""
    base = ARCHIVES_DIR_URL.format(cik=cik_int, acc_nodash=accession.replace("-", ""))
    items = json.loads(_get(f"{base}/index.json", ua))["directory"]["item"]
    return base, [i["name"] for i in items]


def _find_xml(
    base: str,
    names: list[str],
    marker: str,
    *,
    ua: str,
    _get: Callable[[str, str], str],
) -> Optional[str]:
    """Fetch the first ``.xml`` in the dir whose body contains ``marker`` (e.g.
    ``"infoTable"`` for 13F, ``"ownershipDocument"`` for Form 4). ``None`` if absent."""
    for name in names:
        if name.lower().endswith(".xml"):
            text = _get(f"{base}/{name}", ua)
            if marker in text:
                return text
    return None


def _quarter_from_period(period: str) -> str:
    """Map a ``YYYY-MM-DD`` period-of-report to ``YYYYQ#`` (2025-12-31 -> '2025Q4')."""
    dt = datetime.strptime(period[:10], "%Y-%m-%d")
    return f"{dt.year}Q{(dt.month - 1) // 3 + 1}"


def _parse_date_utc(value: str) -> datetime:
    """Parse a ``YYYY-MM-DD`` SEC date as timezone-aware UTC midnight."""
    return datetime.strptime(value[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)


# --- public fetchers ----------------------------------------------------------
def fetch_13f(
    fund_cik: str,
    *,
    ua: Optional[str] = None,
    resolve_tickers: bool = False,
    _get: Callable[[str, str], str] = _get,
) -> Optional[Filing13F]:
    """Fetch + parse a fund's latest 13F-HR into a :class:`Filing13F` (or ``None``).

    The dance: submissions JSON -> newest ``13F-HR`` accession -> filing dir ->
    the information-table ``.xml`` -> :func:`parse_positions`. The quarter is
    derived from the filing's period-of-report (e.g. 2025-12-31 -> ``"2025Q4"``).
    When ``resolve_tickers`` is set, position CUSIPs are mapped to tickers via
    :func:`agent.tools.tickers.resolve_cusips` (network) before assembly.

    Returns ``None`` when the fund has no 13F-HR on file or the info-table XML
    can't be located — never raises for "not found".
    """
    ua = _user_agent(ua)
    cik10 = str(fund_cik).zfill(10)

    subs = _submissions(cik10, ua=ua, _get=_get)
    latest = next(_iter_filings(subs["filings"]["recent"], "13F-HR"), None)
    if latest is None:
        return None
    accession, filing_date, period = latest

    base, names = _dir_filenames(int(cik10), accession, ua=ua, _get=_get)
    xml = _find_xml(base, names, "infoTable", ua=ua, _get=_get)
    if xml is None:
        return None

    positions = parse_positions(xml.encode("utf-8"))
    if resolve_tickers and positions:
        cusip_map = resolve_cusips([p.cusip for p in positions])
        positions = parse_positions(xml.encode("utf-8"), cusip_map)

    # The 13F quarter is the period-of-report (reportDate), NOT the filing date —
    # filings land ~45 days after quarter end (docs/DATA_SOURCES.md).
    quarter_src = period or filing_date
    return build_filing(
        positions,
        fund_cik=cik10,
        fund_name=subs.get("name") or cik10,
        filing_date=_parse_date_utc(filing_date or period),
        quarter=_quarter_from_period(quarter_src),
        accession_number=accession,
    )


def fetch_form4(
    issuer_cik: str,
    *,
    ua: Optional[str] = None,
    limit: int = 20,
    _get: Callable[[str, str], str] = _get,
) -> list[Form4Transaction]:
    """Fetch + parse an issuer's recent Form 4 filings into transactions.

    For up to ``limit`` of the issuer's most-recent ``form == "4"`` filings, the
    ownership ``.xml`` is fetched and handed to :func:`parse_form4`, with the
    filing's accession number stamped onto every emitted transaction (the
    time-series dedupe key). Filings whose ownership XML can't be located are
    skipped. Returns the concatenated transactions across all fetched filings.
    """
    ua = _user_agent(ua)
    cik10 = str(issuer_cik).zfill(10)

    recent = _submissions(cik10, ua=ua, _get=_get)["filings"]["recent"]
    out: list[Form4Transaction] = []
    for accession, _date, _period in list(_iter_filings(recent, "4"))[:limit]:
        base, names = _dir_filenames(int(cik10), accession, ua=ua, _get=_get)
        xml = _find_xml(base, names, "ownershipDocument", ua=ua, _get=_get)
        if xml is None:
            continue
        out.extend(parse_form4(xml, accession_number=accession))
    return out


# --- Mongo ingestors (idempotent) --------------------------------------------
def ingest_13f(
    db,
    fund_ciks: Iterable[str],
    *,
    ua: Optional[str] = None,
    resolve_tickers: bool = False,
    _get: Callable[[str, str], str] = _get,
) -> int:
    """Fetch each fund's latest 13F-HR and upsert into ``filings_13f``.

    Idempotent: upserts on the accession-number natural key, so re-running never
    duplicates a filing. Returns the number of documents written (inserted +
    modified).
    """
    ua = _user_agent(ua)
    now = datetime.now(timezone.utc)
    docs = []
    for cik in fund_ciks:
        filing = fetch_13f(cik, ua=ua, resolve_tickers=resolve_tickers, _get=_get)
        if filing is None:
            continue
        doc = filing.model_dump(mode="python")
        doc["ingested_at"] = now
        docs.append(doc)
    return upsert_many(db, "filings_13f", docs)


def ingest_form4(
    db,
    issuer_ciks: Iterable[str],
    *,
    ua: Optional[str] = None,
    limit: int = 20,
    _get: Callable[[str, str], str] = _get,
) -> int:
    """Fetch each issuer's recent Form 4s and append new ones to ``filings_form4``.

    ``filings_form4`` is a time-series collection (no unique index possible), so
    we dedupe on the accession number: any accession already present in the
    collection — or already seen in this batch — is skipped before the
    time-series insert. Returns the number of transactions actually appended.
    """
    ua = _user_agent(ua)
    now = datetime.now(timezone.utc)

    seen = _existing_accessions(db)
    docs = []
    for cik in issuer_ciks:
        for txn in fetch_form4(cik, ua=ua, limit=limit, _get=_get):
            if txn.accession_number in seen:
                continue
            doc = txn.model_dump(mode="python")
            doc["ingested_at"] = now
            docs.append(doc)
        # Guard within-batch too: mark this issuer's accessions as seen so a
        # filing returned twice in one run isn't double-appended.
        seen.update(d["accession_number"] for d in docs)
    return insert_timeseries(db, "filings_form4", docs)


def _existing_accessions(db) -> set[str]:
    """Accession numbers already stored in ``filings_form4`` (dedupe guard).

    Time-series collections can't carry a unique index, so we read the distinct
    accession numbers up front and skip any we've already appended. A live db
    exposes ``.distinct``; an absent/None db (unit context) yields an empty set.
    """
    try:
        return set(db["filings_form4"].distinct("accession_number"))
    except Exception:
        return set()
