export const meta = {
  name: 'build-parsers',
  description: 'Build Prism\'s 3 pure parsers (13F, Form 4, WSB) with unit tests, each through a builder → adversarial review → fix loop, in parallel.',
  whenToUse: 'One-time data-foundation step: turn the committed schema contracts + SEC fixtures into tested pure parsers.',
  phases: [
    { title: 'Build' },
    { title: 'Review' },
    { title: 'Fix' },
  ],
}

const REVIEW_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    approved: { type: 'boolean' },
    blocking: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
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

const PARSERS = [
  {
    key: '13f',
    name: '13F information-table',
    file: 'agent/tools/parse_13f.py',
    test: 'tests/test_parse_13f.py',
    fixture: 'fixtures/sec/13f_berkshire_sample.xml',
    spec: [
      'def parse_positions(xml: bytes, cusip_to_ticker: dict[str, str] | None = None) -> list[Position13F]:',
      '  Parse the namespaced 13F informationTable XML. Per <infoTable>: nameOfIssuer->issuer, cusip,',
      '  titleOfClass->title_of_class, <value> -> value_usd AS-IS (post-2024 dollars; DO NOT multiply by 1000),',
      '  shrsOrPrnAmt/sshPrnamt -> shares, sshPrnamtType -> share_type, putCall -> put_call (None if empty).',
      '  Resolve ticker via cusip_to_ticker if provided. Use local-name() handling so namespaces don\'t break it.',
      'def build_filing(positions, *, fund_cik, fund_name, filing_date, quarter, accession_number) -> Filing13F.',
      'Tests must OPEN the fixture, read the REAL values, and assert: exactly 3 positions; first position\'s',
      'issuer/cusip/value_usd/shares match the fixture exactly; value_usd looks like dollars (shares>0 and a',
      'sane per-share price = value_usd/shares is between 1 and 100000).',
    ].join('\n'),
  },
  {
    key: 'form4',
    name: 'Form 4 insider transaction',
    file: 'agent/tools/parse_form4.py',
    test: 'tests/test_parse_form4.py',
    fixture: 'fixtures/sec/form4_sample.xml',
    spec: [
      'def parse_form4(xml: bytes | str, *, accession_number: str = "") -> list[Form4Transaction]:',
      '  Parse the Form 4 <ownershipDocument>. issuer: issuerCik (zero-pad to 10 digits), issuerName,',
      '  issuerTradingSymbol -> meta.ticker. reportingOwner: rptOwnerName -> insider_name; officerTitle ->',
      '  insider_title; reportingOwnerRelationship isDirector/isOfficer/isTenPercentOwner -> the meta flags',
      '  (treat "1"/"true" as True). For each <nonDerivativeTransaction>: transactionCoding/transactionCode ->',
      '  transaction_code; transactionDate/value -> transaction_ts (parse YYYY-MM-DD as UTC midnight);',
      '  transactionShares/value -> shares; transactionPricePerShare/value -> price_per_share (may be 0/empty);',
      '  transactionAcquiredDisposedCode/value -> acquired_disposed. is_10b5_1 = True if ANY <footnote> text',
      '  contains "10b5-1" (case-insensitive). Return ALL non-derivative transactions (ingestor filters later).',
      'Tests assert against the REAL Palantir fixture: >=1 transaction; meta.ticker=="PLTR";',
      'meta.issuer_cik=="0001321655"; and the first transaction\'s code/shares/acquired_disposed match the fixture.',
    ].join('\n'),
  },
  {
    key: 'wsb',
    name: 'WSB post',
    file: 'agent/tools/parse_wsb.py',
    test: 'tests/test_parse_wsb.py',
    fixture: 'fixtures/wsb/sample_submission.json (CREATE this — synthetic, mark with a "_note" key)',
    spec: [
      'def extract_tickers(text: str, valid_tickers: set[str]) -> list[str]:',
      '  Find $-prefixed or bare uppercase 1-5 letter tokens, intersect with valid_tickers, dedupe preserving order.',
      'def submission_to_post(sub: dict, valid_tickers: set[str]) -> WSBPost | None:',
      '  Map a PRAW-like dict (keys: id, created_utc [epoch seconds], title, selftext, score, num_comments,',
      '  link_flair_text) to WSBPost. tickers = extract_tickers(title) ∪ extract_tickers(selftext). Return None',
      '  if no tickers. sentiment and embedding stay None (deferred to a Gemini pass). created_utc epoch ->',
      '  timezone-aware UTC datetime.',
      'Create fixtures/wsb/sample_submission.json: a realistic WSB post dict mentioning PLTR plus junk tokens',
      '(THE, CEO, USA) to prove filtering; include a top-level "_note" marking it synthetic.',
      'Tests assert: extract_tickers drops the junk and keeps PLTR; submission_to_post returns a WSBPost with',
      'tickers==["PLTR"], sentiment is None, embedding is None, created_utc tz-aware.',
    ].join('\n'),
  },
]

