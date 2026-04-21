#!/usr/bin/env python3
"""
Omada Controller API automation.

Creates/configures on the customer's Omada Controller:
  - Hotspot Operator account (used by omada_auth.py for portal auth)
  - WLAN broadcasting the guest SSID
  - Captive portal pointing at splash.html
  - Walled garden (pre-authentication access)

Usage:
  python setup_omada.py customer_config.json ADMIN_USERNAME ADMIN_PASSWORD

Works on Omada Software Controller v5.9+.
Prints what succeeded and what needs manual follow-up.
"""

import json
import sys
import urllib3
import requests

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


WALLED_GARDEN = [
    ("url", "script.google.com"),
    ("url", "script.googleusercontent.com"),
    ("url", "fonts.googleapis.com"),
    ("url", "fonts.gstatic.com"),
    ("url", "accounts.google.com"),
]


class OmadaClient:
    def __init__(self, base_url):
        self.base = base_url.rstrip("/")
        self.s = requests.Session()
        self.s.verify = False
        self.cid = None
        self.token = None
        self.site_id = None

    def info(self):
        r = self.s.get(f"{self.base}/api/info", timeout=10)
        r.raise_for_status()
        data = r.json()
        self.cid = data.get("result", {}).get("omadacId")
        if not self.cid:
            raise RuntimeError(f"No omadacId in /api/info response: {data}")
        print(f"  Controller ID: {self.cid}")
        return self.cid

    def login(self, user, pw):
        url = f"{self.base}/{self.cid}/api/v2/login"
        r = self.s.post(url, json={"username": user, "password": pw}, timeout=10)
        r.raise_for_status()
        data = r.json()
        if data.get("errorCode") != 0:
            raise RuntimeError(f"Admin login failed: {data}")
        self.token = data["result"]["token"]
        self.s.headers.update({"Csrf-Token": self.token})
        print("  Logged in as admin")

    def get_sites(self):
        r = self.s.get(f"{self.base}/{self.cid}/api/v2/sites?currentPage=1&currentPageSize=100", timeout=10)
        r.raise_for_status()
        data = r.json()
        sites = data.get("result", {}).get("data", [])
        print(f"  Found {len(sites)} site(s)")
        return sites

    def pick_site(self, preferred_name=None):
        sites = self.get_sites()
        if preferred_name:
            for s in sites:
                if s.get("name") == preferred_name:
                    self.site_id = s["id"]
                    return self.site_id
        # Default to first site
        if sites:
            self.site_id = sites[0]["id"]
            print(f"  Using site: {sites[0].get('name')} ({self.site_id})")
            return self.site_id
        raise RuntimeError("No sites found on controller")

    def create_operator(self, name, pw, site_name=None):
        """Create a Hotspot Operator account. Returns True if created or already exists."""
        url = f"{self.base}/{self.cid}/api/v2/hotspot/operators"
        payload = {
            "name": name,
            "password": pw,
            "description": "Created by setup_omada.py for portal auth",
            "role": 0,  # Administrator
            "allSite": False,
            "sites": [self.site_id],
        }
        r = self.s.post(url, json=payload, timeout=10)
        data = r.json()
        if data.get("errorCode") == 0:
            print(f"  Operator '{name}' created")
            return True
        # -23003 typically "operator already exists"
        if "exist" in str(data.get("msg", "")).lower():
            print(f"  Operator '{name}' already exists (reusing)")
            return True
        print(f"  Operator creation failed: {data}")
        return False

    def create_wlan(self, ssid, password, wpa="wpa2", site_name=None):
        url = f"{self.base}/{self.cid}/api/v2/sites/{self.site_id}/setting/wlans"
        payload = {
            "name": ssid,
            "ssid": ssid,
            "security": "wpa-personal",
            "wpaMode": "wpa2",
            "cipher": "ccmp",
            "psk": password,
            "broadcast": True,
            "accessControl": "none",
            "vlanEnable": False,
        }
        r = self.s.post(url, json=payload, timeout=10)
        data = r.json()
        if data.get("errorCode") == 0:
            print(f"  WLAN '{ssid}' created")
            return data.get("result", {}).get("id")
        if "exist" in str(data.get("msg", "")).lower():
            print(f"  WLAN '{ssid}' already exists (skipping create)")
            return None
        print(f"  WLAN creation failed: {data}")
        return None

    def create_portal(self, name, ssid, portal_url, landing_url, pi_ip, wlan_id=None):
        url = f"{self.base}/{self.cid}/api/v2/sites/{self.site_id}/setting/portals"
        pre_auth_entries = [
            {"type": "ip", "ip": f"{pi_ip}/32"},
        ]
        for kind, value in WALLED_GARDEN:
            pre_auth_entries.append({"type": kind, "url": value} if kind == "url" else {"type": kind, "ip": value})
        payload = {
            "name": name,
            "status": True,
            "authType": "externalPortal",
            "customPortalType": "url",
            "portalUrl": portal_url,
            "httpsRedirect": False,
            "landingPageType": "promotional",
            "promotionalUrl": landing_url,
            "preAuthAccessList": pre_auth_entries,
        }
        # Attach to the SSID (API expects ssidList or similar)
        if wlan_id:
            payload["wlanList"] = [wlan_id]
        r = self.s.post(url, json=payload, timeout=10)
        data = r.json()
        if data.get("errorCode") == 0:
            print(f"  Portal '{name}' created")
            return data.get("result", {}).get("id")
        if "exist" in str(data.get("msg", "")).lower():
            print(f"  Portal '{name}' already exists (skipping)")
            return None
        print(f"  Portal creation failed: {data}")
        return None


def main():
    if len(sys.argv) != 4:
        print("Usage: python setup_omada.py customer_config.json ADMIN_USER ADMIN_PASS")
        sys.exit(2)

    cfg_path, admin_user, admin_pass = sys.argv[1], sys.argv[2], sys.argv[3]
    with open(cfg_path) as f:
        cfg = json.load(f)

    pi_ip = cfg["pi_ip"]
    base_url = f"https://{pi_ip}:8043"

    print(f"Connecting to Omada Controller at {base_url}...")
    client = OmadaClient(base_url)

    print("\n[1/5] Getting controller info...")
    client.info()

    print("\n[2/5] Logging in as admin...")
    client.login(admin_user, admin_pass)

    print("\n[3/5] Picking site...")
    client.pick_site(preferred_name=cfg.get("property_name"))

    print("\n[4/5] Creating Hotspot Operator account...")
    operator_pw = cfg.get("operator_password") or "portal_api_" + cfg["wifi_password"]
    client.create_operator("portal_api", operator_pw)

    print("\n[5/5] Creating WLAN and Portal...")
    wlan_id = client.create_wlan(cfg["wifi_ssid"], cfg["wifi_password"])
    portal_url = f"http://{pi_ip}/splash.html"
    landing_url = f"http://{pi_ip}/welcome_sign.html"
    client.create_portal(cfg["property_name"], cfg["wifi_ssid"], portal_url, landing_url, pi_ip, wlan_id)

    print()
    print("=" * 60)
    print("Omada setup complete. Manual follow-up:")
    print("  1. In Omada Controller, add Apple TV MACs to Authentication-Free Client list")
    print("  2. Update omada_auth.py OMADA_USER/OMADA_PASS env vars to match the operator:")
    print(f"     OMADA_USER=portal_api")
    print(f"     OMADA_PASS={operator_pw}")
    print("     Then: sudo systemctl restart omada-auth")
    print("  3. Plug in the EAP, adopt it in Omada Controller → Devices")
    print("=" * 60)


if __name__ == "__main__":
    main()
