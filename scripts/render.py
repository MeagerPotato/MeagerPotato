#!/usr/bin/env python3
"""
Draw the profile from data/contributions.json and data/activity.json.

Writes the SVG cards into profile/ and rebuilds README.md from
profile/README.template.md. Everything is plain SVG with CSS animation, because
GitHub shows README images as <img> and runs no JavaScript inside them.

    python scripts/render.py
"""
import base64
import datetime
import html
import json
import os
import random

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "profile")

# GitHub's calendar dates are UTC, so the "synced" date uses UTC too and the two always agree
TZ = datetime.timezone.utc

W = 880
# The palette is allenkh.com's (src/universe/design/tokens.ts), so the profile and the site read as one thing
BG = "#0a0f1f"      # space 900
DEEP = "#060914"    # space 950: the ledge under a block
PANEL = "#121a36"
LINE = "#2c3a6b"
INK = "#f1f3fb"
MUTED = "#b9c1dc"
DIM = "#8e98ba"
CORAL = "#f19389"
BUTTER = "#f8d98c"
MINT = "#b8eac4"
SKY = "#8bc0f2"
LILAC = "#ab86bf"
# empty, then dusk to coral to butter: brighter with every level, in the rocket plume's colours
LEVELS = ["#172042", "#6a5585", "#b56f86", CORAL, BUTTER]
LANG = {"TypeScript": "#3178c6", "JavaScript": "#f1e05a", "Python": "#3572a5", "C++": "#f34b7d",
        "C": "#555555", "Rust": "#dea584", "Go": "#00add8", "Java": "#b07219", "HTML": "#e34c26",
        "CSS": "#663399", "Jupyter Notebook": "#da5b0b", "MATLAB": "#e16737", "Swift": "#f05138"}

MONO = "ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,'Liberation Mono',monospace"
SANS = "Outfit,-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"

# Outfit, the site's typeface, travels inside every card: an <img> may not fetch a font, but it may carry one.
# Where a browser refuses even that, the system sans above takes over.
FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
with open(os.path.join(FONTS, "outfit-latin.woff2"), "rb") as _f:
    FONT_FACE = ("@font-face{font-family:Outfit;font-weight:100 900;src:url(data:font/woff2;base64,"
                 + base64.b64encode(_f.read()).decode() + ") format('woff2')}")
with open(os.path.join(FONTS, "outfit-widths.json")) as _f:
    ADVANCE = json.load(_f)  # advance widths per em, at weights 400 and 700


# ---------------------------------------------------------------- helpers

def esc(s):
    return html.escape(str(s), quote=True)


def d(s):
    return datetime.date.fromisoformat(s[:10])


def md(date):
    return f"{date:%b} {date.day}"


def mdy(date):
    return f"{date:%b} {date.day}, {date.year}"


def width(text, size, mono=False, bold=False):
    """Rendered width, so text can be wrapped and trimmed without a browser."""
    if mono:
        return len(text) * size * 0.6
    table = ADVANCE["700" if bold else "400"]
    return sum(size * table.get(c, 0.62) for c in text)


def clip(text, size, max_w, mono=False):
    if width(text, size, mono) <= max_w:
        return text
    while text and width(text + "…", size, mono) > max_w:
        text = text[:-1]
    return text.rstrip(" ,;:-") + "…"


def wrap(text, size, max_w, max_lines):
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if width(trial, size) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = clip(lines[-1] + " …", size, max_w)
    return lines


def svg(h, body, style="", w=W):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'font-family="{SANS}">\n<style>{FONT_FACE}{style}'
        "@media (prefers-reduced-motion: reduce){*{animation:none!important;opacity:1!important;}}"
        f"</style>\n{body}\n</svg>\n"
    )


def frame(h, extra=""):
    return (f'<rect x="1" y="1" width="{W-2}" height="{h-2}" rx="15" fill="{BG}" stroke="{LINE}" stroke-width="2"/>{extra}')


def block(x, y, w, h, rx=10, fill=PANEL):
    """The site's matte block: a solid plate, one hairline edge, a navy ledge under it."""
    return (f'<rect x="{x}" y="{y + 3}" width="{w}" height="{h}" rx="{rx}" fill="{DEEP}"/>'
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{LINE}" stroke-width="2"/>')


def label(x, y, text, color=BUTTER, anchor="start"):
    return (f'<text x="{x}" y="{y}" font-family="{MONO}" font-size="11.5" font-weight="600" letter-spacing="2" '
            f'fill="{color}" text-anchor="{anchor}">{esc(text)}</text>')


def sign(x, y, text, color):
    """A card's name, as the site signs a route: a dot in the family's colour, then the name."""
    return f'<circle cx="{x + 4}" cy="{y - 4}" r="4" fill="{color}"/>' + label(x + 16, y, text, color)


def write(name, content):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "w") as f:
        f.write(content)


