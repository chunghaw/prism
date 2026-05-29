"""Tests for agent.tools.tickers — the committed S&P 500 snapshot + OpenFIGI parsing."""
from __future__ import annotations

from agent.tools.tickers import (
    _parse_openfigi,
    cik_to_symbol,
    normalize_for_yfinance,
    sp500_symbols,
    symbol_to_cik,
    symbol_to_name,
)


def test_sp500_universe_is_sane():
    syms = sp500_symbols()
    assert 480 <= len(syms) <= 520            # ~503 constituents
    assert {"AAPL", "MSFT", "NVDA"} <= syms
    assert all(s == s.upper() for s in syms)


def test_symbol_to_name_and_cik():
    assert "Apple" in symbol_to_name()["AAPL"]
    cik = symbol_to_cik()["AAPL"]
    assert len(cik) == 10 and cik.isdigit()    # zero-padded for SEC endpoints
    assert cik_to_symbol()[cik] == "AAPL"      # round-trips


def test_normalize_for_yfinance_share_classes():
    assert normalize_for_yfinance("BRK.B") == "BRK-B"
    assert normalize_for_yfinance("aapl") == "AAPL"


def test_parse_openfigi_maps_and_skips_no_match():
    cusips = ["037833100", "BADCUSIP1", "459200101"]
    payload = [
        {"data": [{"ticker": "aapl", "exchCode": "US"}]},
        {"warning": "No identifier found."},
        {"data": [{"ticker": "IBM"}]},
    ]
    assert _parse_openfigi(cusips, payload) == {"037833100": "AAPL", "459200101": "IBM"}


def test_parse_openfigi_handles_empty_data_list():
    assert _parse_openfigi(["x"], [{"data": []}]) == {}
