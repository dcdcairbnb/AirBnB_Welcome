#!/usr/bin/env python3
"""Airbnb Welcome Sign generator.

Fetches the Airbnb iCal feed, finds the current or next upcoming guest,
and writes an HTML welcome sign tuned for Nashville TN.
"""

from __future__ import annotations

import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

try:
    import requests
    from icalendar import Calendar
except ImportError as exc:
    sys.stderr.write(f"Missing dependency: {exc}\n")
    sys.stderr.write("Install with: pip install icalendar requests --break-system-packages\n")
    sys.exit(2)


ICAL_URL = (
    "https://www.airbnb.com/calendar/ical/1546687115825271453.ics"
    "?t=1fe96e5261b045f29205ffe550274e08"
)

# Writes the HTML to every reachable path below.
# The primary target (next to this script) works on any OS, including the
# Windows Task Scheduler runtime. The extra entries stay for backward compat
# with earlier Cowork-run deployments.
def output_paths() -> list[str]:
    here = Path(__file__).resolve().parent
    candidates = [
        str(here / "welcome_sign.html"),
        r"C:\Users\dancrose\Documents\WelcomeSign\welcome_sign.html",
        r"C:\Mac\Home\Documents\Claude\Projects\Welcome Sign\welcome_sign.html",
        "/sessions/serene-busy-sagan/mnt/Welcome Sign/welcome_sign.html",
        "/sessions/serene-busy-sagan/mnt/Documents/WelcomeSign/welcome_sign.html",
        "/sessions/nifty-jolly-archimedes/mnt/Welcome Sign/welcome_sign.html",
        "/sessions/serene-busy-sagan/mnt/outputs/welcome_sign.html",
    ]
    seen, out = set(), []
    for p in candidates:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


# Distances below are from 1011A 11th Ave N, Nashville 37208 (Germantown).
# Walking times use 20 min per mile, driving uses city speeds.
RESTAURANTS = [
    {
        "name": "Rolf and Daughters",
        "blurb": "Italian-inspired small plates, a Germantown standard.",
        "detail": "700 Taylor St.",
        "distance": "0.3 mi, 7 min walk",
    },
    {
        "name": "Butcher and Bee",
        "blurb": "Middle Eastern-influenced plates, strong brunch.",
        "detail": "902 Main St, East Nashville.",
        "distance": "2.3 mi, 8 min drive",
    },
    {
        "name": "City House",
        "blurb": "Wood-fired pizzas and house-made pasta.",
        "detail": "1222 4th Ave N.",
        "distance": "0.6 mi, 12 min walk or 3 min drive",
    },
    {
        "name": "Henrietta Red",
        "blurb": "Raw bar, oysters, wood-fired mains.",
        "detail": "1200 4th Ave N.",
        "distance": "0.6 mi, 12 min walk or 3 min drive",
    },
    {
        "name": "Von Elrod's Beer Hall",
        "blurb": "Beer garden with sausages, right next to First Horizon Park.",
        "detail": "1004 4th Ave N.",
        "distance": "0.5 mi, 10 min walk",
    },
    {
        "name": "Biscuit Love Gulch",
        "blurb": "Southern biscuits, bonuts, lines move fast.",
        "detail": "316 11th Ave S, The Gulch.",
        "distance": "2.0 mi, 7 min drive",
    },
    {
        "name": "Butchertown Hall",
        "blurb": "Bavarian-Texan meats, biergarten feel, craft cocktails.",
        "detail": "1416 4th Ave N, Germantown.",
        "distance": "0.7 mi, 14 min walk or 3 min drive",
    },
    {
        "name": "Monell's",
        "blurb": "Family-style Southern meat and three in a historic boardinghouse.",
        "detail": "1235 6th Ave N, Germantown.",
        "distance": "0.4 mi, 8 min walk",
    },
    {
        "name": "5th and Taylor",
        "blurb": "Modern Southern, seasonal menu, good for a special night.",
        "detail": "1411 5th Ave N, Germantown.",
        "distance": "0.6 mi, 12 min walk",
    },
    {
        "name": "Waldos Chicken and Beer",
        "blurb": "Rotisserie and fried chicken, big beer list, fast casual.",
        "detail": "1120 4th Ave N Suite 103, Germantown.",
        "distance": "0.5 mi, 10 min walk",
    },
]


