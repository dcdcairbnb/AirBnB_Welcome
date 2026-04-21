#!/bin/bash
# Emails the current Cloudflare Tunnel URL to the host when it changes.
# Runs every 10 min via systemd timer, plus once after cloudflared starts.

LAST_URL_FILE="/opt/omada-auth/last_tunnel_url.txt"
APPS_SCRIPT_URL="${APPS_SCRIPT_URL:-https://script.google.com/macros/s/AKfycbxYneJMWNnhuVd135ICINzIni3DB-EcFVx-r34JpH1IS6Mvjkga7I0tNpa7BXPhT-kIcw/exec}"

# Extract current URL from cloudflared logs
CURRENT_URL=$(journalctl -u cloudflared-tunnel --no-pager -n 500 2>/dev/null | grep -oE "https://[a-zA-Z0-9-]+\.trycloudflare\.com" | tail -1)

if [ -z "$CURRENT_URL" ]; then
  echo "No tunnel URL found in logs yet"
  exit 0
fi

LAST_URL=""
if [ -f "$LAST_URL_FILE" ]; then
  LAST_URL=$(cat "$LAST_URL_FILE")
fi

if [ "$CURRENT_URL" = "$LAST_URL" ]; then
  echo "Tunnel URL unchanged: $CURRENT_URL"
  exit 0
fi

echo "Tunnel URL changed: $LAST_URL -> $CURRENT_URL"

# POST to Apps Script to send email
curl -s -L -X POST "$APPS_SCRIPT_URL?admin=tunnelurl" \
  -H "Content-Type: application/json" \
  --data "{\"url\":\"$CURRENT_URL\"}" \
  > /dev/null

# Save the new URL so we only email on change
echo "$CURRENT_URL" > "$LAST_URL_FILE"
