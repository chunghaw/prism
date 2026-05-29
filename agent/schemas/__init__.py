"""Prism schema contracts — the single source of truth for all 7 collections
plus the LLM structured-output shapes. Implements docs/SCHEMA.md.

Import from here, never redefine fields elsewhere:

    from agent.schemas import Filing13F, Form4Transaction, WSBPost, AdvocateView
"""
from __future__ import annotations

from .advocate import AdvocateView, Archetype, Citation, DivergenceSynthesis
from .common import (
    EMBEDDING_DIM,
    AcquiredDisposed,
    OutputModel,
    PrimaryEmotion,
    PrismModel,
    RetailStance,
    SentimentLabel,
    ShareType,
    Stance,
    TransactionCode,
)
from .divergence import DivergencePattern, Outcome
from .filings import Filing13F, Position13F
from .insider import Form4Meta, Form4Transaction
from .market import PriceBar
from .research import Paper
from .signals import (
    DivergenceRef,
    InsiderSignal,
    InstitutionalSignal,
    NormalizedSignal,
    PriceSummary,
    RetailSignal,
)
from .social import WSBPost, WSBSentiment

__all__ = [
    "EMBEDDING_DIM",
    "PrismModel",
    "OutputModel",
    "ShareType",
    "TransactionCode",
    "AcquiredDisposed",
    "SentimentLabel",
    "PrimaryEmotion",
    "Stance",
    "RetailStance",
    "Position13F",
    "Filing13F",
    "Form4Meta",
    "Form4Transaction",
    "WSBSentiment",
    "WSBPost",
    "PriceBar",
    "Paper",
    "InstitutionalSignal",
    "InsiderSignal",
    "RetailSignal",
    "PriceSummary",
    "DivergenceRef",
    "NormalizedSignal",
    "Outcome",
    "DivergencePattern",
    "Archetype",
    "Citation",
    "AdvocateView",
    "DivergenceSynthesis",
]
