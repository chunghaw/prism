# Data Sources

> Everything you need to know about the four data feeds, with sample code.

---

## 1. SEC EDGAR 13F-HR (Institutional Holdings)

### What

Quarterly holdings of institutional investment managers with >$100M assets under management. Reported on **Form 13F-HR**.

### Why we use it

- The **only mandatory disclosure** of what hedge funds and asset managers hold
- Covers ~5,000 funds × 4 quarters/year
- Free, no auth, official source
- 32+ years of history

### Where

- Filing search: https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=13F-HR
- Per-CIK submissions index: `https://data.sec.gov/submissions/CIK{cik:010d}.json`
- Bulk full-text search: `https://efts.sec.gov/LATEST/search-index?q=&forms=13F-HR`

### Format

XML, with a `<form13FInfoTable>` containing repeating `<infoTable>` entries:

```xml
<infoTable>
  <nameOfIssuer>APPLE INC</nameOfIssuer>
  <titleOfClass>COM</titleOfClass>
  <cusip>037833100</cusip>
  <value>76410000</value>          <!-- in thousands of USD -->
  <shrsOrPrnAmt>
    <sshPrnamt>300000000</sshPrnamt>
    <sshPrnamtType>SH</sshPrnamtType>
  </shrsOrPrnAmt>
  <putCall></putCall>
</infoTable>
```

### Rate limits

- 10 requests/sec (SEC policy)
- Required `User-Agent` header with your name + email
- Use **8 req/sec** to leave headroom for retries

### Lag

13F filings are due **45 days after quarter end**:

- Q4 2025 → due 2026-02-14
- Q1 2026 → due 2026-05-15

This means institutional data is ALWAYS stale by ~6–8 weeks. Acknowledge this in the demo — it's a regulatory reality, not a bug.

### Sample code

