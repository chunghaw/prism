"""Shared enums, constants, and base models for Prism's collection schemas.

Mirrors docs/SCHEMA.md. Money is whole USD; tickers are upper-case; embeddings
are EMBEDDING_DIM floats from gemini-embedding-001.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict

# gemini-embedding-001 with output_dimensionality=768 (storage-friendly for M0).
# If you change the embed model, change every vector index numDimensions too.
EMBEDDING_DIM = 768


class PrismModel(BaseModel):
    """Base for STORAGE shapes (read/written to MongoDB).

    Lenient on extra keys so Mongo's ``_id`` and future fields round-trip cleanly.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True, str_strip_whitespace=True)


class OutputModel(BaseModel):
    """Base for LLM STRUCTURED-OUTPUT shapes — strict, to reject hallucinated fields."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ShareType(str, Enum):
    SH = "SH"   # shares
    PRN = "PRN"  # principal amount


class TransactionCode(str, Enum):
    PURCHASE = "P"          # open-market purchase
    SALE = "S"              # open-market sale
    OPTION_EXERCISE = "M"
    TAX = "F"               # tax payment via shares
    AWARD = "A"             # award / grant
    GIFT = "G"              # bona fide gift


class AcquiredDisposed(str, Enum):
    ACQUIRED = "A"
    DISPOSED = "D"


class SentimentLabel(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    SARCASTIC = "sarcastic"


class PrimaryEmotion(str, Enum):
    FOMO = "fomo"
    FEAR = "fear"
    EUPHORIA = "euphoria"
    REGRET = "regret"
    ANALYTICAL = "analytical"
    JOKING = "joking"


class Stance(str, Enum):
    """Institutional / insider stance."""

    BUYING = "buying"
    SELLING = "selling"
    NEUTRAL = "neutral"


class RetailStance(str, Enum):
    EUPHORIC = "euphoric"
    BULLISH = "bullish"
    BEARISH = "bearish"
    APATHETIC = "apathetic"
