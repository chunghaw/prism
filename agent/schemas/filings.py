"""13F institutional holdings — see docs/SCHEMA.md §1 (collection ``filings_13f``)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import Field, model_validator

from .common import PrismModel, ShareType


class Position13F(PrismModel):
    cusip: str = Field(pattern=r"^[A-Za-z0-9]{9}$")
    issuer: str
    ticker: Optional[str] = None          # resolved via the cusip map; null if unresolved
    title_of_class: Optional[str] = None
    value_usd: int = Field(ge=0, description="Whole USD. Post-2024 13F <value> is dollars (store as-is); ×1000 only for legacy pre-2024 filings.")
    shares: int = Field(ge=0)
    share_type: ShareType = ShareType.SH
    put_call: Optional[Literal["Put", "Call"]] = None

    @model_validator(mode="after")
    def _upper_ticker(self) -> "Position13F":
        if self.ticker:
            self.ticker = self.ticker.upper()
        return self


class Filing13F(PrismModel):
    fund_cik: str = Field(pattern=r"^\d{10}$")
    fund_name: str
    filing_date: datetime
    quarter: str = Field(pattern=r"^\d{4}Q[1-4]$")   # report period, not filing date
    accession_number: str                            # natural key (unique per filing)
    positions: list[Position13F]
    n_positions: int = 0
    total_value_usd: int = 0
    ingested_at: Optional[datetime] = None

    @model_validator(mode="after")
    def _derive_aggregates(self) -> "Filing13F":
        # positions are the single source of truth; aggregates always derive from them.
        self.n_positions = len(self.positions)
        self.total_value_usd = sum(p.value_usd for p in self.positions)
        return self
