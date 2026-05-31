"""yfinance price ingestion — the thin network/Mongo edge over ``PriceBar``.

No parsing logic lives here: the shape is owned by :class:`agent.schemas.PriceBar`
and the symbol normalisation by :mod:`agent.tools.tickers`. This module only does
the two things a pure core can't — hit Yahoo Finance (via the injectable ``_yf``
seam) and append to the ``prices`` time-series collection (docs/SCHEMA.md §4).

yfinance is unofficial and occasionally flaky (Yahoo changes endpoints), so each
per-ticker fetch is wrapped in a bounded :mod:`tenacity` retry. Writes go through
:func:`agent.ingest.db.insert_timeseries` — ``prices`` is append-only (time-series
collections can't carry a unique index), so re-ingestion idempotency is the
caller's concern (bound the ``period`` / dedupe downstream), exactly as for Form 4.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterator

import pandas as pd
from rich.progress import Progress
from tenacity import retry, stop_after_attempt, wait_exponential

from agent.ingest.db import insert_timeseries
from agent.schemas import PriceBar
from agent.tools.tickers import normalize_for_yfinance

# OHLCV columns yfinance returns from ``.history()`` / ``.download()``.
_OPEN, _HIGH, _LOW, _CLOSE, _VOLUME = "Open", "High", "Low", "Close", "Volume"
_ADJ_CLOSE = "Adj Close"


def _to_utc(index_value) -> datetime:
    """Coerce a pandas index entry (Timestamp / datetime) to tz-aware UTC.

    yfinance indexes bars with a tz-aware ``DatetimeIndex`` (exchange tz), but
    fakes/tests may hand back naive timestamps — treat those as already-UTC so
    the stored ``PriceBar.ts`` is always tz-aware UTC per docs/SCHEMA.md.
    """
    ts = index_value
    to_pydatetime = getattr(ts, "to_pydatetime", None)
    if to_pydatetime is not None:
        ts = to_pydatetime()
    if not isinstance(ts, datetime):
        ts = datetime.fromisoformat(str(ts))
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def _history(yf_module, yahoo_symbol: str, *, period: str, interval: str):
    """One bounded-retry call to ``yf.Ticker(symbol).history(...)``.

    Isolated so tenacity wraps only the network hop; pure mapping below never
    retries. Yahoo wobbles (empty frames, transient 5xx) get up to 3 attempts
    with exponential backoff.
    """

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, max=8),
        reraise=True,
    )
    def _call():
        return yf_module.Ticker(yahoo_symbol).history(period=period, interval=interval)

    return _call()


def fetch_prices(
    tickers,
    *,
    period: str = "5y",
    interval: str = "1d",
    _yf=None,
) -> Iterator[PriceBar]:
    """Yield a :class:`PriceBar` per OHLCV row for each ticker.

    Args:
        tickers: Iterable of symbols in Prism's canonical (upper, dotted) form.
        period / interval: Passed straight to yfinance ``.history()``.
        _yf: Injected yfinance-like module (test seam). Defaults to the real
            ``yfinance`` import, deferred so importing this module needs no creds.

    Each symbol is normalised for Yahoo via
    :func:`agent.tools.tickers.normalize_for_yfinance` (``BRK.B`` → ``BRK-B``)
    before the call, but ``PriceBar.ticker`` keeps the **original upper** symbol
    so it joins cleanly against the rest of Prism's collections.
    """
    if _yf is None:  # pragma: no cover - exercised only with a live yfinance install
        import yfinance as _yf

    symbols = [s.strip().upper() for s in tickers if s and s.strip()]
    with Progress(transient=True) as progress:
        task = progress.add_task("fetch prices", total=len(symbols))
        for symbol in symbols:
            yahoo_symbol = normalize_for_yfinance(symbol)
            frame = _history(_yf, yahoo_symbol, period=period, interval=interval)
            progress.advance(task)
            if frame is None or getattr(frame, "empty", False):
                continue
            columns = set(frame.columns)
            has_adj = _ADJ_CLOSE in columns
            for index_value, row in frame.iterrows():
                # yfinance routinely emits rows with NaN OHLCV — the trailing
                # in-progress bar, halted/illiquid sessions. PriceBar's ge=0
                # constraints reject a NaN price (ValidationError) and int(NaN)
                # raises ValueError, so a single bad bar would abort the WHOLE
                # batch before any insert. Skip it instead so the good bars (and
                # every other ticker in the run) still get written.
                if any(
                    pd.isna(row[col])
                    for col in (_OPEN, _HIGH, _LOW, _CLOSE, _VOLUME)
                ):
                    continue
                # Adj Close can be NaN even when the column exists; degrade to
                # None rather than failing the otherwise-valid row.
                adj_close = None
                if has_adj and not pd.isna(row[_ADJ_CLOSE]):
                    adj_close = float(row[_ADJ_CLOSE])
                yield PriceBar(
                    ts=_to_utc(index_value),
                    ticker=symbol,
                    open=float(row[_OPEN]),
                    high=float(row[_HIGH]),
                    low=float(row[_LOW]),
                    close=float(row[_CLOSE]),
                    adj_close=adj_close,
                    volume=int(row[_VOLUME]),
                    source="yfinance",
                )


def ingest_prices(db, tickers, **kw) -> int:
    """Fetch + append price bars to the ``prices`` time-series collection.

    Stamps ``ingested_at`` at write time and returns the number of rows inserted.
    Keyword args (``period``, ``interval``, ``_yf``) flow through to
    :func:`fetch_prices`.
    """
    now = datetime.now(timezone.utc)
    docs = []
    for bar in fetch_prices(tickers, **kw):
        bar.ingested_at = now
        docs.append(bar.model_dump())
    return insert_timeseries(db, "prices", docs)