THINGS_TO_DO = [
    {
        "name": "Walk the Cumberland River Greenway",
        "detail": "Start at Morgan Park, follow the river south into downtown.",
        "distance": "0.4 mi, 8 min walk to Morgan Park",
    },
    {
        "name": "Nashville Farmers' Market",
        "detail": "900 Rosa L Parks Blvd. Food hall plus produce vendors, open daily.",
        "distance": "1.0 mi, 20 min walk or 4 min drive",
    },
    {
        "name": "Bicentennial Capitol Mall State Park",
        "detail": "Walkable state history park, 95-bell carillon, across from the Farmers' Market.",
        "distance": "1.1 mi, 22 min walk or 4 min drive",
    },
    {
        "name": "Marathon Motor Works / Marathon Village",
        "detail": "Antonio's, Corsair Distillery, Grinder's Switch Winery under one roof.",
        "distance": "0.9 mi, 18 min walk or 4 min drive",
    },
    {
        "name": "Country Music Hall of Fame",
        "detail": "222 Rep. John Lewis Way S, downtown.",
        "distance": "2.0 mi, 7 min drive",
    },
    {
        "name": "Johnny Cash Museum",
        "detail": "119 3rd Ave S, downtown. Covers the Man in Black's career and Nashville roots.",
        "distance": "1.7 mi, 6 min drive",
    },
    {
        "name": "Honky Tonk Highway on Broadway",
        "detail": "Free live music all day, every day, between 2nd and 5th Ave.",
        "distance": "1.7 mi, 6 min drive",
    },
    {
        "name": "Nashville Sounds game at First Horizon Park",
        "detail": "Triple-A baseball in Germantown.",
        "distance": "0.4 mi, 8 min walk",
    },
    {
        "name": "Ryman Auditorium",
        "detail": "116 Rep. John Lewis Way N. Mother Church of Country Music, tours by day, shows most nights.",
        "distance": "1.6 mi, 6 min drive",
    },
    {
        "name": "Centennial Park and the Parthenon",
        "detail": "2500 West End Ave. Full-scale Parthenon replica, lake, and walking paths.",
        "distance": "2.8 mi, 10 min drive",
    },
]


HAPPY_HOUR = [
    {
        "name": "Von Elrod's Beer Hall",
        "hours": "Mon-Fri, 3-6 PM",
        "blurb": "Discounted drafts and bites, big biergarten patio.",
        "detail": "1004 4th Ave N, Germantown.",
        "distance": "0.5 mi, 10 min walk",
    },
    {
        "name": "Henrietta Red",
        "hours": "Tue-Sat, 3-5 PM",
        "blurb": "Oyster hour with discounted bivalves and bar snacks.",
        "detail": "1200 4th Ave N, Germantown.",
        "distance": "0.6 mi, 12 min walk",
    },
    {
        "name": "Butchertown Hall",
        "hours": "Mon-Fri, 3-6 PM",
        "blurb": "Half-price cocktails, beers, and bar bites.",
        "detail": "1416 4th Ave N, Germantown.",
        "distance": "0.7 mi, 14 min walk or 3 min drive",
    },
    {
        "name": "5th and Taylor",
        "hours": "Tue-Fri, 5-6 PM (bar only)",
        "blurb": "Bar happy hour with deviled eggs and house cocktails.",
        "detail": "1411 5th Ave N, Germantown.",
        "distance": "0.6 mi, 12 min walk",
    },
    {
        "name": "Rolf and Daughters",
        "hours": "Nightly, 5-6 PM (bar only)",
        "blurb": "Early bar seating with snack menu and wine specials.",
        "detail": "700 Taylor St, Germantown.",
        "distance": "0.3 mi, 7 min walk",
    },
    {
        "name": "The Mockingbird",
        "hours": "Mon-Fri, 3-6 PM",
        "blurb": "Global comfort food, $2 off cocktails and drafts.",
        "detail": "121 12th Ave N, The Gulch.",
        "distance": "1.6 mi, 6 min drive",
    },
    {
        "name": "Neighbors of Germantown",
        "hours": "Mon-Fri, 4-6 PM",
        "blurb": "Cocktail bar feel, discounted drinks and shareable bites.",
        "detail": "1206 4th Ave N, Germantown.",
        "distance": "0.5 mi, 10 min walk",
    },
    {
        "name": "Jonathan's Grille Germantown",
        "hours": "Daily, 3-6 PM",
        "blurb": "Sports bar staple, discounted apps, drafts, and wells.",
        "detail": "900 Rosa L Parks Blvd, Germantown.",
        "distance": "0.9 mi, 4 min drive",
    },
    {
        "name": "Whiskey Kitchen",
        "hours": "Mon-Fri, 4-6 PM",
        "blurb": "Half-price wells, wines, and select drafts, shareable bar plates.",
        "detail": "118 12th Ave S, The Gulch.",
        "distance": "1.8 mi, 6 min drive",
    },
    {
        "name": "Saint Anejo",
        "hours": "Mon-Fri, 3-6 PM",
        "blurb": "Mexican kitchen with 100+ tequilas, half-off select margaritas and tacos.",
        "detail": "1120 McGavock St, The Gulch.",
        "distance": "1.8 mi, 6 min drive",
    },
]


