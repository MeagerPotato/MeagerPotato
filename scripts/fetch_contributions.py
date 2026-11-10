#!/usr/bin/env python3
"""
Fetch daily contribution counts for the last year and write data/contributions.json.

Sources, tried in order until one works:
  1. github.com/users/<user>/contributions, the public HTML fragment the
     profile page itself draws its calendar from (so the numbers match what
     visitors see, including private counts if that setting is on).
  2. github-contributions-api.jogruber.de, a public mirror of the same data.

Streaks and totals are worked out in render.py, so this file only stores days.
"""
import datetime
import json
import os
import re
import sys

import requests
from bs4 import BeautifulSoup

USER = os.environ.get("PROFILE_USER", "MeagerPotato")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "contributions.json")
UA = {"User-Agent": "profile-readme-bot/2.0"}


def from_github():
    resp = requests.get(f"https://github.com/users/{USER}/contributions", headers=UA, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    tips = {t.get("for"): t.get_text(strip=True) for t in soup.find_all("tool-tip")}
    days = []
    for td in soup.select("td.ContributionCalendar-day"):
        date = td.get("data-date")
        if not date:
            continue
        text = tips.get(td.get("id"), "")
        m = re.match(r"([\d,]+)", text)
        count = int(m.group(1).replace(",", "")) if m else 0
        days.append({"date": date, "count": count, "level": int(td.get("data-level") or 0)})
    return days


def from_mirror():
    resp = requests.get(f"https://github-contributions-api.jogruber.de/v4/{USER}?y=last", headers=UA, timeout=30)
    resp.raise_for_status()
    return [{"date": c["date"], "count": c["count"], "level": c["level"]} for c in resp.json()["contributions"]]


def main():
    days, source = None, None
    for name, fn in (("github", from_github), ("mirror", from_mirror)):
        try:
            got = fn()
            if len(got) >= 300:  # a full year is 365+ days; anything short means the markup changed
                days, source = got, name
                break
            print(f"{name}: only {len(got)} days, trying next source", file=sys.stderr)
        except Exception as e:  # noqa: BLE001 - any failure just moves on to the next source
            print(f"{name}: {e}", file=sys.stderr)
    if days is None:
        sys.exit("every contribution source failed; keeping the last saved data")

    days.sort(key=lambda d: d["date"])
    data = {
        "username": USER,
        "source": source,
        "fetched_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "days": days,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(data, f, indent=1)
        f.write("\n")
    print(f"contributions: {len(days)} days from {source}, {sum(d['count'] for d in days)} total")


if __name__ == "__main__":
    main()
