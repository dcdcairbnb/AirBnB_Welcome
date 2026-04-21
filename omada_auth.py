#!/usr/bin/env python3
"""
Omada External Portal Authentication Bridge
Receives client info from splash.html and authorizes the guest with the Omada Controller.

Flow:
  1. GET controller ID from Omada Controller
  2. POST login with operator credentials, receive CSRF token and session cookie
  3. POST external portal auth with client info and CSRF token
"""

import os
import json
import time
import logging
from flask import Flask, request, jsonify, Response
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- Config (override via environment variables) --------------------
OMADA_URL = os.environ.get("OMADA_URL", "https://127.0.0.1:8043")
OPERATOR_USER = os.environ.get("OMADA_USER", "portal_api")
OPERATOR_PASS = os.environ.get("OMADA_PASS", "Deaboss1203!")
SESSION_DURATION_MS = int(os.environ.get("SESSION_MS", "14400000"))  # 4 hours
LISTEN_HOST = os.environ.get("LISTEN_HOST", "127.0.0.1")
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "5000"))
APPS_SCRIPT_URL = os.environ.get(
    "APPS_SCRIPT_URL",
    "https://script.google.com/macros/s/AKfycbxYneJMWNnhuVd135ICINzIni3DB-EcFVx-r34JpH1IS6Mvjkga7I0tNpa7BXPhT-kIcw/exec",
)
REDIRECT_URL = os.environ.get("REDIRECT_URL", "http://192.168.0.217/welcome_sign.html")
REDIRECT_SECONDS = int(os.environ.get("REDIRECT_SECONDS", "3"))
TM_API_KEY = os.environ.get("TICKETMASTER_KEY", "rAkV87yVeExNjYMqmRPpSppvLcXNWzdG")
TM_CITY = os.environ.get("TM_CITY", "Nashville")
TM_STATE = os.environ.get("TM_STATE", "TN")
EVENTS_CACHE_TTL = int(os.environ.get("EVENTS_CACHE_TTL", "3600"))  # 1 hour
ICAL_URLS = [u.strip() for u in os.environ.get(
    "ICAL_URLS",
    "https://www.airbnb.com/calendar/ical/1546687115825271453.ics?t=1fe96e5261b045f29205ffe550274e08,"
    "https://www.vrbo.com/icalendar/da573616bb5a4f2288f4cabcc1dc9bb4.ics?nonTentative",
).split(",") if u.strip()]
RESERVATION_CACHE_TTL = int(os.environ.get("RESERVATION_CACHE_TTL", "1800"))  # 30 min
# --------------------------------------------------------------------

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("omada_auth")

app = Flask(__name__)


def get_controller_id():
    """Fetch the Omada controller identifier (omadacId)."""
    r = requests.get(f"{OMADA_URL}/api/info", verify=False, timeout=10)
    r.raise_for_status()
    data = r.json()
    cid = data.get("result", {}).get("omadacId")
    if not cid:
        raise RuntimeError(f"No omadacId in /api/info response: {data}")
    return cid


def operator_login(session, cid):
    """Log in as the Hotspot Operator, returns CSRF token."""
    url = f"{OMADA_URL}/{cid}/api/v2/hotspot/login"
    resp = session.post(
        url,
        json={"name": OPERATOR_USER, "password": OPERATOR_PASS},
        verify=False,
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("errorCode") != 0:
        raise RuntimeError(f"Operator login failed: {data}")
    return data["result"]["token"]


def authorize_guest(session, cid, token, payload):
    """Call external portal auth to authorize the client MAC."""
    url = f"{OMADA_URL}/{cid}/api/v2/hotspot/extPortal/auth"
    resp = session.post(
        url,
        json=payload,
        headers={"Csrf-Token": token},
        verify=False,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "service": "omada_auth"})