ROOFTOPS = [
    {
        "name": "L.A. Jackson",
        "blurb": "Thompson Hotel rooftop, Gulch and skyline views, strong cocktails.",
        "detail": "401 11th Ave S, The Gulch.",
        "distance": "2.1 mi, 7 min drive",
    },
    {
        "name": "White Limozeen",
        "blurb": "Dolly-themed pink oasis at the Graduate Hotel, flamingos and panoramic views.",
        "detail": "101 20th Ave N, Midtown.",
        "distance": "2.5 mi, 9 min drive",
    },
    {
        "name": "Bobby Hotel Rooftop Lounge",
        "blurb": "Vintage bus on the roof, fire pits, downtown skyline from above.",
        "detail": "230 4th Ave N, downtown.",
        "distance": "1.5 mi, 6 min drive",
    },
    {
        "name": "Rare Bird at Noelle",
        "blurb": "Quieter rooftop with craft cocktails and a clean view of downtown.",
        "detail": "200 4th Ave N, downtown.",
        "distance": "1.4 mi, 6 min drive",
    },
    {
        "name": "UP Rooftop Lounge",
        "blurb": "Fairlane Hotel rooftop, panoramic skyline, late-night vibe.",
        "detail": "401 Union St, downtown.",
        "distance": "1.5 mi, 6 min drive",
    },
    {
        "name": "Canopy by Hilton Rooftop",
        "blurb": "Downtown rooftop with cocktails and fire pits, quieter than the Broadway crush.",
        "detail": "617 Church St, downtown.",
        "distance": "1.6 mi, 6 min drive",
    },
    {
        "name": "The Pool Club at Virgin Hotels",
        "blurb": "Rooftop pool bar with Music Row views, DJ most nights.",
        "detail": "1 Music Sq W, Music Row.",
        "distance": "2.8 mi, 10 min drive",
    },
    {
        "name": "Hyatt Centric Rooftop",
        "blurb": "Downtown rooftop pool lounge, skyline views, day-to-night crowd.",
        "detail": "815 Commerce St, downtown.",
        "distance": "1.6 mi, 6 min drive",
    },
    {
        "name": "1 Hotel Nashville Rooftop",
        "blurb": "Sleek Gulch rooftop, pool bar feel, solid cocktails.",
        "detail": "710 Demonbreun St, The Gulch.",
        "distance": "1.9 mi, 7 min drive",
    },
    {
        "name": "The Joseph Nashville Rooftop",
        "blurb": "Quiet luxury hotel rooftop near the stadium, curated wine and art focus.",
        "detail": "401 Korean Veterans Blvd, SoBro.",
        "distance": "2.0 mi, 7 min drive",
    },
]


HOUSE_INFO = {
    "wifi": "Scan the QR code on the fridge.",
    "checkout_time": "10:00 AM",
    "contact": "Text Dan at 816-686-5888 for anything urgent.",
}


def fetch_ical(url: str) -> bytes:
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    return resp.content


def to_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    return value


def clean_summary(summary: str) -> str:
    if not summary:
        return ""
    text = str(summary).strip()
    for prefix in ("Reserved - ", "Reserved: ", "Reserved -", "Reserved"):
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix):].strip(" -:")
            break
    return text


