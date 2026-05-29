"""Reddit r/WallStreetBets posts — see docs/SCHEMA.md §3 (collection ``wsb_posts``)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import Field, field_validator

from .common import EMBEDDING_DIM, PrimaryEmotion, PrismModel, SentimentLabel


class WSBSentiment(PrismModel):
    """Filled by a separate Gemini pass — never by classic NLP (WSB irony breaks VADER)."""

    label: SentimentLabel
    confidence: float = Field(ge=0, le=1)
    primary_emotion: PrimaryEmotion
    is_dd_post: bool
    is_loss_porn: bool


class WSBPost(PrismModel):
    post_id: str                          # natural key (Reddit base36 id)
    created_utc: datetime
    title: str
    text: str = ""
    score: int
    num_comments: int = Field(ge=0)
    flair: Optional[str] = None
    tickers: list[str]                    # ∩ tracked-ticker set
    sentiment: Optional[WSBSentiment] = None
    embedding: Optional[list[float]] = None
    ingested_at: Optional[datetime] = None

    @field_validator("text")
    @classmethod
    def _truncate(cls, v: str) -> str:
        return v[:5000]

    @field_validator("tickers")
    @classmethod
    def _upper(cls, v: list[str]) -> list[str]:
        return [t.upper() for t in v]

    @field_validator("embedding")
    @classmethod
    def _check_dim(cls, v: Optional[list[float]]) -> Optional[list[float]]:
        if v is not None and len(v) != EMBEDDING_DIM:
            raise ValueError(f"embedding must have {EMBEDDING_DIM} dims, got {len(v)}")
        return v
