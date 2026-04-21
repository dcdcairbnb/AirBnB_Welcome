#!/bin/bash
# Configure log rotation so nginx + systemd journal can't fill the SD card.
# Run on the Pi with sudo.
set -e

echo "[1/3] Verifying nginx logrotate config..."
if [ -f /etc/logrotate.d/nginx ]; then
  echo "  nginx logrotate already configured at /etc/logrotate.d/nginx"
  head -5 /etc/logrotate.d/nginx
else
  cat > /etc/logrotate.d/nginx <<'EOF'
/var/log/nginx/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 www-data adm
    sharedscripts
    prerotate
        if [ -d /etc/logrotate.d/httpd-prerotate ]; then \
            run-parts /etc/logrotate.d/httpd-prerotate; \
        fi \
    endscript
    postrotate
        invoke-rc.d nginx rotate >/dev/null 2>&1
    endscript
}
EOF
  echo "  nginx logrotate config installed"
fi

echo
echo "[2/3] Configuring systemd journal size limits..."
mkdir -p /etc/systemd/journald.conf.d
cat > /etc/systemd/journald.conf.d/size-limits.conf <<'EOF'
[Journal]
# Cap total journal size at 500 MB across all logs
SystemMaxUse=500M
# Each journal file can be up to 50 MB before rotating
SystemMaxFileSize=50M
# Keep logs for at most 30 days
MaxRetentionSec=30day
EOF
systemctl restart systemd-journald
echo "  journal size limits applied"

echo
echo "[3/3] Current disk usage:"
du -sh /var/log/journal /var/log/nginx 2>/dev/null || true
df -h /

echo
echo "Log rotation setup complete."
echo "Verify nginx rotation:  sudo logrotate -d /etc/logrotate.d/nginx"
echo "Verify journal size:    sudo journalctl --disk-usage"
