param(
  [double]$prereqs_ok=1,
  [double]$resources_ok=1,
  [double]$risk_inverse=1,
  [double]$context_freshness=1,
  [double]$ops_fit=1
)
$payload = @{
  prereqs_ok=$prereqs_ok; resources_ok=$resources_ok; risk_inverse=$risk_inverse;
  context_freshness=$context_freshness; ops_fit=$ops_fit
} | ConvertTo-Json -Compress
$payload | python server/foundation/grs.py
