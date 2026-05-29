"""Pure parser for SEC Form 4 ``<ownershipDocument>`` XML.

No network, no MongoDB, no Vertex AI — give it bytes/str, get back a list of
:class:`agent.schemas.Form4Transaction`. The ingestor is responsible for fetching
the document, deduping by accession number, and persisting; this module only maps
the XML onto the committed Pydantic contract (docs/SCHEMA.md §2).

One ``Form4Transaction`` is emitted per ``<nonDerivativeTransaction>``. Derivative
transactions are intentionally ignored. Filtering (e.g. dropping awards) is the
ingestor's job — we return everything valid.

Resilience contract (mirrors :mod:`agent.tools.parse_13f`): parsing is per-row.
Real EDGAR Form 4s use the full SEC transaction-code set (J, C, W, X, K, D, …),
not just the handful the schema enum models, and required fields are occasionally
absent on malformed rows. A row whose required field (date, transaction code, or
acquired/disposed flag) is missing or outside the schema enum is **skipped** —
it never aborts the filing and discards its sibling rows.
"""
from __future__ import annotations

from datetime import datetime, timezone

from lxml import etree
from pydantic import ValidationError

from agent.schemas import Form4Meta, Form4Transaction

# Reporting-owner relationship flags accept both EDGAR's "1"/"0" and "true"/"false".
_TRUTHY = {"1", "true", "yes"}


def _child(node: etree._Element | None, tag: str) -> etree._Element | None:
    """First direct child whose *local* name is ``tag`` (namespace-agnostic).

    Form 4 XML is rarely namespaced, but EDGAR variants sometimes are; matching on
    ``local-name()`` keeps the parser robust either way. ``ElementPath`` (``.find``)
    can't do this predicate, so we use full XPath.
    """
    if node is None:
        return None
    found = node.xpath(f"./*[local-name()='{tag}']")
    return found[0] if found else None


def _descendants(node: etree._Element, tag: str) -> list[etree._Element]:
    """All descendant elements whose *local* name is ``tag``."""
    return node.xpath(f".//*[local-name()='{tag}']")


def _txn_is_10b5_1(txn: etree._Element, footnotes: dict[str, str]) -> bool:
    """True iff one of *this transaction's own* footnote references mentions a
    Rule 10b5-1 plan.

    Per-transaction, NOT filing-wide: a single Form 4 routinely mixes a
    discretionary 10b5-1 open-market sale with, say, an automatic tax-withholding
    sale on RSU vesting — only the rows whose footnotes cite the plan are 10b5-1.
    """
    for ref in _descendants(txn, "footnoteId"):
        fid = ref.get("id")
        if fid and "10b5-1" in footnotes.get(fid, "").lower():
            return True
    return False


def _find_text(node: etree._Element | None, *path: str) -> str | None:
    """Walk ``path`` (a chain of child local-names) under ``node`` and return the
    stripped text of the deepest element, or ``None`` if any hop is missing/empty."""
    cur = node
    for tag in path:
        cur = _child(cur, tag)
    if cur is None or cur.text is None:
        return None
    text = cur.text.strip()
    return text or None


def _to_bool(value: str | None) -> bool:
    return value is not None and value.strip().lower() in _TRUTHY


def _to_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_date_utc(value: str | None) -> datetime | None:
    """Parse a ``YYYY-MM-DD`` SEC date as UTC midnight."""
    if value is None:
        return None
    try:
        naive = datetime.strptime(value[:10], "%Y-%m-%d")
    except ValueError:
        return None
    return naive.replace(tzinfo=timezone.utc)


def parse_form4(xml: bytes | str, *, accession_number: str = "") -> list[Form4Transaction]:
    """Parse a Form 4 ``<ownershipDocument>`` into ``Form4Transaction`` rows.

    Args:
        xml: Raw Form 4 XML as bytes or str.
        accession_number: Stamped onto every returned transaction (dedupe key).

    Returns:
        One ``Form4Transaction`` per **valid** ``<nonDerivativeTransaction>``
        (possibly empty). Rows with a missing/unmappable required field
        (date, transaction code, or acquired/disposed flag) are skipped.
    """
    data = xml.encode("utf-8") if isinstance(xml, str) else xml
    # ``recover`` tolerates the slightly-malformed XML EDGAR occasionally emits.
    root = etree.fromstring(data, parser=etree.XMLParser(recover=True))
    if root is None:
        return []

    # --- issuer ---------------------------------------------------------------
    issuer = _child(root, "issuer")
    issuer_cik = (_find_text(issuer, "issuerCik") or "").zfill(10)
    issuer_name = _find_text(issuer, "issuerName") or ""
    ticker = (_find_text(issuer, "issuerTradingSymbol") or "").upper()

    # --- reporting owner ------------------------------------------------------
    owner = _child(root, "reportingOwner")
    insider_name = _find_text(owner, "reportingOwnerId", "rptOwnerName") or ""
    insider_title = _find_text(owner, "reportingOwnerRelationship", "officerTitle")
    is_director = _to_bool(_find_text(owner, "reportingOwnerRelationship", "isDirector"))
    is_officer = _to_bool(_find_text(owner, "reportingOwnerRelationship", "isOfficer"))
    is_ten_pct = _to_bool(
        _find_text(owner, "reportingOwnerRelationship", "isTenPercentOwner")
    )

    meta = Form4Meta(
        ticker=ticker,
        issuer_cik=issuer_cik,
        issuer_name=issuer_name,
        insider_name=insider_name,
        insider_title=insider_title,
        is_director=is_director,
        is_officer=is_officer,
        is_ten_pct_owner=is_ten_pct,
    )

    # --- footnote map (id -> text) for per-transaction 10b5-1 detection -------
    footnotes = {
        fn.get("id"): (fn.text or "")
        for fn in _descendants(root, "footnote")
        if fn.get("id")
    }

    # --- non-derivative transactions ------------------------------------------
    transactions: list[Form4Transaction] = []
    for txn in _descendants(root, "nonDerivativeTransaction"):
        transaction_ts = _parse_date_utc(_find_text(txn, "transactionDate", "value"))
        transaction_code = _find_text(txn, "transactionCoding", "transactionCode")
        shares = _to_float(_find_text(txn, "transactionAmounts", "transactionShares", "value"))
        price = _to_float(
            _find_text(txn, "transactionAmounts", "transactionPricePerShare", "value")
        )
        acquired_disposed = _find_text(
            txn, "transactionAmounts", "transactionAcquiredDisposedCode", "value"
        )
        is_10b5_1 = _txn_is_10b5_1(txn, footnotes)

        # Per-row resilience (see module docstring): a row missing a required
        # field, or carrying a transaction/acquired-disposed code outside the
        # schema enum, is dropped — never raised — so its valid siblings survive.
        try:
            transactions.append(
                Form4Transaction(
                    transaction_ts=transaction_ts,
                    meta=meta,
                    accession_number=accession_number,
                    transaction_code=transaction_code,
                    shares=shares if shares is not None else 0.0,
                    price_per_share=price,
                    acquired_disposed=acquired_disposed,
                    is_10b5_1=is_10b5_1,
                )
            )
        except ValidationError:
            continue

    return transactions
