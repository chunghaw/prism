# CLAUDE.md — Prism

> Loaded by Claude Code at the start of every session in this repo.
> Keep it **short, opinionated, and load-bearing**. Move detail into `docs/`.

## Project

Prism is an AI agent that ingests three independent public US market data feeds (SEC 13F, SEC Form 4, Reddit WSB) and reasons across them to surface institutional vs insider vs retail divergence on any US ticker — with cited behavioural-finance research.

Built for the **Google Cloud Rapid Agent Hackathon** — submission deadline **2026-06-11 14:00 PDT**.

## North-star UX

User asks about any US ticker. Three "advocate" sub-agents (institutional / insider / retail) each report their view. A synthesiser agent finds the divergence pattern, looks up historical analogues via MongoDB Atlas Vector Search, and cites relevant behavioural finance research.

## Stack

| Layer               | Technology                                                     |
| ------------------- | -------------------------------------------------------------- |
| **Agent framework** | Google ADK (`pip install google-adk`)                          |
| **Runtime**         | Python 3.11+                                                   |
| **AI model**        | Gemini 2.5 Pro via Vertex AI (structured output for advocates) |
| **Database**        | MongoDB Atlas M0 (free tier)                                   |
| **MCP integration** | MongoDB MCP Server (`npx mongodb-mcp-server@latest`)           |
| **Frontend**        | Streamlit (simple, agent-first — UI is not the differentiator) |
| **Deployment**      | Google Cloud Run                                               |
| **Hosting**         | Public GitHub repo, MIT license                                |

## Critical Rules

1. **Only Google Cloud AI in the agent runtime.** No Claude, OpenAI, or non-Google models at runtime. Using Claude Code to _write_ the code is fine — the restriction is on what the agent _runs_ on.
2. **This is a new project.** Do not port code from any prior project. Concepts and patterns OK; verbatim code is **not**.
3. **Public repo, MIT license.** No proprietary data committed (no real personal broker data, no production credentials, no `.env`).
4. **Demo-ready on `main`.** Every PR should leave `main` in a state you could show a judge.
5. **MongoDB is the only partner MCP integration.** Don't add others — focus.
6. **Public data only.** All data sources must be free, free-to-scrape, or freely API-accessible.

## Repo Conventions

```
agent/
  main.py             # ADK agent entry point + orchestrator definition
  advocates/          # one file per archetype agent
    institutional.py  # reads filings_13f, narrates institutional view
    insider.py        # reads filings_form4, narrates insider view
    retail.py         # reads wsb_posts, narrates retail view
  tools/              # MCP-callable tools
    edgar.py          # SEC EDGAR ingest helpers
    reddit.py         # PRAW wrapper
    yfinance_tool.py  # price data
    divergence.py     # pattern matching via vector search
    research.py       # behavioural finance paper lookup
  prompts/            # system prompts as plain text files
  schemas/            # Pydantic models — one per data source + the unified shape
  ingest/             # batch ingestion jobs
    bootstrap.py      # seed historical data on day 1
    daily.py          # daily refresh job
ui/
  app.py              # Streamlit frontend
tests/                # pytest
docs/
  HANDOFF.md          # full strategy doc
  DAY1_CHECKLIST.md   # concrete first-day tasks
  DATA_SOURCES.md     # URLs + sample queries + rate limits per source
  SCHEMA.md           # MongoDB collection schemas + index configs
  DEMO_ARC.md         # the 3-minute demo script
```

- **Pure core, thin edges.** Pure Python modules (parsers, scorers, schema mappers) belong in `agent/tools/` with unit tests. Anything that hits MongoDB or Vertex AI lives in adapters that wrap the pure cores.
- **Prompts in `agent/prompts/`** as plain `.md` or `.txt` files. Code imports them as strings — never inline.
- **One source of truth per source** — only one place that knows how to parse 13F XML, only one place that knows the WSB sentiment heuristic.

## How to Work in This Repo

1. **Read `docs/HANDOFF.md` end-to-end first.** It's the source of truth for strategy and architecture.
2. **Read `docs/DAY1_CHECKLIST.md`** if you're starting fresh.
3. **Build the data layer before the agent.** No point writing the orchestrator if the data isn't queryable. Order:
   - Week 1: Ingest 1 quarter 13F (top 200 funds) + 30d Form 4 + 30d WSB. Get them into MongoDB with proper indexes.
   - Week 2: Build the `normalized_signals` aggregation pipeline. Implement divergence-pattern vector search. Ingest behavioural-finance paper corpus.
   - Week 3: ADK advocate agents + synthesiser + Streamlit UI.
4. **Test queries before writing tools.** For every MongoDB query the agent will run, hand-run it in MongoDB Compass first. If the query is slow, the agent will be slow.
5. **Every commit must be authored organically** — see Provenance Discipline.

## Provenance Discipline

You will be tempted to study existing tools (Quiver Quantitative, WhaleWisdom, Fintel, TradingAgents framework, IMS Studio extraction patterns) for reference. Hard rules:

- ✅ Read their docs / open-source code to understand _patterns_
- ✅ Cite them in your design docs as inspiration
- ❌ Do **not** copy code, prompts, or schema field names verbatim
- ❌ Do **not** mirror anyone else's directory structure

**Litmus test:** if a file or function looks structurally identical to an existing project's, rewrite it from the concept.

## Success Criteria

- ✅ Hosted Streamlit UI on Cloud Run (live demo URL)
- ✅ Public GitHub repo with MIT license
- ✅ 3-minute demo video showing: ticker query → three views → divergence detection → research citation
- ✅ Devpost submission complete by 2026-06-11 14:00 PDT
- ✅ MongoDB Atlas Vector Search index live in production
- ✅ All 5/5 MongoDB Atlas features genuinely exercised (time-series, vector search, atlas search, aggregations, change streams)

## Non-Goals (don't scope-creep)

- Real-money trading execution
- Personal broker CSV ingestion (this is a _bonus_ feature, NOT week-1 scope)
- Backtesting framework
- Options or derivatives data
- Non-US markets
- Mobile UI
- Auth / multi-tenancy / billing
- More than 3 data sources

## Working with the User

The user (Edmund) is a pragmatic data engineer with deep Fabric / dbt / ACHA-migration context. He values:

- Working software over polished prose
- Local-first development (test before deploy)
- Honest reporting (if a data source breaks, say so — don't fabricate "success")
- No hardcoded / mock data in the demo path (all results must come from real ingestion)
- Saturation-realistic positioning (don't oversell uniqueness — be honest about competitors)

When in doubt, **build the smallest thing that demos a real end-to-end loop, then iterate**. Better to have a 3-step flow that all works than a 6-step flow with broken steps.

## Where to Get Help

- **MongoDB Atlas Vector Search docs:** https://www.mongodb.com/docs/atlas/atlas-vector-search/
- **Google ADK docs:** https://google.github.io/adk-docs/
- **MongoDB MCP Server:** https://github.com/mongodb-js/mongodb-mcp-server
- **SEC EDGAR API:** https://www.sec.gov/edgar/sec-api-documentation
- **PRAW (Reddit API):** https://praw.readthedocs.io/
