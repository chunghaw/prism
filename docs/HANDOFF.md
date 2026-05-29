# Prism — Project Handoff

> Read this end-to-end before writing any code.
> Then read `DAY1_CHECKLIST.md`, `DATA_SOURCES.md`, and `SCHEMA.md`.

---

## 1. What we're building

**Prism** is an AI agent that, given any US stock ticker, reads three independent public market data feeds (SEC 13F, SEC Form 4, Reddit r/WallStreetBets), reasons across them via three "advocate" sub-agents, and surfaces divergence patterns between institutional, insider, and retail behaviour — with cited behavioural-finance research.

### One-sentence pitch

> _"Three lenses on every ticker — institutional, insider, retail. When they disagree, that's the signal."_

### The user

A retail or curious investor who wants to understand what hedge funds, corporate insiders, and retail traders are _each_ doing on a ticker — without checking three dashboards or learning what a 13F filing is.

---

## 2. Why this project

### Hackathon context

- **Event:** Google Cloud Rapid Agent Hackathon
- **Deadline:** 2026-06-11 14:00 PDT (~15 days from project start)
- **Track:** MongoDB partner track (required MCP integration: MongoDB MCP Server)
- **Submission requires:** public repo + MIT license + hosted URL + 3-min demo video + Devpost form
- **Prize:** $5K / $3K / $2K per partner track

### The honest "why"

This is a **learning-first** project, not a "win the prize" project. The expected-value math on a $5K prize across ~7,400 entrants is unfavourable. The real returns are:

1. **MongoDB Atlas Vector Search + Time-Series + Aggregations + Atlas Search + Change Streams** — all five exercised in one project. Hands-on coverage of capabilities that would take months to absorb via tutorials.
2. **Google ADK + MCP** — first hands-on with the agent framework currently winning enterprise mindshare.
3. **Multi-source heterogeneous ETL** — three completely different data formats (XML, XML, JSON). Real schema-reconciliation practice.
4. **Portfolio piece** — interview-worthy: "I built an agent that reasons across three market data feeds with cited research."
5. **Personal utility** — the user actually trades US stocks; Prism is useful day-to-day after the hackathon.

### Competitive landscape — honest acknowledgment

The space has real competitors. We are NOT positioning Prism as novel infrastructure.

| Competitor                         | Overlap with Prism                                                                |
| ---------------------------------- | --------------------------------------------------------------------------------- |
| **Quiver Quantitative**            | Closest. Tracks 13F + insider + Reddit. **Dashboard-only**, no agentic reasoning. |
| **Fintel**                         | 13F + insider + short + options. Tables-only.                                     |
| **WhaleWisdom**                    | Deep 13F. No retail / no narrative.                                               |
| **SwaggyStocks / ApeWisdom**       | WSB sentiment only.                                                               |
| **OpenInsider**                    | Insider only.                                                                     |
| **TradingAgents (UCLA+MIT, 2026)** | Multi-agent debate framework. Open-source. Academic.                              |

**Prism's actual differentiation:**

1. **Conversational interface over the three feeds** (vs separate dashboards)
2. **Automatic divergence-pattern detection** (vs manual eyeballing)
3. **Historical pattern matching via vector search** (vs no temporal context)
4. **Cited behavioural-finance research** (vs raw numbers)
5. **Three "advocate" sub-agents** (vs single aggregated view)
6. **Open source + MIT** (vs closed commercial)

That combination is genuinely not done by any single existing tool. But it's also not a Quiver killer — it's a learning artefact that happens to be useful.

---

## 3. Architecture

### High-level flow

```
User query ("PLTR")
    │
    ▼
ADK Orchestrator Agent
    │
    ├─► institutional_advocate ───► MongoDB MCP: filings_13f, prices ────► Narrative
    ├─► insider_advocate ─────────► MongoDB MCP: filings_form4, prices ──► Narrative
    └─► retail_advocate ──────────► MongoDB MCP: wsb_posts, prices ──────► Narrative
                                                                                │
                                          (all three narratives ▼)              │
                                                                                ▼
                                        Divergence Synthesiser ─► MongoDB MCP: divergence_library
                                                                                │
                                                              (similar past patterns ▼)
                                                                                ▼
                                        Research Citation ─► MongoDB MCP: papers (vector)
                                                                                │
                                                                                ▼
                                                                Final response to user
```

### MongoDB collections

See `SCHEMA.md` for full specifications. Quick summary:

