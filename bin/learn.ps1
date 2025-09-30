param([Parameter(Mandatory=$true)][string]$topic)

# 1) GRS gate (simple defaults; adjust as needed)
$grs = ( @{ prereqs_ok=1; resources_ok=1; risk_inverse=1; context_freshness=1; ops_fit=1 } |
    ConvertTo-Json -Compress ) | python server/foundation/grs.py | ConvertFrom-Json
if (-not $grs.pass) {
  @{type="blocked"; grs=$grs.grs; reasons=$grs.reasons} | ConvertTo-Json
  exit 0
}

# 2) Create module studies from template if missing
$modDir = "server/modules/$topic/studies"
$newFiles = @()
if (-not (Test-Path $modDir)) { New-Item -ItemType Directory -Path $modDir -Force | Out-Null }

$tplH = "server/modules/_templates/studies/heuristics.json"
$tplN = "server/modules/_templates/studies/notes.md"
$hPath = Join-Path $modDir "heuristics.json"
$nPath = Join-Path $modDir "notes.md"

if (-not (Test-Path $hPath)) {
  (Get-Content $tplH -Raw).Replace('"<replace-me>"', '"'+$topic+'"') | Set-Content $hPath -Encoding UTF8
  $newFiles += $hPath
}
if (-not (Test-Path $nPath)) { Copy-Item $tplN $nPath; $newFiles += $nPath }

# 3) Ledger update
$ledgerPath = "server/foundation/ledger.json"
$ledger = Get-Content $ledgerPath -Raw | ConvertFrom-Json
if (-not $ledger.skills.$topic) { $ledger.skills | Add-Member -NotePropertyName $topic -NotePropertyValue 0 }
$ledger.skills.$topic = [int]$ledger.skills.$topic + 1
$ledger.open_questions += "What fast probe would validate first rule for '$topic'?"
$ledger | ConvertTo-Json -Depth 8 | Set-Content $ledgerPath -Encoding UTF8

# 4) Packets
@{type="learn"; project=$topic; applied=$true; files=$newFiles; error=$null} | ConvertTo-Json
# Cross-links (can be 0 on first run)
$xl = python server/foundation/xlinker.py | ConvertFrom-Json
$xl | ConvertTo-Json
