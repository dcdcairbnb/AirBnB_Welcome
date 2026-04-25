# deploy.ps1
# Pushes the latest omada_auth.py and welcome_sign.html to the Pi and reloads the service.
#
# Usage from PowerShell:
#   cd C:\Users\dancrose\Documents\AirBnB_Welcome
#   .\deploy.ps1
#
# Optional target (defaults to local IP):
#   .\deploy.ps1 pi@100.76.203.111   # tailscale

param(
  [string]$Target = "pi@192.168.0.217"
)

$repoRoot   = $PSScriptRoot
$omadaPy    = Join-Path $repoRoot "omada_auth.py"
$welcomeSrc = "C:\Users\dancrose\Documents\WelcomeSign\welcome_sign.html"

if (-not (Test-Path $omadaPy))    { Write-Error "Missing $omadaPy"; exit 1 }
if (-not (Test-Path $welcomeSrc)) { Write-Error "Missing $welcomeSrc"; exit 1 }

Write-Host "Pushing omada_auth.py to $Target..." -ForegroundColor Cyan
scp $omadaPy "${Target}:/tmp/omada_auth.py"
if ($LASTEXITCODE -ne 0) { Write-Error "scp omada_auth.py failed"; exit 1 }

Write-Host "Pushing welcome_sign.html to $Target..." -ForegroundColor Cyan
scp $welcomeSrc "${Target}:/tmp/welcome_sign.html"
if ($LASTEXITCODE -ne 0) { Write-Error "scp welcome_sign.html failed"; exit 1 }

Write-Host "Deploying on Pi..." -ForegroundColor Cyan
$remote = @"
sudo cp /tmp/omada_auth.py /opt/omada-auth/omada_auth.py
sudo mv /tmp/welcome_sign.html /var/www/html/welcome_sign.html
sudo chown www-data:www-data /var/www/html/welcome_sign.html
sudo systemctl restart omada-auth
sleep 4
echo
echo '== /today =='
curl -s http://127.0.0.1/today | python3 -m json.tool 2>/dev/null | head -15
echo
echo '== /sports (first game) =='
curl -s http://127.0.0.1/sports | python3 -m json.tool 2>/dev/null | head -15
"@

ssh $Target $remote
if ($LASTEXITCODE -ne 0) { Write-Error "remote deploy failed"; exit 1 }

Write-Host ""
Write-Host "Deploy complete. Hard refresh the welcome page on your phone." -ForegroundColor Green
