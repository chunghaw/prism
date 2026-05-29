export const meta = {
  name: 'feature-loop',
  description: 'Build a Prism feature, then run adversarial Codex review and auto-fix until the review is clean (or max rounds).',
  whenToUse: 'Implementing any Prism feature where you want builder -> reviewer -> fix to run autonomously.',
  phases: [
    { title: 'Build' },
    { title: 'Review' },
    { title: 'Fix' },
  ],
}

// args may be a plain string (the feature) or { feature, maxRounds }
const feature = typeof args === 'string' ? args : (args && args.feature) || 'Unspecified feature — read CLAUDE.md and docs/ for context.'
const MAX_ROUNDS = (args && args.maxRounds) || 3

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
        properties: {
          file: { type: 'string' },
          issue: { type: 'string' },
          fix: { type: 'string' },
        },
        required: ['issue', 'fix'],
      },
    },
    nits: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' },
  },
  required: ['approved', 'blocking', 'summary'],
}

phase('Build')
log(`Building feature: ${feature}`)
let build = await agent(
  `Implement this Prism feature end-to-end with unit tests, following CLAUDE.md exactly. ` +
  `Run ruff + pytest and fix failures before returning. Stage + commit locally (do not push). Feature:\n\n${feature}`,
  { label: 'build', phase: 'Build', agentType: 'builder' }
)

let round = 0
let lastReview = null
while (round < MAX_ROUNDS) {
  round++
  phase('Review')
  const review = await agent(
    `Adversarially review the current git diff for this feature: "${feature}".\n\nBuilder's summary:\n${build}\n\n` +
    `Use scripts/codex-review.ps1 if Codex CLI is available; otherwise review directly. Return the structured verdict.`,
    { label: `review-r${round}`, phase: 'Review', agentType: 'reviewer-codex', schema: REVIEW_SCHEMA }
  )
  lastReview = review
  if (!review || review.approved) {
    log(`Review round ${round}: APPROVED${review && review.nits && review.nits.length ? ` (${review.nits.length} nit(s) noted)` : ''}`)
    break
  }
  log(`Review round ${round}: ${review.blocking.length} blocking issue(s) — dispatching fix`)
  phase('Fix')
  build = await agent(
    `Address ONLY these blocking review findings, then re-run ruff + pytest and re-commit locally:\n` +
    `${JSON.stringify(review.blocking, null, 2)}\n\nReturn a summary of the fixes and the test result.`,
    { label: `fix-r${round}`, phase: 'Fix', agentType: 'builder' }
  )
}

return {
  feature,
  rounds: round,
  approved: !!(lastReview && lastReview.approved),
  finalReview: lastReview,
}
