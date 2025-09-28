# Tries to close the two PowerShell windows started by up.ps1 (uvicorn and cloudflared).
# If you launched others manually, this won’t touch them.

$procs = Get-Process powershell -ErrorAction SilentlyContinue | Where-Object {
  $_.MainWindowTitle -match "uvicorn server\.main:app" -or
  $_.MainWindowTitle -match "cloudflared tunnel"
}

if ($procs) {
  $procs | ForEach-Object {
    Write-Host "Closing PID $($_.Id): $($_.MainWindowTitle)"
    try { $_.CloseMainWindow() | Out-Null } catch {}
    Start-Sleep -Milliseconds 300
    if (!$_.HasExited) { try { $_.Kill() } catch {} }
  }
} else {
  Write-Host "Nothing to stop."
}
