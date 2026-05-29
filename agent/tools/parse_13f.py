"""Pure 13F information-table parser — see docs/SCHEMA.md §1 (``filings_13f``).

No network, no MongoDB, no Vertex AI. Just bytes in, Pydantic models out.

The SEC 13F informationTable XML is namespaced
(``http://www.sec.gov/edgar/document/thirteenf/informationtable``), and the
namespace prefix/URI varies across filers. We therefore match elements by their
*local name* (XPath ``local-name()``) so namespace churn never breaks parsing.

Money note (docs/SCHEMA.md): the post-2024 ``<value>`` element is in whole
dollars. We store it AS-IS — do **not** multiply by 1000.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from lxml import etree

from agent.schemas import Filing13F, Position13F, ShareType

# Map the raw 13F sshPrnamtType code to the schema enum. Anything unknown
# falls back to SH (the overwhelmingly common case for equity holdings).
_SHARE_TYPE = {"SH": ShareType.SH, "PRN": ShareType.PRN}

# putCall codes seen in the wild -> the schema's Literal["Put", "Call"].
_PUT_CALL = {"PUT": "Put", "CALL": "Call"}


def _local_text(node: etree._Element, local_name: str) -> Optional[str]:
    """Return the stripped text of the first descendant with ``local_name``.

    Namespace-agnostic: matches on ``local-name()`` so any (or no) namespace
    prefix resolves. Returns ``None`` when the element is absent or empty.
    """
    found = node.xpath(".//*[local-name()=$n]", n=local_name)
    if not found:
        return None
    text = found[0].text
    if text is None:
        return None
    text = text.strip()
    return text or None


def _to_int(raw: Optional[str]) -> int:
    """Parse a numeric string to int, tolerating commas/whitespace. 0 if empty."""
    if not raw:
        return 0
    cleaned = raw.replace(",", "").strip()
    if not cleaned:
        return 0
    # Some filers pad with decimals (e.g. "12719675.00"); int() can't take those.
    return int(float(cleaned))


def parse_positions(
    xml: bytes, cusip_to_ticker: dict[str, str] | None = None
) -> list[Position13F]:
    """Parse a 13F informationTable into a list of :class:`Position13F`.

    Args:
        xml: Raw informationTable XML bytes (namespaced).
        cusip_to_ticker: Optional CUSIP -> ticker map. When a position's CUSIP
            is present in the map, its ticker is resolved (else ``None``).

    Per ``<infoTable>``:
        * ``nameOfIssuer``       -> ``issuer``
        * ``cusip``              -> ``cusip``
        * ``titleOfClass``       -> ``title_of_class``
        * ``value``              -> ``value_usd`` (AS-IS; post-2024 dollars)
        * ``sshPrnamt``          -> ``shares``
        * ``sshPrnamtType``      -> ``share_type``
        * ``putCall``            -> ``put_call`` (``None`` when empty)

    Optional fields are tolerated when missing.
    """
    cusip_to_ticker = cusip_to_ticker or {}

    # recover=True so a stray malformed tag doesn't nuke the whole filing.
    parser = etree.XMLParser(recover=True, resolve_entities=False)
    root = etree.fromstring(xml, parser=parser)

    positions: list[Position13F] = []
    for info in root.xpath(".//*[local-name()='infoTable']"):
        cusip = _local_text(info, "cusip")
        issuer = _local_text(info, "nameOfIssuer")
        # cusip + issuer are mandatory for a usable holding; skip junk rows.
        if not cusip or not issuer:
            continue

        share_type_raw = (_local_text(info, "sshPrnamtType") or "SH").upper()
        share_type = _SHARE_TYPE.get(share_type_raw, ShareType.SH)

        put_call_raw = _local_text(info, "putCall")
        put_call = _PUT_CALL.get(put_call_raw.upper()) if put_call_raw else None

        ticker = cusip_to_ticker.get(cusip)
        if ticker is None and cusip:
            # CUSIP maps are typically upper-cased; try a normalized lookup too.
            ticker = cusip_to_ticker.get(cusip.upper())

        positions.append(
            Position13F(
                cusip=cusip,
                issuer=issuer,
                ticker=ticker,
                title_of_class=_local_text(info, "titleOfClass"),
                value_usd=_to_int(_local_text(info, "value")),
                shares=_to_int(_local_text(info, "sshPrnamt")),
                share_type=share_type,
                put_call=put_call,
            )
        )

    return positions


def build_filing(
    positions: list[Position13F],
    *,
    fund_cik: str,
    fund_name: str,
    filing_date: datetime,
    quarter: str,
    accession_number: str,
) -> Filing13F:
    """Assemble a :class:`Filing13F` from parsed positions + filing metadata.

    ``n_positions`` and ``total_value_usd`` are derived from ``positions`` by the
    model validator — positions are the single source of truth.
    """
    return Filing13F(
        fund_cik=fund_cik,
        fund_name=fund_name,
        filing_date=filing_date,
        quarter=quarter,
        accession_number=accession_number,
        positions=positions,
    )
