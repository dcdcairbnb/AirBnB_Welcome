# Music City Retreat - URL Reference

Quick reference for all the URLs and credentials. Keep this private.

## Guest-facing pages

| What | URL |
|------|-----|
| Captive portal splash (WiFi form) | http://192.168.0.217/splash.html |
| Welcome page (phone/computer) | http://192.168.0.217/welcome_sign.html |
| Welcome page (TV) | http://192.168.0.217/welcome_tv.html |

## Admin (only you)

| What | URL |
|------|-----|
| Admin page, local (when home) | http://192.168.0.217/admin |
| Admin page, remote (anywhere) | https://everywhere-juan-directions-internal.trycloudflare.com/admin |

**Admin login:** `dan` / `MusicCity2026`

Note: the remote URL changes when the Pi reboots. To get the current one:

```
ssh pi@192.168.0.217
sudo journalctl -u cloudflared-tunnel --no-pager | grep trycloudflare.com | tail -1
```

## Network management

| What | URL |
|------|-----|
| Omada Controller | https://192.168.0.217:8043/ |

## Google

| What | URL |
|------|-----|
| Guest submissions Sheet | [Google Sheets] |
| Apps Script project | https://script.google.com -> Music City Retreat Portal |
| Apps Script web app | https://script.google.com/macros/s/AKfycbxYneJMWNnhuVd135ICINzIni3DB-EcFVx-r34JpH1IS6Mvjkga7I0tNpa7BXPhT-kIcw/exec |

## SSH

| What | Command |
|------|---------|
| SSH to Pi (local network) | `ssh pi@192.168.0.217` |
| SSH to Pi (from anywhere, via Tailscale) | `ssh pi@100.76.203.111` |

## Guest WiFi

| Setting | Value |
|---------|-------|
| SSID | 1011A2-5G |
| Password | NashRocks! |

## Data sources (for the welcome page)

| Source | URL |
|--------|-----|
| Airbnb iCal | https://www.airbnb.com/calendar/ical/1546687115825271453.ics?t=1fe96e5261b045f29205ffe550274e08 |
| VRBO iCal | https://www.vrbo.com/icalendar/da573616bb5a4f2288f4cabcc1dc9bb4.ics?nonTentative |
| Ticketmaster API key | rAkV87yVeExNjYMqmRPpSppvLcXNWzdG |

## Services running on the Pi

| Service | Purpose |
|---------|---------|
| `nginx` | Serves splash.html, welcome_sign.html, welcome_tv.html, proxies /admin, /authorize, /verify, /events, /reservation |
| `omada-auth` | Flask app on port 5000 - handles Omada auth callback, email verification, events feed, reservation fetch, admin page |
| `cloudflared-tunnel` | Cloudflare Quick Tunnel for remote admin access |
| `tpeap` | Omada Controller itself |

## Useful commands on the Pi

```bash
# Restart the Flask service
sudo systemctl restart omada-auth

# Reload nginx
sudo systemctl reload nginx

# See recent Flask logs
sudo journalctl -u omada-auth -n 50

# See tunnel URL
sudo journalctl -u cloudflared-tunnel | grep trycloudflare.com | tail -1

# Reset admin password
sudo htpasswd -b /etc/nginx/.htpasswd dan NewPassword123
```
