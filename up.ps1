<#
  Usage examples:
    # Local only (same Wi-Fi)
    powershell -NoProfile -ExecutionPolicy Bypass -File .\up.ps1

    # With Cloudflare tunnel (works over cellular)
    powershell -NoProfile -ExecutionPolicy Bypass -File .\up.ps1 -UseTunnel

    # Override secrets on the fly
    powershell -NoProfile -ExecutionPolicy Bypass -File .\up.ps1 -UseTunnel -Token "Daisy17!" -OpenAIKey "sk-..." -Model "gpt-4o-mini"
#>

param(
  [switch]$UseTunnel = $false,
  [string]$Token,
  [string]$OpenAIKey,
  [string]$Model = "gpt-4o-mini"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

function Write-Info($msg){ Write-Host "[peggy]" $msg -ForegroundColor Cyan }
function Ensure-File($path){ if(!(Test-Path $path)){ New-Item -ItemType File -Path $path | Out-Null } }

# --- 1) Python check ---
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  throw "Python is not on PATH. Install Python 3.11+, then re-run."
}

# --- 2) Create venv if missing ---
if (!(Test-Path ".\.venv\Scripts\python.exe")) {
  Write-Info "Creating venv..."
  python -m venv .venv
}
$venvPy = Join-Path $root ".venv\Scripts\python.exe"

# --- 3) Requirements ---
Write-Info "Installing requirements..."
& $venvPy -m pip install --upgrade pip *> $null
& $venvPy -m pip install -r server\requirements.txt *> $null
& $venvPy -m pip install "openai==1.46.0" *> $null
& $venvPy -m pip install "httpx==0.27.2" *> $null


# --- 4) Ensure server is a package ---
Ensure-File ".\server\__init__.py"

# --- 5) .env setup (create if missing) ---
$envPath = ".\.env"
if (!(Test-Path $envPath)) {
  Write-Info "Creating .env..."
  $rand = [guid]::NewGuid().ToString("N")
  @"
ACCESS_TOKEN=$rand
OPENAI_API_KEY=
OPENAI_MODEL=$Model
HISTORY_FILE=history.jsonl
"@ | Set-Content -Encoding UTF8 $envPath
}

# helper: set-or-append env var in .env (regex flags FIXED for PowerShell)
function Set-EnvKV([string]$key,[string]$val){
  $content = if (Test-Path $envPath) { Get-Content $envPath -Raw } else { "" }
  $escapedKey = [regex]::Escape($key)
  # Use inline flags (?im) inside the pattern (PowerShell -match has no '-im' switch)
  if ([regex]::IsMatch($content, "^(?im)$escapedKey=.*$")) {
    $content = [regex]::Replace($content, "^(?im)$escapedKey=.*$", "$key=$val")
  } else {
    if ($content -and -not $content.EndsWith("`n")) { $content += "`n" }
    $content += "$key=$val`n"
  }
  Set-Content -Encoding UTF8 $envPath $content
}

if ($Token)     { Set-EnvKV "ACCESS_TOKEN"   $Token }
if ($OpenAIKey) { Set-EnvKV "OPENAI_API_KEY" $OpenAIKey }
if ($Model)     { Set-EnvKV "OPENAI_MODEL"   $Model }

# --- 6) Launch uvicorn in a new window ---
$uvArgs = @(
  "-NoExit",
  "-Command",
  "& `"$venvPy`" -m uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload"
)
$uvProc = Start-Process -FilePath "powershell" -ArgumentList $uvArgs -PassThru
Write-Info "Started Uvicorn (PID $($uvProc.Id)) at http://localhost:8000   → client at /app/"

# --- 7) Optionally launch Cloudflare quick tunnel ---
if ($UseTunnel) {
  if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    Write-Warning "cloudflared not found. Install with:  winget install Cloudflare.cloudflared"
  } else {
    $cfArgs = @("-NoExit","-Command","cloudflared tunnel --url http://localhost:8000")
    $cfProc = Start-Process -FilePath "powershell" -ArgumentList $cfArgs -PassThru
    Write-Info "Started Cloudflare (PID $($cfProc.Id)). Watch that window for your https://… and wss://… URLs."
  }
}

# --- 8) Open local client in browser ---
Start-Process "http://localhost:8000/app/"
Write-Info "If using the tunnel, open https://<your-subdomain>.trycloudflare.com/app/ on your phone and enter your token."
Write-Info "Done."
