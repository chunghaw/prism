# DEMO_ARC.md — the 3-minute demo

> What we build toward. Every feature should earn its place in this 180 seconds. If it doesn't show here, it's probably scope creep (see CLAUDE.md Non-Goals).

## The hook (say this first)

> _"Every tool gives you a dashboard. Prism gives you an analyst. Type a ticker — it reads what hedge funds, insiders, and Reddit are each doing, tells you where they disagree, and cites the behavioural-finance research on what that disagreement has meant historically."_

## Demo ticker

**Primary: `PLTR`** — reliably shows the three-way split (institutional buying / insider selling / retail euphoria). **Backups: `NVDA`, `GME`, `TSLA`.** Pick the one whose live data shows the cleanest divergence the morning of recording. Re-run ingestion that morning so numbers are fresh (HANDOFF risk table).

## Beat sheet (180s)

| Time | On screen | Narration / what happens |
| --- | --- | --- |
| 0:00–0:20 | Streamlit landing, single ticker box | The hook (above). Type `PLTR`, hit enter. |
| 0:20–0:35 | "Pulling three perspectives…" + three advocate cards spinning | "Three sub-agents each read **one** independent public feed — no shared bias." |
| 0:35–1:05 | 🏛️ **Institutional** card fills (from `filings_13f`) | "Latest 13F: N funds hold it, +X vs prior quarter, net flow +\$Y **buying**. New entrants: Renaissance, Citadel." |
| 1:05–1:30 | 🏢 **Insider** card fills (from `filings_form4`) | "Form 4, 90 days: 100% **selling**, \$Z — but flagged as 10b5-1 programmatic, not panic." (shows we distinguish discretionary vs scheduled) |
| 1:30–1:50 | 👥 **Retail** card fills (from `wsb_posts`) | "WSB: thousands of mentions, ~92% **bullish**, DD posts up 340% — peak attention." |
| 1:50–2:25 | 🚨 **Divergence panel** lights up | "Here's the signal: institutions buying, insiders selling, retail euphoric. Prism vector-searches **23 historical analogues** in `divergence_library` — median 30-day return **−4.2%**, distribution [−18…+14]." |
| 2:25–2:55 | 📚 **Citations** list | "And it grounds that in research: Barber & Odean (2000) on retail overtrading, Lakonishok & Lee (1998) on insider-sell signals — pulled by Atlas Vector Search over the `papers` corpus." |
| 2:55–3:00 | Architecture splash | "Google ADK + Gemini 3.1 Pro, MongoDB Atlas — five Atlas features, three feeds, one analyst. Open source, MIT." |

## What each beat proves (maps to judging criteria)

| Beat | Judging criterion it scores |
| --- | --- |
| Three independent advocates | **Technological Implementation** (multi-agent ADK), **Quality of Idea** (advocate framing) |
| Divergence + historical analogues | **Potential Impact** (actionable signal), Vector Search |
| Cited research | **Quality of Idea** (the differentiator vs Quiver/Fintel) |
| Clean card UI + divergence panel | **Design** |
| "5/5 Atlas features" splash | **Technological Implementation** (partner-track requirement) |

## Honesty notes (say them — judges reward candor)

- 13F data lags ~45 days — that's regulatory reality, not a bug; we use the most recent quarter.
- yfinance is unofficial; fine for a hackathon, not production.
- We're not a Quiver killer — the novelty is the **conversational, divergence-first, research-cited** combination, open-source.

## Hard requirements visible in the video (submission checklist)

- [ ] Live hosted Cloud Run URL shown in the address bar
- [ ] Real data (no mock path) — numbers come from actual ingestion
- [ ] At least one full ticker → three views → divergence → citation loop end-to-end
- [ ] MongoDB Atlas Vector Search visibly driving analogues + citations
- [ ] ≤ ~3:00 runtime; upload unlisted to YouTube; link in Devpost