# ---------------------------------------------------------------- stats

def stats(days):
    total = sum(x["count"] for x in days)
    active = [x for x in days if x["count"] > 0]

    i = len(days) - 1
    if days[i]["count"] == 0:
        i -= 1  # today isn't over, so an empty today doesn't break the streak
    cur = 0
    while i >= 0 and days[i]["count"] > 0:
        cur += 1
        i -= 1
    cur_start = days[i + 1]["date"] if cur else None

    best_len = run = 0
    best_span = (None, None)
    for j, x in enumerate(days):
        run = run + 1 if x["count"] else 0
        if run > best_len:
            best_len, best_span = run, (days[j - run + 1]["date"], x["date"])

    # weeks run Sunday to Saturday, the same columns as the graph
    weeks = {}
    for x in days:
        dt = d(x["date"])
        start = dt - datetime.timedelta(days=(dt.weekday() + 1) % 7)
        weeks[start] = weeks.get(start, 0) + x["count"]
    keys = sorted(weeks)
    k = len(keys) - 1
    if weeks[keys[k]] == 0:
        k -= 1  # this week isn't over yet either
    wk = 0
    while k >= 0 and weeks[keys[k]] > 0:
        wk += 1
        k -= 1

    best_day = max(days, key=lambda x: x["count"])
    return {
        "total": total,
        "active_days": len(active),
        "current": cur,
        "current_start": cur_start,
        "longest": best_len,
        "longest_span": best_span,
        "week_streak": wk,
        "best_day": best_day,
        "last_active": active[-1]["date"] if active else None,
        "today": days[-1]["date"],
    }


# ---------------------------------------------------------------- cards

def hero(st, synced):
    h = 230
    rnd = random.Random(7)  # fixed seed so the stars don't move between runs
    stars = []
    for n in range(90):
        x, y = rnd.uniform(14, W - 14), rnd.uniform(14, h - 14)
        if x < 470 and 30 < y < 215 and n % 3:
            continue  # keep the area behind the name mostly clear
        r = rnd.choice([0.6, 0.8, 0.8, 1.0, 1.3])
        o = rnd.uniform(0.25, 0.8)
        tw = f' class="tw" style="animation-delay:{rnd.uniform(0, 4):.2f}s"' if n % 4 == 0 else ""
        stars.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{INK}" opacity="{o:.2f}"{tw}/>')

    cx, cy = 690, 116
    orbit = (f'M {cx-150} {cy} A 150 46 0 1 1 {cx+150} {cy} A 150 46 0 1 1 {cx-150} {cy}')
    chips, x = [], 40
    for _, _, text, color in LINKS:
        cw = round(width(text, 13) + 44)
        chips.append(block(x, 158, cw, 28, rx=8)
                     + f'<rect x="{x + 10}" y="167" width="10" height="10" rx="2.5" fill="{color}"/>'
                     + f'<text x="{x + 28}" y="177" font-size="13" font-weight="600" fill="{INK}">{esc(text)}</text>')
        x += cw + 10

    status = f"{st['total']:,} contributions this year · synced {mdy(synced)}"
    body = f'''
<defs>
  <radialGradient id="glow" cx="{cx}" cy="{cy}" r="260" gradientUnits="userSpaceOnUse">
    <stop offset="0" stop-color="{LILAC}" stop-opacity="0.22"/><stop offset="1" stop-color="{CORAL}" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="planet" cx="0.35" cy="0.3" r="0.8">
    <stop offset="0" stop-color="{BUTTER}"/><stop offset="0.55" stop-color="{CORAL}"/><stop offset="1" stop-color="#c3645c"/>
  </radialGradient>
  <clipPath id="card"><rect x="1" y="1" width="{W-2}" height="{h-2}" rx="13"/></clipPath>
</defs>
{frame(h)}
<g clip-path="url(#card)">
  <rect width="{W}" height="{h}" fill="url(#glow)"/>
  {''.join(stars)}
  <g transform="rotate(-14 {cx} {cy})">
    <path d="{orbit}" fill="none" stroke="{DIM}" stroke-width="1" stroke-dasharray="3 6" opacity="0.8"/>
    <circle cx="{cx}" cy="{cy}" r="30" fill="url(#planet)"/>
    <path d="M {cx-150} {cy} A 150 46 0 0 0 {cx+150} {cy}" fill="none" stroke="{CORAL}" stroke-width="1.2" opacity="0.35"/>
    <circle r="4.5" fill="{BUTTER}"><animateMotion dur="14s" repeatCount="indefinite" path="{orbit}"/></circle>
    <circle r="10" fill="{BUTTER}" opacity="0.18"><animateMotion dur="14s" repeatCount="indefinite" path="{orbit}"/></circle>
  </g>
</g>
<g class="in">
  {label(40, 48, "// MEAGERPOTATO", CORAL)}
  <text x="38" y="98" font-size="46" font-weight="700" fill="{INK}" letter-spacing="-0.5">Allen Hsieh</text>
  <text x="40" y="128" font-size="17" fill="{MUTED}">Aerospace Engineering @ UC Berkeley</text>
  {''.join(chips)}
  <circle class="pulse" cx="45" cy="210" r="3.5" fill="{MINT}"/>
  <text x="56" y="214" font-family="{MONO}" font-size="12" fill="{DIM}">{esc(status)}</text>
</g>'''
    style = (".tw{animation:tw 4s ease-in-out infinite}@keyframes tw{50%{opacity:.1}}"
             ".pulse{animation:pulse 2.4s ease-in-out infinite}@keyframes pulse{50%{opacity:.25}}"
             ".in{animation:in .8s ease-out both}@keyframes in{from{opacity:0;transform:translateY(8px)}}")
    return svg(h, body, style)