| Collection           | Type            | Purpose                                                     |
| -------------------- | --------------- | ----------------------------------------------------------- |
| `filings_13f`        | Standard        | Hedge fund 13F filings (quarterly)                          |
| `filings_form4`      | **Time-series** | Insider transactions (event stream)                         |
| `wsb_posts`          | Standard        | Reddit r/WallStreetBets posts (with embeddings)             |
| `prices`             | **Time-series** | Stock prices from yfinance                                  |
| `papers`             | Standard        | Behavioural-finance papers (with embeddings)                |
| `normalized_signals` | Standard        | Bronze → Silver → Gold unified shape per ticker / date      |
| `divergence_library` | Standard        | Catalogued historical divergence patterns (with embeddings) |

### Three "advocate" agents

Each advocate is an ADK sub-agent with:

- Its own system prompt (in `agent/prompts/`)
- Access to ONE data source via MongoDB MCP
- A structured output schema (Pydantic) for its narrative

The orchestrator runs all three in parallel, then passes their structured outputs to the synthesiser.

**Important:** each advocate ARGUES for its perspective ("here's what my data says"). The orchestrator's job is to synthesise — not to suppress disagreement, but to surface it explicitly.

---

## 4. Data sources

See `DATA_SOURCES.md` for URLs, sample queries, rate limits, and code snippets. Summary:

### a) SEC EDGAR 13F filings

- **What:** Quarterly disclosures of holdings by institutional investment managers with >$100M AUM
- **Where:** `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=13F-HR`
- **Format:** XML (gnarly, position layout varies by filer)
- **Update cadence:** Reported 45 days after quarter end
- **Rate limit:** 10 requests/sec (SEC policy)
- **Auth:** None — but requires `User-Agent` header identifying you

### b) SEC EDGAR Form 4 filings

- **What:** Real-time disclosures of insider transactions (officers, directors, 10%+ shareholders)
- **Where:** `https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4`
- **Format:** XML
- **Update cadence:** Within 2 business days of transaction; ~1,000 filings/day
- **Rate limit:** 10 requests/sec
- **Auth:** None — `User-Agent` header required

### c) Reddit r/WallStreetBets

