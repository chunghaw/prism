"""Daily refresh: recent insider transactions, fresh WSB posts, latest prices.

    python -m agent.ingest.daily

13F is quarterly (45-day lag) so it isn't refreshed here — re-run bootstrap when a
new quarter lands. Like bootstrap, each feed is isolated so one failure can't abort
the others.
"""
from __future__ import annotations

from typing import Optional

from rich.console import Console

from agent.ingest import edgar, prices, reddit_wsb
from agent.ingest.bootstrap import _step
from agent.ingest.db import ensure_collections, get_db
from agent.tools.tickers import sp500_symbols, symbol_to_cik

_console = Console()


def run(
    *,
    db=None,
    max_issuers: Optional[int] = 50,
    wsb_limit: int = 300,
    form4_limit: int = 5,
    ua: Optional[str] = None,
    reddit=None,
) -> dict[str, int]:
    """Append recent Form 4s + WSB posts + the last few price bars. Returns counts."""
    db = db if db is not None else get_db()
    ensure_collections(db)
    counts: dict[str, int] = {}

    issuers = list(symbol_to_cik().values())
    tickers = sorted(sp500_symbols())
    if max_issuers is not None:
        issuers, tickers = issuers[:max_issuers], tickers[:max_issuers]

    _step(counts, "filings_form4", lambda: edgar.ingest_form4(db, issuers, ua=ua, limit=form4_limit))
    _step(counts, "prices", lambda: prices.ingest_prices(db, tickers, period="5d"))
    _step(counts, "wsb_posts", lambda: reddit_wsb.ingest_wsb(db, reddit=reddit, limit=wsb_limit))

    _console.log(f"[bold]daily refresh complete[/]: {counts}")
    return counts


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    run()
