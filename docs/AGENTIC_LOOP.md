# Agentic Build → Review Loop

How Prism gets built: a small fleet of role-specialised agents, an orchestrator, and an adversarial reviewer, wired into a repeatable loop.

## Roles

| Role | Who | Job |
| --- | --- | --- |
| **Orchestrator** | Claude (main session) | Plans, decomposes work, delegates to sub-agents, runs the loop, owns git pushes & external actions. |
| **Builder** | `builder` sub-agent | Implements features end-to-end with tests. Commits locally; never pushes. |
| **Reviewer** | `reviewer-codex` sub-agent + Codex CLI | Adversarially reviews the diff. Returns approved / blocking / nits. |
| **Specialists** | `data-ingestor`, `adk-agent-engineer`, `mongodb-specialist` | Deep expertise for the data layer, the ADK reasoning layer, and MongoDB Atlas. |

Claude is **orchestrator + implementation (builder)**; **Codex is the reviewer**. The split keeps the author and the critic independent.

## The loop

```
            ┌──────────────────────────────────────────────┐
            │  Orchestrator (Claude) picks the next feature │
            └───────────────────────┬──────────────────────┘
                                     ▼
                         ┌───────────────────────┐
                         │  builder: code + tests │  ── ruff + pytest, local commit
                         └───────────┬───────────┘
                                     ▼
                    ┌────────────────────────────────┐
                    │ reviewer-codex: adversarial pass │  ── scripts/codex-review.ps1
                    └───────────────┬─────────────────┘
                       approved?    │
                  ┌── yes ──────────┴───────── no ──┐
                  ▼                                 ▼
        orchestrator pushes /         builder fixes blocking items,
        opens PR; next feature        loop back to review  (max N rounds)
```

Run it as a workflow:

```
Workflow({ name: "feature-loop", args: { feature: "Ingest one Berkshire 13F into filings_13f", maxRounds: 3 } })
```

or simply `/workflows` and pick **feature-loop**. The script lives at `.claude/workflows/feature-loop.js`.

## Codex integration

**Primary: local Codex CLI.** Install once:

```powershell
npm install -g @openai/codex
codex login
```

`scripts/codex-review.ps1` feeds the git diff to `codex exec` and returns a JSON verdict. If Codex isn't installed, the script prints `CODEX_NOT_INSTALLED` and the diff, and the `reviewer-codex` agent reviews it directly so the loop never blocks.

**Fallback: GitHub PR review (cloud).** Install the Codex GitHub app on `chunghaw/prism`; the orchestrator pushes a feature branch + opens a PR, Codex reviews the PR, and the orchestrator reads the comments. Slower, but zero per-review token cost on your side and a durable on-GitHub trail. The loop is written to work with either — only the review step changes.

> Adjust the `codex exec` flags in `scripts/codex-review.ps1` to match your installed Codex CLI version if needed.

## Autonomy

`.claude/settings.json` allowlists the routine dev loop (Python, pytest, ruff, local git, MongoDB MCP reads, Playwright) so sub-agents run without prompting. **Outward-facing actions stay gated**: `git push`, PR creation, and any Cloud Run / gcloud deploy are done explicitly by the orchestrator, not silently by sub-agents.

## Frontend iteration

UI is designed at https://claude.ai/design, dropped into `ui/`, and iterated against the running Streamlit app using the **Playwright MCP** (navigate → snapshot → screenshot → adjust). See the `verify` / `run` skills for driving the app.
