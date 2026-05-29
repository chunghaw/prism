"""Tests for the pure WSB parser (agent/tools/parse_wsb.py).

Expected values are read from the committed fixture, not guessed.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from agent.schemas import WSBPost
from agent.tools.parse_wsb import extract_tickers, submission_to_post

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "wsb" / "sample_submission.json"

# Tracked universe used across tests. Includes PLTR (which the fixture mentions)
# and other valid symbols that happen to collide with English words, so the test
# proves we keep real tickers and drop pure junk — not just that we drop words.
VALID_TICKERS = {"PLTR", "AAPL", "GME", "TSLA", "AMD"}


@pytest.fixture
def submission() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_fixture_marked_synthetic(submission: dict) -> None:
    assert "_note" in submission
    assert "SYNTHETIC" in submission["_note"].upper()


def test_extract_tickers_drops_junk_keeps_pltr(submission: dict) -> None:
    text = f"{submission['title']} {submission['selftext']}"
    # Sanity-check the junk tokens are actually present in the fixture text.
    for junk in ("THE", "CEO", "USA"):
        assert junk in text
    tickers = extract_tickers(text, VALID_TICKERS)
    assert tickers == ["PLTR"]
    for junk in ("THE", "CEO", "USA"):
        assert junk not in tickers


def test_extract_tickers_dedupes_preserving_order() -> None:
    text = "GME and PLTR, then PLTR again, then GME, plus $AAPL"
    assert extract_tickers(text, VALID_TICKERS) == ["GME", "PLTR", "AAPL"]


def test_extract_tickers_empty_text() -> None:
    assert extract_tickers("", VALID_TICKERS) == []


def test_submission_to_post(submission: dict) -> None:
    post = submission_to_post(submission, VALID_TICKERS)
    assert isinstance(post, WSBPost)

    # Values asserted against the fixture, not hardcoded guesses.
    assert post.tickers == ["PLTR"]
    assert post.post_id == submission["id"]
    assert post.title == submission["title"]
    assert post.text == submission["selftext"]
    assert post.score == submission["score"]
    assert post.num_comments == submission["num_comments"]
    assert post.flair == submission["link_flair_text"]

    # Deferred to the Gemini pass.
    assert post.sentiment is None
    assert post.embedding is None

    # created_utc is tz-aware UTC and matches the fixture epoch.
    assert post.created_utc.tzinfo is not None
    assert post.created_utc.utcoffset() == timezone.utc.utcoffset(None)
    expected = datetime.fromtimestamp(submission["created_utc"], tz=timezone.utc)
    assert post.created_utc == expected


def test_submission_to_post_no_tickers_returns_none() -> None:
    sub = {
        "id": "zzz999",
        "created_utc": 1748563200,
        "title": "THE best CEO play in the USA, no real tickers here",
        "selftext": "Just vibes and YOLO, NFA.",
        "score": 5,
        "num_comments": 1,
        "link_flair_text": "Discussion",
    }
    assert submission_to_post(sub, VALID_TICKERS) is None


def test_submission_to_post_tolerates_missing_optional_fields() -> None:
    sub = {
        "id": "min001",
        "created_utc": 1748563200,
        "title": "$PLTR",
    }
    post = submission_to_post(sub, VALID_TICKERS)
    assert isinstance(post, WSBPost)
    assert post.tickers == ["PLTR"]
    assert post.text == ""
    assert post.score == 0
    assert post.num_comments == 0
    assert post.flair is None
