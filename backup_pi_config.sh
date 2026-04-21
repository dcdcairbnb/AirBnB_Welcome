#!/bin/bash
# Exports all customer-specific config from the Pi into a single tarball.
# Run on the Pi with sudo. Creates /tmp/pi-config-backup-YYYY-MM-DD.tar.gz
set -e

STAMP=$(date +%Y-%m-%d)
OUT="/tmp/pi-config-backup-${STAMP}.tar.gz"
STAGING=$(mktemp -d)

echo "[1/6] Staging Flask service files..."
mkdir -p "$STAGING/opt-omada-auth"
cp -a /opt/omada-auth/. "$STAGING/opt-omada-auth/" 2>/dev/null || true

echo "[2/6] Staging nginx config and auth..."
mkdir -p "$STAGING/etc-nginx"
cp /etc/nginx/sites-enabled/default "$STAGING/etc-nginx/default" 2>/dev/null || true
cp /etc/nginx/.htpasswd "$STAGING/etc-nginx/htpasswd" 2>/dev/null || true

echo "[3/6] Staging systemd units..."
mkdir -p "$STAGING/etc-systemd"
for svc in omada-auth.service cloudflared-tunnel.service tunnel-url-watcher.service tunnel-url-watcher.timer; do
  if [ -f "/etc/systemd/system/$svc" ]; then
    cp "/etc/systemd/system/$svc" "$STAGING/etc-systemd/"
  fi
done

echo "[4/6] Staging web files..."
mkdir -p "$STAGING/var-www"
cp -a /var/www/html/. "$STAGING/var-www/" 2>/dev/null || true

echo "[5/6] Exporting Omada Controller backup (may take 30s)..."
OMADA_BACKUP_DIR=""
for d in /opt/tplink/EAPController /var/lib/tpeap /usr/share/tpeap; do
  if [ -d "$d" ]; then OMADA_BACKUP_DIR="$d"; break; fi
done
if [ -n "$OMADA_BACKUP_DIR" ]; then
  # Find the DB backup tool and run it
  mkdir -p "$STAGING/omada"
  find "$OMADA_BACKUP_DIR" -name "db_backup*" -o -name "backup*.sh" 2>/dev/null | head -5 > "$STAGING/omada/backup_tools_found.txt" || true
  # Copy the Omada data directory so the customer can restore if needed
  tar czf "$STAGING/omada/omada-data.tar.gz" -C "$OMADA_BACKUP_DIR" data 2>/dev/null || echo "  (could not tar Omada data - may need manual export via UI)"
fi

echo "[6/6] Staging cron and crontab..."
mkdir -p "$STAGING/cron"
crontab -u pi -l > "$STAGING/cron/pi-crontab.txt" 2>/dev/null || true
ls /etc/cron.d/ > "$STAGING/cron/etc-cron-d.txt" 2>/dev/null || true

echo "Creating tarball $OUT..."
tar czf "$OUT" -C "$STAGING" .
rm -rf "$STAGING"
chown pi:pi "$OUT"

echo
echo "Done. Download it with:"
echo "  scp pi@100.76.203.111:$OUT ."
echo
ls -lh "$OUT"
