# Day 1 Checklist — Prism

> Goal: by the end of day 1, you have a green-field repo with **all credentials working** and **one record in MongoDB Atlas from a real ingestion script**. No agent, no UI yet — just plumbing.

Estimated time: **4–6 hours**.

---

## ☐ 1. Create the public repo (15 min)

```powershell
gh repo create prism --public --license=mit `
  --description "AI agent for multi-perspective US market analysis. Google Cloud Rapid Agent Hackathon."

cd ~\projects
gh repo clone <your-handle>/prism
cd prism
```

Copy this entire `prism-starter` folder into the new repo:

```powershell
xcopy "<path>\unstructured-ai-studio\docs\prism-starter\*" . /E /I /H
```

Commit the scaffold:

```powershell
git add .
git commit -m "Initial scaffold for Prism — Google Cloud Rapid Agent Hackathon"
git push
```

---

## ☐ 2. Verify the name is free (10 min)

Before going further, run the validation gauntlet on **"Prism"**:

| Check                | Command / URL                                                                     |
| -------------------- | --------------------------------------------------------------------------------- |
| Domain availability  | https://www.namecheap.com → search `prism.ai`, `prism-trading.dev`, `getprism.io` |
| PyPI collision       | https://pypi.org/project/prism/                                                   |
| GitHub org collision | https://github.com/prism                                                          |
| Google search        | "Prism" AI trading agent → check first page                                       |

**If Prism is too generic / too contested**, fall back to one of:

- **Triad** — three perspectives, easy logo
- **Caucus** — gathering of views
- **Refraction** — splits one ticker into a spectrum of views
- **Anvil** — where decisions get forged
- **Spectra** — multi-perspective lens

Pick whichever feels right and do a 5-minute find-replace across the starter folder.

---

## ☐ 3. Set up MongoDB Atlas (30 min)

1. Create account at https://www.mongodb.com/cloud/atlas/register (free)
2. Create a new project: **"prism"**
3. Build a database → **M0 free tier** → AWS / us-east-1 (or closest)
4. Database access:
   - Add user `prism_app` with auto-generated strong password
   - Grant "Read and write to any database" (we'll tighten later)
5. Network access:
   - For dev: add your IP
   - For Cloud Run later: add `0.0.0.0/0` (or use VPC peering — overkill for hackathon)
6. Connect → Drivers → Python → copy the connection string
7. **Save to `.env`** as `MONGODB_URI`

Sanity check:

```powershell
pip install pymongo
python -c "from pymongo import MongoClient; import os; c = MongoClient(os.environ['MONGODB_URI']); print(c.server_info()['version'])"
```

Should print the Atlas server version (`7.0.x` or newer).

---

## ☐ 4. Set up Google Cloud + Vertex AI (45 min)

1. Create / select a GCP project at https://console.cloud.google.com
2. Enable APIs:
   - Vertex AI API
   - Cloud Run API
   - Cloud Build API (for deploy later)
   - Artifact Registry API
3. Request **$100 hackathon GCP credits** if you haven't (form on the hackathon page; deadline was June 4)
4. Service account:
   - IAM → Service Accounts → Create
   - Name: `prism-agent`
   - Roles: `Vertex AI User`, `Storage Object Viewer`
   - Create key (JSON) → save locally as `gcp-key.json` (gitignored)
5. **Save to `.env`** as `GOOGLE_APPLICATION_CREDENTIALS=./gcp-key.json` and `GOOGLE_CLOUD_PROJECT=<your-project-id>`

Sanity check:

```powershell
pip install google-cloud-aiplatform
python -c "from google.cloud import aiplatform; aiplatform.init(); print('OK')"
```

Then test Gemini:

```powershell
pip install google-genai
python -c "from google import genai; client = genai.Client(vertexai=True, project='<your-project-id>', location='us-central1'); print(client.models.generate_content(model='gemini-2.5-pro', contents='Say hi in one word.').text)"
```

Should print something like `Hi.`

---

## ☐ 5. Reddit app for PRAW (10 min)

1. Go to https://www.reddit.com/prefs/apps/
2. Click "create another app..." at the bottom
3. Type: **script**
4. Redirect URI: `http://localhost:8080` (placeholder — script type doesn't need it)
5. Save the **client ID** (under the app name) and **secret**
6. **Save to `.env`** as `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT=prism/0.1 by u/<your_handle>`

Sanity check:

