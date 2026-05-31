export const meta = {
  name: 'build-ingest-adapters',
  description: 'Build Prism\'s 3 ingestion adapters (yfinance prices, SEC EDGAR 13F+Form4, Reddit WSB) wrapping the pure parsers + db/tickers infra, with mocked-network tests, via builder → review → fix in parallel.',
  whenToUse: 'Week-1 data layer: turn the pure parsers + ingestion infra into runnable, tested ingestion adapters (run for real once credentials are set).',
  phases: [{ title: 'Build' }, { title: 'Review' }, { title: 'Fix' }],
}

const REVIEW_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    approved: { type: 'boolean' },
    blocking: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        properties: { file: { type: 'string' }, issue: { type: 'string' }, fix: { type: 'string' } },
        required: ['issue', 'fix'],
      },
    },
    nits: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' },
  },
  required: ['approved', 'blocking', 'summary'],
}

const PY = '.venv/Scripts/python.exe'

const SHARED = [
  'Reuse — do NOT reimplement:',
  '- agent.schemas (Filing13F/Position13F, Form4Transaction, WSBPost, PriceBar)',
  '- agent.tools.parse_13f / parse_form4 / parse_wsb (the pure parsers)',
  '- agent.tools.tickers (sp500_symbols, symbol_to_cik, normalize_for_yfinance, resolve_cusips)',
  '- agent.ingest.db (get_db, ensure_collections, upsert_many, insert_timeseries, NATURAL_KEYS)',
  'Hard rules: pure parsing stays in the parsers; this adapter is the thin edge (network/Mongo).',
  'Idempotent writes. Read all secrets/URIs from env, never hardcode. tenacity for retries; rich for progress.',
  'Tests MUST mock the network/credentials (no live calls, no creds) and be deterministic.',
].join('\n')

const ADAPTERS = [
  {
    key: 'prices',
    name: 'yfinance price ingestion',
    file: 'agent/ingest/prices.py',
    test: 'tests/test_ingest_prices.py',
    spec: [
      'def fetch_prices(tickers, *, period="5y", interval="1d", _yf=None) -> Iterator[PriceBar]:',
      '  Use yfinance (inject via the _yf seam so tests can substitute a fake). For each ticker, call',
      '  normalize_for_yfinance() before querying Yahoo, but STORE the original upper symbol on PriceBar.ticker.',
      '  Map each OHLCV row -> PriceBar with ts as timezone-aware UTC (pandas index -> python datetime, tz=UTC).',
      'def ingest_prices(db, tickers, **kw) -> int: write via db.insert_timeseries(db, "prices", ...). Returns rows.',
      'Test: monkeypatch the _yf seam to return a tiny pandas DataFrame (2-3 rows, columns Open/High/Low/Close/Volume,',
      'a DatetimeIndex). Assert PriceBar objects: correct close/volume, ts tz-aware UTC, ticker upper. No network.',
    ].join('\n'),
  },
  {
    key: 'edgar',
    name: 'SEC EDGAR 13F + Form 4 ingestion',
    file: 'agent/ingest/edgar.py',
    test: 'tests/test_ingest_edgar.py',
    spec: [
      'Mirror the SEC fetch dance in scripts/fetch_fixtures.py (submissions JSON -> latest accession ->',
      'filing dir index.json -> the .xml). Put ALL HTTP behind one injectable seam, e.g.',
      '`def _get(url: str, ua: str) -> str` (module-level), so tests substitute the committed fixtures with NO network.',
      'Always send the SEC_USER_AGENT header; throttle ~7/sec.',
      'def fetch_13f(fund_cik, *, ua, resolve_tickers=False, _get=_get) -> Filing13F | None:',
      '  find latest 13F-HR; derive quarter from periodOfReport (e.g. 2025-12-31 -> "2025Q4"); fetch the infoTable',
      '  xml; parse_positions(); optionally resolve_cusips() to fill tickers; build_filing(...).',
      'def fetch_form4(issuer_cik, *, ua, limit=20, _get=_get) -> list[Form4Transaction]:',
      '  for the recent form=="4" filings (up to limit) fetch each ownership xml and parse_form4(); stamp accession.',
      'def ingest_13f(db, fund_ciks, **kw) -> int (upsert_many "filings_13f"); def ingest_form4(db, issuer_ciks, **kw)',
      '  -> int (insert_timeseries "filings_form4", deduping accession via a small seen-set or guard).',
      'Tests: monkeypatch _get to return fixtures/sec/13f_berkshire_sample.xml and form4_sample.xml (and a small',
      'fake submissions JSON + index.json). Assert fetch_13f yields a Filing13F with 3 positions and dollar values;',
      'fetch_form4 yields PLTR transactions. No network.',
    ].join('\n'),
  },
  {
    key: 'wsb',
    name: 'Reddit WSB ingestion',
    file: 'agent/ingest/reddit_wsb.py',
    test: 'tests/test_ingest_wsb.py',
    spec: [
      'def make_reddit(): build a praw.Reddit from REDDIT_CLIENT_ID/SECRET/USER_AGENT env (raise clearly if missing).',
      'def fetch_wsb_posts(reddit, *, limit=200, valid_tickers=None) -> Iterator[WSBPost]:',
      '  iterate reddit.subreddit("wallstreetbets").new(limit=limit); for each submission build a dict',
      '  {id, created_utc, title, selftext, score, num_comments, link_flair_text} and pass to',
      '  parse_wsb.submission_to_post(dict, valid_tickers or sp500_symbols()); yield non-None results.',
      'def ingest_wsb(db, reddit=None, **kw) -> int: upsert_many(db, "wsb_posts", ...). Sentiment/embedding stay None.',
      'Test: pass a fake reddit whose .subreddit().new() yields simple objects/namespaces (one mentioning PLTR, one',
      'all-junk). Assert only the PLTR post becomes a WSBPost, sentiment is None. No network, no creds.',
    ].join('\n'),
  },
]

