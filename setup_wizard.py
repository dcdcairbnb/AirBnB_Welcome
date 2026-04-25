#!/usr/bin/env python3
"""
New Customer Setup Wizard
Interactively collects customer info and generates a deploy-ready kit.

Usage:
    python setup_wizard.py

Output: ./customers/<property_slug>/ folder with customized files.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
CUSTOMERS_DIR = REPO_ROOT / "customers"

BANNER = """
============================================================
  AIRBNB GUEST WIFI + WELCOME SIGN - NEW CUSTOMER WIZARD
============================================================
This wizard collects your customer's info and generates a
deploy-ready kit. You'll still do these manual steps after:
  1. Google Sheet + Apps Script (~5 min in browser)
  2. Omada Controller portal config (~10 min in Controller UI)
  3. EAP adoption + SSID creation (~5 min)
  4. Tailscale install on the Pi for your remote support
"""


def ask(prompt, default=None, required=True, validator=None):
    while True:
        shown = prompt
        if default is not None:
            shown = f"{prompt} [{default}]"
        value = input(f"{shown}: ").strip()
        if not value:
            if default is not None:
                value = default
            elif required:
                print("  (required)")
                continue
            else:
                value = ""
        if validator:
            err = validator(value)
            if err:
                print(f"  {err}")
                continue
        return value


def ask_yes_no(prompt, default=True):
    hint = "Y/n" if default else "y/N"
    while True:
        v = input(f"{prompt} [{hint}]: ").strip().lower()
        if not v:
            return default
        if v in ("y", "yes"):
            return True
        if v in ("n", "no"):
            return False


def ask_multi_url(prompt):
    print(f"{prompt} (blank line to finish)")
    urls = []
    while True:
        v = input(f"  URL {len(urls) + 1}: ").strip()
        if not v:
            break
        if not v.startswith("http"):
            print("  must start with http")
            continue
        urls.append(v)
    return urls


def slugify(name):
    s = re.sub(r"[^a-zA-Z0-9]+", "-", name.lower()).strip("-")
    return s or "customer"


def collect_config():
    print(BANNER)
    cfg = {}

    print("\n--- Property basics ---")
    cfg["property_name"] = ask("Property name (e.g., Music City Retreat)")
    cfg["location_label"] = ask("Location label shown on pages (e.g., Nashville)")
    cfg["property_city"] = ask("City for event feed (e.g., Nashville)", default=cfg["location_label"])
    cfg["property_state"] = ask("State code (e.g., TN)").upper()
    cfg["host_email"] = ask("Host email for alerts (e.g., host@gmail.com)")

    print("\n--- Guest WiFi ---")
    cfg["wifi_ssid"] = ask("Guest WiFi SSID")
    cfg["wifi_password"] = ask("Guest WiFi password")
    cfg["wifi_band"] = ask("Primary SSID band (dual, 2.4, or 5)", default="dual")

    print("\n--- Extra SSIDs (optional) ---")
    print("Add any additional networks the EAP should broadcast that use the same splash page.")
    print("Common use: a 2.4 GHz only SSID for IoT devices or a secondary guest network.")
    cfg["extra_ssids"] = []
    while True:
        more = ask("Add an extra SSID? (y/n)", default="n").lower()
        if more != "y":
            break
        extra_ssid = ask("  SSID name")
        extra_pw = ask("  Password")
        extra_band = ask("  Band (dual, 2.4, or 5)", default="2.4")
        cfg["extra_ssids"].append({
            "ssid": extra_ssid,
            "password": extra_pw,
            "band": extra_band,
        })

    print("\n--- Pi ---")
    cfg["pi_ip"] = ask("Pi local IP address (e.g., 192.168.0.217)")
    cfg["admin_username"] = ask("Admin username for remote admin page", default="dan")
    cfg["admin_password"] = ask("Admin password for remote admin page")

    print("\n--- iCal feeds (Airbnb + VRBO) ---")
    print("Get Airbnb iCal: Airbnb host -> Listing -> Pricing & Availability -> Sync calendars -> Export")
    print("Get VRBO iCal: VRBO host dashboard -> Calendar -> Import/Export")
    cfg["ical_urls"] = ask_multi_url("Paste each iCal URL on its own line")

    print("\n--- Google ---")
    cfg["sheet_id"] = ask("Google Sheet ID (from the Sheet URL - paste just the ID)")
    cfg["apps_script_url"] = ask(
        "Apps Script web app URL (get after you deploy the Apps Script)",
        default="REPLACE_AFTER_DEPLOY",
        required=False,
    )

    print("\n--- Ticketmaster (for events feed) ---")
    cfg["ticketmaster_key"] = ask(
        "Ticketmaster API key",
        default="rAkV87yVeExNjYMqmRPpSppvLcXNWzdG",
    )

    print("\n--- Cross-promo (optional) ---")
    cfg["promo_enabled"] = ask_yes_no("Add 'Also check out our other property' section?", default=False)
    if cfg["promo_enabled"]:
        cfg["promo_name"] = ask("Other property name")
        cfg["promo_location"] = ask("Other property location (e.g., 'Silverthorne, Colorado')")
        cfg["promo_tagline"] = ask("One-line tagline")
        cfg["promo_url"] = ask("Airbnb listing URL")

    print("\n--- Content ---")
    cfg["hero_image"] = ask("Hero image filename (copy the jpg into the kit folder)", default="hero.jpg")
    print("NOTE: The wizard will copy welcome_sign.html and welcome_tv.html templates.")
    print("      You'll need to manually edit the restaurants/rooftops/things-to-do lists")
    print("      in those files for this customer's city. They start with the Nashville template.")

    print("\n--- TV display (optional) ---")
    cfg["has_fire_stick"] = ask_yes_no("Does this property have an Amazon Fire Stick on a TV for kiosk display?", default=False)
    if cfg["has_fire_stick"]:
        print("  Good. The wizard will include Fire Stick kiosk setup in NEXT_STEPS.md.")
    else:
        print("  Default setup uses the printable QR code on the fridge (no TV display).")

    print("\n--- Guest name greeting ---")
    print("1 = Auto-detect: scans their Gmail for Airbnb emails + manual admin fallback")
    print("2 = Manual only: owner sets name via admin page, 10am email reminder")
    print("3 = Generic: never show guest name, just 'Welcome to [Property]'")
    while True:
        choice = ask("Pick 1, 2, or 3", default="2")
        if choice in ("1", "2", "3"):
            cfg["greeting_mode"] = {"1": "auto", "2": "manual", "3": "generic"}[choice]
            break

    return cfg


def substitute(text, cfg):
    """Replace template values in a file's text."""
    ical_block = ",\n    ".join(f"'{u}'" for u in cfg["ical_urls"])
    apps_script_url = cfg.get("apps_script_url", "REPLACE_AFTER_DEPLOY")
    subs = {
        "__PROPERTY_NAME__": cfg["property_name"],
        "__LOCATION_LABEL__": cfg["location_label"],
        "__PROPERTY_CITY__": cfg["property_city"],
        "__PROPERTY_STATE__": cfg["property_state"],
        "__HOST_EMAIL__": cfg["host_email"],
        "__WIFI_SSID__": cfg["wifi_ssid"],
        "__WIFI_PASSWORD__": cfg["wifi_password"],
        "__PI_IP__": cfg["pi_ip"],
        "__SHEET_ID__": cfg["sheet_id"],
        "__APPS_SCRIPT_URL__": apps_script_url,
        "__TICKETMASTER_KEY__": cfg["ticketmaster_key"],
        "__ADMIN_USERNAME__": cfg["admin_username"],
        "__ICAL_URLS_BLOCK__": ical_block,
        "__HERO_IMAGE__": cfg["hero_image"],
    }
    for k, v in subs.items():
        text = text.replace(k, v)
    return text


