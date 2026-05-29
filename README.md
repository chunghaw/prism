# Prism

> Three lenses on every ticker — institutional, insider, retail.

Prism is an AI agent that reads three independent public US market data feeds — **SEC 13F filings, SEC Form 4 insider transactions, and Reddit r/WallStreetBets sentiment** — and reasons across them to surface what hedge funds, corporate insiders, and retail traders are _each_ doing on any ticker. When they disagree, that's the signal.

Built for the **Google Cloud Rapid Agent Hackathon** — submission deadline **2026-06-11 14:00 PDT**.

---

## Why this matters

Every existing tool gives you a dashboard. Prism gives you an analyst.

- **WhaleWisdom / Fintel** show you raw 13F numbers — but no narrative
- **OpenInsider** shows insider trades — but no context
- **SwaggyStocks / ApeWisdom** show WSB sentiment — but no institutional comparison
- **Quiver Quantitative** aggregates all three — but in siloed dashboards, not a conversation

Prism layers **agentic reasoning + behavioural finance research + historical pattern matching** on top of these data sources. Type a ticker. Get three perspectives, the divergence, the historical analogues, and the cited research about what the divergence has historically meant.

---

## What it does

```
User:  "Show me what's happening with PLTR."

Agent: Pulling three perspectives on PLTR (Palantir)...

       🏛️ INSTITUTIONAL (latest 13F):
       • 387 funds hold PLTR, +46 vs prior quarter
       • Net flow +$2.1B (BUYING)
       • New entries: Renaissance, Citadel

       🏢 INSIDERS (Form 4, 90 days):
       • 14 transactions, 100% SELLING ($143M total)
       • Pattern: programmatic 10b5-1 plans, not panic

       👥 RETAIL (WSB, 30 days):
       • 8,400 mentions, 92% bullish
       • DD posts +340% MoM — peak attention

       🚨 DIVERGENCE FLAG:
       Three-way split: institutional buying / insider selling / retail euphoric.
       Historical pattern (23 prior instances):
         median 30-day return: −4.2%
         distribution: [−18%, −9%, −4%, +2%, +14%]

       Behavioural lens (Barber & Odean, 2000; Lakonishok & Lee, 1998):
       "Insider selling into retail euphoria has historically preceded
        mean reversion. Institutional buying may reflect catalyst pricing,
        not conviction."
```

---

## Stack

| Layer           | Choice                                                                 |
| --------------- | ---------------------------------------------------------------------- |
| Agent framework | [Google ADK](https://google.github.io/adk-docs/) (Python 3.11+)        |
| AI model        | Gemini 2.5 Pro via Vertex AI                                           |
| Database        | [MongoDB Atlas M0](https://www.mongodb.com/atlas) (free tier)          |
| MCP integration | [MongoDB MCP Server](https://github.com/mongodb-js/mongodb-mcp-server) |
| Frontend        | Streamlit                                                              |
| Deployment      | Google Cloud Run                                                       |
| License         | MIT                                                                    |

---

## Quick start

Prereqs: Python 3.11+, Node 20+, a MongoDB Atlas account, a GCP project with Vertex AI enabled, a Reddit app for PRAW.

```bash
git clone <your-repo-url>
cd prism
python -m venv .venv
.venv\Scripts\activate                  # Windows PowerShell
pip install -r requirements.txt
cp .env.example .env                    # fill in credentials
python -m agent.ingest.bootstrap        # seed historical data (15 min)
adk web                                 # start ADK local dev server
# in another terminal:
streamlit run ui/app.py
```

See `docs/DAY1_CHECKLIST.md` for the precise first-day setup.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                          USER (Streamlit)                       │
└───────────────────────────────┬─────────────────────────────────┘
                                │ "what's happening with PLTR?"
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ADK Orchestrator Agent                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ Institutional│  │   Insider    │  │      Retail          │  │
│  │   Advocate   │  │   Advocate   │  │     Advocate         │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘  │
│         │                 │                     │              │
│         ▼                 ▼                     ▼              │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              Divergence Synthesiser                       │  │
│  │  • Pattern matching via Atlas Vector Search              │  │
│  │  • Behavioural research citation                          │  │
│  └────────────────────────┬─────────────────────────────────┘  │
└───────────────────────────┼─────────────────────────────────────┘
                            │ MongoDB MCP
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                       MongoDB Atlas                              │
│  filings_13f  │  filings_form4  │  wsb_posts  │  papers          │
│  prices (TS)  │  normalized_signals (gold)    │  divergence_lib  │
└─────────────────────────────────────────────────────────────────┘
                            ▲
              ┌─────────────┼─────────────┐
              │             │             │
        ┌─────┴────┐  ┌─────┴────┐  ┌─────┴────┐
        │ SEC EDGAR│  │SEC EDGAR │  │ Reddit   │
        │  13F XML │  │ Form 4   │  │ PRAW API │
        │          │  │   XML    │  │          │
        └──────────┘  └──────────┘  └──────────┘
```

---

## Status

🚧 Active development. See `docs/HANDOFF.md` for the full project plan.

---

## License

MIT — see `LICENSE`.
