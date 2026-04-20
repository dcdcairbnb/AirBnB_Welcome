# Sync local source files from Windows to omada-controller
# Run from Windows PowerShell when you change splash.html, living-room.jpg, or welcome_sign.html

$OmadaUser = "pi"
$OmadaHost = "omada-controller"    # or use IP if hostname doesn't resolve
$OmadaDest = "~/webroot-src"

$Files = @(
  "C:\Users\dancrose\Documents\splash.html",
  "C:\Users\dancrose\Documents\living-room.jpg",
  "C:\Users\dancrose\Documents\WelcomeSign\welcome_sign.html"
)

Write-Host "Ensuring $OmadaDest exists on $OmadaHost..." -ForegroundColor Cyan
ssh "${OmadaUser}@${OmadaHost}" "mkdir -p $OmadaDest"

foreach ($f in $Files) {
  if (-not (Test-Path $f)) {
    Write-Host "SKIP  $f - not found" -ForegroundColor Yellow
    continue
  }
  Write-Host "SYNC  $(Split-Path $f -Leaf)" -ForegroundColor White
  scp $f "${OmadaUser}@${OmadaHost}:$OmadaDest/"
}

Write-Host ""
Write-Host "Now SSH into omada-controller and run: bash ~/deploy-splash.sh" -ForegroundColor Green