def _admin_html(current_guest, checkin_label, checkout_label, source='', saved=False):
    notice = '<p class="saved">Saved.</p>' if saved else ''
    res_panel = ''
    if checkin_label and checkout_label:
        source_line = ''
        if source:
            source_line = '<p class="range"><strong>Source:</strong> ' + source + '</p>'
        res_panel = (
            '<div class="res">'
            '<p class="label">Current reservation</p>'
            + source_line +
            '<p class="range"><strong>Check-in:</strong> ' + checkin_label + '</p>'
            '<p class="range"><strong>Check-out:</strong> ' + checkout_label + '</p>'
            '</div>'
        )
    else:
        res_panel = '<div class="res"><p class="label">No active reservation.</p></div>'

    escaped = (current_guest or '').replace('"', '&quot;')
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Guest Name Admin</title>'
        '<style>body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;'
        'background:linear-gradient(160deg,#2B1055 0%,#7597DE 30%,#FF5E62 65%,#FFB86C 100%);'
        'min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px;margin:0;color:#2d1b3d}'
        '.card{background:#fff;border-radius:16px;box-shadow:0 20px 60px rgba(0,0,0,.3);'
        'padding:36px 28px;max-width:440px;width:100%}'
        'h1{margin:0 0 6px 0;font-size:22px}p.sub{color:#6b5b73;margin:0 0 20px 0;font-size:14px}'
        'label{display:block;font-weight:600;margin-bottom:6px;font-size:14px}'
        'input{width:100%;padding:12px 14px;border:2px solid #e5e0e8;border-radius:8px;font-size:16px;box-sizing:border-box}'
        'input:focus{outline:none;border-color:#FF5E62}'
        'button{width:100%;padding:14px;margin-top:14px;background:linear-gradient(135deg,#FF5E62 0%,#FF9966 100%);'
        'color:#fff;border:none;border-radius:8px;font-size:16px;font-weight:600;cursor:pointer}'
        '.saved{color:#0d7a3e;font-weight:600;margin:14px 0 0 0}'
        '.current{color:#6b5b73;margin:0 0 16px 0;font-size:13px}'
        '.current strong{color:#2d1b3d}'
        '.res{background:#f6f2fa;border-radius:10px;padding:14px 16px;margin:0 0 18px 0}'
        '.res .label{color:#6b5b73;text-transform:uppercase;letter-spacing:0.15em;font-size:11px;font-weight:700;margin:0 0 8px 0}'
        '.res .range{margin:0 0 4px 0;font-size:14px;color:#2d1b3d}'
        '</style></head>'
        '<body><div class="card">'
        '<h1>Set current guest</h1>'
        '<p class="sub">Shown on the TV and welcome pages as "Welcome, [name]".</p>'
        + res_panel +
        '<p class="current">Currently: <strong>' + (escaped or 'not set') + '</strong></p>'
        '<form method="post" action="/admin">'
        '<label for="guestName">Guest first name (leave blank to clear)</label>'
        '<input type="text" id="guestName" name="guestName" value="' + escaped + '" autofocus>'
        '<button type="submit">Save</button>'
        '</form>' + notice +
        '</div></body></html>'
    )


def _fetch_guest_name():
    try:
        r = requests.get(APPS_SCRIPT_URL, params={"api": "guest"}, timeout=8, allow_redirects=True)
        data = r.json()
        return data.get("name", "") if data.get("ok") else ""
    except Exception:
        return ""


def _fetch_reservation_labels():
    """Call /reservation locally to get fresh date labels and source."""
    try:
        r = requests.get("http://127.0.0.1:5000/reservation", timeout=15)
        data = r.json()
        return data.get("checkin_label", ""), data.get("checkout_label", ""), data.get("source", "")
    except Exception as e:
        log.warning("Local /reservation fetch failed: %s", e)
        return "", "", ""


@app.route("/admin", methods=["GET"])
def admin_get():
    guest = _fetch_guest_name()
    ci, co, src = _fetch_reservation_labels()
    return Response(_admin_html(guest, ci, co, src, saved=False), mimetype="text/html")


