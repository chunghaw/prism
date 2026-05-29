"""Tests for the pure 13F information-table parser (agent/tools/parse_13f.py).

These read the REAL fixture bytes and assert against values pulled straight out
of the fixture XML — never against hand-typed guesses.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from agent.schemas import Filing13F, Position13F, ShareType
from agent.tools.parse_13f import build_filing, parse_positions

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "sec"
    / "13f_berkshire_sample.xml"
)


def _fixture_bytes() -> bytes:
    return FIXTURE.read_bytes()


def _first_infotable_raw() -> dict[str, str]:
    """Pull the first <infoTable>'s raw field values directly from the XML text.

    Namespace-agnostic regex over the raw bytes so the EXPECTED values come from
    the fixture itself, independent of the parser under test.
    """
    text = _fixture_bytes().decode("utf-8")
    first = text.split("<infoTable>", 2)[1].split("</infoTable>", 1)[0]

    def tag(name: str) -> str:
        m = re.search(rf"<{name}>(.*?)</{name}>", first, re.DOTALL)
        assert m is not None, f"<{name}> not found in first infoTable"
        return m.group(1).strip()

    return {
        "issuer": tag("nameOfIssuer"),
        "cusip": tag("cusip"),
        "value": tag("value"),
        "shares": tag("sshPrnamt"),
    }


def test_parses_exactly_three_positions() -> None:
    positions = parse_positions(_fixture_bytes())
    assert len(positions) == 3
    assert all(isinstance(p, Position13F) for p in positions)


def test_first_position_matches_fixture_exactly() -> None:
    expected = _first_infotable_raw()
    first = parse_positions(_fixture_bytes())[0]

    assert first.issuer == expected["issuer"]
    assert first.cusip == expected["cusip"]
    assert first.value_usd == int(expected["value"])
    assert first.shares == int(expected["shares"])
    assert first.share_type is ShareType.SH
    assert first.put_call is None


def test_value_looks_like_dollars_not_thousands() -> None:
    # Post-2024 13F <value> is whole dollars (stored as-is, NOT x1000).
    # Sanity check: implied per-share price must be plausible for an equity.
    first = parse_positions(_fixture_bytes())[0]
    assert first.shares > 0
    price_per_share = first.value_usd / first.shares
    assert 1 < price_per_share < 100_000, price_per_share


def test_ticker_resolution_via_cusip_map() -> None:
    cusip = _first_infotable_raw()["cusip"]
    positions = parse_positions(_fixture_bytes(), {cusip: "ALLY"})
    assert positions[0].ticker == "ALLY"
    # Unmapped CUSIP stays None.
    assert parse_positions(_fixture_bytes())[0].ticker is None


def test_build_filing_derives_aggregates() -> None:
    positions = parse_positions(_fixture_bytes())
    filing = build_filing(
        positions,
        fund_cik="0001067983",
        fund_name="BERKSHIRE HATHAWAY INC",
        filing_date=datetime(2026, 2, 14, tzinfo=timezone.utc),
        quarter="2025Q4",
        accession_number="0000950123-26-001234",
    )
    assert isinstance(filing, Filing13F)
    assert filing.n_positions == 3
    assert filing.total_value_usd == sum(p.value_usd for p in positions)
