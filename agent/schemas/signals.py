"""Gold unified per-ticker signal — see docs/SCHEMA.md §6 (``normalized_signals``)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import Field

from .common import PrismModel, RetailStance, Stance


class InstitutionalSignal(PrismModel):
    n_funds: int = Field(ge=0)
    n_funds_delta: int = 0
    net_flow_usd: int = 0
    stance: Stance = Stance.NEUTRAL
    top_buyers: list[str] = Field(default_factory=list)
    top_sellers: list[str] = Field(default_factory=list)


class InsiderSignal(PrismModel):
    n_transactions: int = Field(ge=0)
    pct_selling: float = Field(ge=0, le=1)
    net_value_usd: int = 0
    stance: Stance = Stance.NEUTRAL
    discretionary_share: float = Field(default=1.0, ge=0, le=1)  # 1 - (10b5-1 share)


class RetailSignal(PrismModel):
    n_mentions: int = Field(ge=0)
    pct_bullish: float = Field(ge=0, le=1)
    mention_growth_30d: float = 0.0
    dd_growth_30d: float = 0.0
    stance: RetailStance = RetailStance.APATHETIC


class PriceSummary(PrismModel):
    close: Optional[float] = None
    ret_30d: Optional[float] = None


class DivergenceRef(PrismModel):
    type: str
    score: float = Field(ge=0, le=1)
    pattern_id: Optional[str] = None


class NormalizedSignal(PrismModel):
    ticker: str
    as_of_date: datetime                  # natural key with ticker
    institutional: InstitutionalSignal
    insider: InsiderSignal
    retail: RetailSignal
    price: PriceSummary = Field(default_factory=PriceSummary)
    divergence: Optional[DivergenceRef] = None
    computed_at: Optional[datetime] = None
