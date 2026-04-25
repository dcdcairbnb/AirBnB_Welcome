#!/usr/bin/env python3
"""
Omada Controller API automation.

Creates/configures on the customer's Omada Controller:
  - Hotspot Operator account (used by omada_auth.py for portal auth)
  - WLAN broadcasting the guest SSID
  - Captive portal pointing at splash.html
  - Walled garden (pre-authentication access)
  - Auto-backup (daily, 7-day retention)
  - Manual backup immediately after config completes (saved locally)

Usage:
  python setup_omada.py customer_config.json ADMIN_USERNAME ADMIN_PASSWORD

Works on Omada Software Controller v5.9+.
Prints what succeeded and what needs manual follow-up.
"""

import json
import os
import sys
import urllib3
import requests
from datetime import datetime
from pathlib import Path

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

    def create_wlan(self, ssid, password, wpa="wpa2", band="dual", site_name=None):
        """Create a WLAN on the selected band(s).

        band options:
          dual    both 2.4 and 5 GHz (default)
          2.4     2.4 GHz only
          5       5 GHz only
        """
        url = f"{self.base}/{self.cid}/api/v2/sites/{self.site_id}/setting/wlans"
        band2g = band in ("dual", "2.4", "2g", "2.4g")
        band5g = band in ("dual", "5", "5g")
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
            "band2g": band2g,
            "band5g": band5g,
            "band6g": False,
        }
        r = self.s.post(url, json=payload, timeout=10)
        data = r.json()
        if data.get("errorCode") == 0:
            band_label = "2.4+5 GHz" if band2g and band5g else ("2.4 GHz" if band2g else "5 GHz")
            print(f"  WLAN '{ssid}' created on {band_label}")
            return data.get("result", {}).get("id")
        if "exist" in str(data.get("msg", "")).lower():
            print(f"  WLAN '{ssid}' already exists (skipping create)")
            return self.find_wlan_id(ssid)
        print(f"  WLAN creation failed: {data}")
        return None

    def find_wlan_id(self, ssid):
        """Look up an existing WLAN id by SSID."""
        url = f"{self.base}/{self.cid}/api/v2/sites/{self.site_id}/setting/wlans"
        try:
            r = self.s.get(url, timeout=10)
            data = r.json()
            wlans = data.get("result", {}).get("data", []) or data.get("result", [])
            for w in wlans:
                if w.get("ssid") == ssid or w.get("name") == ssid:
                    return w.get("id")
        except Exception:
            pass
        return None

    def find_portal_id(self, name):
        """Look up an existing portal id by name."""
        url = f"{self.base}/{self.cid}/api/v2/sites/{self.site_id}/setting/portals"
        try:
            r = self.s.get(url, timeout=10)
            data = r.json()
            portals = data.get("result", {}).get("data", []) or data.get("result", [])
            for p in portals:
                if p.get("name") == name:
                    return p.get("id"), p
        except Exception:
            pass
        return None, None

    def attach_wlan_to_portal(self, portal_name, wlan_id):
        """Add a WLAN id to an existing portal's wlanList."""
        portal_id, portal = self.find_portal_id(portal_name)
        if not portal_id:
            print(f"  Portal '{portal_name}' not found, cannot attach WLAN")
            return False
        existing = portal.get("wlanList", []) or []
        if wlan_id in existing:
            print(f"  WLAN already attached to portal '{portal_name}'")
            return True
        existing.append(wlan_id)
        url = f"{self.base}/{self.cid}/api/v2/sites/{self.site_id}/setting/portals/{portal_id}"
        payload = dict(portal)
        payload["wlanList"] = existing
        try:
            r = self.s.patch(url, json=payload, timeout=10)
            data = r.json()
            if data.get("errorCode") == 0:
                print(f"  WLAN attached to portal '{portal_name}'")
                return True
            r = self.s.put(url, json=payload, timeout=10)
            data = r.json()
            if data.get("errorCode") == 0:
                print(f"  WLAN attached to portal '{portal_name}'")
                return True
            print(f"  Portal update failed: {data}")
        except Exception as e:
            print(f"  Portal update error: {e}")
        return False

    def enable_auto_backup(self, keep_backups=7, occur_time="03:00"):
        """Enable daily auto backup. Tolerant of API path variations across versions."""
        candidates = [
            f"{self.base}/{self.cid}/api/v2/maintenance/autoBackupSetting",
            f"{self.base}/{self.cid}/api/v2/maintenance/controllerAutoBackupSetting",
        ]
        payload = {
            "enable": True,
            "mode": "daily",
            "keepBackups": keep_backups,
            "occurTime": occur_time,
        }
        for url in candidates:
            try:
                r = self.s.post(url, json=payload, timeout=10)
                data = r.json()
                if data.get("errorCode") == 0:
                    print(f"  Auto-backup enabled (daily {occur_time}, keep last {keep_backups})")
                    return True
            except Exception:
                continue
        print("  Auto-backup API not reachable. Enable in UI: Settings > Maintenance > Auto Backup")
        return False

    def trigger_backup_and_download(self, dest_dir):
        """Trigger a manual backup and download the .cfg file to dest_dir."""
        Path(dest_dir).mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_file = Path(dest_dir) / f"omada_backup_{timestamp}.cfg"

        create_candidates = [
            f"{self.base}/{self.cid}/api/v2/maintenance/controllerBackupFile",
            f"{self.base}/{self.cid}/api/v2/maintenance/backup",
        ]
        download_candidates = [
            f"{self.base}/{self.cid}/api/v2/maintenance/controllerBackupFile/download",
            f"{self.base}/{self.cid}/api/v2/maintenance/backup/download",
            f"{self.base}/{self.cid}/api/v2/files/backup",
        ]

        created = False
        for url in create_candidates:
            try:
                r = self.s.post(url, json={}, timeout=120)
                if r.status_code == 200 and r.headers.get("content-type", "").startswith("application/octet-stream"):
                    dest_file.write_bytes(r.content)
                    print(f"  Backup saved: {dest_file}")
                    return str(dest_file)
                data = r.json()
                if data.get("errorCode") == 0:
                    created = True
                    break
            except Exception:
                continue

        if not created:
            print("  Backup create API not reachable. Export manually from UI: Settings > Maintenance > Backup")
            return None

        for url in download_candidates:
            try:
                r = self.s.get(url, timeout=120, stream=True)
                if r.status_code == 200 and len(r.content) > 1000:
                    dest_file.write_bytes(r.content)
                    print(f"  Backup saved: {dest_file}")
                    return str(dest_file)
            except Exception:
                continue
        print("  Backup download API not reachable. File is on the Pi at /opt/tplink/EAPController/data/autobackup/")
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

    print("\n[1/7] Getting controller info...")
    client.info()

    print("\n[2/7] Logging in as admin...")
    client.login(admin_user, admin_pass)

    print("\n[3/7] Picking site...")
    client.pick_site(preferred_name=cfg.get("property_name"))

    print("\n[4/7] Creating Hotspot Operator account...")
    operator_pw = cfg.get("operator_password") or "portal_api_" + cfg["wifi_password"]
    client.create_operator("portal_api", operator_pw)

    print("\n[5/7] Creating WLANs and Portal...")
    primary_band = cfg.get("wifi_band", "dual")
    wlan_id = client.create_wlan(cfg["wifi_ssid"], cfg["wifi_password"], band=primary_band)
    portal_url = f"http://{pi_ip}/splash.html"
    landing_url = f"http://{pi_ip}/welcome_sign.html"
    client.create_portal(cfg["property_name"], cfg["wifi_ssid"], portal_url, landing_url, pi_ip, wlan_id)

    extra_wlan_ids = []
    for extra in cfg.get("extra_ssids", []):
        eid = client.create_wlan(
            extra["ssid"],
            extra["password"],
            band=extra.get("band", "dual"),
        )
        if eid:
            extra_wlan_ids.append(eid)
            client.attach_wlan_to_portal(cfg["property_name"], eid)

    print("\n[6/7] Enabling auto-backup...")
    client.enable_auto_backup(keep_backups=7, occur_time="03:00")

    print("\n[7/7] Creating manual backup...")
    slug = cfg.get("slug") or cfg.get("property_name", "customer").lower().replace(" ", "_")
    customer_dir = Path(cfg_path).resolve().parent
    backup_dir = customer_dir / "backups"
    backup_path = client.trigger_backup_and_download(str(backup_dir))

    print()
    print("=" * 60)
    print("Omada setup complete. Manual follow-up:")
    print("  1. In Omada Controller, add Apple TV MACs to Authentication-Free Client list")
    print("  2. Update omada_auth.py OMADA_USER/OMADA_PASS env vars to match the operator:")
    print(f"     OMADA_USER=portal_api")
    print(f"     OMADA_PASS={operator_pw}")
    print("     Then: sudo systemctl restart omada-auth")
    print("  3. Plug in the EAP, adopt it in Omada Controller > Devices")
    if backup_path:
        print(f"  4. Backup saved locally: {backup_path}")
        print("     Copy this .cfg to Google Drive for off-site recovery")
    else:
        print("  4. Export a backup manually from the UI:")
        print("     Settings > Maintenance > Backup & Restore > Backup")
        print(f"     Save the .cfg to {backup_dir} and to Google Drive")
    print("  5. Auto-backup runs daily at 03:00 on the Pi.")
    print("     Files live in /opt/tplink/EAPController/data/autobackup/ (in the omada-data volume)")
    print("=" * 60)


if __name__ == "__main__":
    main()
