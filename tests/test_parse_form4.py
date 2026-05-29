"""Tests for ``agent.tools.parse_form4`` against the real Palantir Form 4 fixture.

Expected values are read from the fixture XML itself (via a tiny independent lxml
pass), never hard-coded guesses — so the asserts stay honest if the fixture changes.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from lxml import etree

from agent.tools.parse_form4 import parse_form4

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sec" / "form4_sample.xml"


def _raw() -> bytes:
    return FIXTURE.read_bytes()


def _expected_from_fixture() -> dict:
    """Independently pull the ground-truth values straight out of the fixture XML."""
    root = etree.fromstring(_raw(), parser=etree.XMLParser(recover=True))

    def child(node, tag):
        if node is None:
            return None
        hits = node.xpath(f"./*[local-name()='{tag}']")
        return hits[0] if hits else None

    def text(node, *path):
        cur = node
        for tag in path:
            cur = child(cur, tag)
        return None if cur is None or cur.text is None else cur.text.strip()

    issuer = child(root, "issuer")
    txns = root.xpath(".//*[local-name()='nonDerivativeTransaction']")
    first = txns[0]
    return {
        "cik": text(issuer, "issuerCik"),
        "ticker": text(issuer, "issuerTradingSymbol"),
        "n_txns": len(txns),
        "first_code": text(first, "transactionCoding", "transactionCode"),
        "first_shares": float(
            text(first, "transactionAmounts", "transactionShares", "value")
        ),
        "first_ad": text(
            first, "transactionAmounts", "transactionAcquiredDisposedCode", "value"
        ),
        "first_price": float(
            text(first, "transactionAmounts", "transactionPricePerShare", "value")
        ),
        "first_date": text(first, "transactionDate", "value"),
    }


def test_returns_all_non_derivative_transactions():
    exp = _expected_from_fixture()
    txns = parse_form4(_raw())
    assert len(txns) >= 1
    assert len(txns) == exp["n_txns"]


def test_accepts_str_and_bytes_equivalently():
    as_bytes = parse_form4(_raw())
    as_str = parse_form4(_raw().decode("utf-8"))
    assert len(as_bytes) == len(as_str) >= 1


def test_issuer_meta_matches_fixture():
    exp = _expected_from_fixture()
    meta = parse_form4(_raw())[0].meta
    assert meta.ticker == "PLTR"
    assert meta.ticker == exp["ticker"].upper()
    assert meta.issuer_cik == "0001321655"
    assert meta.issuer_cik == exp["cik"].zfill(10)
    assert meta.issuer_cik == exp["cik"]  # fixture is already 10-digit
    assert "Palantir" in meta.issuer_name


def test_reporting_owner_relationship_flags():
    meta = parse_form4(_raw())[0].meta
    # Fixture: isOfficer=1, isDirector=0, isTenPercentOwner=0, officerTitle "See Remarks".
    assert meta.is_officer is True
    assert meta.is_director is False
    assert meta.is_ten_pct_owner is False
    assert meta.insider_title == "See Remarks"
    assert meta.insider_name == "Buckley Jeffrey"


def test_first_transaction_fields_match_fixture():
    exp = _expected_from_fixture()
    first = parse_form4(_raw())[0]
    assert first.transaction_code.value == exp["first_code"]
    assert first.shares == exp["first_shares"]
    assert first.acquired_disposed.value == exp["first_ad"]
    assert first.price_per_share == exp["first_price"]


def test_transaction_ts_is_utc_midnight():
    exp = _expected_from_fixture()
    ts = parse_form4(_raw())[0].transaction_ts
    expected = datetime.strptime(exp["first_date"], "%Y-%m-%d").replace(
        tzinfo=timezone.utc
    )
    assert ts == expected
    assert ts.tzinfo is not None
    assert (ts.hour, ts.minute, ts.second) == (0, 0, 0)


def test_10b5_1_detected_from_footnote():
    # Fixture footnotes reference a "Rule 10b5-1 trading plan".
    assert parse_form4(_raw())[0].is_10b5_1 is True


def test_accession_number_is_stamped():
    acc = "0001234567-26-000045"
    txns = parse_form4(_raw(), accession_number=acc)
    assert all(t.accession_number == acc for t in txns)


def test_empty_document_returns_empty_list():
    assert parse_form4(b"<ownershipDocument></ownershipDocument>") == []


# --- per-row resilience (out-of-enum / missing required fields) ---------------
#
# Real EDGAR Form 4s use the full SEC transaction-code set (J, C, W, X, K, D, …),
# and malformed rows sometimes omit required fields entirely. None of these may
# abort the filing and discard the valid sibling rows ("we return everything
# valid", mirroring parse_13f.py).

_ISSUER_OWNER = """
    <issuer>
        <issuerCik>0001321655</issuerCik>
        <issuerName>Palantir Technologies Inc.</issuerName>
        <issuerTradingSymbol>PLTR</issuerTradingSymbol>
    </issuer>
    <reportingOwner>
        <reportingOwnerId><rptOwnerName>Buckley Jeffrey</rptOwnerName></reportingOwnerId>
        <reportingOwnerRelationship><isOfficer>1</isOfficer></reportingOwnerRelationship>
    </reportingOwner>