def extract_guest_name(event) -> str:
    summary = clean_summary(str(event.get("SUMMARY", "")))
    if summary and summary.lower() not in {"airbnb", "reserved", "not available", "blocked"}:
        return summary
    description = str(event.get("DESCRIPTION", "")) if event.get("DESCRIPTION") else ""
    match = re.search(r"Guest:\s*([A-Za-z][A-Za-z '\-]+)", description)
    if match:
        return match.group(1).strip()
    return "Guest"


def pick_event(events, today: date):
    current = []
    upcoming = []
    for ev in events:
        summary = str(ev.get("SUMMARY", "")).strip().lower()
        if summary in {"airbnb (not available)", "not available", "blocked", "unavailable"}:
            continue
        dtstart = ev.get("DTSTART")
        dtend = ev.get("DTEND")
        if not dtstart or not dtend:
            continue
        start = to_date(dtstart.dt)
        end = to_date(dtend.dt)
        if start <= today < end:
            current.append((start, end, ev))
        elif start >= today and (start - today).days <= 30:
            upcoming.append((start, end, ev))
    if current:
        current.sort(key=lambda x: x[0])
        return current[0], "current"
    if upcoming:
        upcoming.sort(key=lambda x: x[0])
        return upcoming[0], "upcoming"
    return None, None


def format_date(d: date) -> str:
    return d.strftime("%A, %B %-d") if os.name != "nt" else d.strftime("%A, %B %#d")


