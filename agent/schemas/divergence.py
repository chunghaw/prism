"""Catalogued historical divergence patterns — see docs/SCHEMA.md §7 (``divergence_library``)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import Field, field_validator

from .common import EMBEDDING_DIM, PrismModel


class Outcome(PrismModel):
    horizon_days: int = Field(gt=0)
    return_pct: float
    distribution: list[float] = Field(default_factory=list)  # percentile spread of analogues


class DivergencePattern(PrismModel):
    pattern_id: str                       # natural key (e.g. "div-0007")
    ticker: str
    as_of_date: datetime
    pattern_type: str                     # e.g. "inst_buy/insider_sell/retail_euphoric"
    description: str
    signal_vector: list[float] = Field(default_factory=list)  # [inst, insider, retail_bull, growth]
    embedding: Optional[list[float]] = None
    outcome: Outcome
    n_prior_instances: int = Field(default=0, ge=0)
    related_papers: list[str] = Field(default_factory=list)   # paper_id slugs
    ingested_at: Optional[datetime] = None

    @field_validator("embedding")
    @classmethod
    def _check_dim(cls, v: Optional[list[float]]) -> Optional[list[float]]:
        if v is not None and len(v) != EMBEDDING_DIM:
            raise ValueError(f"embedding must have {EMBEDDING_DIM} dims, got {len(v)}")
        return v
