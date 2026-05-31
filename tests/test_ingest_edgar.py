"""Tests for ``agent.ingest.edgar`` — the SEC EDGAR 13F + Form 4 ingestion edge.

Every test substitutes the single network seam (:func:`edgar._get`) with a fake
that serves the committed fixtures plus a tiny fake submissions JSON / index.json.
NO real network is hit and NO credentials are required — the fetch dance and the
Mongo write paths run fully offline and deterministically.

The Mongo helpers are exercised against in-memory fakes that mimic just the
``pymongo`` surface the ingestors use (``bulk_write`` / ``insert_many`` /
``distinct``), so idempotency and time-series dedupe are asserted without a
cluster.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.ingest import edgar
from agent.schemas import Filing13F

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "sec"
F13F_XML = (FIXTURES / "13f_berkshire_sample.xml").read_text(encoding="utf-8")
FORM4_XML = (FIXTURES / "form4_sample.xml").read_text(encoding="utf-8")

BERKSHIRE_CIK = "0001067983"
PALANTIR_CIK = "0001321655"
F13F_ACCESSION = "0000950123-26-001234"
FORM4_ACCESSION = "0001234567-26-000045"


# --- fake network seam --------------------------------------------------------
def _submissions_json(*, form: str, accession: str, period: str, name: str) -> str:
    """A minimal submissions JSON: one filing of ``form`` in the recent block."""
    return json.dumps(
        {
            "name": name,
            "filings": {
                "recent": {
                    "form": ["3", form, "10-K"],          # decoys around the target
                    "accessionNumber": ["acc-3", accession, "acc-10k"],
                    "filingDate": ["2026-02-01", "2026-02-14", "2026-01-01"],
                    "reportDate": ["2025-12-31", period, "2025-12-31"],
                }
            },
        }
    )


def _index_json(xml_name: str) -> str:
    """A minimal filing-dir index.json listing one .xml plus a non-xml decoy."""
    return json.dumps(
        {"directory": {"item": [{"name": "primary_doc.html"}, {"name": xml_name}]}}
    )


def make_fake_get(*, form: str, accession: str, xml: str, period: str, name: str):
    """Build a ``_get(url, ua)`` stand-in routing each URL to the right fixture.

    Routing mirrors the real fetch dance: submissions JSON -> index.json -> .xml.
    Records every URL it served so tests can assert the dance happened in order.
    Asserts a User-Agent is always supplied (the SEC contract).
    """
    calls: list[str] = []
    xml_name = "infotable.xml" if "infoTable" in xml else "ownership.xml"

    def fake_get(url: str, ua: str) -> str:
        assert ua, "every SEC call must carry a User-Agent"
        calls.append(url)
        if "submissions/CIK" in url:
            return _submissions_json(
                form=form, accession=accession, period=period, name=name
            )
        if url.endswith("index.json"):
            return _index_json(xml_name)
        if url.endswith(".xml"):
            return xml
        raise AssertionError(f"unexpected URL: {url}")

    fake_get.calls = calls  # type: ignore[attr-defined]
    return fake_get


# --- fake Mongo surface -------------------------------------------------------
class _FakeCollection:
    def __init__(self) -> None:
        self.upserts: dict[tuple, dict] = {}
        self.rows: list[dict] = []

    # mirrors pymongo bulk_write(UpdateOne(...), upsert=True)
    def bulk_write(self, ops, ordered=False):
        upserted = modified = 0
        for op in ops:
            flt = tuple(sorted(op._filter.items()))
            doc = op._doc["$set"]
            if flt in self.upserts:
                modified += 1
            else:
                upserted += 1
            self.upserts[flt] = doc

        class _Res:
            pass

        res = _Res()
        res.upserted_count = upserted
        res.modified_count = modified
        return res

    # mirrors pymongo insert_many for the time-series collection
    def insert_many(self, docs):
        docs = list(docs)
        self.rows.extend(docs)

        class _Res:
            pass

        res = _Res()
        res.inserted_ids = list(range(len(docs)))
        return res

    def distinct(self, field):
        return [r[field] for r in self.rows if field in r]


class _FakeDB:
    def __init__(self) -> None:
        self._colls: dict[str, _FakeCollection] = {}

    def __getitem__(self, name):
        return self._colls.setdefault(name, _FakeCollection())


# --- fetch_13f ----------------------------------------------------------------
def test_fetch_13f_yields_filing_with_three_positions_and_dollar_values():
    fake_get = make_fake_get(
        form="13F-HR",
        accession=F13F_ACCESSION,
        xml=F13F_XML,
        period="2025-12-31",
        name="BERKSHIRE HATHAWAY INC",
    )
    filing = edgar.fetch_13f(BERKSHIRE_CIK, ua="Tester t@example.com", _get=fake_get)

    assert isinstance(filing, Filing13F)
    assert filing.n_positions == 3
    assert len(filing.positions) == 3
    # Fixture is post-2024 whole-dollar <value>: 498,992,850 ≈ $499M (NOT thousands).
    assert filing.positions[0].value_usd == 498_992_850
    assert filing.positions[0].shares == 12_719_675
    assert filing.total_value_usd == 498_992_850 + 109_996_016 + 165_872_286
    # period 2025-12-31 -> Q4
    assert filing.quarter == "2025Q4"
    assert filing.fund_cik == BERKSHIRE_CIK
    assert filing.fund_name == "BERKSHIRE HATHAWAY INC"
    assert filing.accession_number == F13F_ACCESSION


def test_fetch_13f_quarter_derived_from_period_not_filing_date():
    # period 2025-03-31 (Q1) even though it was filed in May.
    fake_get = make_fake_get(
        form="13F-HR",
        accession=F13F_ACCESSION,
        xml=F13F_XML,
        period="2025-03-31",
        name="ACME CAPITAL",
    )
    filing = edgar.fetch_13f(BERKSHIRE_CIK, ua="Tester t@example.com", _get=fake_get)
    assert filing is not None
    assert filing.quarter == "2025Q1"


def test_fetch_13f_follows_the_full_dance_in_order():
    fake_get = make_fake_get(
        form="13F-HR",
        accession=F13F_ACCESSION,
        xml=F13F_XML,
        period="2025-12-31",
        name="BERKSHIRE",
    )
    edgar.fetch_13f(BERKSHIRE_CIK, ua="Tester t@example.com", _get=fake_get)
    urls = fake_get.calls
    assert any("submissions/CIK" in u for u in urls)
    assert any(u.endswith("index.json") for u in urls)
    assert any(u.endswith(".xml") for u in urls)
    # submissions before index before xml
    assert next(i for i, u in enumerate(urls) if "submissions" in u) < next(
        i for i, u in enumerate(urls) if u.endswith("index.json")
    )


def test_fetch_13f_returns_none_when_no_13f_on_file():
    def fake_get(url: str, ua: str) -> str:
        # submissions with only a Form 4, no 13F-HR
        return _submissions_json(
            form="4", accession="x", period="2025-12-31", name="NO 13F CO"
        )

    assert edgar.fetch_13f(BERKSHIRE_CIK, ua="Tester t@example.com", _get=fake_get) is None


def test_fetch_13f_resolve_tickers_uses_resolver(monkeypatch):
    fake_get = make_fake_get(
        form="13F-HR",
        accession=F13F_ACCESSION,
        xml=F13F_XML,
        period="2025-12-31",
        name="BERKSHIRE",
    )
    seen = {}

    def fake_resolve(cusips, **kw):
        seen["cusips"] = list(cusips)
        return {"02005N100": "ALLY"}

    monkeypatch.setattr(edgar, "resolve_cusips", fake_resolve)
    filing = edgar.fetch_13f(
        BERKSHIRE_CIK, ua="Tester t@example.com", resolve_tickers=True, _get=fake_get
    )
    assert filing is not None
    assert "02005N100" in seen["cusips"]
    assert all(p.ticker == "ALLY" for p in filing.positions)


# --- fetch_form4 --------------------------------------------------------------
def test_fetch_form4_yields_pltr_transactions_with_accession_stamped():
    fake_get = make_fake_get(
        form="4",
        accession=FORM4_ACCESSION,
        xml=FORM4_XML,
        period="2026-05-20",
        name="Palantir Technologies Inc",
    )
    txns = edgar.fetch_form4(PALANTIR_CIK, ua="Tester t@example.com", _get=fake_get)

    assert len(txns) >= 1
    assert all(t.meta.ticker == "PLTR" for t in txns)
    assert all(t.accession_number == FORM4_ACCESSION for t in txns)
    # All fixture rows are open-market sales (S) disposed (D).
    assert all(t.transaction_code.value == "S" for t in txns)
    # First-row 10b5-1 footnote is detected by the pure parser.
    assert txns[0].is_10b5_1 is True


def test_fetch_form4_skips_filings_without_ownership_xml():
    def fake_get(url: str, ua: str) -> str:
        if "submissions/CIK" in url:
            return _submissions_json(
                form="4", accession=FORM4_ACCESSION, period="2026-05-20", name="X"
            )
        if url.endswith("index.json"):
            # dir has no .xml at all
            return json.dumps({"directory": {"item": [{"name": "primary_doc.html"}]}})
        raise AssertionError(f"should not fetch: {url}")

    assert edgar.fetch_form4(PALANTIR_CIK, ua="Tester t@example.com", _get=fake_get) == []


# --- ingest_13f (idempotent upsert) ------------------------------------------
def test_ingest_13f_upserts_and_is_idempotent():
    fake_get = make_fake_get(
        form="13F-HR",
        accession=F13F_ACCESSION,
        xml=F13F_XML,
        period="2025-12-31",
        name="BERKSHIRE HATHAWAY INC",
    )
    db = _FakeDB()

    written = edgar.ingest_13f(
        db, [BERKSHIRE_CIK], ua="Tester t@example.com", _get=fake_get
    )
    assert written == 1
    coll = db["filings_13f"]
    assert len(coll.upserts) == 1
    stored = next(iter(coll.upserts.values()))
    assert stored["accession_number"] == F13F_ACCESSION
    assert stored["n_positions"] == 3
    assert "ingested_at" in stored

    # Re-ingest: same accession -> upsert key unchanged, no duplicate doc.
    edgar.ingest_13f(db, [BERKSHIRE_CIK], ua="Tester t@example.com", _get=fake_get)
    assert len(coll.upserts) == 1


# --- ingest_form4 (time-series append + accession dedupe) --------------------
def test_ingest_form4_appends_and_dedupes_accession():
    fake_get = make_fake_get(
        form="4",
        accession=FORM4_ACCESSION,
        xml=FORM4_XML,
        period="2026-05-20",
        name="Palantir Technologies Inc",
    )
    db = _FakeDB()

    n_first = edgar.ingest_form4(
        db, [PALANTIR_CIK], ua="Tester t@example.com", _get=fake_get
    )
    coll = db["filings_form4"]
    assert n_first >= 1
    assert len(coll.rows) == n_first
    assert all(r["accession_number"] == FORM4_ACCESSION for r in coll.rows)
    assert all("transaction_ts" in r and "meta" in r for r in coll.rows)
    assert all("ingested_at" in r for r in coll.rows)

    # Re-ingest the same accession: it's already stored -> nothing new appended.
    n_second = edgar.ingest_form4(
        db, [PALANTIR_CIK], ua="Tester t@example.com", _get=fake_get
    )
    assert n_second == 0
    assert len(coll.rows) == n_first


# --- credentials / env contract ----------------------------------------------
def test_missing_user_agent_raises(monkeypatch):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    with pytest.raises(RuntimeError, match="SEC_USER_AGENT"):
        edgar.fetch_13f(BERKSHIRE_CIK, _get=lambda url, ua: "")


def test_user_agent_read_from_env(monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "Env Reader env@example.com")
    fake_get = make_fake_get(
        form="13F-HR",
        accession=F13F_ACCESSION,
        xml=F13F_XML,
        period="2025-12-31",
        name="BERKSHIRE",
    )
    filing = edgar.fetch_13f(BERKSHIRE_CIK, _get=fake_get)  # no explicit ua
    assert filing is not None
    assert filing.n_positions == 3