@app.route("/admin", methods=["POST"])
def admin_post():
    guest_name = (request.form.get("guestName") or "").strip()
    try:
        requests.post(
            APPS_SCRIPT_URL,
            params={"admin": "1"},
            data={"guestName": guest_name},
            timeout=10,
            allow_redirects=True,
        )
    except Exception as e:
        log.warning("Admin save push to Apps Script failed: %s", e)
    ci, co, src = _fetch_reservation_labels()
    return Response(_admin_html(guest_name, ci, co, src, saved=True), mimetype="text/html")


_events_cache = {"data": None, "fetched_at": 0}
_reservation_cache = {"data": None, "fetched_at": 0}


def _parse_ical_dates(text):
    """Lightweight iCal parser. Returns list of (start_date, end_date) tuples."""
    import datetime as _dt
    events = []
    in_event = False
    start = end = None
    for raw in text.splitlines():
        line = raw.strip()
        if line == "BEGIN:VEVENT":
            in_event = True
            start = end = None
        elif line == "END:VEVENT":
            if in_event and start and end:
                events.append((start, end))
            in_event = False
        elif in_event:
            if line.startswith("DTSTART"):
                value = line.split(":", 1)[-1].strip()
                start = _dt.date(int(value[0:4]), int(value[4:6]), int(value[6:8]))
            elif line.startswith("DTEND"):
                value = line.split(":", 1)[-1].strip()
                end = _dt.date(int(value[0:4]), int(value[4:6]), int(value[6:8]))
    return events


