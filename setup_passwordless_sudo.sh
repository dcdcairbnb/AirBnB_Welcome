#!/bin/bash
#
# setup_passwordless_sudo.sh
# Allows the pi user to run a focused list of admin commands without
# being prompted for a password. Required for deploy.ps1 to run end to end.
#
# Run on the Pi:
#   sudo bash setup_passwordless_sudo.sh
#
# Allowed commands (passwordless):
#   - cp, mv, chown, chmod  (deploying files into /opt and /var/www/html)
#   - systemctl              (restart/reload/status of services)
#   - journalctl             (read service journals)
#   - docker                 (Omada Controller container management)
#   - nginx, htpasswd        (nginx config test, password rotation)
#   - ss, lsof               (port and process checks for health script)
#   - tail, cat              (read service logs and config files)
#   - bash backup_pi_config.sh (run the backup tarball script)
#
# Everything else still requires a password.

set -e

if [ "$EUID" -ne 0 ]; then
  echo "Run with sudo: sudo bash $0"
  exit 1
fi

SUDOERS_FILE="/etc/sudoers.d/airbnb-welcome"
TARGET_USER="${SUDO_USER:-pi}"

cat > "$SUDOERS_FILE" <<EOF
# Airbnb Welcome system maintenance - passwordless commands for $TARGET_USER
# Created by setup_passwordless_sudo.sh
$TARGET_USER ALL=(ALL) NOPASSWD: /usr/bin/cp, /bin/cp
$TARGET_USER ALL=(ALL) NOPASSWD: /usr/bin/mv, /bin/mv
$TARGET_USER ALL=(ALL) NOPASSWD: /usr/bin/chown, /bin/chown
$TARGET_USER ALL=(ALL) NOPASSWD: /usr/bin/chmod, /bin/chmod
$TARGET_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl, /bin/systemctl
$TARGET_USER ALL=(ALL) NOPASSWD: /usr/bin/journalctl, /bin/journalctl
$TARGET_USER ALL=(ALL) NOPASSWD: /usr/bin/docker
$TARGET_USER ALL=(ALL) NOPASSWD: /usr/sbin/nginx
$TARGET_USER ALL=(ALL) NOPASSWD: /usr/bin/htpasswd
$TARGET_USER ALL=(ALL) NOPASSWD: /usr/bin/ss, /bin/ss
$TARGET_USER ALL=(ALL) NOPASSWD: /usr/bin/lsof
$TARGET_USER ALL=(ALL) NOPASSWD: /usr/bin/tail, /bin/tail
$TARGET_USER ALL=(ALL) NOPASSWD: /usr/bin/cat, /bin/cat
$TARGET_USER ALL=(ALL) NOPASSWD: /usr/bin/bash /home/$TARGET_USER/AirBnB_Welcome/backup_pi_config.sh
$TARGET_USER ALL=(ALL) NOPASSWD: /usr/bin/bash /tmp/backup_pi_config.sh
EOF

chmod 0440 "$SUDOERS_FILE"

# Validate before activating - if visudo fails, the file is already chmod'd safely.
if visudo -c -f "$SUDOERS_FILE"; then
  echo "OK: passwordless sudo configured for $TARGET_USER"
  echo "File: $SUDOERS_FILE"
else
  echo "FAIL: sudoers file did not validate. Removing."
  rm -f "$SUDOERS_FILE"
  exit 1
fi

echo
echo "Test it:"
echo "  sudo systemctl is-active omada-auth"
echo "Should return 'active' immediately with no password prompt."
