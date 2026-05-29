"""yfinance price bars — see docs/SCHEMA.md §4 (time-series ``prices``)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import Field, model_validator

from .common import PrismModel


class PriceBar(PrismModel):
    ts: datetime                          # timeField
    ticker: str                           # metaField
    open: float = Field(ge=0)
    high: float = Field(ge=0)
    low: float = Field(ge=0)
    close: float = Field(ge=0)
    adj_close: Optional[float] = Field(default=None, ge=0)
    volume: int = Field(ge=0)
    source: str = "yfinance"
    ingested_at: Optional[datetime] = None

    @model_validator(mode="after")
    def _upper_ticker(self) -> "PriceBar":
        self.ticker = self.ticker.upper()
        return self
