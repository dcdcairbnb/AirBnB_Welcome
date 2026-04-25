# backup_all.ps1
# One-shot backup of everything: laptop repo to git, Pi config tarball, Omada UI nudge.
#
# Usage:
#   .\backup_all.ps1
#   .\backup_all.ps1 pi@100.76.203.111   # tailscale target
#
# What it does:
#   1. Copy live welcome_sign.html from C:\Users\dancrose\Documents\WelcomeSign into the repo
#   2. Git add, commit, push to GitHub
#   3. SCP backup_pi_config.sh to Pi if missing, run it, pull the tarball into customers\<slug>\backups\
#   4. Remind you to pull the Omada Controller .cfg from the UI

param(
  [string]$Target  = "pi@192.168.0.217",
  [string]$Slug    = "music_city_retreat"
)

$ErrorActionPreference = "Stop"

$repoRoot   = $PSScriptRoot
$welcomeSrc = "C:\Users\dancrose\Documents\WelcomeSign\welcome_sign.html"
$welcomeDst = Join-Path $repoRoot "welcome_sign.html"
$fridgeSrc  = "C:\Users\dancrose\Documents\WelcomeSign\fridge_wifi_welcome.html"
$backupsDir = Join-Path $repoRoot "customers\$Slug\backups"
$piBackup   = Join-Path $repoRoot "backup_pi_config.sh"

Write-Host ""
Write-Host "===========================================" -ForegroundColor Cyan
Write-Host " AirBnB Welcome backup ($(Get-Date -Format 'yyyy-MM-dd HH:mm'))" -ForegroundColor Cyan
Write-Host "===========================================" -ForegroundColor Cyan
Write-Host ""

# Ensure backups dir exists
New-Item -ItemType Directory -Force -Path $backupsDir | Out-Null

# Step 1. Sync welcome_sign.html into the repo
Write-Host "[1/4] Sync welcome_sign.html into repo..." -ForegroundColor Yellow
if (Test-Path $welcomeSrc) {
  Copy-Item $welcomeSrc $welcomeDst -Force
  Write-Host "      copied $welcomeSrc"
} else {
  Write-Host "      skipped, $welcomeSrc not found" -ForegroundColor DarkYellow
}

# Optional: also keep a copy of the live fridge sign in the customer folder
if (Test-Path $fridgeSrc) {
  $liveDst = Join-Path $backupsDir "fridge_wifi_welcome.html"
  Copy-Item $fridgeSrc $liveDst -Force
  Write-Host "      copied live fridge sign to $liveDst"
}

# Step 2. Git add / commit / push
Write-Host ""
Write-Host "[2/4] Git commit and push..." -ForegroundColor Yellow
Push-Location $repoRoot
try {
  git add . | Out-Null
  $status = git status --porcelain
  if ([string]::IsNullOrWhiteSpace($status)) {
    Write-Host "      nothing to commit"
  } else {
    $msg = "Backup $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
    git commit -m $msg | Out-Null
    git push
    Write-Host "      pushed: $msg" -ForegroundColor Green
  }
} catch {
  Write-Host "      git step failed: $_" -ForegroundColor Red
} finally {
  Pop-Location
}

# Step 3. Pi config backup tarball
Write-Host ""
Write-Host "[3/4] Pi config backup tarball..." -ForegroundColor Yellow
if (-not (Test-Path $piBackup)) {
  Write-Host "      $piBackup not found, skipping" -ForegroundColor DarkYellow
} else {
  Write-Host "      pushing backup script to Pi..."
  scp $piBackup "${Target}:/tmp/backup_pi_config.sh"
  if ($LASTEXITCODE -ne 0) { Write-Host "      scp failed" -ForegroundColor Red }

  Write-Host "      running backup on Pi..."
  ssh $Target "sudo bash /tmp/backup_pi_config.sh"
  if ($LASTEXITCODE -ne 0) { Write-Host "      remote backup failed" -ForegroundColor Red }

  Write-Host "      pulling tarball into $backupsDir ..."
  scp "${Target}:/tmp/pi-config-backup-*.tar.gz" $backupsDir
  if ($LASTEXITCODE -ne 0) {
    Write-Host "      scp pull failed" -ForegroundColor Red
  } else {
    $latest = Get-ChildItem $backupsDir -Filter "pi-config-backup-*.tar.gz" |
              Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($latest) {
      Write-Host "      saved $($latest.FullName)" -ForegroundColor Green
    }
  }
}

# Step 4. Omada Controller .cfg reminder
Write-Host ""
Write-Host "[4/4] Omada Controller .cfg" -ForegroundColor Yellow
Write-Host "      The Omada UI does not export over the API on this version."
Write-Host "      Open https://192.168.0.217:8043 -> gear icon -> Maintenance -> Backup & Restore -> Backup"
Write-Host "      Then move the .cfg from your Downloads to:"
Write-Host "      $backupsDir" -ForegroundColor Cyan
Write-Host ""

Write-Host "===========================================" -ForegroundColor Cyan
Write-Host " Backup complete." -ForegroundColor Green
Write-Host " Next: upload $backupsDir to Google Drive."
Write-Host "===========================================" -ForegroundColor Cyan
Write-Host ""
