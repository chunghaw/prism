"""Reddit r/WallStreetBets ingestion adapter — the thin network/Mongo edge.

This module is deliberately *thin*: all parsing/ticker logic lives in the pure
core (:mod:`agent.tools.parse_wsb`, :mod:`agent.tools.tickers`) and the storage
shape is the committed :class:`agent.schemas.WSBPost` contract. Here we only:

1. build a ``praw.Reddit`` client from environment credentials,
2. pull ``r/wallstreetbets`` *new* submissions over the network, and
3. upsert the parsed posts into the ``wsb_posts`` collection idempotently.

Secrets (REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET / REDDIT_USER_AGENT) are read
from the environment, never hardcoded. ``sentiment`` and ``embedding`` stay
``None`` — both are filled by a separate downstream Gemini pass (see SCHEMA.md §3).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Iterator

from rich.console import Console
from tenacity import retry, stop_after_attempt, wait_exponential

from agent.ingest.db import upsert_many
from agent.schemas import WSBPost
from agent.tools.parse_wsb import submission_to_post
from agent.tools.tickers import sp500_symbols

_SUBREDDIT = "wallstreetbets"
_console = Console()

# PRAW submission attributes mapped onto the parser's expected dict keys. The
# parser is the one source of truth for the field names — we just hand it a dict.
_SUBMISSION_ATTRS = (
    "id",
    "created_utc",
    "title",
    "selftext",
    "score",
    "num_comments",
    "link_flair_text",
)


def make_reddit():
    """Build a read-only ``praw.Reddit`` from environment credentials.

    Raises a clear ``RuntimeError`` listing every missing variable so a misconfig
    is obvious at ingest time rather than as an opaque PRAW error later.
    """
    import praw  # local import: keep the module importable without praw installed

    env = {
        "client_id": "REDDIT_CLIENT_ID",
        "client_secret": "REDDIT_CLIENT_SECRET",
        "user_agent": "REDDIT_USER_AGENT",
    }
    values = {arg: os.environ.get(var) for arg, var in env.items()}
    missing = [env[arg] for arg, val in values.items() if not val]
    if missing:
        raise RuntimeError(
            "Missing Reddit credentials: " + ", ".join(missing) + " (add them to .env)"
        )
    return praw.Reddit(check_for_async=False, **values)


def _submission_to_dict(sub) -> dict:
    """Pull the PRAW submission attributes the pure parser expects into a dict."""
    return {attr: getattr(sub, attr, None) for attr in _SUBMISSION_ATTRS}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=30), reraise=True)
def _new_submissions(reddit, *, limit: int) -> list:
    """Fetch the ``new`` listing (network) and return it as a concrete list.

    ``reddit.subreddit(...).new(...)`` returns a *lazy* PRAW ``ListingGenerator``:
    merely constructing it does no network I/O — the HTTP fetch happens during
    iteration. We therefore materialise the listing with ``list(...)`` *inside*
    this retried function so the network hop is genuinely enclosed by ``@retry``
    and transient PRAW/network errors actually trigger exponential backoff
    (mirrors edgar.py's ``_get`` reading the response inside the retry boundary).
    """
    return list(reddit.subreddit(_SUBREDDIT).new(limit=limit))


def fetch_wsb_posts(
    reddit,
    *,
    limit: int = 200,
    valid_tickers: set[str] | None = None,
) -> Iterator[WSBPost]:
    """Yield parsed ``WSBPost`` objects from the latest ``r/wallstreetbets`` posts.

    Iterates ``reddit.subreddit("wallstreetbets").new(limit=limit)``, marshals each
    submission into the dict the pure parser expects, and yields only the non-``None``
    results (posts that mention at least one tracked ticker). ``valid_tickers``
    defaults to the committed S&P 500 universe.
    """
    universe = valid_tickers if valid_tickers is not None else sp500_symbols()
    for sub in _new_submissions(reddit, limit=limit):
        post = submission_to_post(_submission_to_dict(sub), universe)
        if post is not None:
            yield post


def ingest_wsb(db, reddit=None, *, limit: int = 200, valid_tickers: set[str] | None = None) -> int:
    """Fetch latest WSB posts and idempotently upsert them into ``wsb_posts``.

    Returns the number of rows written (inserted + modified). Re-ingestion of the
    same posts is a no-op beyond field refreshes — the ``post_id`` natural key
    de-dupes. ``sentiment`` / ``embedding`` are left ``None`` for the Gemini pass.
    """
    reddit = reddit or make_reddit()
    now = datetime.now(timezone.utc)
    docs = []
    for post in fetch_wsb_posts(reddit, limit=limit, valid_tickers=valid_tickers):
        doc = post.model_dump(mode="python")
        doc["ingested_at"] = now
        docs.append(doc)

    written = upsert_many(db, "wsb_posts", docs)
    _console.log(f"wsb_posts: upserted {written} of {len(docs)} parsed posts")
    return written
