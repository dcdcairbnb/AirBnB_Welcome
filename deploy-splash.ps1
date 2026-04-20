# Deploy splash page, welcome sign, and hero image to Pi web server
# Each file is copied individually so one failure does not block the others

$PiUser = "pi"
$PiHost = "192.168.0.217"
$PiPath = "/var/www/html"

$Files = @(
  @{ Local = "C:\Users\dancrose\Documents\splash.html";                    Name = "splash.html"       },
  @{ Local = "C:\Users\dancrose\Documents\living-room.jpg";                Name = "living-room.jpg"   },
  @{ Local = "C:\Users\dancrose\Documents\WelcomeSign\welcome_sign.html";  Name = "welcome_sign.html" }
)

Write-Host "Deploying to $PiHost..." -ForegroundColor Cyan

foreach ($f in $Files) {
  if (-not (Test-Path $f.Local)) {
    Write-Host "SKIP  $($f.Name) - local file not found at $($f.Local)" -ForegroundColor Yellow
    continue
  }
  Write-Host "COPY  $($f.Name)" -ForegroundColor White
  scp $f.Local "${PiUser}@${PiHost}:/tmp/$($f.Name)"
  if ($LASTEXITCODE -ne 0) {
    Write-Host "FAIL  $($f.Name)" -ForegroundColor Red
    continue
  }
  ssh "${PiUser}@${PiHost}" "sudo mv /tmp/$($f.Name) $PiPath/$($f.Name) && sudo chown www-data:www-data $PiPath/$($f.Name)"
  if ($LASTEXITCODE -eq 0) {
    Write-Host "OK    $($f.Name)" -ForegroundColor Green
  } else {
    Write-Host "FAIL  $($f.Name) on move" -ForegroundColor Red
  }
}

Write-Host ""
Write-Host "URLs:" -ForegroundColor Cyan
Write-Host "  http://$PiHost/splash.html"
Write-Host "  http://$PiHost/welcome_sign.html"
