"""LLM structured-output shapes for the advocates + synthesiser.

These use OutputModel (extra='forbid') so Gemini cannot smuggle in hallucinated
fields. The advocate prompts in agent/prompts/ must produce exactly these shapes.
"""
from __future__ import annotations

from typing import Literal, Union

from pydantic import Field

from .common import OutputModel

Archetype = Literal["institutional", "insider", "retail"]


class Citation(OutputModel):
    paper_id: str
    title: str
    relevance: str            # one line: why this paper applies to the detected pattern


class AdvocateView(OutputModel):
    """What one advocate sub-agent returns after reading its single data source."""

    archetype: Archetype
    ticker: str
    stance: str               # the advocate's read, in its own words
    headline: str
    bullets: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    key_numbers: dict[str, Union[float, int, str]] = Field(default_factory=dict)


class DivergenceSynthesis(OutputModel):
    """The synthesiser's final cross-archetype output."""

    ticker: str
    divergence_type: str
    divergence_summary: str
    institutional: AdvocateView
    insider: AdvocateView
    retail: AdvocateView
    historical_analogues: list[str] = Field(default_factory=list)   # pattern_ids
    median_30d_return: float | None = None
    citations: list[Citation] = Field(default_factory=list)
    bottom_line: str
