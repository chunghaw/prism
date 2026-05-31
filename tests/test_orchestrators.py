"""Tests for the bootstrap + daily orchestrators (feeds mocked — no network/creds)."""
from __future__ import annotations

from agent.ingest import bootstrap, daily, edgar, prices, reddit_wsb


def _patch_common(monkeypatch, module, *, wsb_exc=None):
    """Stub every feed + ensure_collections; record the issuer/ticker slices passed."""
    calls: dict[str, object] = {}
    monkeypatch.setattr(module, "ensure_collections", lambda db: calls.__setitem__("ensure", True))

    def f4(db, issuers, **kw):
        calls["issuers"] = list(issuers)
        return 40

    def pr(db, tickers, **kw):
        calls["tickers"] = list(tickers)
        return 1000

    def wsb(*a, **k):
        if wsb_exc:
            raise wsb_exc
        return 25

    monkeypatch.setattr(edgar, "ingest_form4", f4)
    monkeypatch.setattr(prices, "ingest_prices", pr)
    monkeypatch.setattr(reddit_wsb, "ingest_wsb", wsb)
    return calls


def test_top_fund_ciks_are_verified_and_note_excluded():
    ciks = bootstrap.top_fund_ciks()
    assert all(c.isdigit() and len(c) == 10 for c in ciks)
    assert "0001067983" in ciks            # Berkshire (verified)
    assert len(ciks) >= 5


def test_bootstrap_wires_all_feeds_and_respects_max_issuers(monkeypatch):
    calls = _patch_common(monkeypatch, bootstrap)
    monkeypatch.setattr(bootstrap, "seed_papers", lambda db: 18)
    monkeypatch.setattr(edgar, "ingest_13f", lambda db, ciks, **kw: 7)

    counts = bootstrap.run(db=object(), max_issuers=3, reddit=object())

    assert counts == {"papers": 18, "filings_13f": 7, "filings_form4": 40, "prices": 1000, "wsb_posts": 25}
    assert calls["ensure"] is True
    assert len(calls["issuers"]) == 3 and len(calls["tickers"]) == 3   # slice honoured


def test_bootstrap_isolates_a_failing_feed(monkeypatch):
    _patch_common(monkeypatch, bootstrap, wsb_exc=RuntimeError("no Reddit creds"))
    monkeypatch.setattr(bootstrap, "seed_papers", lambda db: 18)
    monkeypatch.setattr(edgar, "ingest_13f", lambda db, ciks, **kw: 7)

    counts = bootstrap.run(db=object(), max_issuers=2)

    assert counts["wsb_posts"] == 0          # failure reported as 0, not raised
    assert counts["papers"] == 18 and counts["prices"] == 1000   # others unaffected


def test_daily_refresh_wires_feeds(monkeypatch):
    calls = _patch_common(monkeypatch, daily)
    counts = daily.run(db=object(), max_issuers=4, reddit=object())
    assert set(counts) == {"filings_form4", "prices", "wsb_posts"}
    assert len(calls["issuers"]) == 4 and len(calls["tickers"]) == 4
