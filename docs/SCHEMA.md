# SCHEMA.md — MongoDB collections & indexes

> The contract. `agent/schemas/` (Pydantic) implements exactly these shapes. Change here first, then the schemas, then any code. Database: `prism` (env `MONGODB_DATABASE`).

## Conventions

- **Money** is stored as integer **USD**. ⚠️ SEC amended Form 13F effective 2024: the `<value>` element is now in **whole dollars**, not thousands — the parser stores it as-is. (Legacy pre-2024 filings reported thousands; multiply those by 1000. We only ingest the most recent quarter, so dollars is the norm. Verified against the Berkshire fixture: 12.7M ALLY shares → value 498,992,850 ≈ $499M, i.e. dollars.)
- **Tickers** are upper-case symbols; CUSIPs are 9-char strings. A `cusip → ticker` map (seeded from the S&P 500 list) lives in `agent/tools/`.
- **Timestamps** are timezone-aware UTC. Time-series collections use a `ts`/`transaction_ts` BSON date.
- **Embeddings** are `float[768]` from `gemini-embedding-001` (`output_dimensionality=768` — storage-friendly for M0's 512 MB). The dim is fixed in `.env` indirectly via the embed model; if you change models, change every vector index `numDimensions`.
- **Natural keys** for idempotent upsert are called out per collection. Re-ingestion must not duplicate.

## Atlas feature coverage (success criterion: all 5 exercised)

| Feature | Where |
| --- | --- |
| **Time-series** | `filings_form4`, `prices` |
| **Vector Search** | `wsb_posts`, `papers`, `divergence_library` |
| **Atlas Search** | full-text over `wsb_posts.title/text` (ticker discovery, DD lookup) |
| **Aggregations** | `normalized_signals` pipeline (3 sources → 1 gold shape) |
| **Change Streams** | watch `filings_form4` for new insider sales → divergence re-alert (Phase 2) |

---

## 1. `filings_13f` — institutional holdings (standard)

One document per fund per quarter.

```jsonc
{
  "_id": ObjectId,
  "fund_cik": "0001067983",          // 10-digit, zero-padded
  "fund_name": "BERKSHIRE HATHAWAY INC",
  "filing_date": ISODate("2026-02-14"),
  "quarter": "2025Q4",                // report period, NOT filing date
  "accession_number": "0000950123-26-001234",   // NATURAL KEY (unique per filing)
  "n_positions": 42,
  "total_value_usd": 312_000_000_000,
  "positions": [
    {
      "cusip": "037833100",
      "issuer": "APPLE INC",
      "ticker": "AAPL",              // resolved via cusip map; null if unresolved
      "title_of_class": "COM",
      "value_usd": 76_410_000_000,   // whole USD (post-2024 13F <value> is already dollars)
      "shares": 300_000_000,
      "share_type": "SH",            // SH | PRN
      "put_call": null               // null | "Put" | "Call"
    }
  ],
  "ingested_at": ISODate
}
```

**Indexes:** unique `{accession_number: 1}`; `{quarter: 1, "positions.ticker": 1}`; `{fund_cik: 1, quarter: 1}`.

---

## 2. `filings_form4` — insider transactions (**time-series**)

One document per transaction. Created with:

```js
db.createCollection("filings_form4", {
  timeseries: { timeField: "transaction_ts", metaField: "meta", granularity: "hours" }
})
```

```jsonc
{
  "transaction_ts": ISODate("2026-05-20T00:00:00Z"),  // timeField
  "meta": {                                            // metaField (indexed dimension)
    "ticker": "PLTR",
    "issuer_cik": "0001321655",
    "issuer_name": "Palantir Technologies Inc",
    "insider_name": "KARP ALEXANDER C",
    "insider_title": "Chief Executive Officer",
    "is_director": false,
    "is_officer": true,
    "is_ten_pct_owner": false
  },
  "accession_number": "0001234567-26-000045",   // for dedupe (kept in a side set, see note)
  "transaction_code": "S",            // P | S | M | F | A | G
  "shares": 50_000,
  "price_per_share": 148.32,
  "value_usd": 7_416_000,
  "acquired_disposed": "D",           // A (acquired) | D (disposed)
  "is_10b5_1": true,                  // pre-scheduled programmatic plan (less informative)
  "ingested_at": ISODate
}
```

**Indexes:** time-series auto-indexes `transaction_ts` + `meta`. Add `{ "meta.ticker": 1, transaction_ts: -1 }` for the per-ticker advocate query. (Time-series collections can't have unique indexes — dedupe accession numbers via a tiny `_form4_seen` standard collection or an upsert guard in the ingestor.)

---

## 3. `wsb_posts` — retail sentiment (standard + embedding)

One document per Reddit post mentioning ≥1 tracked ticker.

```jsonc
{
  "_id": ObjectId,
  "post_id": "1abcd2e",               // NATURAL KEY (Reddit base36 id)
  "created_utc": ISODate,
  "title": "PLTR to the moon 🚀 DD inside",
  "text": "...",                      // truncated to 5000 chars
  "score": 4210,
  "num_comments": 318,
  "flair": "DD",
  "tickers": ["PLTR"],                // ∩ tracked-ticker set
  "sentiment": {                      // filled by a SEPARATE Gemini pass; null until then
    "label": "bullish",              // bullish | bearish | neutral | sarcastic
    "confidence": 0.88,
    "primary_emotion": "euphoria",   // fomo|fear|euphoria|regret|analytical|joking
    "is_dd_post": true,
    "is_loss_porn": false
  },
  "embedding": [/* 768 floats */],    // null until embedded
  "ingested_at": ISODate
}
```

**Indexes:** unique `{post_id: 1}`; `{tickers: 1, created_utc: -1}`.
**Vector index** `wsb_posts_vector_idx` (env `MONGODB_VECTOR_INDEX_WSB`):
```jsonc
{ "fields": [{ "type": "vector", "path": "embedding", "numDimensions": 768, "similarity": "cosine" },
             { "type": "filter", "path": "tickers" }] }
```
**Atlas Search index** over `title` + `text` for ticker discovery / DD lookup.

---

## 4. `prices` — price ground-truth (**time-series**)

```js
db.createCollection("prices", { timeseries: { timeField: "ts", metaField: "ticker", granularity: "hours" } })
```

```jsonc
{
  "ts": ISODate("2026-05-20T00:00:00Z"),
  "ticker": "PLTR",                   // metaField
  "open": 22.10, "high": 23.40, "low": 21.95, "close": 23.02,
  "adj_close": 23.02,
  "volume": 81_300_000,
  "source": "yfinance",
  "ingested_at": ISODate
}
```
**Indexes:** auto `ts`+`ticker`; add `{ ticker: 1, ts: -1 }`.

---

## 5. `papers` — behavioural-finance corpus (standard + embedding)

Static seed (~50–100). Embed once, never re-ingest.

```jsonc
{
  "_id": ObjectId,
  "paper_id": "barber-odean-2000",    // NATURAL KEY (slug)
  "title": "Trading Is Hazardous to Your Wealth",
  "authors": ["Barber, Brad M.", "Odean, Terrance"],
  "year": 2000,
  "venue": "Journal of Finance",
  "abstract": "...",
  "url": "https://...",
  "bias_tags": ["overtrading", "overconfidence"],
  "pattern_explained": "Retail overtrading erodes returns vs buy-and-hold.",
  "embedding": [/* 768 floats over title+abstract */],
  "ingested_at": ISODate
}
```
**Indexes:** unique `{paper_id: 1}`.
**Vector index** `papers_vector_idx` (env `MONGODB_VECTOR_INDEX_PAPERS`): `numDimensions: 768, similarity: cosine`.

---

## 6. `normalized_signals` — gold, per ticker/date (standard, aggregation output)

The unified shape the divergence detector consumes. Produced by an aggregation pipeline (Bronze 13F/Form4/WSB → Silver per-source rollups → Gold).

```jsonc
{
  "_id": ObjectId,
  "ticker": "PLTR",
  "as_of_date": ISODate("2026-05-29"),   // NATURAL KEY with ticker
  "institutional": {
    "n_funds": 387, "n_funds_delta": 46,
    "net_flow_usd": 2_100_000_000,
    "stance": "buying",                  // buying | selling | neutral
    "top_buyers": ["Renaissance Technologies", "Citadel Advisors"],
    "top_sellers": []
  },
  "insider": {
    "n_transactions": 14, "pct_selling": 1.0,
    "net_value_usd": -143_000_000,
    "stance": "selling",
    "discretionary_share": 0.0           // 1 - (10b5-1 share)
  },
  "retail": {
    "n_mentions": 8400, "pct_bullish": 0.92,
    "mention_growth_30d": 3.4, "dd_growth_30d": 3.4,
    "stance": "euphoric"                 // euphoric | bullish | bearish | apathetic
  },
  "price": { "close": 23.02, "ret_30d": null },
  "divergence": { "type": "inst_buy/insider_sell/retail_euphoric", "score": 0.81, "pattern_id": "div-0007" },
  "computed_at": ISODate
}
```
**Indexes:** unique `{ticker: 1, as_of_date: 1}`.

---

## 7. `divergence_library` — catalogued historical patterns (standard + embedding)

≥50 historical instances. The synthesiser vector-searches this for analogues.

```jsonc
{
  "_id": ObjectId,
  "pattern_id": "div-0007",            // NATURAL KEY
  "ticker": "GME",
  "as_of_date": ISODate("2021-01-15"),
  "pattern_type": "inst_buy/insider_sell/retail_euphoric",
  "description": "Institutions accumulating, insiders distributing into a retail mania.",
  "signal_vector": [0.81, -1.0, 0.92, 3.4],   // [inst_score, insider_score, retail_bull, mention_growth]
  "embedding": [/* 768 floats over the description */],
  "outcome": {
    "horizon_days": 30,
    "return_pct": -4.2,
    "distribution": [-18, -9, -4, 2, 14]      // percentile spread of analogues
  },
  "n_prior_instances": 23,
  "related_papers": ["barber-odean-2000", "lakonishok-lee-1998"],
  "ingested_at": ISODate
}
```
**Indexes:** unique `{pattern_id: 1}`; `{ticker: 1, as_of_date: -1}`.
**Vector index** `divergence_vector_idx` (env `MONGODB_VECTOR_INDEX_DIVERGENCE`): `numDimensions: 768, similarity: cosine`.

---

## Index creation order (do this day 1 — warm-up is async)

1. Create the two time-series collections (`filings_form4`, `prices`) explicitly *before* first insert (can't convert after).
2. Create standard collections implicitly on first insert.
3. Create unique/natural-key indexes.
4. Create the 3 Atlas **Vector Search** indexes + 1 Atlas **Search** index via Atlas UI or `mongosh` (they warm up while you build).
