# Airbnb Guest WiFi & Welcome Sign - Procedures

Rinse-and-repeat playbook for deploying this system to a new property. Cut and reuse for each customer.

---

## 1. What This System Does

- Captive portal for guest WiFi, collects guest name/email/stay length
- Logs submissions to Google Sheet, sends verification email
- Welcome sign on guest's phone with live reservation dates, guest name, local events (Ticketmaster), nearby food/drinks/things-to-do, and cross-promo for other properties
- Printable QR code for the fridge that opens the welcome page on a guest's phone
- Admin web page (remote access via Cloudflare Tunnel) to set guest name per reservation
- Daily 10am email reminder on check-in days

**On display strategy:** the system does NOT run on an always-on TV display. The welcome page is designed for phones/computers. Guests scan a QR code on the fridge (framed for decor) and the welcome page loads on their phone where they can tap through restaurants, events, etc. This works better than a wall display because it's interactive and doesn't require dedicated hardware. A TV-optimized page is available at `/welcome_tv.html` if you ever do want to AirPlay or display it, but the QR-on-fridge flow is the default.

---

## 2. Prerequisites Per Customer

### Hardware (buy once per property)
- Raspberry Pi 5 or Pi 4 (4GB+ RAM recommended)
- microSD card, 32GB+
- TP-Link Omada access point (EAP650 or similar, WiFi 6 with PoE+)
- Ethernet cable (to connect EAP to router)
- Power supply for Pi (official 27W for Pi 5)

### Accounts (customer-specific or reused)
- Gmail or Google Workspace account for the customer (owns the Sheet, Apps Script, sends verification emails)
- Ticketmaster developer account (your account - one key can service multiple properties; change city/state per property)
- Cloudflare account (optional, for permanent remote admin URL - requires domain)

### Customer info to collect up front
- Property name ("Music City Retreat")
- Property city/state (for event feed)
- Host contact email (where 10am reminders go)
- Guest WiFi SSID + password
- Airbnb listing URL + iCal export URL
- VRBO listing URL + iCal export URL (if applicable)
- Photo for splash page hero image
- Restaurant/bar/things-to-do list (curated)
- Other property info for cross-promo (optional)

---

## 3. One-Time Pi Setup (per property)

### 3.1 Image the Pi
1. Flash Raspberry Pi OS (64-bit, Lite) to microSD with Raspberry Pi Imager
2. In imager Advanced settings: set hostname (e.g., `{customer}-controller`), enable SSH, set username `pi`, set a strong password, configure WiFi if needed
3. Boot the Pi, connect via Ethernet to the customer's router

### 3.2 Install Omada Controller (Docker, recommended)
```bash
ssh pi@<pi-ip>
sudo apt update && sudo apt upgrade -y
sudo apt install -y docker.io
sudo systemctl enable --now docker

sudo docker run -d \
  --name omada-controller \
  --network host \
  --restart unless-stopped \
  -v omada-data:/opt/tplink/EAPController/data \
  -v omada-logs:/opt/tplink/EAPController/logs \
  mbentley/omada-controller:latest
```
- Wait 3-5 min for initial setup
- Open `https://<pi-ip>:8043/` in browser, run through wizard
- Set a strong admin password, note the Omada site name

**IMPORTANT**: Do NOT also install the native Omada Controller package (`tpeap` service). The Docker container and native install conflict on ports 29810-29816 and the Docker one will crash loop. If tpeap exists from a prior install:
```bash
sudo systemctl stop tpeap
sudo systemctl disable tpeap
# Kill any leftover jsvc processes
sudo pkill -9 -f jsvc || true
sudo docker restart omada-controller
```

### 3.3 Install nginx + Python
```bash
sudo apt install -y nginx python3-venv python3-pip apache2-utils
```

### 3.4 Clone the code repo
```bash
cd ~
git clone https://github.com/dcdcairbnb/AirBnB_Welcome.git
```

### 3.5 Configure customer-specific values
Edit these files in the clone:
- `omada_auth.py`: update ICAL_URLS, TM_CITY, TM_STATE, APPS_SCRIPT_URL
- `welcome_sign.html` and `welcome_tv.html`: replace Nashville-specific content (restaurants, things to do, etc.)
- `apps-script-code.gs`: update SHEET_ID, WIFI_SSID, WIFI_PASSWORD, PROPERTY_NAME, host email in sendCheckinReminderEmail

### 3.6 Deploy the Omada Auth Bridge
```bash
cd ~/AirBnB_Welcome
sudo bash setup_omada_auth.sh
```

