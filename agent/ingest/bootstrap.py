"""Day-1 bootstrap: seed historical data into MongoDB Atlas.

Run once after credentials are in .env. Idempotent — safe to re-run.

    python -m agent.ingest.bootstrap

Each source is wrapped independently: if one feed fails (e.g. no Reddit creds),
the others still complete and the failure is reported honestly — never silently
counted as success.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from rich.console import Console

from agent.ingest import edgar, prices, reddit_wsb
from agent.ingest.db import ensure_collections, get_db
from agent.ingest.papers_seed import seed_papers
from agent.tools.tickers import sp500_symbols, symbol_to_cik

_FUNDS = Path(__file__).resolve().parent / "data" / "top_funds.json"
_console = Console()


def top_fund_ciks() -> list[str]:
    """Verified 13F-filer CIKs from data/top_funds.json (skips the ``_note`` key)."""
    raw = json.loads(_FUNDS.read_text(encoding="utf-8"))
    return [k for k in raw if k.isdigit()]


def _step(counts: dict[str, int], name: str, fn) -> None:
    """Run one ingestion step, recording its count or reporting failure honestly."""
    try:
        counts[name] = fn()
        _console.log(f"[green]{name}[/]: {counts[name]}")
    except Exception as exc:  # noqa: BLE001 — one feed failing must not abort the rest
        counts[name] = 0
        _console.log(f"[yellow]{name} skipped[/]: {type(exc).__name__}: {exc}")


def run(
    *,
    db=None,
    max_issuers: Optional[int] = 50,
    price_period: str = "5y",
    wsb_limit: int = 500,
    ua: Optional[str] = None,
    reddit=None,
) -> dict[str, int]:
    """Seed papers + all four feeds. Returns a per-collection write count.

    ``max_issuers`` caps the S&P 500 slice used for Form 4 + prices (None = all 503);
    keep it small for a first smoke run, raise it for the full demo dataset.
    """
    db = db if db is not None else get_db()
    ensure_collections(db)
    counts: dict[str, int] = {}

    _step(counts, "papers", lambda: seed_papers(db))
    _step(counts, "filings_13f", lambda: edgar.ingest_13f(db, top_fund_ciks(), ua=ua, resolve_tickers=True))

    issuers = list(symbol_to_cik().values())
    tickers = sorted(sp500_symbols())
    if max_issuers is not None:
        issuers, tickers = issuers[:max_issuers], tickers[:max_issuers]

    _step(counts, "filings_form4", lambda: edgar.ingest_form4(db, issuers, ua=ua))
    _step(counts, "prices", lambda: prices.ingest_prices(db, tickers, period=price_period))
    _step(counts, "wsb_posts", lambda: reddit_wsb.ingest_wsb(db, reddit=reddit, limit=wsb_limit))

    _console.log(f"[bold]bootstrap complete[/]: {counts}")
    return counts


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    run()
