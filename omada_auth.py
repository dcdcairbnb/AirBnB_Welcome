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
import logging
from flask import Flask, request, jsonify
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
