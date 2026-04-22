#!/usr/bin/env python3
"""
Healthchecks.io monitoring setup.

Creates a monitoring check for the customer's Pi and installs the cron job
to ping it every hour. If the Pi stops pinging, Healthchecks emails you.

Get a Healthchecks API key at: https://healthchecks.io/projects/ -> API Access

Usage:
    python setup_healthchecks.py customer_config.json HC_API_KEY
"""

import json
import subprocess
import sys
import requests


HC_API_URL = "https://healthchecks.io/api/v3/checks/"


def main():
    if len(sys.argv) != 3:
        print("Usage: python setup_healthchecks.py customer_config.json HC_API_KEY")
        sys.exit(2)

    cfg_path, api_key = sys.argv[1], sys.argv[2]
    with open(cfg_path) as f:
        cfg = json.load(f)

    check_name = f"{cfg['property_name']} Pi"
    pi_ip = cfg["pi_ip"]

    print(f"Creating Healthchecks check '{check_name}'...")
    resp = requests.post(
        HC_API_URL,
        headers={"X-Api-Key": api_key, "Content-Type": "application/json"},
        json={
            "name": check_name,
            "tags": "airbnb pi",
            "timeout": 3600,   # expect ping every hour
            "grace": 3600,     # grace period of 1 hour before alerting
            "unique": ["name"] # don't create duplicate if we re-run
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    ping_url = data.get("ping_url")
    if not ping_url:
        print(f"Failed to get ping URL: {data}")
        sys.exit(1)
    print(f"  Ping URL: {ping_url}")

    # Save back into customer config
    cfg["healthchecks_ping_url"] = ping_url
    with open(cfg_path, "w") as f:
        json.dump(cfg, f, indent=2)

    # Install cron job via SSH
    cron_line = f"0 * * * * curl -fsS -m 10 --retry 3 {ping_url} > /dev/null"
    ssh_cmd = (
        f'(crontab -l 2>/dev/null | grep -v "hc-ping.com"; echo "{cron_line}") | crontab -'
    )

    print(f"\nInstalling cron job on pi@{pi_ip}...")
    try:
        result = subprocess.run(
            ["ssh", f"pi@{pi_ip}", ssh_cmd],
            timeout=30,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"  SSH failed: {result.stderr}")
            print(f"  Manual fallback: ssh pi@{pi_ip} and run:")
            print(f"    (crontab -l; echo '{cron_line}') | crontab -")
            sys.exit(1)
        print("  Cron job installed")
    except Exception as e:
        print(f"  SSH error: {e}")
        print(f"  Manual fallback: ssh pi@{pi_ip} and run:")
        print(f"    (crontab -l; echo '{cron_line}') | crontab -")
        sys.exit(1)

    # Trigger one ping right now so the check turns green
    print("\nSending first ping...")
    try:
        requests.get(ping_url, timeout=5)
        print("  First ping sent - check should be green within a minute")
    except Exception as e:
        print(f"  First ping failed (not fatal): {e}")

    print()
    print("=" * 60)
    print(f"Healthchecks monitoring active for {cfg['property_name']}.")
    print(f"View at: https://healthchecks.io/checks/")
    print(f"Pi will ping every hour. Alert email fires if 2+ pings are missed.")
    print(f"Ping URL saved to {cfg_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
