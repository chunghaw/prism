"""Ticker universe + CUSIP→ticker resolution.

The S&P 500 constituent list is a committed snapshot (``data/sp500.csv``) so the
tracked-ticker universe is deterministic and offline — it's the filter for WSB
ingestion and the issuer set for Form 4. 13F filings carry **CUSIPs, not tickers**,
so :func:`resolve_cusips` maps them via the free OpenFIGI API (network, batched).
"""
from __future__ import annotations

import csv
import functools
import json
import os
import time
import urllib.request
from pathlib import Path

_DATA = Path(__file__).resolve().parent / "data" / "sp500.csv"
OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"


@functools.lru_cache(maxsize=1)
def _rows() -> tuple[dict[str, str], ...]:
    with _DATA.open(encoding="utf-8") as f:
        return tuple(csv.DictReader(f))


def sp500_symbols() -> set[str]:
    """Upper-cased ticker set (the WSB tracked-ticker filter)."""
    return {r["Symbol"].strip().upper() for r in _rows() if r.get("Symbol")}


def symbol_to_name() -> dict[str, str]:
    return {r["Symbol"].strip().upper(): r["Security"].strip() for r in _rows() if r.get("Symbol")}


def symbol_to_cik() -> dict[str, str]:
    """Ticker → zero-padded 10-digit CIK (for SEC submissions endpoints)."""
    return {
        r["Symbol"].strip().upper(): r["CIK"].strip().zfill(10)
        for r in _rows()
        if r.get("Symbol") and r.get("CIK")
    }


def cik_to_symbol() -> dict[str, str]:
    return {cik: sym for sym, cik in symbol_to_cik().items()}


def normalize_for_yfinance(symbol: str) -> str:
    """Yahoo uses '-' for share classes where SEC/S&P use '.' (BRK.B → BRK-B)."""
    return symbol.strip().upper().replace(".", "-")


def _parse_openfigi(cusips: list[str], payload: list[dict]) -> dict[str, str]:
    """Pure: map a batch of CUSIPs onto tickers from an OpenFIGI response.

    OpenFIGI returns one result object per request item, in order; each has a
    ``data`` list (empty / absent on no-match) whose first entry holds ``ticker``.
    """
    out: dict[str, str] = {}
    for cusip, item in zip(cusips, payload):
        data = (item or {}).get("data") or []
        if data and data[0].get("ticker"):
            out[cusip] = data[0]["ticker"].strip().upper()
    return out


def resolve_cusips(
    cusips: list[str],
    *,
    api_key: str | None = None,
    batch_size: int = 10,
    sleep: float = 0.3,
) -> dict[str, str]:
    """Resolve CUSIPs → tickers via OpenFIGI. Network call; runs at ingest time.

    Without an API key OpenFIGI allows small request bursts; with a free key the
    batch limit is higher. Unmatched CUSIPs are simply absent from the result.
    """
    api_key = api_key or os.environ.get("OPENFIGI_API_KEY")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-OPENFIGI-APIKEY"] = api_key

    resolved: dict[str, str] = {}
    unique = list(dict.fromkeys(c for c in cusips if c))
    for i in range(0, len(unique), batch_size):
        batch = unique[i : i + batch_size]
        body = json.dumps([{"idType": "ID_CUSIP", "idValue": c} for c in batch]).encode()
        req = urllib.request.Request(OPENFIGI_URL, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode())
        resolved.update(_parse_openfigi(batch, payload))
        time.sleep(sleep)
    return resolved