def streak(st):
    h = 280
    # ring: how far the current streak is toward the longest one
    rcx, rcy, r = 160, 140, 84
    circ = 2 * 3.14159265 * r
    frac = min(1.0, st["current"] / st["longest"]) if st["longest"] else 0
    arc = circ * frac
    if st["current"]:
        hint = f"since {md(d(st['current_start']))}"
    elif st["last_active"]:
        hint = f"last active {md(d(st['last_active']))}"
    else:
        hint = "no activity yet"

    ls, le = st["longest_span"]
    tiles = [
        ("LONGEST STREAK", f"{st['longest']}", "days", f"{md(d(ls))} to {md(d(le))}" if ls else "none yet"),
        ("WEEKLY STREAK", f"{st['week_streak']}", "week" if st["week_streak"] == 1 else "weeks", "weeks in a row with activity"),
        ("CONTRIBUTIONS", f"{st['total']:,}", "", f"{st['active_days']} active days, last 12 months"),
        ("BEST DAY", f"{st['best_day']['count']:,}", "contribution" if st["best_day"]["count"] == 1 else "contributions", mdy(d(st["best_day"]["date"]))),
    ]
    tx, ty, tw_, th, gap = 330, 28, 251, 106, 14
    tiles_svg = []
    for n, (name, big, small, sub) in enumerate(tiles):
        x = tx + (n % 2) * (tw_ + gap)
        y = ty + (n // 2) * (th + gap)
        bw = width(big, 34, bold=True)
        tiles_svg.append(f'''
<g class="tile" style="animation-delay:{0.15 + n * 0.12:.2f}s">
  {block(x, y, tw_, th)}
  {label(x + 18, y + 28, name, DIM)}
  <text x="{x + 17}" y="{y + 68}" font-size="34" font-weight="700" fill="{INK}">{esc(big)}</text>
  <text x="{x + 24 + bw:.0f}" y="{y + 68}" font-size="15" fill="{MUTED}">{esc(small)}</text>
  <text x="{x + 18}" y="{y + 90}" font-size="12.5" fill="{DIM}">{esc(clip(sub, 12.5, tw_ - 34))}</text>
</g>''')

    # while a streak is alive the ring breathes: a soft wave leaves it every few seconds
    halo = (f'<circle class="halo" cx="{rcx}" cy="{rcy + 8}" r="{r}" fill="none" stroke="{BUTTER}" stroke-width="14" opacity="0"/>'
            if st["current"] else "")
    body = f'''
<defs>
  <linearGradient id="plume" x1="0" y1="1" x2="1" y2="0">
    <stop offset="0" stop-color="{CORAL}"/><stop offset="1" stop-color="{BUTTER}"/>
  </linearGradient>
</defs>
{frame(h)}
{sign(40, 44, "STREAK", CORAL)}
<circle cx="{rcx}" cy="{rcy + 8}" r="{r}" fill="none" stroke="{PANEL}" stroke-width="14"/>
<circle cx="{rcx}" cy="{rcy + 8}" r="{r}" fill="none" stroke="{LINE}" stroke-width="1" stroke-dasharray="2 5" opacity="0.9"/>
<circle class="arc" opacity="{1 if arc else 0}" cx="{rcx}" cy="{rcy + 8}" r="{r}" fill="none" stroke="url(#plume)" stroke-width="14"
  stroke-linecap="round" stroke-dasharray="{arc:.1f} {circ:.1f}" transform="rotate(-90 {rcx} {rcy + 8})"
  style="--len:{arc:.1f}"/>
{halo}
<text class="num" x="{rcx}" y="{rcy + 22}" font-size="58" font-weight="700" fill="{INK}" text-anchor="middle">{st['current']}</text>
<text x="{rcx}" y="{rcy + 46}" font-family="{MONO}" font-size="12" fill="{MUTED}" text-anchor="middle">day streak</text>
<text x="{rcx}" y="{h - 22}" font-family="{MONO}" font-size="12" fill="{DIM}" text-anchor="middle">{esc(hint)}</text>
{''.join(tiles_svg)}'''
    style = (f".arc{{animation:draw 1.4s cubic-bezier(.2,.7,.2,1) .2s both}}"
             f"@keyframes draw{{from{{stroke-dasharray:0 {circ:.1f}}}}}"
             ".num{animation:land .55s cubic-bezier(.2,1.5,.4,1) 1.1s both;transform-box:fill-box;transform-origin:center}"
             "@keyframes land{from{opacity:0;transform:scale(.5)}}"
             ".halo{animation:breathe 3.2s ease-out 1.9s infinite}"
             "@keyframes breathe{0%{opacity:.4;stroke-width:14px}70%,100%{opacity:0;stroke-width:40px}}"
             "@media (prefers-reduced-motion: reduce){.halo{display:none}}"
             ".tile{animation:up .5s ease-out both}@keyframes up{from{opacity:0;transform:translateY(10px)}}")
    return svg(h, body, style)


def graph(days, st):
    h = 236
    first = d(days[0]["date"])
    lead = (first.weekday() + 1) % 7  # Sunday = row 0
    cell, step = 12, 15
    cols = (lead + len(days) + 6) // 7
    top = 86
    grid_w = cols * step - (step - cell)
    left = (W - grid_w - 28) // 2 + 28  # center the grid, leaving room for day labels

    rects, over, months = [], [], []
    seen = set()
    for n, x in enumerate(days):
        pos = lead + n
        c, row = pos // 7, pos % 7
        cx, cy = left + c * step, top + row * step
        dt = d(x["date"])
        # label a month at the first column that holds its 1st (and the very first column)
        key = (dt.year, dt.month)
        if (dt.day <= 7 and row == (dt.weekday() + 1) % 7 and c not in seen and key not in seen) or n == 0:
            seen.update({c, key})
            if c < cols - 1 and not (n == 0 and dt.day > 21):
                months.append(f'<text x="{cx}" y="{top - 10}" font-size="11.5" fill="{MUTED}">{dt:%b}</text>')
        # the graph floods in left to right, and every active day pops as the wave reaches it: the busier
        # the day, the further it swells and the longer it glows
        delay = c * 0.065 + row * 0.02
        lv = x["level"]
        tip = f"{x['count']} on {mdy(dt)}"
        box = f'x="{cx}" y="{cy}" width="{cell}" height="{cell}" rx="2.5"'
        rects.append((lv, f'<rect class="c l{lv}" {box} fill="{LEVELS[lv]}" '
                          f'style="animation-delay:{delay:.2f}s"><title>{tip}</title></rect>'))
        if lv >= 3:
            over.append(f'<rect class="ping p{lv}" {box} fill="none" stroke="{LEVELS[lv]}" stroke-width="1.5" '
                        f'style="animation-delay:{delay + 0.12:.2f}s"/>')
        if x["date"] == st["today"]:
            over.append(f'<rect class="today" x="{cx - 1.5}" y="{cy - 1.5}" width="{cell + 3}" height="{cell + 3}" rx="4" '
                        f'fill="none" stroke="{INK}" stroke-width="1.5" style="animation-delay:{delay + 0.5:.2f}s"/>')
    # busier days are drawn later, so a swelling day covers its quieter neighbours and not the other way round
    rects = [r for _, r in sorted(rects, key=lambda t: t[0])]

    day_labels = "".join(
        f'<text x="{left - 10}" y="{top + r * step + 10}" font-size="10.5" fill="{DIM}" text-anchor="end">{n}</text>'
        for n, r in (("Mon", 1), ("Wed", 3), ("Fri", 5)))
    lx = W - 40 - 5 * 15 - 36
    legend = (f'<text x="{lx - 8}" y="{h - 26}" font-size="11" fill="{DIM}" text-anchor="end">less</text>'
              + "".join(f'<rect x="{lx + i * 15}" y="{h - 36}" width="12" height="12" rx="2.5" fill="{c}"/>'
                        for i, c in enumerate(LEVELS))
              + f'<text x="{lx + 5 * 15 + 4}" y="{h - 26}" font-size="11" fill="{DIM}">more</text>')

    span = f"{mdy(first)} to {mdy(d(days[-1]['date']))}"
    body = f'''
{frame(h)}
{sign(40, 44, "CONTRIBUTIONS", BUTTER)}
<text x="{W - 40}" y="44" font-size="13" fill="{MUTED}" text-anchor="end"><tspan font-weight="700" fill="{INK}">{st['total']:,}</tspan> in the last year</text>
{''.join(months)}
{day_labels}
{''.join(rects)}
{''.join(over)}
<text x="40" y="{h - 26}" font-family="{MONO}" font-size="11" fill="{DIM}">{esc(span)}</text>
{legend}'''
    # level: (peak scale, seconds, the colour it flashes on the way)
    swell = {1: (1.35, 0.55, "#b7a1d8"), 2: (1.7, 0.65, "#f3b3c4"), 3: (2.1, 0.8, "#ffdccd"), 4: (2.6, 0.95, "#fff6dc")}
    style = (".c,.ping{transform-box:fill-box;transform-origin:center}"
             ".l0{animation:in .4s ease-out both}@keyframes in{from{opacity:0;transform:scale(.3)}}"
             + "".join(
                 f".l{lv}{{animation:pop{lv} {sec}s cubic-bezier(.2,.8,.3,1) both}}"
                 f"@keyframes pop{lv}{{0%{{opacity:0;transform:scale(.2)}}"
                 f"40%{{opacity:1;transform:scale({peak});fill:{flash}}}100%{{transform:scale(1)}}}}"
                 for lv, (peak, sec, flash) in swell.items())
             + ".ping{animation:ping 1s ease-out both}.p4{animation-duration:1.3s}"
             "@keyframes ping{0%{opacity:0;transform:scale(1)}15%{opacity:.9}100%{opacity:0;transform:scale(3.4)}}"
             ".today{animation:mark .4s ease-out both,blink 2s ease-in-out 5s infinite}"
             "@keyframes mark{from{opacity:0}}@keyframes blink{50%{stroke-opacity:.2}}"
             "@media (prefers-reduced-motion: reduce){.ping{display:none}}")
    return svg(h, body, style)


def activity(act):
    pad, inner = 40, W - 80
    repos = act.get("repos", [])
    t = act.get("totals", {})
    days = act.get("window_days", 30)

    parts = []
    if t.get("commits"):
        parts.append(f"{t['commits']} commit{'s' if t['commits'] != 1 else ''}")
    if t.get("prs_merged"):
        parts.append(f"{t['prs_merged']} PR{'s' if t['prs_merged'] != 1 else ''} merged")
    if t.get("repos"):
        parts.append(f"{t['repos']} repo{'s' if t['repos'] != 1 else ''}")
    summary = " · ".join(parts) or "quiet stretch"

    y = 82
    rows = []
    if not repos:
        rows.append(f'<text x="{pad}" y="{y + 10}" font-size="15" fill="{MUTED}">Nothing public in the last '
                    f'{days} days.</text>')
        y += 56
    for n, r in enumerate(repos):
        g = [f'<g class="row" style="animation-delay:{0.1 + n * 0.15:.2f}s">']
        if n:
            g.append(f'<line x1="{pad}" x2="{W - pad}" y1="{y - 22}" y2="{y - 22}" stroke="{LINE}"/>')
        name = r["name"]
        g.append(f'<text x="{pad}" y="{y}" font-family="{MONO}" font-size="17" font-weight="700" fill="{INK}">{esc(name)}</text>')
        meta_x = pad + width(name, 17, mono=True) + 16
        if r.get("language"):
            g.append(f'<circle cx="{meta_x + 4:.0f}" cy="{y - 5}" r="4.5" fill="{LANG.get(r["language"], MUTED)}"/>'
                     f'<text x="{meta_x + 14:.0f}" y="{y}" font-size="12.5" fill="{MUTED}">{esc(r["language"])}</text>')
        bits = []
        if r.get("commits"):
            bits.append(f"{r['commits']} commit{'s' if r['commits'] != 1 else ''}")
        if r.get("prs_merged"):
            bits.append(f"{r['prs_merged']} merged")
        if r.get("prs_open"):
            bits.append(f"{r['prs_open']} in review")
        when = f"active {md(d(r['last_active']))}"
        g.append(f'<text x="{W - pad}" y="{y}" font-family="{MONO}" font-size="12" fill="{DIM}" text-anchor="end">'
                 f'{esc(" · ".join(bits + [when]))}</text>')
        y += 26
        for line in wrap(r.get("blurb") or "", 14, inner, 2):
            g.append(f'<text x="{pad}" y="{y}" font-size="14" fill="{MUTED}">{esc(line)}</text>')
            y += 21
        y += 6
        for hl in r.get("highlights", [])[:3]:
            kind = hl.get("kind", "commit")
            color = {"merged": LILAC, "open": MINT}.get(kind, DIM)
            tag = {"merged": "merged", "open": "in review"}.get(kind, "commit")
            tw_ = 78
            g.append(f'<rect x="{pad}" y="{y - 13}" width="{tw_}" height="18" rx="9" fill="none" stroke="{color}" stroke-opacity="0.6"/>'
                     f'<text x="{pad + tw_ / 2}" y="{y}" font-family="{MONO}" font-size="10.5" fill="{color}" text-anchor="middle">{tag}</text>'
                     f'<text x="{pad + tw_ + 12}" y="{y}" font-size="14" fill="{INK}">{esc(clip(hl["title"], 14, inner - tw_ - 12))}</text>')
            y += 26
        y += 30
        g.append("</g>")
        rows.append("".join(g))
    h = y - 16

    body = f'''
{frame(h)}
{sign(pad, 44, "RECENTLY", SKY)}
<text x="{W - pad}" y="44" font-family="{MONO}" font-size="12" fill="{MUTED}" text-anchor="end">last {days} days · {esc(summary)}</text>
{''.join(rows)}'''
    style = ".row{animation:up .5s ease-out both}@keyframes up{from{opacity:0;transform:translateY(10px)}}"
    return svg(h, body, style)


# ---------------------------------------------------------------- links

# An image in a README can carry one link. So the banner shows the three addresses as tags and links to the
# first, and all three are also real text links in the line right under it.
LINKS = [
    ("site", "https://allenkh.com", "allenkh.com", BUTTER),
    ("linkedin", "https://www.linkedin.com/in/allenkhsieh", "in/allenkhsieh", SKY),
    ("alai", "https://tryalai.app", "tryalai.app", MINT),
]


# ---------------------------------------------------------------- readme

def readme(act):
    with open(os.path.join(OUT, "README.template.md")) as f:
        tpl = f.read()
    links = " · ".join(f'<a href="{esc(r["url"])}">{esc(r["name"])}</a>' for r in act.get("repos", []))
    mine = " · ".join(f'<a href="{esc(url)}">{esc(text)}</a>' for _, url, text, _ in LINKS)
    return tpl.replace("{{RECENT_LINKS}}", links or "&nbsp;").replace("{{LINKS}}", mine)


def main():
    with open(os.path.join(DATA, "contributions.json")) as f:
        days = json.load(f)["days"]
    try:
        with open(os.path.join(DATA, "activity.json")) as f:
            act = json.load(f)
    except FileNotFoundError:
        act = {}

    st = stats(days)
    synced = datetime.datetime.now(TZ).date()
    write("hero.svg", hero(st, synced))
    write("streak.svg", streak(st))
    write("contributions.svg", graph(days, st))
    write("recent.svg", activity(act))
    with open(os.path.join(ROOT, "README.md"), "w") as f:
        f.write(readme(act))
    print(f"rendered: streak {st['current']}d (best {st['longest']}d), weekly {st['week_streak']}w, "
          f"{st['total']} contributions, {len(act.get('repos', []))} recent repos")


if __name__ == "__main__":
    main()
