<#
  Usage:
    # First time: create an empty repo on github.com (no README), copy its HTTPS URL,
    # then run with your remote:
    powershell -NoProfile -ExecutionPolicy Bypass -File .\git.ps1 -Remote "https://github.com/<you>/peggy-ws.git"

    # Later commits (same remote already set):
    powershell -NoProfile -ExecutionPolicy Bypass -File .\git.ps1 -Commit "feat: add session IDs"
#>

param(
  [string]$Remote = "",
  [string]$Commit = "init: peggy-ws minimal websocket + client"
)

$ErrorActionPreference = "Stop"

function Info($m){ Write-Host "[git]" $m -ForegroundColor Cyan }

# Ensure we're in the project
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

# Safety: prove .env is ignored
if (Test-Path .\.env) {
  Info "Found .env locally (good). It should be IGNORED by .gitignore."
}

# Init if needed
if (-not (Test-Path .\.git)) {
  Info "git init"
  git init | Out-Null
  git branch -M main
}

# Add remote if provided and not set yet
$hasRemote = (git remote 2>$null) -ne $null
if ($Remote -and -not $hasRemote) {
  Info "git remote add origin $Remote"
  git remote add origin $Remote
}

# Stage + commit
Info "git add ."
git add .

# Confirm .env not staged
$trackedEnv = git ls-files .env
if ($trackedEnv) {
  throw ".env appears staged! Check .gitignore; do NOT push secrets."
}

Info "git commit -m `"$Commit`""
git commit -m "$Commit" | Out-Null

# Push (requires remote to be set)
$origin = git remote get-url origin 2>$null
if ($origin) {
  Info "git push -u origin main  →  $origin"
  git push -u origin main
} else {
  Info "No remote set. Create a repo on github.com (no README), then run:"
  Write-Host "    .\git.ps1 -Remote `"https://github.com/<you>/peggy-ws.git`""
}
