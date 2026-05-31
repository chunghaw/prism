"""Tests for the thin WSB ingestion adapter (agent/ingest/reddit_wsb.py).

Everything is mocked: no network, no Reddit credentials, no live MongoDB. The
adapter is the *edge* — these tests prove it wires the pure parser to Mongo
correctly and idempotently, leaving sentiment/embedding for the Gemini pass.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent.ingest import reddit_wsb
from agent.schemas import WSBPost

VALID_TICKERS = {"PLTR", "AAPL", "GME", "TSLA", "AMD"}

# One submission mentions a real tracked ticker ($PLTR); the other is pure
# uppercase junk (THE / CEO / USA) that must be dropped by the parser.
_PLTR_SUB = SimpleNamespace(
    id="pltr01",
    created_utc=1748563200.0,
    title="$PLTR to the moon DD inside",
    selftext="loaded up on PLTR calls",
    score=4210,
    num_comments=318,
    link_flair_text="DD",
)
_JUNK_SUB = SimpleNamespace(
    id="junk99",
    created_utc=1748563200.0,
    title="THE best CEO play in the USA, no real tickers here",
    selftext="Just vibes and YOLO, NFA.",
    score=5,
    num_comments=1,
    link_flair_text="Discussion",
)


class _FakeSubreddit:
    """Records the limit passed to .new() and replays canned submissions."""

    def __init__(self, submissions):
        self._submissions = submissions
        self.last_limit = None

    def new(self, limit=None):
        self.last_limit = limit
        return iter(self._submissions)


class _FakeReddit:
    def __init__(self, submissions):
        self._subreddit = _FakeSubreddit(submissions)
        self.requested = None

    def subreddit(self, name):
        self.requested = name
        return self._subreddit


class _FlakySubreddit:
    """Raises on the first .new() materialisation, then succeeds on retry.

    Models a real lazy PRAW ListingGenerator: the network error surfaces *during
    iteration* (i.e. when _new_submissions does list(...)), so it only re-runs
    correctly if the materialisation lives inside the @retry boundary.
    """

    def __init__(self, submissions, *, fail_times: int):
        self._submissions = submissions
        self._fail_times = fail_times
        self.new_calls = 0

    def new(self, limit=None):
        self.new_calls += 1

        def _gen():
            if self.new_calls <= self._fail_times:
                raise ConnectionError("transient reddit failure")
            yield from self._submissions

        return _gen()


class _FlakyReddit:
    def __init__(self, submissions, *, fail_times: int):
        self._subreddit = _FlakySubreddit(submissions, fail_times=fail_times)

    def subreddit(self, name):
        return self._subreddit


class _FakeDB:
    """Captures upsert_many calls without touching MongoDB."""

    def __init__(self):
        self.calls = []

    # upsert_many returns before touching the db when docs is empty; otherwise it
    # would call db[collection].bulk_write. We stub bulk_write via this mapping.
    def __getitem__(self, collection):
        return _FakeCollection(self, collection)


class _FakeCollection:
    def __init__(self, db, name):
        self._db = db
        self._name = name

    def bulk_write(self, ops, ordered=False):
        self._db.calls.append((self._name, ops))
        return SimpleNamespace(upserted_count=len(ops), modified_count=0)


# --------------------------------------------------------------------------- #
# fetch_wsb_posts
# --------------------------------------------------------------------------- #
def test_fetch_keeps_only_ticker_post_and_defers_sentiment():
    reddit = _FakeReddit([_PLTR_SUB, _JUNK_SUB])
    posts = list(reddit_wsb.fetch_wsb_posts(reddit, limit=50, valid_tickers=VALID_TICKERS))

    # Only the PLTR submission survives; the all-junk one is dropped by the parser.
    assert len(posts) == 1
    post = posts[0]
    assert isinstance(post, WSBPost)
    assert post.post_id == "pltr01"
    assert post.tickers == ["PLTR"]
    assert post.score == 4210
    assert post.num_comments == 318
    assert post.flair == "DD"

    # Sentiment + embedding are left for the downstream Gemini pass.
    assert post.sentiment is None
    assert post.embedding is None

    # created_utc is tz-aware UTC.
    assert post.created_utc.tzinfo is not None
    assert post.created_utc.utcoffset().total_seconds() == 0


def test_fetch_targets_wallstreetbets_and_passes_limit():
    reddit = _FakeReddit([_PLTR_SUB])
    list(reddit_wsb.fetch_wsb_posts(reddit, limit=17, valid_tickers=VALID_TICKERS))
    assert reddit.requested == "wallstreetbets"
    assert reddit._subreddit.last_limit == 17


def test_new_submissions_retries_transient_network_error(monkeypatch):
    # Don't actually sleep through tenacity's exponential backoff.
    monkeypatch.setattr("tenacity.nap.time.sleep", lambda *_: None)

    # Fails on the first .new() materialisation, succeeds on the second. Because
    # _new_submissions does list(...) INSIDE the @retry boundary, the transient
    # error is seen by tenacity and the call is retried to success.
    reddit = _FlakyReddit([_PLTR_SUB], fail_times=1)
    subs = reddit_wsb._new_submissions(reddit, limit=5)

    assert reddit._subreddit.new_calls == 2  # 1 failure + 1 success
    assert [s.id for s in subs] == ["pltr01"]


# --------------------------------------------------------------------------- #
# ingest_wsb
# --------------------------------------------------------------------------- #
def test_ingest_upserts_only_ticker_post():
    reddit = _FakeReddit([_PLTR_SUB, _JUNK_SUB])
    db = _FakeDB()
    written = reddit_wsb.ingest_wsb(db, reddit=reddit, valid_tickers=VALID_TICKERS)

    assert written == 1
    assert len(db.calls) == 1
    collection, ops = db.calls[0]
    assert collection == "wsb_posts"
    assert len(ops) == 1

    # The upsert filter targets the post_id natural key (pymongo UpdateOne stores
    # the filter in ._filter and the update doc in ._doc), upsert is on, and the
    # $set carries the parsed post plus ingested_at while deferring sentiment.
    op = ops[0]
    assert op._filter == {"post_id": "pltr01"}
    assert op._upsert is True
    set_doc = op._doc["$set"]
    assert set_doc["post_id"] == "pltr01"
    assert set_doc["tickers"] == ["PLTR"]
    assert set_doc["ingested_at"] is not None
    assert set_doc["sentiment"] is None
    assert set_doc["embedding"] is None


def test_ingest_empty_when_no_ticker_posts_is_noop():
    reddit = _FakeReddit([_JUNK_SUB])
    db = _FakeDB()
    written = reddit_wsb.ingest_wsb(db, reddit=reddit, valid_tickers=VALID_TICKERS)
    assert written == 0
    assert db.calls == []  # upsert_many short-circuits on empty input


# --------------------------------------------------------------------------- #
# make_reddit credential handling (no creds, no network)
# --------------------------------------------------------------------------- #
def test_make_reddit_raises_clearly_when_creds_missing(monkeypatch):
    for var in ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(RuntimeError) as exc:
        reddit_wsb.make_reddit()
    msg = str(exc.value)
    assert "REDDIT_CLIENT_ID" in msg
    assert "REDDIT_CLIENT_SECRET" in msg
    assert "REDDIT_USER_AGENT" in msg


def test_make_reddit_builds_client_without_network(monkeypatch):
    monkeypatch.setenv("REDDIT_CLIENT_ID", "cid")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "secret")
    monkeypatch.setenv("REDDIT_USER_AGENT", "prism-test")

    captured = {}

    class _StubReddit:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    # Replace the real praw module so no client is constructed against Reddit.
    stub_praw = SimpleNamespace(Reddit=_StubReddit)
    monkeypatch.setitem(__import__("sys").modules, "praw", stub_praw)

    client = reddit_wsb.make_reddit()
    assert isinstance(client, _StubReddit)
    assert captured["client_id"] == "cid"
    assert captured["client_secret"] == "secret"
    assert captured["user_agent"] == "prism-test"