function buildPrompt(a) {
  return (
    `Build the ${a.name} adapter for Prism — the thin network/Mongo edge over the pure parsers, ` +
    `following CLAUDE.md and docs/{SCHEMA,DATA_SOURCES}.md.\n\n${SHARED}\n\n` +
    `CREATE: ${a.file}\nCREATE TEST: ${a.test}\n\nSPEC:\n${a.spec}\n\n` +
    `Run \`${PY} -m ruff check ${a.file} ${a.test}\` and \`${PY} -m pytest ${a.test} -q\`; fix until BOTH are green. ` +
    `Do NOT modify other files (esp. __init__.py) and do NOT run git.\n` +
    `Return: public signatures, what the tests assert, and the exact pytest result line.`
  )
}

function reviewPrompt(a, summary) {
  return (
    `Adversarially review the ${a.name} adapter just written (UNCOMMITTED): ${a.file} and ${a.test}. ` +
    `Builder summary:\n${summary}\n\nCheck: (1) correctness (UTC handling, idempotent writes, time-series vs upsert ` +
    `chosen correctly, SEC UA + rate limit, CUSIP/ticker mapping); (2) purity — NO parsing logic duplicated that ` +
    `belongs in the parsers, NO hardcoded secrets; (3) tests genuinely mock the network/creds and are deterministic ` +
    `(no live calls); (4) schema drift vs agent/schemas. Re-run \`${PY} -m pytest ${a.test} -q\` yourself. ` +
    `Prefer few high-confidence blocking findings. Return the structured verdict.`
  )
}

function fixPrompt(a, review) {
  return (
    `Fix ONLY these blocking findings in ${a.file} / ${a.test}, then re-run ruff + pytest until green. No git.\n` +
    `${JSON.stringify(review.blocking, null, 2)}\n\nReturn the fixes and the pytest result.`
  )
}

async function buildAndReview(a) {
  let summary = await agent(buildPrompt(a), { label: `build:${a.key}`, phase: 'Build' })
  let review = await agent(reviewPrompt(a, summary), { label: `review:${a.key}`, phase: 'Review', schema: REVIEW_SCHEMA })
  if (review && !review.approved && review.blocking && review.blocking.length) {
    log(`${a.key}: ${review.blocking.length} blocking finding(s) — fixing`)
    summary = await agent(fixPrompt(a, review), { label: `fix:${a.key}`, phase: 'Fix' })
    review = await agent(reviewPrompt(a, summary), { label: `review2:${a.key}`, phase: 'Review', schema: REVIEW_SCHEMA })
  }
  return { adapter: a.key, approved: !!(review && review.approved), review }
}

phase('Build')
log('Building 3 ingestion adapters in parallel, each with its own build → review → fix loop')
const results = await parallel(ADAPTERS.map((a) => () => buildAndReview(a)))

return {
  adapters: results.filter(Boolean).map((r) => ({ adapter: r.adapter, approved: r.approved, review: r.review && r.review.summary })),
  allApproved: results.filter(Boolean).every((r) => r.approved),
}