Use [`sec-edgar-downloader`](https://github.com/jadchaar/sec-edgar-downloader):

```python
from sec_edgar_downloader import Downloader
import os

dl = Downloader("Prism", os.environ["SEC_USER_AGENT"].split()[-1], "./data/sec")

# Get Berkshire Hathaway's last 4 quarters of 13F-HRs
dl.get("13F-HR", "0001067983", limit=4)
```

For raw API calls (when you need the XML directly), use `requests` with the right headers:

```python
import requests
import os

headers = {"User-Agent": os.environ["SEC_USER_AGENT"]}
resp = requests.get(
    "https://data.sec.gov/submissions/CIK0001067983.json",
    headers=headers,
)
data = resp.json()
# data['filings']['recent'] has the most recent 1000 filings
```

### Suggested top-200 fund list

Start with funds where 13F changes have predictive value (well-known names):

```python
TOP_FUNDS_CIK = {
    "0001067983": "Berkshire Hathaway",
    "0001037389": "Renaissance Technologies",
    "0001336528": "Bridgewater Associates",
    "0001112511": "Citadel Advisors",
    "0001029160": "Two Sigma Investments",
    # ... 195 more
}
```

The full top-200 list is available on [WhaleWisdom's home page](https://whalewisdom.com/) — capture by hand or scrape (legal — public list of fund names).

---

## 2. SEC EDGAR Form 4 (Insider Transactions)

### What

Real-time disclosure of stock purchases / sales / option exercises by **officers, directors, and 10%+ shareholders** of public companies. Required within **2 business days** of the transaction.

### Why we use it

- The **most timely** structured data on insider activity
- Free, no auth, official source
- High signal: insiders selling into retail euphoria is a well-known bear signal (Harvard 2022 study: insider buying has 6% alpha over 3 years)

### Where

- Real-time feed: https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4
- Per-CIK feed: same `submissions/CIK*.json` endpoint as 13F, filter by `form == "4"`

### Format

XML (`ownership.xml`), with `<nonDerivativeTransaction>` entries:

```xml
<nonDerivativeTransaction>
  <securityTitle><value>Common Stock</value></securityTitle>
  <transactionDate><value>2026-05-20</value></transactionDate>
  <transactionCoding>
    <transactionCode>S</transactionCode>          <!-- S=sale, P=purchase, M=option exercise -->
    <equitySwapInvolved>0</equitySwapInvolved>
  </transactionCoding>
  <transactionAmounts>
    <transactionShares><value>50000</value></transactionShares>
    <transactionPricePerShare><value>148.32</value></transactionPricePerShare>
    <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
  </transactionAmounts>
</nonDerivativeTransaction>
```

### Volume

~1,000 Form 4 filings per day across all US public companies. To stay within scope:

- Filter to **S&P 500 tickers only** for the MVP (still ~30K filings/year)
- Store as a **time-series collection** in MongoDB (`granularity: "hours"`)

### Transaction codes to know

| Code | Meaning                |
| ---- | ---------------------- |
| P    | Open-market purchase   |
| S    | Open-market sale       |
| M    | Option exercise        |
| F    | Tax payment via shares |
| A    | Award / grant          |
| G    | Bona fide gift         |

For the demo, **filter to P and S** — these are the discretionary trades that matter.

### 10b5-1 plans

Some insider sales are pre-scheduled programmatic sales (10b5-1). They appear in Form 4 but should be **distinguished from discretionary sales** in the demo (less informative). The XML has an `<isDirectFootnote>` field that often indicates this.

### Sample code

```python
import requests
import os
from lxml import etree

headers = {"User-Agent": os.environ["SEC_USER_AGENT"]}

# Get Form 4s for a specific company (e.g., Palantir, CIK 0001321655)
resp = requests.get(
    "https://data.sec.gov/submissions/CIK0001321655.json",
    headers=headers,
)
data = resp.json()

# Filter to Form 4
form4_filings = [
    (date, acc) for form, date, acc in zip(
        data["filings"]["recent"]["form"],
        data["filings"]["recent"]["filingDate"],
        data["filings"]["recent"]["accessionNumber"],
    )
    if form == "4"
]

# Each filing has an XML accessible at:
# https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_no_dashes_stripped}/{primary_doc}
```

---

## 3. Reddit r/WallStreetBets (Retail Sentiment)

### What

The largest English-language retail trader community (~17M members). Posts mention tickers, discuss strategy, share P&L. The signal is noisy — but the signal-of-the-noise is the signal.

### Why we use it

- Real-time retail psychology
- Free via Reddit API (PRAW)
- Used by Bloomberg, hedge funds for sentiment overlays

### Where

- API: https://www.reddit.com/r/wallstreetbets/ via [PRAW](https://praw.readthedocs.io/)
- Historical bulk: [Pushshift archives](https://github.com/Watchful1/PushshiftDumps) (terabytes of historical Reddit dumps)

### Rate limits

- PRAW handles automatic rate-limiting (60 req/min for OAuth)
- For bulk historical, use Pushshift dumps — no API calls needed

### Sample code

```python
import praw
import os
import re

reddit = praw.Reddit(
    client_id=os.environ["REDDIT_CLIENT_ID"],
    client_secret=os.environ["REDDIT_CLIENT_SECRET"],
    user_agent=os.environ["REDDIT_USER_AGENT"],
)

TICKER_RE = re.compile(r"\b[A-Z]{1,5}\b")          # crude
# Better: filter against an S&P 500 ticker set

for post in reddit.subreddit("wallstreetbets").new(limit=200):
    title_tickers = TICKER_RE.findall(post.title)
    body_tickers = TICKER_RE.findall(post.selftext)
    tickers = set(title_tickers + body_tickers) & SP500_TICKERS
    if not tickers:
        continue

    doc = {
        "post_id": post.id,
        "created_utc": post.created_utc,
        "title": post.title,
        "text": post.selftext[:5000],         # truncate; full text rarely needed
        "score": post.score,
        "num_comments": post.num_comments,
        "flair": post.link_flair_text,
        "tickers": list(tickers),
        # sentiment + embedding computed in a separate pass
    }
```

### Sentiment scoring

**Don't use VADER or classic NLP libraries** — WSB language (memes, sarcasm, irony) is too unique. Use Gemini with structured output:

```python
class WSBSentiment(BaseModel):
    sentiment: Literal["bullish", "bearish", "neutral", "sarcastic"]
    confidence: float = Field(ge=0, le=1)
    primary_emotion: Literal["fomo", "fear", "euphoria", "regret", "analytical", "joking"]
    is_dd_post: bool          # "due diligence" — substantive analysis
    is_loss_porn: bool        # bragging about losses (signature WSB)
```

### Tickers to filter for

Don't waste embeddings on `THE`, `CEO`, `USA`, etc. (which the regex above will catch). Maintain a set of valid US tickers (S&P 500 + Russell 1000 is plenty for MVP).

A good free source for the S&P 500 list is [DataHub](https://datahub.io/core/s-and-p-500-companies).

---

## 4. yfinance (Price Ground-Truth)

### What

Open / close / high / low / volume for any US ticker. Used to compute "what actually happened" after a 13F filing / insider trade / WSB mention.

### Where

- Library: [`yfinance`](https://github.com/ranaroussi/yfinance)
- Free, no key, no rate limit (Yahoo doesn't publish one)

### Caveats

- **Unofficial** — yfinance scrapes Yahoo Finance
- Occasionally breaks when Yahoo changes their endpoints (recent breakages: Oct 2024, Mar 2025)
- For hackathon: **good enough**. For production: pay for Polygon / Alpha Vantage / IEX Cloud.

### Sample code

```python
import yfinance as yf

# Single ticker, 5 years of daily prices
data = yf.Ticker("PLTR").history(period="5y", interval="1d")
# data is a pandas DataFrame with columns: Open, High, Low, Close, Volume, Dividends, Stock Splits

# Bulk download for many tickers
import pandas as pd
sp500 = ["AAPL", "MSFT", "GOOGL", ...]   # full list
bulk = yf.download(sp500, period="5y", interval="1d", group_by="ticker", threads=True)
```

### Storage

Store as a **time-series collection** with:

- `timeField: "ts"`
- `metaField: "ticker"`
- `granularity: "hours"`

Compresses well; queries fast.

---

## 5. Behavioural Finance Paper Corpus (seed data)

### What

A static, curated set of ~50–100 behavioural finance papers. Used by Prism to cite research when describing detected patterns.

### Why

The cited-research layer is one of the two sharpening tweaks that makes Prism distinct from Quiver / Fintel.

### Where

- **SSRN** (free abstracts, often free full-text): https://www.ssrn.com/index.cfm/en/jelpubs/?jel=G41
- **PubMed** (open biomedical/psychology): https://pubmed.ncbi.nlm.nih.gov/ via NCBI E-utilities (free, no key)
- **arxiv q-fin** (open finance preprints): https://arxiv.org/list/q-fin/recent
- **Wikipedia [List of cognitive biases](https://en.wikipedia.org/wiki/List_of_cognitive_biases)** (clean taxonomy, ~200 biases)

### Suggested seed list

Bare-minimum 12 papers covering the patterns Prism will detect:

| Paper                                                                       | Pattern it explains                    |
| --------------------------------------------------------------------------- | -------------------------------------- |
| Barber & Odean (2000), _Trading is Hazardous to Your Wealth_                | Overtrading                            |
| Barber & Odean (2001), _Boys Will Be Boys: Gender, Overconfidence, and ..._ | Overconfidence                         |
| Shefrin & Statman (1985), _The Disposition Effect_                          | Selling winners early / riding losers  |
| Lakonishok & Lee (1998), _Are Insider Trades Informative?_                  | Insider buying signal                  |
| Kumar (2009), _Who Gambles in the Stock Market?_                            | Lottery-stock preference (retail)      |
| Bali, Cakici & Whitelaw (2011), _Maxing Out: Stocks as Lotteries_           | Skewness preference                    |
| De Long, Shleifer, Summers & Waldmann (1990), _Noise Trader Risk_           | Sentiment-driven mispricing            |
| Hirshleifer & Teoh (2003), _Limited Attention_                              | Attention-driven trades                |
| Pedersen (2024), _Game On: Social Networks and Markets_                     | GME / meme stock dynamics              |
| Black (1986), _Noise_                                                       | Foundation: rational vs noise traders  |
| Kahneman & Tversky (1979), _Prospect Theory_                                | Loss aversion                          |
| Thaler (1985), _Mental Accounting_                                          | Anchoring / framing in trade decisions |

### Seed once, never re-ingest

This corpus is **static** for the hackathon. Embed once during week 2. Don't build a live paper-ingestion pipeline — out of scope.

---

## Quick-reference rate limits

| Source      | Limit          | Notes                                            |
| ----------- | -------------- | ------------------------------------------------ |
| SEC EDGAR   | 10 req/sec     | Required `User-Agent` header; use 8 req/sec      |
| Reddit PRAW | 60 req/min     | Handled automatically by PRAW                    |
| yfinance    | None published | Be reasonable; cache responses                   |
| Vertex AI   | per quota      | Check via `gcloud compute project-info describe` |
| MongoDB M0  | 100 conn/s     | Free tier; sufficient for hackathon              |
