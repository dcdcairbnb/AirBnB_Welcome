#!/usr/bin/env python3
"""
Add a single SSID to the Omada Controller and bind it to the existing portal.

Use when you want to broadcast a new network (e.g., second 2.4 GHz SSID for IoT
or a secondary guest network) and want guests to hit the same splash page.

Usage:
  python add_ssid.py customer_config.json ADMIN_USER ADMIN_PASS SSID PASSWORD [BAND]

BAND options:
  dual   both 2.4 and 5 GHz (default)
  2.4    2.4 GHz only
  5      5 GHz only

Example:
  python add_ssid.py customers/music_city_retreat/customer_config.json admin MusicCity2026 1011A2 NashRocks! 2.4
"""

import json
import sys

from setup_omada import OmadaClient


def main():
    if len(sys.argv) < 6:
        print("Usage: python add_ssid.py customer_config.json ADMIN_USER ADMIN_PASS SSID PASSWORD [BAND]")
        sys.exit(2)

    cfg_path = sys.argv[1]
    admin_user = sys.argv[2]
    admin_pass = sys.argv[3]
    ssid = sys.argv[4]
    ssid_pw = sys.argv[5]
    band = sys.argv[6] if len(sys.argv) >= 7 else "dual"

    with open(cfg_path) as f:
        cfg = json.load(f)

    pi_ip = cfg["pi_ip"]
    portal_name = cfg["property_name"]
    base_url = f"https://{pi_ip}:8043"

    print(f"Connecting to Omada Controller at {base_url}...")
    client = OmadaClient(base_url)
    client.info()
    client.login(admin_user, admin_pass)
    client.pick_site(preferred_name=portal_name)

    print(f"\nCreating WLAN '{ssid}' on band '{band}'...")
    wlan_id = client.create_wlan(ssid, ssid_pw, band=band)
    if not wlan_id:
        print("Failed to create or find WLAN. Aborting.")
        sys.exit(1)

    print(f"\nAttaching WLAN to portal '{portal_name}'...")
    ok = client.attach_wlan_to_portal(portal_name, wlan_id)

    print()
    if ok:
        print(f"Done. The EAP should start broadcasting '{ssid}' within 60 seconds.")
        print("Guests who join this SSID will hit the same splash page.")
    else:
        print("WLAN was created but could not be auto-attached to the portal.")
        print("Open the portal in the UI and add the new SSID under SSID & Network.")


if __name__ == "__main__":
    main()
