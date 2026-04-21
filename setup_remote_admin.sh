#!/bin/bash
# One-shot installer: basic auth for /admin + Cloudflare Tunnel for remote access
# Usage: sudo bash setup_remote_admin.sh ADMIN_USERNAME ADMIN_PASSWORD
set -e

USER_NAME="${1:-dan}"
USER_PASS="${2:-change_me_please}"

echo "[1/4] Installing apache2-utils (for htpasswd) and curl..."
apt-get update -qq
apt-get install -y apache2-utils curl

echo "[2/4] Creating /etc/nginx/.htpasswd with user '$USER_NAME'..."
htpasswd -bc /etc/nginx/.htpasswd "$USER_NAME" "$USER_PASS"
chown root:www-data /etc/nginx/.htpasswd
chmod 640 /etc/nginx/.htpasswd

echo "[3/4] Installing cloudflared..."
if ! command -v cloudflared >/dev/null 2>&1; then
  ARCH=$(dpkg --print-architecture)
  if [ "$ARCH" = "arm64" ]; then
    URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb"
  elif [ "$ARCH" = "armhf" ]; then
    URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm.deb"
  else
    URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb"
  fi
  curl -L -o /tmp/cloudflared.deb "$URL"
  dpkg -i /tmp/cloudflared.deb
fi
echo "cloudflared installed: $(cloudflared --version)"

echo "[4/4] Installing cloudflared as a quick-tunnel systemd service..."
cat > /etc/systemd/system/cloudflared-tunnel.service <<'EOF'
[Unit]
Description=Cloudflare Quick Tunnel for Pi
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/cloudflared tunnel --url http://localhost:80 --no-autoupdate
Restart=on-failure
RestartSec=10
User=root

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable cloudflared-tunnel
systemctl restart cloudflared-tunnel

echo
echo "Waiting 10 seconds for the tunnel to connect..."
sleep 10

echo
echo "Your public URL (admin available at this URL + /admin):"
journalctl -u cloudflared-tunnel --no-pager -n 50 | grep -oE "https://[a-zA-Z0-9-]+\.trycloudflare\.com" | head -1

echo
echo "Reloading nginx to apply basic auth..."
nginx -t && systemctl reload nginx

echo
echo "Done. To see the tunnel URL later:"
echo "  sudo journalctl -u cloudflared-tunnel --no-pager -n 50 | grep trycloudflare.com"
echo
echo "Admin credentials: username=$USER_NAME password=$USER_PASS"
