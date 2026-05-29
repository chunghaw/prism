"""Form 4 insider transactions — see docs/SCHEMA.md §2 (time-series ``filings_form4``)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import Field, model_validator

from .common import AcquiredDisposed, PrismModel, TransactionCode


class Form4Meta(PrismModel):
    """The time-series metaField: the dimensions an advocate filters/groups on."""

    ticker: str
    issuer_cik: str = Field(pattern=r"^\d{10}$")
    issuer_name: str
    insider_name: str
    insider_title: Optional[str] = None
    is_director: bool = False
    is_officer: bool = False
    is_ten_pct_owner: bool = False

    @model_validator(mode="after")
    def _upper_ticker(self) -> "Form4Meta":
        self.ticker = self.ticker.upper()
        return self


class Form4Transaction(PrismModel):
    transaction_ts: datetime              # timeField
    meta: Form4Meta                       # metaField
    accession_number: str                 # dedupe key (kept in a side set; TS has no unique idx)
    transaction_code: TransactionCode
    shares: float = Field(ge=0)
    price_per_share: Optional[float] = Field(default=None, ge=0)
    value_usd: Optional[int] = Field(default=None, ge=0)
    acquired_disposed: AcquiredDisposed
    is_10b5_1: bool = False               # programmatic plan → less informative
    ingested_at: Optional[datetime] = None

    @model_validator(mode="after")
    def _derive_value(self) -> "Form4Transaction":
        if self.value_usd is None and self.price_per_share is not None:
            self.value_usd = round(self.shares * self.price_per_share)
        return self