@app.route("/reservation", methods=["GET"])
def reservation():
    import datetime as _dt
    now = time.time()
    if _reservation_cache["data"] and (now - _reservation_cache["fetched_at"]) < RESERVATION_CACHE_TTL:
        return jsonify(_reservation_cache["data"])

    events = []
    errors = []
    alert_file_dir = "/opt/omada-auth"
    for url in ICAL_URLS:
        if "airbnb.com" in url.lower():
            source = "Airbnb"
        elif "vrbo.com" in url.lower() or "homeaway" in url.lower():
            source = "VRBO"
        else:
            source = "Other"
        alert_key = source.lower()
        alert_file = os.path.join(alert_file_dir, "ical_alert_" + alert_key + ".txt")
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            for s, e in _parse_ical_dates(r.text):
                events.append((s, e, source))
            # Fetch succeeded. Clear any previous alert marker.
            if os.path.exists(alert_file):
                try:
                    os.remove(alert_file)
                except Exception:
                    pass
        except Exception as exc:
            log.warning("iCal fetch failed for %s: %s", url, exc)
            errors.append(source + ": " + str(exc))
            # Send alert email, but at most once per 24h per source
            last_alerted = 0
            if os.path.exists(alert_file):
                try:
                    last_alerted = float(open(alert_file).read().strip())
                except Exception:
                    pass
            if (now - last_alerted) > 86400:
                try:
                    requests.post(
                        APPS_SCRIPT_URL,
                        params={"admin": "icalalert"},
                        json={"source": source, "url": url, "error": str(exc)},
                        timeout=8,
                        allow_redirects=True,
                    )
                    with open(alert_file, "w") as f:
                        f.write(str(now))
                except Exception as ae:
                    log.warning("iCal alert email failed: %s", ae)

    if not events and errors:
        return jsonify({"ok": False, "error": "; ".join(errors)}), 500

    today = _dt.date.today()
    current = None
    upcoming = None
    for s, e, src in sorted(events, key=lambda x: x[0]):
        if s <= today < e:
            current = (s, e, src)
            break
        if s > today and (upcoming is None or s < upcoming[0]):
            upcoming = (s, e, src)

    if current:
        s, e, src = current
        result = {
            "ok": True,
            "status": "current",
            "source": src,
            "checkin": s.isoformat(),
            "checkout": e.isoformat(),
            "checkin_label": s.strftime("%A, %B ") + str(s.day),
            "checkout_label": e.strftime("%A, %B ") + str(e.day),
        }
    elif upcoming:
        s, e, src = upcoming
        result = {
            "ok": True,
            "status": "upcoming",
            "source": src,
            "checkin": s.isoformat(),
            "checkout": e.isoformat(),
            "checkin_label": s.strftime("%A, %B ") + str(s.day),
            "checkout_label": e.strftime("%A, %B ") + str(e.day),
        }
    else:
        result = {"ok": True, "status": "none"}

    # Auto-clear guest name when a new reservation rolls in
    checkin_current = result.get("checkin", "")
    checkin_file = "/opt/omada-auth/last_checkin.txt"
    last_checkin = ""
    try:
        if os.path.exists(checkin_file):
            with open(checkin_file, "r") as f:
                last_checkin = f.read().strip()
    except Exception:
        pass

    if checkin_current and checkin_current != last_checkin:
        try:
            requests.post(
                APPS_SCRIPT_URL,
                params={"admin": "1"},
                data={"guestName": ""},
                timeout=8,
                allow_redirects=True,
            )
            log.info("Reservation rolled over (%s -> %s), cleared guest name", last_checkin, checkin_current)
        except Exception as e:
            log.warning("Auto-clear guest name failed: %s", e)
        try:
            with open(checkin_file, "w") as f:
                f.write(checkin_current)
        except Exception as e:
            log.warning("Could not write last_checkin.txt: %s", e)

    # Pull current guest name from Apps Script (manually set via admin page)
    try:
        gr = requests.get(APPS_SCRIPT_URL, params={"api": "guest"}, timeout=8, allow_redirects=True)
        gdata = gr.json()
        if gdata.get("ok") and gdata.get("name"):
            result["guest_name"] = gdata["name"]
    except Exception as e:
        log.warning("Guest name fetch failed: %s", e)

    # Push the reservation back to Apps Script so the admin page can show dates
    try:
        requests.post(
            APPS_SCRIPT_URL,
            params={"admin": "reservation"},
            json={
                "status": result.get("status", ""),
                "checkin": result.get("checkin", ""),
                "checkout": result.get("checkout", ""),
                "checkin_label": result.get("checkin_label", ""),
                "checkout_label": result.get("checkout_label", ""),
            },
            timeout=8,
            allow_redirects=True,
        )
    except Exception as e:
        log.warning("Reservation push to Apps Script failed: %s", e)

    _reservation_cache["data"] = result
    _reservation_cache["fetched_at"] = now
    return jsonify(result)


@app.route("/events", methods=["GET"])
def events():
    now = time.time()
    if _events_cache["data"] and (now - _events_cache["fetched_at"]) < EVENTS_CACHE_TTL:
        return jsonify(_events_cache["data"])

    try:
        start_iso = time.strftime("%Y-%m-%dT00:00:00Z", time.gmtime(now))
        r = requests.get(
            "https://app.ticketmaster.com/discovery/v2/events.json",
            params={
                "apikey": TM_API_KEY,
                "city": TM_CITY,
                "stateCode": TM_STATE,
                "size": 30,
                "sort": "date,asc",
                "startDateTime": start_iso,
            },
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        out = []
        for ev in data.get("_embedded", {}).get("events", []):
            start = ev.get("dates", {}).get("start", {}) or {}
            venues = ev.get("_embedded", {}).get("venues", []) or []
            venue_name = venues[0].get("name", "") if venues else ""
            classifications = ev.get("classifications", []) or []
            segment = ""
            if classifications:
                seg = classifications[0].get("segment") or {}
                segment = seg.get("name", "")
            out.append({
                "name": ev.get("name", ""),
                "url": ev.get("url", ""),
                "date": start.get("localDate", ""),
                "time": start.get("localTime", ""),
                "venue": venue_name,
                "segment": segment,
            })
        result = {"ok": True, "events": out, "count": len(out), "cached_at": int(now)}
        _events_cache["data"] = result
        _events_cache["fetched_at"] = now
        return jsonify(result)
    except Exception as e:
        log.exception("Ticketmaster fetch failed")
        return jsonify({"ok": False, "error": str(e)}), 500


def _verify_page_html(title, message, redirect_url=None):
    meta = ''
    script = ''
    if redirect_url:
        meta = '<meta http-equiv="refresh" content="{}; url={}">'.format(REDIRECT_SECONDS, redirect_url)
        script = '<script>setTimeout(function(){{window.top.location.href="{}"}},{});</script>'.format(
            redirect_url, REDIRECT_SECONDS * 1000
        )
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        + meta +
        '<title>' + title + '</title>'
        '<style>body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;'
        'background:linear-gradient(160deg,#2B1055 0%,#7597DE 30%,#FF5E62 65%,#FFB86C 100%);'
        'min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px;margin:0}'
        '.card{background:#fff;border-radius:16px;box-shadow:0 20px 60px rgba(0,0,0,.3);'
        'padding:40px 32px;max-width:440px;width:100%;text-align:center;color:#2d1b3d}'
        'h1{margin:0 0 12px 0;font-size:24px}p{color:#6b5b73;line-height:1.5}</style></head>'
        '<body><div class="card"><h1>' + title + '</h1><p>' + message + '</p></div>'
        + script +
        '</body></html>'
    )


