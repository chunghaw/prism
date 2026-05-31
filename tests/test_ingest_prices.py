"""Tests for agent.ingest.prices — the thin yfinance/Mongo edge.

No network, no credentials, deterministic: the ``_yf`` seam is monkeypatched
with a fake module returning a tiny in-memory pandas DataFrame, and the Mongo
write is intercepted with a fake ``db`` object.
"""
from __future__ import annotations

from datetime import timezone

import pandas as pd

from agent.ingest import prices
from agent.schemas import PriceBar


def _frame(*, with_adj=False, tz="America/New_York"):
    """Tiny 3-row OHLCV frame shaped like yfinance ``.history()`` output."""
    index = pd.DatetimeIndex(
        pd.to_datetime(["2026-05-20", "2026-05-21", "2026-05-22"])
    )
    if tz is not None:
        index = index.tz_localize(tz)
    data = {
        "Open": [22.10, 23.00, 23.50],
        "High": [23.40, 23.80, 24.10],
        "Low": [21.95, 22.80, 23.20],
        "Close": [23.02, 23.55, 23.90],
        "Volume": [81_300_000, 70_100_000, 65_400_000],
    }
    if with_adj:
        data["Adj Close"] = [23.00, 23.53, 23.88]
    return pd.DataFrame(data, index=index)


class _FakeTicker:
    def __init__(self, symbol, frames):
        self._symbol = symbol
        self._frames = frames

    def history(self, *, period, interval):
        return self._frames[self._symbol]


class _FakeYF:
    """Stand-in for the ``yfinance`` module; records the symbols it was asked for."""

    def __init__(self, frames):
        self._frames = frames
        self.seen: list[str] = []

    def Ticker(self, symbol):  # noqa: N802 — mirror yfinance's API
        self.seen.append(symbol)
        return _FakeTicker(symbol, self._frames)


class _FakeDB:
    def __init__(self):
        self.inserted: dict[str, list] = {}

    # mimic agent.ingest.db.insert_timeseries -> pymongo insert_many
    def __getitem__(self, name):
        db = self

        class _Coll:
            def insert_many(self, docs):
                docs = list(docs)
                db.inserted.setdefault(name, []).extend(docs)

                class _Res:
                    inserted_ids = list(range(len(docs)))

                return _Res()

        return _Coll()


def test_fetch_prices_maps_rows_to_pricebars():
    fake = _FakeYF({"AAPL": _frame()})
    bars = list(prices.fetch_prices(["AAPL"], _yf=fake))

    assert len(bars) == 3
    assert all(isinstance(b, PriceBar) for b in bars)

    first = bars[0]
    assert first.close == 23.02
    assert first.volume == 81_300_000
    assert first.ticker == "AAPL"
    # ts is timezone-aware UTC
    assert first.ts.tzinfo is not None
    assert first.ts.utcoffset() == timezone.utc.utcoffset(None)
    assert first.source == "yfinance"


def test_fetch_prices_normalizes_for_yahoo_but_stores_original():
    fake = _FakeYF({"BRK-B": _frame()})
    bars = list(prices.fetch_prices(["BRK.B"], _yf=fake))

    # Yahoo was queried with the dash form...
    assert fake.seen == ["BRK-B"]
    # ...but the bar keeps the original upper (dotted) symbol.
    assert all(b.ticker == "BRK.B" for b in bars)


def test_fetch_prices_handles_adj_close_and_naive_index():
    fake = _FakeYF({"MSFT": _frame(with_adj=True, tz=None)})
    bars = list(prices.fetch_prices(["MSFT"], _yf=fake))

    assert bars[0].adj_close == 23.00
    # naive index entries are treated as UTC
    assert bars[0].ts.tzinfo is not None
    assert bars[0].ts.utcoffset() == timezone.utc.utcoffset(None)


def _frame_with_nan_middle_row():
    """3-row OHLCV frame whose MIDDLE bar is all-NaN.

    Mirrors yfinance's dominant real-world failure mode: a halted/illiquid
    session (or the trailing in-progress bar) comes back with NaN OHLCV.
    """
    index = pd.DatetimeIndex(
        pd.to_datetime(["2026-05-20", "2026-05-21", "2026-05-22"])
    ).tz_localize("America/New_York")
    nan = float("nan")
    data = {
        "Open": [22.10, nan, 23.50],
        "High": [23.40, nan, 24.10],
        "Low": [21.95, nan, 23.20],
        "Close": [23.02, nan, 23.90],
        "Volume": [81_300_000, nan, 65_400_000],
        # Adj Close present on the good rows, NaN on the bad one.
        "Adj Close": [23.00, nan, 23.88],
    }
    return pd.DataFrame(data, index=index)


def test_fetch_prices_skips_nan_rows_without_poisoning_batch():
    """A single NaN bar must not abort the whole run — the good bars survive."""
    fake = _FakeYF({"AAPL": _frame_with_nan_middle_row()})
    bars = list(prices.fetch_prices(["AAPL"], _yf=fake))

    # Middle (NaN) bar dropped; the two flanking good bars come through.
    assert len(bars) == 2
    assert all(isinstance(b, PriceBar) for b in bars)
    assert [b.close for b in bars] == [23.02, 23.90]
    assert [b.adj_close for b in bars] == [23.00, 23.88]


def test_fetch_prices_drops_nan_adj_close_only():
    """A NaN Adj Close on an otherwise-valid bar degrades to None, not a drop."""
    frame = _frame(with_adj=True)
    frame.loc[frame.index[0], "Adj Close"] = float("nan")
    fake = _FakeYF({"AAPL": frame})

    bars = list(prices.fetch_prices(["AAPL"], _yf=fake))

    assert len(bars) == 3                      # row kept despite NaN adj_close
    assert bars[0].adj_close is None
    assert bars[1].adj_close == 23.53


def test_ingest_prices_writes_good_bars_when_one_row_is_nan():
    """End-to-end: the NaN bar no longer poisons the insert — good bars persist."""
    fake = _FakeYF({"AAPL": _frame_with_nan_middle_row()})
    db = _FakeDB()

    written = prices.ingest_prices(db, ["AAPL"], _yf=fake)

    assert written == 2
    docs = db.inserted["prices"]
    assert len(docs) == 2
    assert [d["close"] for d in docs] == [23.02, 23.90]


def test_fetch_prices_skips_empty_frame():
    fake = _FakeYF({"NVDA": pd.DataFrame()})
    assert list(prices.fetch_prices(["NVDA"], _yf=fake)) == []


def test_ingest_prices_writes_timeseries_and_returns_count():
    fake = _FakeYF({"AAPL": _frame()})
    db = _FakeDB()

    written = prices.ingest_prices(db, ["AAPL"], _yf=fake)

    assert written == 3
    docs = db.inserted["prices"]
    assert len(docs) == 3
    assert docs[0]["ticker"] == "AAPL"
    assert docs[0]["close"] == 23.02
    assert docs[0]["source"] == "yfinance"
    assert docs[0]["ingested_at"] is not None        # stamped at write time
    assert docs[0]["ts"].tzinfo is not None           # tz-aware UTC survives model_dump


def test_ingest_prices_empty_is_noop():
    db = _FakeDB()
    fake = _FakeYF({})
    assert prices.ingest_prices(db, [], _yf=fake) == 0
    assert db.inserted == {}