"""


def _txn(*, date="2026-05-20", code="S", shares="10", ad="D") -> str:
    """Build one ``<nonDerivativeTransaction>``; pass ``None`` to omit an element."""
    parts = ['<nonDerivativeTransaction>']
    if date is not None:
        parts.append(f"<transactionDate><value>{date}</value></transactionDate>")
    coding = "<transactionCoding>"
    if code is not None:
        coding += f"<transactionCode>{code}</transactionCode>"
    coding += "</transactionCoding>"
    parts.append(coding)
    amounts = "<transactionAmounts>"
    if shares is not None:
        amounts += f"<transactionShares><value>{shares}</value></transactionShares>"
    if ad is not None:
        amounts += (
            "<transactionAcquiredDisposedCode>"
            f"<value>{ad}</value>"
            "</transactionAcquiredDisposedCode>"
        )
    amounts += "</transactionAmounts>"
    parts.append(amounts)
    parts.append("</nonDerivativeTransaction>")
    return "".join(parts)


def _doc(*txns: str) -> bytes:
    body = "".join(txns)
    return (
        f"<ownershipDocument>{_ISSUER_OWNER}"
        f"<nonDerivativeTable>{body}</nonDerivativeTable>"
        f"</ownershipDocument>"
    ).encode("utf-8")


def test_out_of_enum_code_skips_only_that_row():
    # 'J' (other) is a real SEC code outside the schema enum; the valid 'S' row
    # alongside it must still survive — the whole filing must not abort.
    txns = parse_form4(_doc(_txn(code="J"), _txn(code="S")))
    assert len(txns) == 1
    assert txns[0].transaction_code.value == "S"


def test_missing_transaction_code_skips_only_that_row():
    txns = parse_form4(_doc(_txn(code=None), _txn(code="P")))
    assert len(txns) == 1
    assert txns[0].transaction_code.value == "P"


def test_missing_acquired_disposed_skips_only_that_row():
    txns = parse_form4(_doc(_txn(ad=None), _txn(ad="A")))
    assert len(txns) == 1
    assert txns[0].acquired_disposed.value == "A"


def test_missing_date_skips_only_that_row():
    txns = parse_form4(_doc(_txn(date=None), _txn(date="2026-05-21")))
    assert len(txns) == 1
    assert txns[0].transaction_ts == datetime(2026, 5, 21, tzinfo=timezone.utc)


def test_all_invalid_rows_returns_empty_without_raising():
    # A filing of only junk rows yields [] rather than raising.
    assert parse_form4(_doc(_txn(code="J"), _txn(code=None))) == []


# --- 10b5-1 is per-transaction, not filing-wide -------------------------------

_PER_TXN_10B5_DOC = """
<ownershipDocument>
    <issuer>
        <issuerCik>0001321655</issuerCik>
        <issuerName>Palantir Technologies Inc.</issuerName>
        <issuerTradingSymbol>PLTR</issuerTradingSymbol>
    </issuer>
    <reportingOwner>
        <reportingOwnerId><rptOwnerName>Buckley Jeffrey</rptOwnerName></reportingOwnerId>
        <reportingOwnerRelationship><isOfficer>1</isOfficer></reportingOwnerRelationship>
    </reportingOwner>
    <nonDerivativeTable>
        <nonDerivativeTransaction>
            <transactionDate><value>2026-05-20</value></transactionDate>
            <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
            <transactionAmounts>
                <transactionShares><value>100</value></transactionShares>
                <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
            </transactionAmounts>
            <footnoteId id="F1"/>
        </nonDerivativeTransaction>
        <nonDerivativeTransaction>
            <transactionDate><value>2026-05-20</value></transactionDate>
            <transactionCoding><transactionCode>F</transactionCode></transactionCoding>
            <transactionAmounts>
                <transactionShares><value>50</value></transactionShares>
                <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
            </transactionAmounts>
            <footnoteId id="F2"/>
        </nonDerivativeTransaction>
    </nonDerivativeTable>
    <footnotes>
        <footnote id="F1">Open-market sale pursuant to a Rule 10b5-1 trading plan.</footnote>
        <footnote id="F2">Shares withheld to satisfy tax obligations on RSU vesting.</footnote>
    </footnotes>
</ownershipDocument>
"""


def test_10b5_1_is_per_transaction_not_filing_wide():
    # The 'S' row cites a 10b5-1 plan footnote; the 'F' (tax-withholding) row cites
    # a plain footnote. The flag must be per-transaction, not bleed across the filing.
    txns = parse_form4(_PER_TXN_10B5_DOC)
    by_code = {t.transaction_code.value: t for t in txns}
    assert by_code["S"].is_10b5_1 is True
    assert by_code["F"].is_10b5_1 is False
