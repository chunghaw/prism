"""Behavioural-finance paper corpus — see docs/SCHEMA.md §5 (collection ``papers``)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import Field, field_validator

from .common import EMBEDDING_DIM, PrismModel


class Paper(PrismModel):
    paper_id: str                         # natural key (slug, e.g. "barber-odean-2000")
    title: str
    authors: list[str]
    year: int = Field(ge=1900, le=2100)
    venue: Optional[str] = None
    abstract: str
    url: Optional[str] = None
    bias_tags: list[str] = Field(default_factory=list)
    pattern_explained: Optional[str] = None
    embedding: Optional[list[float]] = None
    ingested_at: Optional[datetime] = None

    @field_validator("embedding")
    @classmethod
    def _check_dim(cls, v: Optional[list[float]]) -> Optional[list[float]]:
        if v is not None and len(v) != EMBEDDING_DIM:
            raise ValueError(f"embedding must have {EMBEDDING_DIM} dims, got {len(v)}")
        return v