function buildPrompt(p) {
  return (
    `Implement the ${p.name} parser for Prism as a PURE function module (no network, no MongoDB, no Vertex AI), ` +
    `following CLAUDE.md and docs/SCHEMA.md, against the committed Pydantic contracts in agent/schemas (import the models from \`agent.schemas\`).\n\n` +
    `CREATE: ${p.file}\nCREATE TEST: ${p.test}\nFIXTURE: ${p.fixture}\n\nSPEC:\n${p.spec}\n\n` +
    `Rules:\n` +
    `- Pure functions only. Parse XML with lxml; handle namespaces with local-name. Tolerate missing optional fields.\n` +
    `- The test must read concrete expected values from the fixture itself, not from guesses.\n` +
    `- Run \`${PY} -m ruff check ${p.file} ${p.test}\` and \`${PY} -m pytest ${p.test} -q\`; fix until BOTH are green.\n` +
    `- Do NOT modify any other file (especially not agent/tools/__init__.py). Do NOT run any git command.\n\n` +
    `Return: the public function signatures, what the tests assert, and the exact pytest result line.`
  )
}

function reviewPrompt(p, summary) {
  return (
    `Adversarially review the ${p.name} parser just written. Files to inspect directly (they are UNCOMMITTED): ` +
    `${p.file} and ${p.test} (and its fixture). Builder's summary:\n${summary}\n\n` +
    `Check, in priority order: (1) correctness vs the real fixture data and docs/SCHEMA.md (esp. 13F value is ` +
    `dollars NOT thousands; Form 4 date->UTC; WSB junk-token filtering); (2) schema drift vs agent/schemas; ` +
    `(3) CLAUDE.md violations (impurity, network/Mongo in the parser, hardcoded values that should be parsed); ` +
    `(4) missing edge-case tests. Re-run \`${PY} -m pytest ${p.test} -q\` yourself to confirm it actually passes. ` +
    `Prefer few high-confidence blocking findings. Return the structured verdict.`
  )
}

function fixPrompt(p, review) {
  return (
    `Fix ONLY these blocking findings in ${p.file} / ${p.test}, then re-run ruff + pytest until green. ` +
    `Do NOT run git. Findings:\n${JSON.stringify(review.blocking, null, 2)}\n\nReturn the fixes made and the pytest result.`
  )
}

// NOTE: custom .claude/agents types (builder, reviewer-codex) only register on a
// fresh session, so this run uses the default workflow agent with roles inline.
// CLAUDE.md auto-loads into every sub-agent, so the project rules still apply.
async function buildAndReview(p) {
  let summary = await agent(buildPrompt(p), { label: `build:${p.key}`, phase: 'Build' })
  let review = await agent(reviewPrompt(p, summary), { label: `review:${p.key}`, phase: 'Review', schema: REVIEW_SCHEMA })
  if (review && !review.approved && review.blocking && review.blocking.length) {
    log(`${p.key}: ${review.blocking.length} blocking finding(s) — fixing`)
    summary = await agent(fixPrompt(p, review), { label: `fix:${p.key}`, phase: 'Fix' })
    review = await agent(reviewPrompt(p, summary), { label: `review2:${p.key}`, phase: 'Review', schema: REVIEW_SCHEMA })
  }
  return { parser: p.key, approved: !!(review && review.approved), review, summary }
}

phase('Build')
log('Building 3 parsers in parallel, each with its own build → review → fix loop')
const results = await parallel(PARSERS.map((p) => () => buildAndReview(p)))

return {
  parsers: results.filter(Boolean).map((r) => ({ parser: r.parser, approved: r.approved, review: r.review && r.review.summary })),
  allApproved: results.filter(Boolean).every((r) => r.approved),
}