def render_html(guest_name: str, start: date, end: date, status: str, generated_at: datetime) -> str:
    personal = guest_name and guest_name != "Guest"
    if status == "current":
        headline = f"Welcome, {guest_name}." if personal else "Welcome."
        subheadline = f"Your stay is through {format_date(end)}."
    elif status == "upcoming":
        headline = f"Welcome, {guest_name}." if personal else "Welcome."
        subheadline = f"Check in on {format_date(start)}. Checkout {format_date(end)}."
    else:
        headline = "Welcome."
        subheadline = "No active reservation on file."

    restaurants_html = "\n".join(
        f"""<li class=\"card\">\n<h4>{r['name']}</h4>\n<p class=\"blurb\">{r['blurb']}</p>\n<p class=\"detail\">{r['detail']}</p>\n<p class=\"distance\">{r['distance']}</p>\n</li>"""
        for r in RESTAURANTS
    )

    things_html = "\n".join(
        f"""<li class=\"card\">\n<h4>{t['name']}</h4>\n<p class=\"detail\">{t['detail']}</p>\n<p class=\"distance\">{t['distance']}</p>\n</li>"""
        for t in THINGS_TO_DO
    )

    happy_html = "\n".join(
        f"""<li class=\"card\">\n<h4>{h['name']}</h4>\n<p class=\"hours\">{h['hours']}</p>\n<p class=\"blurb\">{h['blurb']}</p>\n<p class=\"detail\">{h['detail']}</p>\n<p class=\"distance\">{h['distance']}</p>\n</li>"""
        for h in HAPPY_HOUR
    )

    rooftops_html = "\n".join(
        f"""<li class=\"card\">\n<h4>{r['name']}</h4>\n<p class=\"blurb\">{r['blurb']}</p>\n<p class=\"detail\">{r['detail']}</p>\n<p class=\"distance\">{r['distance']}</p>\n</li>"""
        for r in ROOFTOPS
    )

    house_html = f"""
    <div class=\"house\">
      <div><strong>Wi-Fi:</strong> {HOUSE_INFO['wifi']}</div>
      <div><strong>Checkout:</strong> {HOUSE_INFO['checkout_time']}</div>
      <div><strong>Contact:</strong> {HOUSE_INFO['contact']}</div>
    </div>
    """

    return f"""<!doctype html>
<html lang=\"en\">
<head>
<meta charset=\"utf-8\" />
<meta http-equiv=\"refresh\" content=\"3600\" />
<title>Welcome</title>
<style>
  :root {{
    --bg: #0b1f2a;
    --panel: #122c3a;
    --ink: #f5efe0;
    --accent: #e8a03a;
    --muted: #a9b8c0;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    font-family: 'Helvetica Neue', Arial, sans-serif;
    background: var(--bg);
    color: var(--ink);
    min-height: 100vh;
    padding: 4vh 5vw;
  }}
  header {{
    text-align: center;
    margin-bottom: 4vh;
  }}
  h1 {{
    font-size: 5.5vw;
    margin: 0 0 1vh 0;
    letter-spacing: -0.02em;
  }}
  .sub {{
    font-size: 2vw;
    color: var(--accent);
    margin: 0;
  }}
  .dates {{
    font-size: 1.3vw;
    color: var(--muted);
    margin-top: 1vh;
  }}
  h2 {{
    font-size: 2.4vw;
    border-bottom: 2px solid var(--accent);
    padding-bottom: 0.5vh;
    margin-top: 5vh;
  }}
  ul {{
    list-style: none;
    padding: 0;
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 1.2vw;
  }}
  .card {{
    background: var(--panel);
    border-left: 4px solid var(--accent);
    padding: 1.5vh 1.5vw;
    border-radius: 4px;
  }}
  h4 {{
    margin: 0 0 0.5vh 0;
    font-size: 1.4vw;
  }}
  .blurb {{
    margin: 0 0 0.5vh 0;
    font-size: 1.1vw;
  }}
  .detail {{
    margin: 0;
    color: var(--muted);
    font-size: 1vw;
  }}
  .distance {{
    margin: 0.4vh 0 0 0;
    color: var(--accent);
    font-size: 0.95vw;
    font-weight: 600;
  }}
  .hours {{
    margin: 0 0 0.5vh 0;
    color: var(--accent);
    font-size: 1.05vw;
    font-weight: 700;
    letter-spacing: 0.02em;
  }}
  .house {{
    background: var(--panel);
    padding: 2vh 2vw;
    border-radius: 6px;
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 1vh 2vw;
    font-size: 1.1vw;
  }}
  footer {{
    margin-top: 5vh;
    text-align: center;
    color: var(--muted);
    font-size: 0.9vw;
  }}
</style>
</head>
<body>
  <header>
    <h1>{headline}</h1>
    <p class=\"sub\">{subheadline}</p>
    <p class=\"dates\">Nashville TN</p>
  </header>

  <section>
    <h2>House info</h2>
    {house_html}
  </section>

  <section>
    <h2>Where to eat</h2>
    <ul>
      {restaurants_html}
    </ul>
  </section>

  <section>
    <h2>Happy hour</h2>
    <p class=\"detail\" style=\"margin-bottom:1.5vh;\">Happy hours can change, you may want to call ahead.</p>
    <ul>
      {happy_html}
    </ul>
  </section>

  <section>
    <h2>Rooftop bars</h2>
    <p class=\"detail\" style=\"margin-bottom:1.5vh;\">Views of the Nashville skyline, call ahead on weekends.</p>
    <ul>
      {rooftops_html}
    </ul>
  </section>

  <section>
    <h2>Things to do</h2>
    <ul>
      {things_html}
    </ul>
  </section>

  <footer>
    Updated {generated_at.strftime('%Y-%m-%d %H:%M %Z').strip()}
  </footer>
</body>
</html>
"""


def write_output(html: str) -> list[str]:
    written = []
    for path in output_paths():
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(html, encoding="utf-8")
            written.append(str(p))
        except Exception as exc:
            sys.stderr.write(f"Skipped {path}: {exc}\n")
    return written


def main() -> int:
    today = datetime.now(timezone.utc).date()
    try:
        raw = fetch_ical(ICAL_URL)
    except Exception as exc:
        sys.stderr.write(f"Failed to fetch iCal: {exc}\n")
        return 1

    try:
        cal = Calendar.from_ical(raw)
    except Exception as exc:
        sys.stderr.write(f"Failed to parse iCal: {exc}\n")
        return 1

    events = [c for c in cal.walk() if c.name == "VEVENT"]
    picked, status = pick_event(events, today)

    if picked is None:
        guest = "Guest"
        start = today
        end = today + timedelta(days=1)
        status = "none"
    else:
        start, end, ev = picked
        guest = extract_guest_name(ev)

    html = render_html(guest, start, end, status, datetime.now())
    written = write_output(html)

    print(f"Events found: {len(events)}")
    print(f"Selected status: {status}")
    print(f"Guest: {guest}")
    print(f"Start: {start}  End: {end}")
    print("Wrote:")
    for w in written:
        print(f"  {w}")
    if not written:
        print("WARNING: no output files written")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