### 3.7 Configure nginx
```bash
sudo cp nginx-default.conf /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

### 3.8 Deploy welcome pages and splash
```bash
sudo cp splash.html welcome_sign.html welcome_tv.html living-room.jpg /var/www/html/
sudo chown www-data:www-data /var/www/html/*
```

### 3.9 Set up admin auth and remote access
```bash
sudo bash setup_remote_admin.sh dan <strong-password>
```
- Record the printed Cloudflare Tunnel URL

### 3.10 Install tunnel URL auto-email watcher
```bash
sudo cp email_tunnel_url.sh /opt/omada-auth/email_tunnel_url.sh
sudo chmod +x /opt/omada-auth/email_tunnel_url.sh
sudo cp tunnel-url-watcher.service /etc/systemd/system/
sudo cp tunnel-url-watcher.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tunnel-url-watcher.timer
```
- Host will now receive an email whenever the tunnel URL changes

### 3.11 Set up log rotation
```bash
sudo bash setup_log_rotation.sh
```
- Caps systemd journal at 500MB, 30-day retention
- Installs nginx logrotate (14 days, compressed)
- Prevents the SD card from filling up over time

### 3.12 Set up Healthchecks.io monitoring
One-time: get an API key from https://healthchecks.io/projects -> API Access.

```bash
python setup_healthchecks.py customer_config.json YOUR_HC_API_KEY
```
Creates a hourly uptime check, installs the cron job on the Pi, and sends first ping. You get an email within 2 hours if the Pi goes offline.

### 3.13 Add reservation refresh cron
Keeps the Google Sheet's Reservation tab current so the 10am check-in reminder trigger always sees today's data.

SSH into the Pi and run:
```bash
(crontab -l 2>/dev/null; echo "*/30 * * * * curl -fsS http://127.0.0.1/reservation > /dev/null") | crontab -
```
Verify with `crontab -l`.

### 3.14 Install Tailscale for remote SSH admin access
Gives you (the system admin) SSH access to this Pi from anywhere via a stable 100.x.y.z IP.

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```
- The command prints a login URL. Open it in your browser signed in as **your** Tailscale admin account (not the customer's).
- Approve the device.
- Run `tailscale ip -4` to get the Pi's permanent Tailscale IP.
- Save this IP alongside the customer's other info. Format: `ssh pi@100.x.y.z`.

**Important**: The customer does NOT need Tailscale on their devices. This is for your remote support only.

---

## 4. One-Time Google Setup (per property)

### 4.1 Create Google Sheet
1. Go to sheets.google.com, create blank sheet
2. Rename to "<Property Name> - Guest Log"
3. Copy the Sheet ID from URL (`docs.google.com/spreadsheets/d/<SHEET_ID>/edit`)

### 4.2 Create Apps Script project
1. Go to script.google.com, "New project"
2. Rename to "<Property Name> Portal"
3. Paste contents of `apps-script-code.gs`
4. Update CONFIG section at top: SHEET_ID, WIFI_SSID, WIFI_PASSWORD, FROM_NAME, PROPERTY_NAME, host email in sendCheckinReminderEmail
5. Save (Ctrl+S)
6. Deploy → New deployment → Web app
   - Execute as: Me
   - Who has access: Anyone
7. Authorize when prompted (grant all permissions including external_request)
8. Copy the web app URL
9. Update `omada_auth.py` APPS_SCRIPT_URL on the Pi with this URL
10. Run `setupCheckinReminderTrigger` function once from the editor to install the daily 10am email
11. Run `setupWeeklyBackupTrigger` function once to install Sunday 3am weekly Sheet backup (grant Drive permission when prompted)
12. (Optional, only if greeting_mode == "auto") Run `autoDetectGuestName` once to grant Gmail access, then `setupAutoDetectTrigger` for the daily 8am Gmail scan. Tell the customer to not delete Airbnb reservation emails.

### 4.3 Redeploy Pi with updated URL
```bash
sudo systemctl restart omada-auth
```

---

## 5. One-Time Omada Setup (per property)

### Fast path: API automation
```bash
python setup_omada.py <customer_config.json> YOUR_OMADA_ADMIN_USER YOUR_OMADA_ADMIN_PASS
```
Creates operator account, WLAN, portal, and walled garden automatically.

You'll still need to:
- Add Apple TV MACs to Authentication-Free Client list (UI)
- Plug in and adopt the EAP (physical + UI)
- Update `omada_auth.py` env vars with the operator credentials

### Slow path: manual UI

### 5.1 Adopt the EAP
1. Plug EAP into router LAN port with PoE+ or DC power
2. Wait 90 seconds
3. In Omada Controller → Devices, click "Adopt" when EAP appears

### 5.2 Create guest SSID
1. Settings → Wireless Networks → Create New WLAN
2. SSID: <customer's SSID>, Security: WPA2-Personal, Password: <customer's password>
3. Apply to the EAP

### 5.3 Create captive portal
1. Settings → Authentication → Portal → Create New Portal
2. Name: <Property Name>
3. SSID & Network: select the new guest SSID
4. Authentication Type: External Portal Server
5. Custom Portal Server URL: `http://<pi-ip>/splash.html`
6. Landing Page → Promotional URL: `http://<pi-ip>/welcome_sign.html`
7. Save

### 5.4 Configure walled garden
1. Settings → Authentication → Portal → Access Control tab
2. Enable Pre-Authentication Access
3. Add entries:
   - IP Range: `<pi-ip>/32`
   - URL: `script.google.com`
   - URL: `script.googleusercontent.com`
   - URL: `fonts.googleapis.com`
   - URL: `fonts.gstatic.com`
   - URL: `accounts.google.com`
4. Enable Authentication-Free Client, add MAC addresses for owner devices, Apple TVs, smart TVs, Roku, printers, smart home, etc.
5. Apply

### 5.5 Turn off router WiFi
1. Log into the customer's router admin
2. Disable 2.4GHz and 5GHz radios (EAP now handles WiFi)
3. Save

### 5.6 Print and frame the QR code card
Open `welcome_qr_printable.html` in a browser, Ctrl+P, save as PDF or print directly. Frame it in a cheap 8x10 frame (~$5 at Target) and put it on the fridge or nightstand. Guests scan with their phone camera and the welcome page loads.

For the WiFi QR card, use `wifi_qr_printable.html`. Print and place next to the welcome QR (or combine into one frame).

### 5.7 Test
1. Forget WiFi on your phone, reconnect
2. Captive portal should open `splash.html`
3. Fill form, verify internet works after
4. Check Google Sheet for new row
5. Check Gmail for verification email
6. Click verification link, should redirect to welcome page

---

## 6. Daily Operations

### 6.1 When a new guest checks in
- 10am email reminder arrives if you haven't set their name
- Open admin URL on phone: `https://<tunnel-url>.trycloudflare.com/admin`
- Login (dan / <password>)
- Enter guest first name, save
- TV updates within 30 seconds

### 6.2 When a guest submits WiFi form
- Nothing to do - automatic
- Row added to Sheet
- Verification email sent
- Internet granted

### 6.3 Weekly maintenance
- Tunnel URL changes arrive by email automatically. No manual check needed.
- iCal expiration alerts arrive by email automatically. If you get one, regenerate the iCal URL in the host dashboard and update ICAL_URLS in `/opt/omada-auth/omada_auth.py`.
- Check Sheet for any weird submissions to clean up
- Weekly Sheet backup runs Sunday 3am automatically. Spot-check the "* Sheet Backups" folder in Drive monthly.

### 6.4 Monthly maintenance
- Review Google Apps Script executions tab for any errors
- Apt update the Pi:
  ```bash
  ssh pi@<pi-ip> "sudo apt update && sudo apt upgrade -y && sudo reboot"
  ```
- Run a fresh Pi config backup:
  ```bash
  ssh pi@<pi-ip> "sudo bash ~/AirBnB_Welcome/backup_pi_config.sh"
  scp pi@<pi-ip>:/tmp/pi-config-backup-*.tar.gz ~/Documents/backups/
  ```


---

## 7. Troubleshooting

### Omada Controller Docker container crash-looping with "port already in use"
- Zombie `jsvc` processes from the native `tpeap` service are holding the Omada ports
- Check: `sudo ss -tulpn | grep 29810` (if pid shown, that's the zombie)
- Stop tpeap properly and kill zombies:
  ```bash
  sudo systemctl stop tpeap
  sudo systemctl disable tpeap
  sudo pkill -9 -f jsvc
  sudo docker restart omada-controller
  ```
- Wait 5 min and verify `sudo docker ps | grep omada` shows "(healthy)"

### Captive portal doesn't appear when guest connects
- Check Omada portal is enabled for the SSID
- Check EAP is online in Omada Devices page
- Check walled garden has `<pi-ip>/32` entry
- SSH to Pi: `curl -I http://127.0.0.1/splash.html` should return 200

### Form submits but no email / no Sheet row
- Check Apps Script Executions tab (left sidebar clock icon)
- Verify SCRIPT_URL in splash.html matches deployed Apps Script URL
- Verify Apps Script is deployed with "Anyone" access

### Internet doesn't work after submitting form
- Check omada-auth Flask service: `sudo systemctl status omada-auth`
- Check omada-auth logs: `sudo journalctl -u omada-auth -n 30`
- Verify Operator account exists in Omada Hotspot Manager
- Verify OMADA_USER/OMADA_PASS in `omada_auth.py` matches

### Welcome page shows no events
- Check Ticketmaster API key is valid
- Test endpoint: `curl http://<pi-ip>/events`
- Check Flask logs for "Ticketmaster fetch failed"

### Welcome page shows wrong dates
- Check inbox for automated "iCal fetch failed" email from the Pi - fires within 24h of first failure
- Check iCal URLs are correct (copy fresh from Airbnb/VRBO - they can expire)
- Test: `curl http://<pi-ip>/reservation`
- Check Flask logs for "iCal fetch failed"
- If an iCal token expired, regenerate in the host dashboard and update ICAL_URLS in `/opt/omada-auth/omada_auth.py`, then `sudo systemctl restart omada-auth`

### Admin page shows Google Drive error (multi-account)
- Use the Pi-hosted admin (`<tunnel-url>.trycloudflare.com/admin`), not Apps Script URL

### Remote admin URL doesn't work
- Pi might have rebooted. You should have received an email with the new URL.
- Search email inbox for "admin tunnel URL changed"
- If no email arrived, force a check: `ssh pi@<pi-ip> "sudo systemctl start tunnel-url-watcher"`
- Or fall back to manual: `sudo journalctl -u cloudflared-tunnel | grep trycloudflare.com | tail -1`

### "Sorry, unable to open the file at this time" in browser
- Multi-account Google issue. Open the URL in incognito mode.

---

## 8. Architecture Reference

### Services on the Pi
| Service | Port | Purpose |
|---------|------|---------|
| nginx | 80 | Serves splash/welcome pages, proxies /admin /authorize /verify /events /reservation |
| omada-auth (Flask) | 5000 | Omada auth callback, email verification, events, reservation, admin |
| tpeap (Omada Controller) | 8088, 8043 | Manages EAP and captive portal |
| cloudflared-tunnel | - | Cloudflare Tunnel for remote admin (host-to-customer) |
| tunnel-url-watcher.timer | - | Emails host when tunnel URL changes (runs every 10 min) |
| tailscaled | - | Tailscale VPN for remote SSH access (admin-to-Pi) |

### Data flow on form submit
1. Guest connects to SSID → Omada captures, redirects to `splash.html`
2. Guest fills form → splash.html POSTs to Apps Script (log to Sheet, send email)
3. splash.html simultaneously POSTs to `/authorize` on Pi
4. Flask authenticates with Omada Hotspot API using Operator credentials, authorizes guest MAC
5. Guest gets internet, redirected to `welcome_sign.html`

### Data flow on verification link click
1. Guest clicks link in email → lands on `<pi-ip>/verify?token=X`
2. Flask calls Apps Script server-side with token
3. Apps Script marks token verified in Sheet, returns JSON
4. Flask renders success page with redirect to welcome_sign

### Code location
- All code is in GitHub: https://github.com/dcdcairbnb/AirBnB_Welcome
- Pi's live code is at:
  - `/var/www/html/` (static pages)
  - `/opt/omada-auth/omada_auth.py` (Flask service)
  - `/etc/nginx/sites-enabled/default` (nginx config)
  - `/etc/nginx/.htpasswd` (admin password)

### Customer-specific customization checklist
Copy this checklist for each new customer:

- [ ] Property name replaced in `apps-script-code.gs` (PROPERTY_NAME, FROM_NAME)
- [ ] Property name replaced in `welcome_sign.html` (title, headers)
- [ ] Property name replaced in `welcome_tv.html` (title, headers)
- [ ] Property name replaced in `splash.html` (title, header)
- [ ] SHEET_ID updated (new Google Sheet per customer)
- [ ] WIFI_SSID and WIFI_PASSWORD updated
- [ ] Airbnb iCal URL updated
- [ ] VRBO iCal URL updated (or removed if not applicable)
- [ ] Host email updated in `sendCheckinReminderEmail`
- [ ] Ticketmaster city/state updated in `omada_auth.py`
- [ ] Restaurants/bars/things-to-do list replaced in welcome_sign.html and welcome_tv.html
- [ ] Hero image replaced (splash.html references `living-room.jpg`)
- [ ] Local iCal URLs in `omada_auth.py` ICAL_URLS
- [ ] Apps Script deployed with new customer's URL
- [ ] Admin password set via `htpasswd`
- [ ] Cloudflare tunnel URL saved to URLS.md

---

## 9. Per-Customer Deployment Time Estimate
- Pi hardware setup + OS install: 30 min
- Omada Controller install: 15 min
- Code clone + customer-specific edits: 45 min
- Apps Script + Google Sheet setup: 20 min
- Omada portal + walled garden config: 20 min
- EAP adoption + SSID creation: 10 min
- Tailscale install (for your remote admin access): 5 min
- Testing + fixes: 30 min
- **Total: ~3 hours per property**

After the first property, expect 2 hours on #2 as you refine the templates.

---

## 10. Rebuild / Disaster Recovery

When to use: SD card failure, Pi hardware death, corrupted system, moved to new hardware. Rebuild time: ~45 minutes if you have a recent backup tarball.

### 10.1 Prerequisites
- A backup tarball (from `backup_pi_config.sh`) stored somewhere safe (your PC, cloud drive, or other Pi)
- Fresh Pi hardware + SD card
- Access to the customer's network (can be temporary via cellular hotspot)

### 10.2 Taking backups

#### Run a fresh backup anytime
```bash
ssh pi@<tailscale-ip>
sudo bash ~/AirBnB_Welcome/backup_pi_config.sh
```
Script prints the filename (e.g., `/tmp/pi-config-backup-2026-04-21.tar.gz`).

#### Pull the backup to your computer
```bash
scp pi@<tailscale-ip>:/tmp/pi-config-backup-*.tar.gz ~/Documents/backups/
```

#### Recommended backup cadence
- Monthly, plus any time you make significant config changes
- Keep at least the last 3 backups in a safe place (external drive, cloud, or second Pi)

### 10.3 Rebuilding a dead Pi

#### Step 1: Provision fresh Pi base
Follow sections 3.1 through 3.3 of this doc:
- Flash Raspberry Pi OS
- Install Omada Controller
- Install nginx + python3-venv + apache2-utils + cloudflared

Stop before the customer-specific steps (3.4 onward). The restore script handles those.

#### Step 2: Copy backup to new Pi
```bash
scp ~/Documents/backups/pi-config-backup-2026-04-21.tar.gz pi@<new-pi-ip>:/tmp/
```

#### Step 3: Copy restore script and run
```bash
scp restore_pi_config.sh pi@<new-pi-ip>:/tmp/
ssh -t pi@<new-pi-ip> "sudo bash /tmp/restore_pi_config.sh /tmp/pi-config-backup-2026-04-21.tar.gz"
```

This restores:
- All `/opt/omada-auth` code and state
- nginx config and admin password
- All systemd units (omada-auth, cloudflared-tunnel, tunnel-url-watcher)
- All web files (splash.html, welcome pages, hero image)
- Omada Controller data directory (portal, SSIDs, walled garden, operator accounts)
- Pi user crontab (Healthchecks ping)

#### Step 4: Reinstall Tailscale (needs fresh auth)
```bash
ssh pi@<new-pi-ip>
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
# Open the printed URL in your Tailscale admin account to approve
```
Note: the Tailscale IP will change on the new Pi. Update URLS.md.

#### Step 5: Verify everything
```bash
sudo systemctl is-active nginx omada-auth cloudflared-tunnel tunnel-url-watcher.timer tpeap tailscaled
curl -s http://127.0.0.1/reservation
curl -s http://127.0.0.1/events | head -5
```
All services should be `active` and endpoints should return data.

#### Step 6: Note new tunnel URL
You'll receive an auto-email with the new Cloudflare Tunnel URL. Save to URLS.md.

### 10.4 What isn't in the backup (needs manual reconfig)
- Tailscale auth (must re-auth on new Pi)
- Healthchecks.io ping URL (already in crontab, restored automatically)
- New Cloudflare Tunnel URL (random, auto-emailed when tunnel connects)

### 10.5 Partial restores
If only the code broke (not hardware), you don't need a full rebuild. Just:
```bash
git clone https://github.com/dcdcairbnb/AirBnB_Welcome.git
sudo cp AirBnB_Welcome/omada_auth.py /opt/omada-auth/
sudo systemctl restart omada-auth
```

## 11. Cost Per Property (Recurring)
- Pi hardware: ~$150 (one-time)
- EAP hardware: ~$100 (one-time)
- Domain for Cloudflare Tunnel: $10/year (optional, shared across properties)
- Ticketmaster API: Free tier sufficient (shared key)
- Apps Script + Sheets: Free
- Gmail for verification emails: Free
- **Monthly recurring: $0. One-time per property: $250**
