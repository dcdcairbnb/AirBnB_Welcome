# check_health.ps1
# Runs check_health.sh on the Pi over SSH from your Windows laptop.
#
# Usage:
#   .\check_health.ps1 pi@192.168.0.217
#   .\check_health.ps1 pi@100.76.203.111    # tailscale
#
# Exit code matches the remote script's (0 healthy, 1 issues found).

param(
  [Parameter(Mandatory=$true, Position=0)]
  [string]$Target
)

$script = Join-Path $PSScriptRoot "check_health.sh"
if (-not (Test-Path $script)) {
  Write-Error "check_health.sh not found next to this script"
  exit 2
}

Write-Host "Running health check on $Target..." -ForegroundColor Cyan
Get-Content $script -Raw | ssh $Target 'bash -s'
exit $LASTEXITCODE
