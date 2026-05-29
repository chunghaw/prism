#requires -Version 5.1
<#
.SYNOPSIS
  Codex review bridge for Prism's build -> review loop.
.DESCRIPTION
  Collects the current git diff and asks the OpenAI Codex CLI to review it,
  returning a JSON verdict. If the Codex CLI is not installed, prints the
  sentinel CODEX_NOT_INSTALLED followed by the diff so the reviewer agent
  can fall back to reviewing it directly.
.PARAMETER BaseRef
  Compare against this ref (e.g. origin/main). Empty = review uncommitted changes.
.EXAMPLE
  pwsh scripts/codex-review.ps1
  pwsh scripts/codex-review.ps1 -BaseRef origin/main
#>
param(
  [string]$BaseRef = "",
  [string]$Context = "You are reviewing a change to Prism (a Google-ADK + Gemini agent over SEC 13F, SEC Form 4, and Reddit WSB data, backed by MongoDB Atlas). Review adversarially for: correctness bugs, schema drift vs agent/schemas + docs/SCHEMA.md, CLAUDE.md violations (non-Google runtime AI, hardcoded model ids, inlined prompts, mock data in demo path, copied competitor code), missing tests, and queries that need an index."
)
$ErrorActionPreference = "Stop"

function Get-Diff {
  param([string]$Ref)
  if ($Ref) { $d = git diff $Ref -- . 2>$null } else { $d = git diff HEAD -- . 2>$null }
  if ([string]::IsNullOrWhiteSpace($d)) { $d = git diff --staged -- . 2>$null }
  return $d
}

$diff = Get-Diff -Ref $BaseRef
if ([string]::IsNullOrWhiteSpace($diff)) {
  Write-Output '{"approved": true, "blocking": [], "nits": [], "summary": "No changes to review."}'
  exit 0
}

$prompt = @"
$Context

Return ONLY a JSON object of this shape (no prose around it):
{ "approved": <bool>, "blocking": [ {"file": "<path>", "issue": "<what is wrong>", "fix": "<concrete fix>"} ], "nits": ["<minor>"], "summary": "<one line>" }
'approved' is true only if 'blocking' is empty.

=== GIT DIFF ===
$diff
"@

$codex = Get-Command codex -ErrorAction SilentlyContinue
if ($null -ne $codex) {
  # Non-interactive Codex run. Flags may need tuning to your Codex CLI version.
  try {
    $prompt | & codex exec --skip-git-repo-check
  } catch {
    Write-Output "CODEX_ERROR: $($_.Exception.Message)"
    Write-Output "=== DIFF FOR MANUAL/AGENT REVIEW ==="
    Write-Output $diff
  }
} else {
  Write-Warning "Codex CLI not found. Install: npm install -g @openai/codex ; then 'codex login'."
  Write-Output "CODEX_NOT_INSTALLED"
  Write-Output "=== DIFF FOR MANUAL/AGENT REVIEW ==="
  Write-Output $diff
}