- **What:** Retail trader discussion, ticker mentions, sentiment
- **Where:** `https://www.reddit.com/r/wallstreetbets/` via [PRAW](https://praw.readthedocs.io/)
- **Format:** JSON
- **Update cadence:** Real-time
- **Rate limit:** PRAW handles (60 req/min for OAuth)
- **Auth:** Reddit app credentials

### d) yfinance (price ground-truth)

- **What:** Open/close/volume for any US ticker
- **Library:** [`yfinance`](https://github.com/ranaroussi/yfinance)
- **Cost:** Free, no API key
- **Note:** Unofficial; not for production-grade reliability, but excellent for hackathon

### e) Behavioural finance papers

- **Where:** SSRN behavioural finance corpus + PubMed psychology papers
- **Scope:** Top 500 most-cited papers on cognitive biases in trading
- **Storage:** Static seeded corpus in `papers` collection — no live ingestion needed
- **Examples to seed:**
  - Barber & Odean (2000), _Trading is Hazardous to Your Wealth_
  - Shefrin & Statman (1985), _The Disposition Effect_
  - Lakonishok & Lee (1998), _Are Insider Trades Informative?_
  - Kumar (2009), _Who Gambles in the Stock Market?_
  - Pedersen (2024), _Game on: Social Networks and Markets_ (GME case study)

---

## 5. Scope — 15-day execution plan

Each milestone should leave `main` deployable.

### Week 1 (Days 1–5): Foundation + Ingestion

| Day | Goal                                                                            |
| --- | ------------------------------------------------------------------------------- |
| 1   | Repo init, MongoDB Atlas cluster (M0), GCP project, Reddit app, dependencies    |
| 2   | Ingest 1 quarter of 13F for top 200 funds → `filings_13f` collection            |
| 3   | Ingest 30 days of Form 4 (S&P 500 tickers only) → `filings_form4` (time-series) |
| 4   | Ingest 30 days of WSB posts mentioning S&P 500 tickers → `wsb_posts`            |
| 5   | Ingest yfinance prices for S&P 500, last 5 years → `prices` (time-series)       |

**End of week 1:** All four data sources in MongoDB. Indexes created. Spot-check with MongoDB Compass that data is queryable.

### Week 2 (Days 6–10): Reasoning Layer

| Day | Goal                                                                                                   |
| --- | ------------------------------------------------------------------------------------------------------ |
| 6   | Build `normalized_signals` aggregation pipeline (3 sources → 1 per-ticker shape)                       |
| 7   | Compute embeddings for `wsb_posts` + `papers` + (later) `divergence_library`                           |
| 8   | Create Atlas Vector Search indexes; verify queries return reasonable results                           |
| 9   | Seed `papers` collection with 50–100 behavioural finance abstracts                                     |
| 10  | Build divergence-pattern detection logic + populate `divergence_library` (50–100 historical instances) |

**End of week 2:** You can run a MongoDB query that returns the full Prism response for any S&P 500 ticker. Not via an agent yet — just queries.

### Week 3 (Days 11–15): Agent + Demo

| Day | Goal                                                                          |
| --- | ----------------------------------------------------------------------------- |
| 11  | ADK agent skeleton + MongoDB MCP wiring + first advocate (`institutional`)    |
| 12  | Other two advocates (`insider`, `retail`) + synthesiser                       |
| 13  | Streamlit UI (text input + advocate-cards + divergence panel + citation list) |
| 14  | Deploy to Cloud Run; smoke-test with 5 tickers; demo video v1                 |
| 15  | Polish video, finalise README, submit Devpost                                 |

### Cut-list (drop these if behind schedule)

In order of "drop first":

1. Change Streams real-time alerts (Phase 2)
2. Personal broker CSV upload (Phase 3 — explicitly out of MVP)
3. Sectoral / cross-ticker queries
4. Atlas Search facets (Vector Search alone is enough for MVP)
5. The third advocate (retail) — institutional + insider is still a story

**Do NOT cut:**

- One advocate end-to-end (proves the pattern)
- Divergence detection (it's the hook)
- At least 3 cited research papers (it's the differentiator)
- Cloud Run hosted URL (it's a submission requirement)

---

## 6. Critical risks and mitigations

| Risk                                                      | Likelihood | Mitigation                                                                                     |
| --------------------------------------------------------- | :--------: | ---------------------------------------------------------------------------------------------- |
| SEC EDGAR XML parsing is inconsistent across filers       |    High    | Use the `sec-edgar-downloader` Python lib for the file dance; parse with `pydantic-xml`        |
| WSB sentiment scoring on memes / sarcasm is hard          |    High    | Don't use classic NLP — let Gemini score sentiment per post (with `generateObject` schema)     |
| Reddit API quotas pinch during ingestion                  |   Medium   | Use [Pushshift archive dumps](https://github.com/Watchful1/PushshiftDumps) for bulk historical |
| MongoDB Atlas Vector Search index creation takes time     |    Low     | Create indexes day 1 — they're idempotent and warm up while you build other parts              |
| 13F filings lag 45 days (no real-time institutional data) |  Certain   | This is regulatory reality — acknowledge in demo. Use the most recent quarter only.            |
| Multi-agent ADK orchestration has steep learning curve    |   Medium   | Start with ONE advocate end-to-end before adding the other two. Get the pattern right first.   |
| Gemini API rate limits during demo                        |    Low     | Cache demo responses; use Vertex AI quota requests if needed                                   |
| Demo dataset feels stale by submission day                |    Low     | Re-run ingestion the morning of submission                                                     |

---

## 7. What "done" looks like (definition of submission-ready)

- [ ] Public GitHub repo, MIT license, README with screenshots
- [ ] Hosted URL on Cloud Run (`https://prism-<hash>-uc.a.run.app`)
- [ ] Streamlit UI works for any S&P 500 ticker
- [ ] All five MongoDB Atlas features genuinely exercised (proven in code)
- [ ] Three advocate sub-agents, each callable independently
- [ ] At least 50 historical divergence patterns in `divergence_library`
- [ ] At least 50 papers in `papers` collection
- [ ] 3-minute demo video uploaded to YouTube (unlisted is fine)
- [ ] Devpost submission complete with all required fields
- [ ] `docs/` is up to date with what you actually built

---

## 8. Working principles

1. **Build the smallest end-to-end loop first.** Don't write all three advocates before testing one. Don't seed all 500 papers before testing one. Don't deploy before testing locally.
2. **MongoDB queries before agent tools.** Every tool the agent will call should be a query you've already validated in Compass.
3. **Pydantic schemas before prompts.** If the structured output isn't well-defined, the prompt won't help.
4. **One data source per ingest module.** Don't share state across sources at the ingest layer — they're independent.
5. **Test with messy data, not curated data.** Real 13F filings have formatting quirks. Bake that into your tests from day 1.

---

## 9. Onward

When you're ready:

1. Read `DAY1_CHECKLIST.md` and execute it
2. Read `DATA_SOURCES.md` before touching any ingestion code
3. Read `SCHEMA.md` before creating any collections
4. Check `DEMO_ARC.md` to know what you're building toward

Build small, ship daily, demo every Friday. Good luck.
