"""Pure WSB (Reddit r/WallStreetBets) post parser — see docs/SCHEMA.md §3.

No network, no MongoDB, no Vertex AI. Maps a PRAW-like submission dict to the
committed ``WSBPost`` storage contract. Ticker extraction is a deliberately dumb
regex-plus-allowlist intersection: WSB prose is full of uppercase noise
(``THE``, ``CEO``, ``USA``), so we keep ONLY tokens that are in the tracked-ticker
set. Sentiment and embedding are left ``None`` — both are filled by a separate
Gemini pass downstream (classic NLP breaks on WSB irony).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from agent.schemas import WSBPost

# $-prefixed (cashtag) OR bare uppercase tokens, 1-5 letters. The leading
# boundary stops us matching the tail of a CamelCase / mixed-alnum word; the $
# is optional and not captured.
_TICKER_RE = re.compile(r"(?<![A-Za-z0-9])\$?([A-Z]{1,5})(?![A-Za-z0-9])")


def extract_tickers(text: str, valid_tickers: set[str]) -> list[str]:
    """Return tracked tickers mentioned in ``text``, deduped, in first-seen order.

    Matches ``$``-prefixed cashtags and bare uppercase 1-5 letter tokens, then
    intersects with ``valid_tickers`` so junk uppercase words are dropped.
    """
    if not text:
        return []
    seen: dict[str, None] = {}  # ordered set: preserves first-occurrence order
    for token in _TICKER_RE.findall(text):
        if token in valid_tickers and token not in seen:
            seen[token] = None
    return list(seen)


def submission_to_post(sub: dict, valid_tickers: set[str]) -> WSBPost | None:
    """Map a PRAW-like submission dict to a ``WSBPost``.

    Tickers are the union (title first, then body) of the per-field extractions.
    Returns ``None`` when the post mentions no tracked ticker — those rows never
    enter ``wsb_posts``. ``sentiment`` and ``embedding`` stay ``None`` (deferred
    to the Gemini pass). Optional fields are tolerated when missing.
    """
    title = sub.get("title") or ""
    text = sub.get("selftext") or ""

    tickers: list[str] = []
    seen: set[str] = set()
    for source in (title, text):
        for ticker in extract_tickers(source, valid_tickers):
            if ticker not in seen:
                seen.add(ticker)
                tickers.append(ticker)
    if not tickers:
        return None

    created_utc = datetime.fromtimestamp(float(sub["created_utc"]), tz=timezone.utc)

    return WSBPost(
        post_id=sub["id"],
        created_utc=created_utc,
        title=title,
        text=text,
        score=int(sub.get("score", 0)),
        num_comments=int(sub.get("num_comments", 0)),
        flair=sub.get("link_flair_text"),
        tickers=tickers,
        sentiment=None,
        embedding=None,
    )
