#!/bin/bash
# One-shot installer for the Omada Auth Bridge
# Run on the Pi (192.168.0.217) with sudo
set -e

INSTALL_DIR="/opt/omada-auth"
SERVICE_FILE="/etc/systemd/system/omada-auth.service"

echo "[1/5] Installing python3-venv if needed..."
apt-get update -qq
apt-get install -y python3-venv python3-pip

echo "[2/5] Creating ${INSTALL_DIR}..."
mkdir -p "$INSTALL_DIR"
cp omada_auth.py "$INSTALL_DIR/omada_auth.py"
chown -R pi:pi "$INSTALL_DIR"

echo "[3/5] Creating Python virtual environment and installing Flask + requests..."
sudo -u pi python3 -m venv "$INSTALL_DIR/venv"
sudo -u pi "$INSTALL_DIR/venv/bin/pip" install --quiet flask requests

echo "[4/5] Installing systemd service..."
cp omada-auth.service "$SERVICE_FILE"
systemctl daemon-reload
systemctl enable omada-auth
systemctl restart omada-auth

echo "[5/5] Reloading nginx with new proxy config..."
cp nginx-default.conf /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

echo
echo "Done. Service status:"
systemctl --no-pager status omada-auth | head -10
echo
echo "Test it:"
echo "  curl http://127.0.0.1:5000/health"
echo "  curl http://192.168.0.217/health  # via nginx proxy (should 404 since /health isn't proxied; this is expected)"
