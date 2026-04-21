#!/bin/bash
# Restores the Pi from a tarball created by backup_pi_config.sh.
# Run on a fresh Pi with sudo, after the base packages are installed
# (apt update, nginx, python3-venv, apache2-utils, cloudflared, Omada Controller).
# Usage: sudo bash restore_pi_config.sh /path/to/pi-config-backup-YYYY-MM-DD.tar.gz
set -e

TARBALL="$1"
if [ -z "$TARBALL" ] || [ ! -f "$TARBALL" ]; then
  echo "Usage: sudo bash restore_pi_config.sh <tarball>"
  exit 1
fi

STAGING=$(mktemp -d)
echo "[1/7] Extracting $TARBALL to $STAGING..."
tar xzf "$TARBALL" -C "$STAGING"

echo "[2/7] Restoring /opt/omada-auth..."
mkdir -p /opt/omada-auth
cp -a "$STAGING/opt-omada-auth/." /opt/omada-auth/ 2>/dev/null || echo "  no /opt/omada-auth in backup"
chown -R pi:pi /opt/omada-auth
# If venv is missing, recreate it
if [ ! -d /opt/omada-auth/venv ]; then
  echo "  venv missing, rebuilding..."
  sudo -u pi python3 -m venv /opt/omada-auth/venv
  sudo -u pi /opt/omada-auth/venv/bin/pip install --quiet flask requests
fi

echo "[3/7] Restoring nginx config and auth..."
if [ -f "$STAGING/etc-nginx/default" ]; then
  cp "$STAGING/etc-nginx/default" /etc/nginx/sites-enabled/default
fi
if [ -f "$STAGING/etc-nginx/htpasswd" ]; then
  cp "$STAGING/etc-nginx/htpasswd" /etc/nginx/.htpasswd
  chown root:www-data /etc/nginx/.htpasswd
  chmod 640 /etc/nginx/.htpasswd
fi

echo "[4/7] Restoring systemd units..."
if [ -d "$STAGING/etc-systemd" ]; then
  cp "$STAGING/etc-systemd/"*.service /etc/systemd/system/ 2>/dev/null || true
  cp "$STAGING/etc-systemd/"*.timer /etc/systemd/system/ 2>/dev/null || true
  systemctl daemon-reload
fi

echo "[5/7] Restoring web files..."
mkdir -p /var/www/html
cp -a "$STAGING/var-www/." /var/www/html/ 2>/dev/null || echo "  no /var/www in backup"
chown -R www-data:www-data /var/www/html

echo "[6/7] Restoring crontab for pi user..."
if [ -f "$STAGING/cron/pi-crontab.txt" ]; then
  crontab -u pi "$STAGING/cron/pi-crontab.txt"
fi

echo "[7/7] Restoring Omada Controller data (if present)..."
if [ -f "$STAGING/omada/omada-data.tar.gz" ]; then
  OMADA_BASE=""
  for d in /opt/tplink/EAPController /var/lib/tpeap /usr/share/tpeap; do
    if [ -d "$d" ]; then OMADA_BASE="$d"; break; fi
  done
  if [ -n "$OMADA_BASE" ]; then
    systemctl stop tpeap 2>/dev/null || true
    tar xzf "$STAGING/omada/omada-data.tar.gz" -C "$OMADA_BASE"
    chown -R omada:omada "$OMADA_BASE/data" 2>/dev/null || true
    systemctl start tpeap 2>/dev/null || true
    echo "  Omada data restored (Controller restarted, may take 2-3 min to be reachable)"
  else
    echo "  Omada Controller not installed on this Pi yet - install it first, then re-run this script"
  fi
fi

rm -rf "$STAGING"

echo
echo "Enabling and starting services..."
for svc in omada-auth cloudflared-tunnel tunnel-url-watcher.timer; do
  systemctl enable "$svc" 2>/dev/null || true
  systemctl restart "$svc" 2>/dev/null || true
done
nginx -t && systemctl reload nginx

echo
echo "Restore complete. Manual steps remaining:"
echo "  1. Install Tailscale: curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up"
echo "  2. Verify services: sudo systemctl is-active nginx omada-auth cloudflared-tunnel tunnel-url-watcher.timer tpeap"
echo "  3. Get current tunnel URL: sudo journalctl -u cloudflared-tunnel | grep trycloudflare.com | tail -1"
echo "  4. Test endpoints: curl http://127.0.0.1/reservation"
