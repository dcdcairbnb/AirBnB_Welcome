#!/usr/bin/env python3
"""
Standalone Omada Controller backup script.

Triggers a fresh manual backup via API and saves the .cfg file locally.
Run this before any risky change (Docker image swap, OS upgrade, hardware move).

Usage:
  python backup_omada.py customer_config.json ADMIN_USERNAME ADMIN_PASSWORD

Saves to: <customer_dir>/backups/omada_backup_<timestamp>.cfg
"""

import json
import sys
from pathlib import Path

from setup_omada import OmadaClient


def main():
    if len(sys.argv) != 4:
        print("Usage: python backup_omada.py customer_config.json ADMIN_USER ADMIN_PASS")
        sys.exit(2)

    cfg_path, admin_user, admin_pass = sys.argv[1], sys.argv[2], sys.argv[3]
    with open(cfg_path) as f:
        cfg = json.load(f)

    pi_ip = cfg["pi_ip"]
    base_url = f"https://{pi_ip}:8043"

    print(f"Connecting to Omada Controller at {base_url}...")
    client = OmadaClient(base_url)
    client.info()
    client.login(admin_user, admin_pass)

    customer_dir = Path(cfg_path).resolve().parent
    backup_dir = customer_dir / "backups"
    print(f"\nCreating backup in {backup_dir}...")
    backup_path = client.trigger_backup_and_download(str(backup_dir))

    if backup_path:
        print(f"\nBackup complete: {backup_path}")
        print("Copy this file to Google Drive for off-site recovery.")
    else:
        print("\nBackup failed via API. Export manually from the UI.")
        sys.exit(1)


if __name__ == "__main__":
    main()
