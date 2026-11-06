#!/usr/bin/env python3
"""
Collect what Allen has been working on lately and write data/activity.json.

Looks at his own public repos pushed in the last 30 days (90 if 30 is too quiet) and, for each
one, counts commits and pull requests and keeps a few recent titles. A one-line
"what is this" comes from the repo description, or the first sentence of its
README when the description is empty. Pull requests he opened in other people's
repos are picked up from his public event feed.

Uses GITHUB_TOKEN when it is set (the workflow passes it in) so rate limits are
not a problem, and works without one for local runs.
"""
import base64
import datetime
import json
import os
import re
import sys

import requests

USER = os.environ.get("PROFILE_USER", "MeagerPotato")
# look back 30 days; if that turns up fewer than 2 repos, widen to 90 so the card isn't empty
WINDOWS = (30, 90)
MAX_REPOS = 4
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "activity.json")

API = "https://api.github.com"
S = requests.Session()
S.headers.update({"Accept": "application/vnd.github+json", "User-Agent": "profile-readme-bot/2.0"})
if os.environ.get("GITHUB_TOKEN"):
    S.headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"

NOW = datetime.datetime.now(datetime.timezone.utc)
SINCE = NOW - datetime.timedelta(days=WINDOWS[0])


def get(path, **params):
    r = S.get(f"{API}{path}", params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def ts(s):
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def plain(md):
    """Markdown to plain text, good enough for one sentence."""
    md = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", md)            # images and badges
    md = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", md)         # links keep their text
    md = re.sub(r"<[^>]+>", "", md)                          # inline html
    md = re.sub(r"[*_`]+", "", md)
    return re.sub(r"\s+", " ", md).strip()


def first_sentence(text, limit=140):
    m = re.match(r"(.+?[.!?])(\s|$)", text)
    s = m.group(1) if m else text
    return s if len(s) <= limit else s[: limit - 1].rsplit(" ", 1)[0] + "…"


def blurb(repo):
    if repo.get("description"):
        return first_sentence(repo["description"].strip())
    try:
        readme = get(f"/repos/{repo['full_name']}/readme")
        body = base64.b64decode(readme["content"]).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001 - no README is fine
        return ""
    for para in re.split(r"\n\s*\n", body):
        p = para.strip()
        if not p or p.startswith(("#", "<", "|", "```", "-", "*", ">")) or p.startswith("[!["):
            continue
        text = plain(p)
        if len(text) > 20:
            return first_sentence(text)
    return ""


def is_noise(msg):
    first = msg.splitlines()[0] if msg else ""
    return "[skip ci]" in msg or first.startswith(("Merge pull request", "Merge branch", "Merge remote-tracking"))


def repo_activity(repo):
    name = repo["full_name"]
    commits = get(f"/repos/{name}/commits", since=SINCE.isoformat(), per_page=100)
    commits = [c for c in commits if len(c.get("parents", [])) < 2 and not is_noise(c["commit"]["message"])]

    pulls = get(f"/repos/{name}/pulls", state="all", sort="updated", direction="desc", per_page=50)
    opened = [p for p in pulls if ts(p["created_at"]) >= SINCE]
    merged = [p for p in pulls if p.get("merged_at") and ts(p["merged_at"]) >= SINCE]
    still_open = [p for p in opened if p["state"] == "open"]

    # newest first, whatever kind of work it was
    events = [(p["merged_at"], p["title"], "merged") for p in merged]
    events += [(p["created_at"], p["title"], "open") for p in still_open]
    events += [(c["commit"]["committer"]["date"], c["commit"]["message"].splitlines()[0].strip(), "commit")
               for c in commits]
    highlights, seen = [], set()
    for when, title, kind in sorted(events, key=lambda e: e[0], reverse=True):
        if title and title not in seen:
            seen.add(title)
            highlights.append({"title": title, "kind": kind, "date": when[:10]})

    dates = [ts(c["commit"]["committer"]["date"]) for c in commits]
    dates += [ts(p["created_at"]) for p in opened] + [ts(p["merged_at"]) for p in merged]
    last = max(dates) if dates else ts(repo["pushed_at"])

    return {
        "name": repo["name"],
        "url": repo["html_url"],
        "blurb": blurb(repo),
        "language": repo.get("language") or "",
        "stars": repo.get("stargazers_count", 0),
        "commits": len(commits),
        "prs_opened": len(opened),
        "prs_merged": len(merged),
        "prs_open": len(still_open),
        "highlights": highlights[:3],
        "last_active": last.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def outside_prs():
    """PRs opened in repos Allen doesn't own, from his public event feed."""
    found = {}
    try:
        events = get(f"/users/{USER}/events/public", per_page=100)
    except Exception as e:  # noqa: BLE001 - optional extra
        print(f"events: {e}", file=sys.stderr)
        return []
    for ev in events:
        if ev.get("type") != "PullRequestEvent" or ts(ev["created_at"]) < SINCE:
            continue
        repo = ev["repo"]["name"]
        if repo.split("/")[0].lower() == USER.lower():
            continue
        pr = ev.get("payload", {}).get("pull_request") or {}
        if ev["payload"].get("action") != "opened" or not pr.get("title"):
            continue
        item = found.setdefault(repo, {
            "name": repo, "url": f"https://github.com/{repo}", "blurb": "", "language": "",
            "stars": 0, "commits": 0, "prs_opened": 0, "prs_merged": 0, "prs_open": 0,
            "highlights": [], "last_active": ev["created_at"], "outside": True,
        })
        item["prs_opened"] += 1
        if len(item["highlights"]) < 3:
            item["highlights"].append({"title": pr["title"], "kind": "open", "date": ev["created_at"][:10]})
    return list(found.values())


def collect(repos):
    candidates = [
        r for r in repos
        if not r["fork"] and not r["archived"] and not r["private"]
        and r["name"].lower() != USER.lower() and ts(r["pushed_at"]) >= SINCE
    ]
    items = []
    for r in candidates:
        try:
            a = repo_activity(r)
        except Exception as e:  # noqa: BLE001 - skip one broken repo, keep the rest
            print(f"{r['full_name']}: {e}", file=sys.stderr)
            continue
        if a["commits"] or a["prs_opened"] or a["prs_merged"]:
            items.append(a)
    items += outside_prs()
    items.sort(key=lambda a: a["last_active"], reverse=True)
    return items


def main():
    global SINCE
    repos = get(f"/users/{USER}/repos", type="owner", sort="pushed", per_page=50)
    for days in WINDOWS:
        SINCE = NOW - datetime.timedelta(days=days)
        items = collect(repos)
        if len(items) >= 2:
            break

    data = {
        "username": USER,
        "fetched_at": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_days": days,
        "totals": {
            "repos": len(items),
            "commits": sum(a["commits"] for a in items),
            "prs_merged": sum(a["prs_merged"] for a in items),
            "prs_opened": sum(a["prs_opened"] for a in items),
        },
        "repos": items[:MAX_REPOS],
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(data, f, indent=1)
        f.write("\n")
    t = data["totals"]
    print(f"activity: {t['repos']} repos, {t['commits']} commits, {t['prs_merged']} merged PRs in {days} days")


if __name__ == "__main__":
    main()