def copy_and_substitute(src, dst, cfg):
    with open(src, "r", encoding="utf-8") as f:
        text = f.read()
    text = substitute(text, cfg)
    with open(dst, "w", encoding="utf-8") as f:
        f.write(text)


def generate_kit(cfg):
    slug = slugify(cfg["property_name"])
    out = CUSTOMERS_DIR / slug
    if out.exists():
        if not ask_yes_no(f"\nFolder {out} exists. Overwrite?", default=False):
            print("Aborted.")
            sys.exit(1)
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    # Save the config
    with open(out / "customer_config.json", "w") as f:
        json.dump(cfg, f, indent=2)

    # Files that get hardcoded config injected
    for name in ("splash.html", "welcome_sign.html", "welcome_tv.html", "fridge_qr.html",
                 "omada_auth.py",
                 "apps-script-code.gs", "nginx-default.conf", "setup_omada_auth.sh",
                 "setup_remote_admin.sh", "setup_log_rotation.sh", "backup_pi_config.sh",
                 "restore_pi_config.sh", "omada-auth.service", "email_tunnel_url.sh",
                 "tunnel-url-watcher.service", "tunnel-url-watcher.timer",
                 "setup_omada.py", "setup_healthchecks.py", "setup_passwordless_sudo.sh",
                 "check_health.sh", "check_health.ps1", "deploy.ps1",
                 "backup_omada.py", "add_ssid.py",
                 "backup_all.ps1", "backup_all.bat"):
        src = REPO_ROOT / name
        if src.exists():
            # For now, just copy - the real customer should substitute after understanding
            shutil.copy(src, out / name)

    # Replace Nashville-specific hardcoded values with customer values in the key files
    for name in ("splash.html", "welcome_sign.html", "welcome_tv.html"):
        path = out / name
        if not path.exists():
            continue
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        text = text.replace("Music City Retreat", cfg["property_name"])
        text = text.replace("Nashville", cfg["location_label"])
        text = text.replace("1011A2-5G", cfg["wifi_ssid"])
        text = text.replace("NashRocks!", cfg["wifi_password"])
        text = text.replace("192.168.0.217", cfg["pi_ip"])
        text = text.replace("living-room.jpg", cfg["hero_image"])
        # In generic greeting mode, disable the guest name substitution in JS
        if cfg.get("greeting_mode") == "generic":
            text = text.replace("data.guest_name", "false /* generic mode */")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    # Templatize the printable fridge QR sign (separate handling because the QR data
    # parameters need to be URL-encoded, not just text-substituted)
    fridge_path = out / "fridge_qr.html"
    if fridge_path.exists():
        from urllib.parse import quote
        wifi_qr_payload = f"WIFI:T:WPA;S:{cfg['wifi_ssid']};P:{cfg['wifi_password']};;"
        welcome_qr_payload = f"http://{cfg['pi_ip']}/welcome_sign.html"
        with open(fridge_path, "r", encoding="utf-8") as f:
            text = f.read()
        text = text.replace("Music City Retreat", cfg["property_name"])
        text = text.replace("Nashville, TN", f"{cfg.get('location_label', cfg.get('property_city', ''))}, {cfg['property_state']}")
        text = text.replace("1011A2-5G", cfg["wifi_ssid"])
        text = text.replace("NashRocks!", cfg["wifi_password"])
        text = text.replace("192.168.0.217", cfg["pi_ip"])
        text = text.replace("__WIFI_QR_DATA__", quote(wifi_qr_payload, safe=""))
        text = text.replace("__WELCOME_QR_DATA__", quote(welcome_qr_payload, safe=""))
        with open(fridge_path, "w", encoding="utf-8") as f:
            f.write(text)

    # Update omada_auth.py
    path = out / "omada_auth.py"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        # Swap out Nashville iCal URLs with customer's
        ical_py = ",\n    ".join(f'"{u}"' for u in cfg["ical_urls"])
        text = re.sub(
            r'ICAL_URLS = \[u\.strip\(\) for u in os\.environ\.get\([^)]+\)\.split\(","\) if u\.strip\(\)\]',
            f'ICAL_URLS = [\n    {ical_py}\n]',
            text,
        )
        text = text.replace("rAkV87yVeExNjYMqmRPpSppvLcXNWzdG", cfg["ticketmaster_key"])
        text = text.replace('TM_CITY", "Nashville"', f'TM_CITY", "{cfg["property_city"]}"')
        text = text.replace('TM_STATE", "TN"', f'TM_STATE", "{cfg["property_state"]}"')
        if cfg["apps_script_url"] != "REPLACE_AFTER_DEPLOY":
            text = re.sub(
                r'"https://script\.google\.com/macros/s/[^"]+"',
                f'"{cfg["apps_script_url"]}"',
                text,
            )
        text = text.replace("192.168.0.217", cfg["pi_ip"])
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    # Update apps-script-code.gs with real values
    path = out / "apps-script-code.gs"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        text = text.replace("'1yKriONwlQ1PFUf3Qkwqns7MVl42NNXfJH0KhxdivCzw'", f"'{cfg['sheet_id']}'")
        text = text.replace("'Music City Retreat'", f"'{cfg['property_name']}'")
        text = text.replace("'1011A2-5G'", f"'{cfg['wifi_ssid']}'")
        text = text.replace("'NashRocks!'", f"'{cfg['wifi_password']}'")
        text = text.replace("192.168.0.217", cfg["pi_ip"])
        text = text.replace("'jayhawks01@gmail.com'", f"'{cfg['host_email']}'")
        # Update ICAL_URLS block
        ical_js = ",\n  ".join(f"'{u}'" for u in cfg["ical_urls"])
        text = re.sub(
            r"var ICAL_URLS = \[[^\]]+\];",
            f"var ICAL_URLS = [\n  {ical_js}\n];",
            text,
            flags=re.DOTALL,
        )
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    # Deploy script
    deploy_script = f"""#!/bin/bash
# Deploy this customer's kit to their Pi. Run from this folder.
# Usage: ./deploy.sh  (on any machine with ssh to the Pi)
set -e

PI_USER="pi"
PI_IP="{cfg['pi_ip']}"

echo "Pushing all files to /tmp on Pi..."
scp splash.html welcome_sign.html welcome_tv.html $HERO_IMAGE_FILE \\
    omada_auth.py omada-auth.service nginx-default.conf \\
    email_tunnel_url.sh tunnel-url-watcher.service tunnel-url-watcher.timer \\
    setup_omada_auth.sh setup_remote_admin.sh setup_log_rotation.sh \\
    backup_pi_config.sh restore_pi_config.sh \\
    ${{PI_USER}}@${{PI_IP}}:/tmp/

echo "Running setup on Pi..."
ssh -t ${{PI_USER}}@${{PI_IP}} "cd /tmp && \\
  sudo bash setup_omada_auth.sh && \\
  sudo cp splash.html welcome_sign.html welcome_tv.html ${{HERO_IMAGE_FILE:-hero.jpg}} /var/www/html/ && \\
  sudo chown www-data:www-data /var/www/html/* && \\
  sudo cp nginx-default.conf /etc/nginx/sites-enabled/default && \\
  sudo nginx -t && sudo systemctl reload nginx && \\
  sudo bash setup_remote_admin.sh {cfg['admin_username']} '{cfg['admin_password']}' && \\
  sudo bash setup_log_rotation.sh && \\
  sudo cp email_tunnel_url.sh /opt/omada-auth/ && \\
  sudo chmod +x /opt/omada-auth/email_tunnel_url.sh && \\
  sudo cp tunnel-url-watcher.service tunnel-url-watcher.timer /etc/systemd/system/ && \\
  sudo systemctl daemon-reload && \\
  sudo systemctl enable --now tunnel-url-watcher.timer"

echo "Deploy complete."
"""
    deploy_path = out / "deploy.sh"
    with open(deploy_path, "w", encoding="utf-8") as f:
        f.write(deploy_script.replace("$HERO_IMAGE_FILE", cfg["hero_image"]))
    os.chmod(deploy_path, 0o755)

    # Manual steps instructions
    next_steps = f"""# NEXT STEPS for {cfg['property_name']}

The wizard generated a deploy-ready kit. Here's what to do:

## 1. Copy the hero image
Put the photo for the splash page into this folder as: `{cfg['hero_image']}`

## 2. Edit the welcome pages for this city (restaurants, rooftops, things to do)
The templates use Nashville content as a placeholder. Edit:
- welcome_sign.html
- welcome_tv.html
Replace the restaurant/rooftop/things-to-do lists with ones for {cfg['property_city']}.

## 3. Google setup (manual, 10 min)
1. Create a Google Sheet titled "{cfg['property_name']} - Guest Log"
2. The Sheet ID you entered is: {cfg['sheet_id']}
   (If you haven't created it yet, do so now and put the ID here.)
3. Go to script.google.com, New project, rename to "{cfg['property_name']} Portal"
4. Paste the contents of apps-script-code.gs into Code.gs
5. Save, Deploy → New deployment → Web app, Execute as: Me, Access: Anyone
6. Copy the /exec URL from the deployment
7. Run these once from the Apps Script editor (function dropdown, then Run):
   - setupCheckinReminderTrigger (daily 10am email reminder)
   - setupWeeklyBackupTrigger (Sunday 3am Sheet backup)
{AUTO_DETECT_STEP}
8. Go to the editor, update ICAL_URLS with Ticketmaster API access if you re-authorize

## 4. Provide the Apps Script URL to the Pi
Edit omada_auth.py in this folder and replace `REPLACE_AFTER_DEPLOY`
(if shown) with the /exec URL you copied in step 3.7.

Or rerun the wizard and enter the URL when prompted.

## 5. Deploy to the Pi
```
./deploy.sh
```
(Requires ssh access to pi@{cfg['pi_ip']}.)

## 6. Omada Controller setup

### Option A: Automated (recommended)
```
python setup_omada.py customer_config.json YOUR_OMADA_ADMIN_USER YOUR_OMADA_ADMIN_PASS
```
This creates the operator account, WLAN, captive portal, and walled garden automatically.

You'll still manually add Apple TV MACs to Authentication-Free Client list and plug in/adopt the EAP.

### Option B: Manual (if the API automation fails)
Log in to https://{cfg['pi_ip']}:8043/

1. Settings → Wireless Networks → Create WLAN:
   - SSID: {cfg['wifi_ssid']}
   - Password: {cfg['wifi_password']}
   - Security: WPA2-Personal

2. Settings → Authentication → Portal → Create:
   - Name: {cfg['property_name']}
   - SSID: {cfg['wifi_ssid']}
   - Authentication Type: External Portal Server
   - Custom Portal Server URL: http://{cfg['pi_ip']}/splash.html
   - Landing Page → Promotional URL: http://{cfg['pi_ip']}/welcome_sign.html

3. Settings → Authentication → Portal → Access Control:
   - Enable Pre-Authentication Access, add:
     * IP Range: {cfg['pi_ip']}/32
     * URL: script.google.com
     * URL: script.googleusercontent.com
     * URL: fonts.googleapis.com
     * URL: fonts.gstatic.com
     * URL: accounts.google.com
   - Enable Authentication-Free Client, add MACs for: Apple TVs, smart TVs, owner devices

4. Settings → Hotspot → Operators → Create:
   - Username: portal_api
   - Password: (strong password - store in your password manager)
   - Role: Administrator
   - Site Privileges: this site
5. Update omada_auth.py on the Pi with the operator username/password (env vars or inline), then `sudo systemctl restart omada-auth`.

## 7. Adopt the EAP
1. Plug the EAP into the customer's router with PoE+ or DC power
2. Wait 2 min, go to Omada Controller → Devices, click Adopt
3. Wait for it to finish provisioning
4. Your SSID should start broadcasting

## 8. Install Tailscale for your remote admin
```
ssh pi@{cfg['pi_ip']}
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```
Open the printed URL in your Tailscale admin account.

## 9. Set up Healthchecks.io monitoring (automated)
Get your Healthchecks.io API key once at https://healthchecks.io/projects -> API Access. Then:
```
python setup_healthchecks.py customer_config.json YOUR_HC_API_KEY
```
This creates the check, installs the cron job on the Pi, and sends a first ping.

## 9b. Add reservation refresh cron (so 10am email trigger works)
SSH into the Pi and run:
```
(crontab -l 2>/dev/null; echo "*/30 * * * * curl -fsS http://127.0.0.1/reservation > /dev/null") | crontab -
```

## 10. Test!
1. Forget the WiFi on your phone, reconnect
2. Captive portal should open splash.html
3. Fill form, confirm you get online
4. Check Sheet, Gmail, welcome page

{FIRE_STICK_BLOCK}

You're done. Total time: ~2 hours for this customer.
"""
    fire_stick_block = ""
    if cfg.get("has_fire_stick"):
        fire_stick_block = f"""## 11. Set up Fire Stick kiosk display (optional)
Since this property has a Fire Stick, you can use it to display the welcome page 24/7 on a TV.

1. On the Fire Stick, go to the Appstore and install "Silk Browser" (free, by Amazon).
2. Open Silk. Set homepage to: http://{cfg['pi_ip']}/welcome_tv.html
   - Menu -> Settings -> General -> Set Homepage
3. Install "Fully Kiosk Browser" from the Appstore (free) for auto-start kiosk mode.
   - Opens URL on boot, prevents navigation away, auto-recovers
   - Set URL to: http://{cfg['pi_ip']}/welcome_tv.html
4. Fire Stick Settings -> My Fire TV -> Developer options -> enable "ADB debugging"
5. Set Fully Kiosk Browser to launch on boot using the Fire Stick's launch-on-boot app setting
6. Test by unplugging the Fire Stick power, plugging back in - should return to the welcome page within 30 seconds

If the property has Apple TVs too, you can leave them for entertainment use. The Fire Stick handles the welcome display on a dedicated HDMI input.
"""
    next_steps = next_steps.replace("{FIRE_STICK_BLOCK}", fire_stick_block)

    greeting_mode = cfg.get("greeting_mode", "manual")
    if greeting_mode == "auto":
        auto_detect_step = "   - autoDetectGuestName (run once to grant Gmail access, then the trigger installs)\n   - setupAutoDetectTrigger (daily 8am Gmail scan for guest name)\n\n**Tell the customer: don't delete Airbnb reservation emails**. Set up a Gmail filter to label them instead."
    elif greeting_mode == "manual":
        auto_detect_step = "\nGreeting mode: manual. Customer types guest name in the admin page when a new guest arrives. 10am email reminder will prompt them on check-in day."
    else:
        auto_detect_step = "\nGreeting mode: generic. Welcome pages never show a guest name, just 'Welcome to {prop}'. Skip `setupCheckinReminderTrigger` above - no check-in email needed.".format(prop=cfg["property_name"])
    next_steps = next_steps.replace("{AUTO_DETECT_STEP}", auto_detect_step)
    with open(out / "NEXT_STEPS.md", "w", encoding="utf-8") as f:
        f.write(next_steps)

    # Generate a customized customer handover doc
    handover_src = REPO_ROOT / "CUSTOMER_HANDOVER_TEMPLATE.md"
    if handover_src.exists():
        with open(handover_src, "r", encoding="utf-8") as f:
            handover = f.read()
        sheet_url = f"https://docs.google.com/spreadsheets/d/{cfg['sheet_id']}/edit"
        handover_subs = {
            "{PROPERTY_NAME}": cfg["property_name"],
            "{PI_IP}": cfg["pi_ip"],
            "{WIFI_SSID}": cfg["wifi_ssid"],
            "{WIFI_PASSWORD}": cfg["wifi_password"],
            "{ADMIN_USER}": cfg["admin_username"],
            "{ADMIN_PASSWORD}": cfg["admin_password"],
            "{HOST_EMAIL}": cfg["host_email"],
            "{SHEET_URL}": sheet_url,
            "{TUNNEL_URL}": "[fill in after tunnel comes up - see first auto-email]",
            "{OMADA_ADMIN}": "[your Omada Controller admin username]",
            "{OMADA_PASSWORD}": "[your Omada Controller admin password - store in password manager]",
            "{OMADA_ADMIN_USER}": "[your Omada Controller admin username]",
            "{OMADA_ADMIN_PASSWORD}": "[your Omada Controller admin password - store in password manager]",
            "{YOUR_EMAIL}": "[your support email]",
            "{YOUR_PHONE}": "[your support phone]",
            "{YOUR_NAME}": "[your name]",
            "{INSTALL_DATE}": "[install date]",
            "{SERVICE_TERMS_HERE}": "[your service terms - pricing, SLA, what's included]",
        }
        for k, v in handover_subs.items():
            handover = handover.replace(k, v)
        with open(out / "CUSTOMER_HANDOVER.md", "w", encoding="utf-8") as f:
            f.write(handover)

    return out


def main():
    try:
        cfg = collect_config()
    except (KeyboardInterrupt, EOFError):
        print("\nAborted.")
        sys.exit(1)

    out = generate_kit(cfg)
    print(f"\n[OK] Kit generated at: {out}")
    print(f"[OK] Config saved to:  {out}/customer_config.json")
    print(f"[OK] Read next steps:  {out}/NEXT_STEPS.md")
    print()
    print("When ready, cd into the customer folder and run ./deploy.sh to push to their Pi.")


if __name__ == "__main__":
    main()