@app.route("/verify", methods=["GET"])
def verify():
    token = request.args.get("token", "").strip()
    if not token:
        return Response(
            _verify_page_html("Invalid link", "No verification token was provided."),
            mimetype="text/html",
        )

    try:
        r = requests.get(
            APPS_SCRIPT_URL,
            params={"token": token, "api": "1"},
            timeout=15,
            allow_redirects=True,
        )
        data = r.json()
    except Exception as e:
        log.exception("Verify call to Apps Script failed")
        return Response(
            _verify_page_html("Verification error", "We could not reach the verification service. " + str(e)),
            mimetype="text/html",
        )

    if data.get("ok"):
        name = data.get("name", "")
        greeting = "Thank you" + (", " + name if name else "") + "."
        if data.get("status") == "already":
            msg = greeting + " This email has already been verified. Redirecting you to the welcome page..."
            title = "Already verified"
        else:
            msg = greeting + " Your email is verified. Redirecting you to the welcome page..."
            title = "Verified!"
        return Response(_verify_page_html(title, msg, REDIRECT_URL), mimetype="text/html")

    err = data.get("error", "Unknown error")
    return Response(_verify_page_html("Not found", "That verification link is invalid or expired. (" + err + ")"), mimetype="text/html")


@app.route("/authorize", methods=["POST"])
def authorize():
    body = request.get_json(silent=True) or {}
    required = ["clientMac", "apMac", "ssidName", "site"]
    missing = [k for k in required if not body.get(k)]
    if missing:
        return jsonify({"ok": False, "error": f"missing fields: {missing}"}), 400

    payload = {
        "clientMac": body["clientMac"],
        "apMac": body["apMac"],
        "ssidName": body["ssidName"],
        "radioId": int(body.get("radioId", 1)),
        "site": body["site"],
        "time": SESSION_DURATION_MS,
        "authType": 4,
    }

    try:
        cid = get_controller_id()
        s = requests.Session()
        token = operator_login(s, cid)
        result = authorize_guest(s, cid, token, payload)
    except Exception as e:
        log.exception("Omada auth call failed")
        return jsonify({"ok": False, "error": str(e)}), 500

    if result.get("errorCode") == 0:
        log.info("authorized %s on %s", body["clientMac"], body["ssidName"])
        return jsonify({"ok": True})

    log.warning("authorize returned errorCode %s: %s", result.get("errorCode"), result.get("msg"))
    return jsonify({"ok": False, "error": result.get("msg", "auth failed"), "code": result.get("errorCode")}), 500


if __name__ == "__main__":
    app.run(host=LISTEN_HOST, port=LISTEN_PORT)