```powershell
pip install praw
python -c "import praw, os; r = praw.Reddit(client_id=os.environ['REDDIT_CLIENT_ID'], client_secret=os.environ['REDDIT_CLIENT_SECRET'], user_agent=os.environ['REDDIT_USER_AGENT']); print(next(r.subreddit('wallstreetbets').hot(limit=1)).title)"
```

Should print a current WSB post title.

---

## ☐ 6. SEC EDGAR User-Agent (5 min)

SEC requires a `User-Agent` header identifying the requester. They will block IPs that don't comply.

Format: `Your Name your@email.com`

**Save to `.env`** as `SEC_USER_AGENT="Edmund Tan etan@imsystems.com.au"` (use your real email — SEC monitors).

Sanity check:

```powershell
pip install requests
python -c "import requests, os; r = requests.get('https://data.sec.gov/submissions/CIK0001318605.json', headers={'User-Agent': os.environ['SEC_USER_AGENT']}); print(r.status_code, r.json()['name'])"
```

Should print `200 Tesla, Inc.`

---

## ☐ 7. Project structure (15 min)

Create the folder tree from `CLAUDE.md`:

```powershell
New-Item -ItemType Directory agent\advocates, agent\tools, agent\prompts, agent\schemas, agent\ingest, ui, tests, fixtures -Force | Out-Null
```

Touch placeholder files:

```powershell
"# agent" | Out-File agent\__init__.py -Encoding utf8
"# advocates" | Out-File agent\advocates\__init__.py -Encoding utf8
"# tools" | Out-File agent\tools\__init__.py -Encoding utf8
"# schemas" | Out-File agent\schemas\__init__.py -Encoding utf8
"# ingest" | Out-File agent\ingest\__init__.py -Encoding utf8
```

Create `requirements.txt`:

```
google-adk>=0.5
google-genai>=1.0
google-cloud-aiplatform>=1.70
pymongo>=4.10
praw>=7.7
yfinance>=0.2
pydantic>=2.9
pydantic-xml>=2.13
sec-edgar-downloader>=5.0
streamlit>=1.40
python-dotenv>=1.0
tenacity>=9.0          # for retries on flaky SEC/Reddit
rich>=13.0             # nicer CLI output during ingestion
pytest>=8.0
```

Install:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## ☐ 8. The first real ingestion script (60 min)

This is the day-1 milestone. Write `agent/ingest/smoke_test.py`:

**Goal:** download one 13F filing from EDGAR, parse it (any way that works), and write one document to `filings_13f` in Atlas.

Pseudocode:

1. Fetch the latest 13F-HR filing from Berkshire Hathaway (CIK `0001067983`)
2. Parse the `informationTable` XML — extract `(cusip, nameOfIssuer, value, sshPrnamt)` per holding
3. Insert one document into `filings_13f` with shape:
   ```json
   {
     "fund_cik": "0001067983",
     "fund_name": "Berkshire Hathaway Inc",
     "filing_date": "2026-02-14",
     "quarter": "2025Q4",
     "positions": [
       {"cusip": "037833100", "issuer": "APPLE INC", "value": 76410000000, "shares": 300000000},
       ...
     ]
   }
   ```

Sanity check: open MongoDB Compass, navigate to `prism.filings_13f`, confirm one document is there.

Commit:

```powershell
git add agent/ingest/smoke_test.py
git commit -m "Day 1: end-to-end smoke test — Berkshire 13F → MongoDB"
git push
```

---

## ☐ 9. Set up daily journal (5 min)

Create `docs/DEVLOG.md`:

```markdown
# Devlog

## 2026-MM-DD — Day 1

- Set up Atlas, GCP, Reddit, EDGAR access
- First 13F ingested (Berkshire)
- Blockers: ...
- Tomorrow: ...
```

Commit it. Update daily.

---

## End-of-day verification

You're done with day 1 when ALL of these pass:

- [ ] Public GitHub repo exists, MIT license, this folder copied in
- [ ] `.env` has all 8 secrets filled in (never committed)
- [ ] All four sanity-check scripts in this checklist printed expected output
- [ ] One document exists in `prism.filings_13f` in your Atlas cluster
- [ ] Devlog entry committed

If you're stuck for >30 minutes on any item, ask for help — don't grind. There's not enough time to lose half a day.

---

## What NOT to do on day 1

- Don't write any ADK agent code — that's day 11+
- Don't write a Streamlit UI — that's day 13+
- Don't try to parse all 200 funds' 13Fs — that's day 2
- Don't optimise indexes — that's day 5

**Day 1 is plumbing day. Make every credential work. Land one record. Sleep.**
