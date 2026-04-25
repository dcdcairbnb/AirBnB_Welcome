# {PROPERTY_NAME} - Guest WiFi & Welcome Sign System

Your installation is complete. Here is everything you need to know.

---

## What you have

A custom guest WiFi system that:

1. Shows a welcome form on new guests' phones when they connect to WiFi
2. Logs each guest's name, email, and stay length to a Google Sheet
3. Sends each guest a verification email with WiFi details
4. Shows guests a live welcome page on their phone (restaurants, rooftop bars, happy hour, things to do, tonight's local events) when they scan the QR code on the fridge
5. Greets them by name on the welcome page once you've entered the guest name via the admin page
6. Automatically knows when guests are arriving/leaving (pulls from your Airbnb + VRBO calendars)

---

## Your URLs and logins

### Guest-facing (what your guests see)
Guests don't need URLs - these load automatically when they connect to WiFi. For reference:

- WiFi portal: `http://{PI_IP}/splash.html`
- Full welcome page: `http://{PI_IP}/welcome_sign.html`
- TV welcome page: `http://{PI_IP}/welcome_tv.html`

### Admin (for you)

**Set guest names here:**
- Local (when you're home): `http://{PI_IP}/admin`
- Remote (from anywhere): `{TUNNEL_URL}/admin`
- Login: `{ADMIN_USER}` / `{ADMIN_PASSWORD}`

**Your Google Sheet (guest submissions):**
- {SHEET_URL}

**Your Omada Controller (network management):**
- `https://{PI_IP}:8043`
- Login: `{OMADA_ADMIN}` / `{OMADA_PASSWORD}`

---

## Your weekly routine

### When a new guest is checking in today
Every morning at 10am, if a guest is checking in that day and you haven't set their name, you'll get an email. Click the button in the email. Log in. Type their first name. Save. Done.

The TV welcome sign updates within 30 seconds and greets them by name.

### When a guest fills the WiFi form
Nothing to do. It's automatic:
- Their info is logged to your Google Sheet
- They get a welcome email with WiFi details
- They get internet access
- The welcome page loads with local restaurants/bars/events

### Between guests
Nothing to do. The system:
- Auto-clears the previous guest's name when a new reservation starts
- Pulls new reservation dates from your Airbnb + VRBO calendars every 30 minutes

---

## Alerts you'll receive

You'll get emails when:

1. **Check-in reminder** - 10am on the day a guest checks in, if you haven't set their name yet
2. **Repeat guest alert** - when someone who stayed before submits the WiFi form
3. **Tunnel URL changed** - if your Pi reboots, the remote admin URL updates (auto-sent)
4. **iCal URL expired** - if your Airbnb or VRBO calendar export stops working
5. **Pi offline** - if the Pi loses power or internet for more than 2 hours (Healthchecks.io)

All emails go to: `{HOST_EMAIL}`

---

## Your hardware

### Raspberry Pi
- Lives at your property, plugged into ethernet on the router
- IP address: `{PI_IP}`
- Powers the welcome system, WiFi portal, and Omada Controller
- Draws about 5 watts. Leave it plugged in 24/7.

### TP-Link Omada EAP
- Your guest WiFi access point
- Serves the guest SSID `{WIFI_SSID}`

### Your existing router
- Still provides internet to the property
- WiFi is now handled by the EAP (router WiFi turned off)

---

## Basic troubleshooting

### Guests say "the WiFi portal isn't showing up"
- The Pi may need to be rebooted. Unplug its power for 30 seconds, plug back in.
- Wait 3 minutes for the system to fully boot.

### Welcome page on TV is blank
- Internet may be down at the property. Check the main router.
- Or the Pi is off. Verify it has power (steady LED).

### I need to change my WiFi password
- Log into Omada Controller (`https://{PI_IP}:8043`)
- Settings → Wireless Networks → edit the WLAN
- Email me the new password so I can update the system

### I got a "iCal fetch failed" email
- Means your Airbnb or VRBO calendar export token expired
- Regenerate it in your host dashboard (Airbnb: Pricing & Availability → Sync calendars → Export)
- Email me the new URL and I'll update the system

### Something broke and I can't fix it
- Email me: `{YOUR_EMAIL}`
- Or text me: `{YOUR_PHONE}`

---

## What I can do remotely

Because I installed a secure remote access tool (Tailscale) on your Pi, I can:
- Monitor that your system is running (I get an alert if it goes down)
- Update the software when needed
- Fix most issues without visiting your property

This does not give me access to your Google account, your guest data, or your network traffic. Only to the Pi's system configuration.

---

## Data privacy

The system collects:
- Guest's name, email, length of stay
- Stored in your Google Sheet (you own it)
- Never shared with third parties
- Auto-backed up weekly to your Google Drive

---

## Service included

{SERVICE_TERMS_HERE}

_Example:_
- Remote monitoring and alerts: included
- Software updates: included
- Emergency fixes: response within 24 hours
- Monthly: $X
- Quarterly backup to your secondary storage: included

---

## Omada backup (how to save network settings)

The Omada Controller holds your WiFi, captive portal, and walled garden config. Auto-backup runs daily at 03:00 and keeps 7 days of backups on the Pi. Pull a manual `.cfg` to Google Drive monthly or before any change.

### Pull a backup from the UI

1. Open `https://{PI_IP}:8043` in your browser
2. Log in with admin user `{OMADA_ADMIN_USER}` and password `{OMADA_ADMIN_PASSWORD}`
3. In the **top right**, click the gear icon next to your user avatar. **Or** in the top left, switch the view dropdown from "Site" to "Global"
4. Click **Maintenance** in the left sidebar
5. Click the **Backup & Restore** tab
6. Click **Backup**. A file named `Omada_Controller_Backup_<date>.cfg` downloads to your computer
7. Upload that file to your Google Drive folder `{PROPERTY_NAME} / Omada Backups`

### Restore from backup

If the controller is wiped or replaced:

1. Open `https://{PI_IP}:8043` and log in
2. Switch to Global View (same gear icon or view dropdown as above)
3. **Maintenance** > **Backup & Restore** tab > click **Restore**
4. Upload the most recent `.cfg` from Google Drive
5. Controller restarts. All SSIDs, captive portal, walled garden, operator account, and adopted device records come back automatically

---

## Quick reference card

Print and stick this inside your kitchen cabinet:

```
PROPERTY: {PROPERTY_NAME}
-------------------------------
Admin (phone): {TUNNEL_URL}/admin
Login:         {ADMIN_USER} / {ADMIN_PASSWORD}

Pi IP:         {PI_IP}
Omada UI:      https://{PI_IP}:8043

Support:       {YOUR_EMAIL}
               {YOUR_PHONE}

Guest SSID:    {WIFI_SSID}
Guest WiFi PW: {WIFI_PASSWORD}
```

---

Installed by {YOUR_NAME} on {INSTALL_DATE}
