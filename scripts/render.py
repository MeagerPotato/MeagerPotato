#!/usr/bin/env python3
"""
Draw the profile from data/contributions.json and data/activity.json.

Writes the SVG cards into profile/ and rebuilds README.md from
profile/README.template.md. Everything is plain SVG with CSS animation, because
GitHub shows README images as <img> and runs no JavaScript inside them.

The banner is put together here from the layers in profile/banner/, as four pictures that stand side by
side (profile/hero.svg and hero-*.svg), since each link in it needs a picture of its own. The layers are
what scripts/banner/capture.js renders from a 3D scene: see scripts/banner/README.md.

    python scripts/render.py
    python scripts/render.py --print-launch   # where and when the rocket leaves the streak card, as JSON
"""
import base64
import math
import re
import datetime
import html
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "profile")
BANNER = os.path.join(OUT, "banner")
FONTS = os.path.join(HERE, "fonts")


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

# One blocky face for everything: Jersey 25, the finest grid of its family, so small text stays easy to read.
# It travels inside every card: an <img> may not fetch a font, but it may carry one. Where a browser refuses
# even that, the system sans takes over.
SANS = "'Jersey 25',-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
MONO = SANS
with open(os.path.join(FONTS, "jersey25-latin.woff2"), "rb") as _f:
    FONT_FACE = ("@font-face{font-family:'Jersey 25';src:url(data:font/woff2;base64,"
                 + base64.b64encode(_f.read()).decode() + ") format('woff2')}")
with open(os.path.join(FONTS, "jersey25-widths.json")) as _f:
    ADVANCE = json.load(_f)  # advance widths per em
SMALL = 1.22  # Jersey is narrow and low: text under 16 px is set this much larger


def px(size):
    """The cards are laid out in the sizes of an ordinary sans; this is the size Jersey is set at to fill them."""
    return size * SMALL if size < 16 else size * 1.08


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
    return sum(px(size) * ADVANCE.get(c, 0.5) for c in text)


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


def svg(h, body, style="", w=W, top=0):
    """top: where the picture begins in the drawing, for a card that is cut into strips (h is the strip's height)."""
    body = re.sub(r'font-size="([0-9.]+)"', lambda m: f'font-size="{px(float(m.group(1))):.1f}"', body)
    body = body.replace('font-weight="700"', 'font-weight="400"').replace('font-weight="600"', 'font-weight="400"')
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 {top} {w} {h}" '
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
    return (f'<text x="{x}" y="{y}" font-family="{MONO}" font-size="11.5" font-weight="600" letter-spacing="1.5" '
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

def _layer(name):
    with open(os.path.join(BANNER, name), "rb") as f:
        return "data:image/webp;base64," + base64.b64encode(f.read()).decode()


SPLIT = 375  # where the banner is cut between the words and the scene: nothing that moves comes left of it


def hero(st):
    """The banner: a voxel planet, the purple world that circles it, and the rocket. It is a stack of pictures
    rendered once from the 3D scene (scripts/banner/), moved here by CSS alone:

      the sky / whatever is behind the planet / the planet / whatever is in front of it / the words

    The purple world is one picture that slides round its orbit. The rocket is a strip of pictures, one for each
    step of its orbit, shown in turn while the strip slides along the same path, so it turns as it goes round.
    Which of the two stacks a thing is in (behind the planet or in front of it) changes at the sides of its orbit,
    where it is clear of the planet.

    The page opens without the rocket. The streak card under this one launches it, and it comes up through the
    bottom edge here at the moment and place it left that card (LAUNCH), flies a short arc and takes its place in
    orbit. Two pictures cannot talk to each other on GitHub: they share nothing but the moment the page loaded.
    With no streak there is no launch, and no rocket here.

    An image in a README carries one link, and the banner shows three addresses. So it is cut into four pictures
    that stand side by side with nothing between them: a column for each tag (the words above the tag are in its
    column too), each linked to its own address, and the scene, which is everything that moves. Returns
    [(name, its share of the banner's width in thousandths of a percent, svg)], left to right: the README is built
    from the same list."""
    h = 260
    with open(os.path.join(BANNER, "banner.json")) as f:
        B = json.load(f)
    P, T = B["period"], B["launch"]
    live = st["current"] > 0
    if live and any(abs(LAUNCH[k] - T[k]) > 0.002 for k in ("enter", "x", "below", "lean", "v")):
        print("warning: the streak card now launches the rocket somewhere else than the banner catches it.\n"
              "         Render the banner again: node scripts/banner/capture.js", file=sys.stderr)

    def keys(rows, fmt):
        n = len(rows)
        return "".join(f"{k * 100 / n:.3f}%{{{fmt(rows[k % n])}}}" for k in range(n + 1))

    def flips(flags, on, off):
        """Keyframes that switch a stack on for the part of the loop where its flag holds."""
        n, out, last = len(flags), [], None
        for k, f in enumerate(flags):
            if f != last:
                out.append(f"{k * 100 / n:.3f}%{{visibility:{on if f else off}}}")
                last = f
        return "".join(out) + f"100%{{visibility:{on if flags[0] else off}}}"

    css = []
    back, front, late = [], [], ""

    # ---- the purple world
    m = B["moon"]
    mk = m["keys"]  # x, y, scale, in front?
    rest = B["rest"]  # the moment shown to someone who has asked for no motion
    mr = mk[round(rest * len(mk)) % len(mk)]
    moon = f'<g class="moon" transform="translate({mr[0]} {mr[1]}) scale({mr[2]})"><use href="#moon"/></g>'
    back.append(f'<g class="mb" visibility="{"hidden" if mr[3] else "visible"}">{moon}</g>')
    front.append(f'<g class="mf" visibility="{"visible" if mr[3] else "hidden"}">{moon}</g>')
    css.append(f".moon{{animation:moon {P}s linear infinite}}"
               f"@keyframes moon{{{keys(mk, lambda r: f'transform:translate({r[0]}px,{r[1]}px) scale({r[2]})')}}}"
               f".mf{{animation:mf {P}s steps(1) infinite}}@keyframes mf{{{flips([r[3] for r in mk], 'visible', 'hidden')}}}"
               f".mb{{animation:mb {P}s steps(1) infinite}}@keyframes mb{{{flips([not r[3] for r in mk], 'visible', 'hidden')}}}")

    # ---- the rocket
    if live:
        o = B["orbit"]
        n = len(o["frames"])
        step = P / n
        ri = round(rest * n) % n
        pr = o["path"][round(rest * len(o["path"])) % len(o["path"])]
        stacks = {True: [], False: []}
        for k, fr in enumerate(o["frames"]):
            stacks[fr["front"]].append(
                f'<image class="f{" rest" if k == ri else ""}" x="{fr["dx"]}" y="{fr["dy"]}" width="{fr["w"]}" height="{fr["h"]}" '
                f'href="{_layer(fr["file"])}" style="animation-delay:{(k - 0.5) * step - P:.3f}s"/>')
        for flag, stack in ((False, back), (True, front)):
            stack.append(f'<g class="late"><g class="orb" transform="translate({pr[0]} {pr[1]})">{"".join(stacks[flag])}</g></g>')
        a = B["arrive"]
        slot = 1 / a["fps"]
        late = '<g class="arr">' + "".join(
            f'<image class="a" x="{fr["x"]}" y="{fr["y"]}" width="{fr["w"]}" height="{fr["h"]}" href="{_layer(fr["file"])}" '
            f'style="animation-delay:{T["enter"] + k * slot:.3f}s"/>' for k, fr in enumerate(a["frames"])) + "</g>"
        css.append(
            f".orb{{animation:orb {P}s linear infinite}}@keyframes orb{{{keys(o['path'], lambda r: f'transform:translate({r[0]}px,{r[1]}px)')}}}"
            f".f{{opacity:0;animation:f {P}s steps(1) infinite}}@keyframes f{{0%{{opacity:1}}{100 / n:.4f}%,100%{{opacity:0}}}}"
            f".late{{visibility:hidden;animation:show 1ms linear {T['join']}s forwards}}@keyframes show{{to{{visibility:visible}}}}"
            f".arr{{visibility:hidden;animation:arr {len(a['frames']) * slot:.3f}s linear {T['enter']}s}}@keyframes arr{{from,to{{visibility:visible}}}}"
            f".a{{opacity:0;animation:on {slot:.4f}s steps(1)}}@keyframes on{{from,to{{opacity:1}}}}")

    # ---- the words: who, what, and the three addresses as tags. The cuts between the columns fall in the
    # middle of the gaps between the tags.
    tags, x, cuts, gap = [], 39.6, [0], 6.9
    for _, _, text, color, _ in LINKS:
        tw = 15.4 * sum(ADVANCE.get(c, 0.5) for c in text)
        bw = round(tw + 9.7 + 6.2 + 2 * 8.4 + 2, 1)
        tags.append(f'<rect x="{x:.1f}" y="184.6" width="{bw}" height="27" rx="7" fill="{DEEP}"/>'
                    f'<rect x="{x:.1f}" y="182" width="{bw}" height="27" rx="7" fill="{PANEL}" stroke="{LINE}" stroke-width="1.8"/>'
                    f'<rect x="{x + 9.3:.1f}" y="190.6" width="9.7" height="9.7" rx="2.2" fill="{color}"/>'
                    f'<text x="{x + 25.2:.1f}" y="200.6" font-size="15.4" fill="{INK}">{esc(text)}</text>')
        x += bw + gap
        cuts.append(round(x - gap / 2))
    cuts[-1] = SPLIT
    # Each column's width in the README is a share of the banner's, in thousandths of a percent, and a browser
    # works out each picture's height from its own width. So the cuts are moved (by less than a hundredth of a
    # pixel) to where those shares put them: then every picture has the banner's proportions exactly, and they
    # all come out the same height. The shares add up to 99.98%: see readme().
    share = [math.floor((cuts[k + 1] - cuts[k]) / W * 99980) for k in range(len(LINKS))]
    share.append(99980 - sum(share))
    cuts = [round(W * sum(share[:k]) / 99980, 4) for k in range(len(share))] + [W]
    words = (f'<text x="39.6" y="65" font-size="15.4" letter-spacing="3.1" fill="{CORAL}">// MEAGERPOTATO</text>'
             f'<text x="39.6" y="125" font-size="58" letter-spacing="0.6" fill="{DEEP}">Allen Hsieh</text>'
             f'<text x="39.6" y="122" font-size="58" letter-spacing="0.6" fill="{INK}">Allen Hsieh</text>'
             f'<text x="39.6" y="160" font-size="21" fill="{MUTED}">Aerospace Engineering @ UC Berkeley</text>'
             + "".join(tags))
    css.append("@media (prefers-reduced-motion: reduce){*{animation:none!important}.f{display:none}"
               ".f.rest{display:inline;opacity:1}.late{visibility:visible}}")

    p = B["planet"]
    left = min([p["x"]] + [r[0] - m["w"] / 2 * r[2] for r in mk]
               + ([q[0] + fr["dx"] for q, fr in zip(o["path"], o["frames"])] + [fr["x"] for fr in a["frames"]] if live else []))
    if x - gap + 1 > SPLIT or left < SPLIT:
        print(f"warning: the banner is cut at x = {SPLIT}, but the tags end at {x - gap:.0f} and the scene begins at {left:.0f}.",
              file=sys.stderr)

    def piece(x0, x1, style, defs, inside):
        w = round(x1 - x0, 4)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="{x0} 0 {w} {h}" font-family="{SANS}">\n'
            f'<style>{style}</style>\n'
            f'<defs><clipPath id="card"><rect x="1" y="1" width="{W - 2}" height="{h - 2}" rx="14"/></clipPath>{defs}</defs>\n'
            f'<rect x="1" y="1" width="{W - 2}" height="{h - 2}" rx="14" fill="{DEEP}"/>\n'
            '<g clip-path="url(#card)">\n'
            f'<image width="{W}" height="{h}" href="{_layer(B["sky"])}"/>\n'
            + inside
            + f'\n</g>\n<rect x="1" y="1" width="{W - 2}" height="{h - 2}" rx="14" fill="none" stroke="{LINE}" stroke-width="2"/>\n</svg>\n')

    scene = ("\n".join(back)
             + f'\n<image x="{p["x"]}" y="{p["y"]}" width="{p["w"]}" height="{p["h"]}" href="{_layer(p["file"])}"/>\n'
             + "\n".join(front) + "\n" + late)
    moon_def = f'<image id="moon" x="{-m["w"] / 2}" y="{-m["h"] / 2}" width="{m["w"]}" height="{m["h"]}" href="{_layer(m["file"])}"/>'
    out = [(key, share[k], piece(cuts[k], cuts[k + 1], FONT_FACE, "", words)) for k, (key, *_) in enumerate(LINKS)]
    out.append(("scene", share[-1], piece(cuts[-2], W, "".join(css), moon_def, scene)))
    return out


LAUNCH = {}  # what the banner above has to know to catch the rocket: filled in by streak()


def _flame(rows, cell, up=True):
    """A flame in blocks. rows: one list per colour (outer first), each a list of (width, shift) from the base to
    the tip, in cells. The base sits on y = 0."""
    cols = [CORAL, BUTTER, "#fff6dc"]
    out = []
    for n, layer in enumerate(rows):
        for k, (wd, sh) in enumerate(layer):
            y = -(k + 1) * cell if up else k * cell
            out.append(f'<rect x="{(sh - wd / 2) * cell / 4:.1f}" y="{y:.1f}" width="{wd * cell / 4:.1f}" height="{cell + 0.4:.1f}" fill="{cols[n]}"/>')
    return "".join(out)


FLAMES = [  # three drawings of one flame, shown in turn
    [[(12, 0), (16, 0), (14, 0), (10, 1), (6, 2), (3, 3)], [(8, 0), (10, 0), (8, 0), (4, 1), (2, 2)], [(4, 0), (5, 0), (3, 0)]],
    [[(12, 0), (16, -1), (14, -1), (10, -2), (6, -2), (3, -4)], [(8, 0), (10, -1), (8, -1), (4, -2)], [(4, 0), (5, 0), (2, -1)]],
    [[(12, 0), (14, 1), (14, 0), (9, -1), (6, 1), (4, 2), (2, 3)], [(8, 0), (9, 0), (8, 0), (5, 0), (2, 1)], [(4, 0), (4, 0), (3, 0), (2, 0)]],
]


def _rocket(u=1.8):
    """The banner's rocket seen from the side: the same parts in the same colours, a block of the model to
    u here. Centre at 0,0, nose up. Returns (art, the nozzle's y)."""
    mid = 13.5

    def Y(v):
        return (mid - v) * u

    def R(x0, v_top, x1, v_bot, fill, extra=""):
        return f'<rect x="{x0 * u:.2f}" y="{Y(v_top):.2f}" width="{(x1 - x0) * u:.2f}" height="{(v_top - v_bot) * u:.2f}" fill="{fill}"{extra}/>'

    def P(pts, fill):
        return '<polygon points="' + " ".join(f"{x * u:.2f},{Y(v):.2f}" for x, v in pts) + f'" fill="{fill}"/>'

    o = []
    for s in (-1, 1):  # the two fins seen flat on
        o.append(P([(s * 5, 9.5), (s * 12.5, 0.2), (s * 12.5, -4.5), (s * 10.6, -4.5), (s * 5, -0.5)], CORAL))
        o.append(P([(s * 11.2, 1.8), (s * 12.5, 0.2), (s * 12.5, -4.5), (s * 10.6, -4.5), (s * 10.2, -4.2), (s * 11.2, -3.6)], "#c3645c"))
    o.append(R(-4.2, -0.5, 4.2, -1.5, "#8e98ba") + R(-3.6, -1.5, 3.6, -2.5, "#6f7aa6"))
    o.append(P([(-3, -2.5), (3, -2.5), (4.7, -6.5), (-4.7, -6.5)], "#565f85"))
    o.append(R(-2.6, -5.3, 2.6, -6.5, BUTTER))
    o.append(R(-5.5, 18.5, 5.5, -0.5, "#f1f3fb"))
    for v in (3, 9, 15):
        o.append(R(-5.5, v + 0.5, 5.5, v - 0.5, "#d9deee"))
    o.append(R(-5.5, 1.5, 5.5, -0.5, "#8e98ba") + R(-5.5, 5.5, 5.5, 3.5, BUTTER) + R(-5.5, 18.5, 5.5, 16.5, "#c3645c"))
    for v in range(19, 31):
        f = (v - 18) / 12.6
        hw = math.floor(max(0.6, 5.3 * math.sqrt(1 - f ** 1.8))) + 0.5
        o.append(R(-hw, v + 0.5, hw, v - 0.5, "#fcecc6" if v >= 28 else CORAL))
    o.append(R(-0.5, 31.5, 0.5, 30.5, "#fcecc6") + R(-0.4, 33.5, 0.4, 31.5, "#b9c1dc"))
    o.append(R(2.5, 30.5, 5.5, -0.5, DEEP, ' opacity="0.13"'))  # the side away from the light
    o.append(R(-0.45, 8.5, 0.45, -4.5, "#e07f75"))             # the fin that faces us, edge on
    o.append(f'<circle cx="0" cy="{Y(11):.2f}" r="{3.3 * u:.2f}" fill="#6f7aa6"/><circle cx="0" cy="{Y(11):.2f}" r="{2.2 * u:.2f}" fill="{SKY}"/>'
             f'<rect x="{-1.5 * u:.2f}" y="{Y(12.4):.2f}" width="{1.2 * u:.2f}" height="{1.2 * u:.2f}" fill="#f1f3fb"/>')
    return "".join(o), Y(-6.5)


def _walk(points):
    """A polyline's running length."""
    acc = [0.0]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        acc.append(acc[-1] + math.hypot(x1 - x0, y1 - y0))
    return acc


def _cubic(p0, p1, p2, p3, n=120):
    out = []
    for k in range(1, n + 1):
        s = k / n
        m = 1 - s
        out.append((m ** 3 * p0[0] + 3 * m * m * s * p1[0] + 3 * m * s * s * p2[0] + s ** 3 * p3[0],
                    m ** 3 * p0[1] + 3 * m * m * s * p1[1] + 3 * m * s * s * p2[1] + s ** 3 * p3[1]))
    return out


def streak(st):
    """The streak as a fuse. It is coiled round the number and ends under a rocket: the flame burns round it while
    the number counts up to the streak, and when it gets there the rocket lifts off and leaves by the top of the
    card, for the banner above to catch (LAUNCH says where and when). With no streak the fuse stays unlit and the
    rocket stays on its pad."""
    h = 280
    cx, cy, r = 140, 146, 84
    a0, sweep = 45.0, 315.0  # the fuse starts lower right and coils clockwise, all the way round to the right
    live = st["current"] > 0
    record = live and st["current"] >= st["longest"]

    def pt(deg, rad=r):
        return cx + rad * math.cos(math.radians(deg)), cy + rad * math.sin(math.radians(deg))

    # ---- the rocket on its pad, and the way it flies
    rx, ry = 287, 202
    art, noz = _rocket()
    c1 = ((rx, ry - 22), (rx, ry - 70), (rx + 46, ry - 96), (rx + 78, ry - 134))  # it leans out over the tiles,
    c2 = (c1[3], (rx + 98, ry - 158), (rx + 110, ry - 192), (rx + 116, ry - 300))  # then straightens for the banner
    fly_d = (f"M {rx} {ry} L {rx} {ry - 22} C " + " ".join(f"{x} {y}" for x, y in c1[1:]) + " C " + " ".join(f"{x} {y}" for x, y in c2[1:]))
    line = [(rx, ry), (rx, ry - 22)] + _cubic(*c1) + _cubic(*c2)
    run = _walk(line)
    fly_len = run[-1]

    def along(dist):
        """Where the rocket is once it has flown this far, and which way it points (dx, dy)."""
        dist = max(0.0, min(fly_len - 1e-6, dist))
        k = next(i for i in range(1, len(run)) if run[i] >= dist)
        (x0, y0), (x1, y1) = line[k - 1], line[k]
        f = (dist - run[k - 1]) / (run[k] - run[k - 1])
        return x0 + (x1 - x0) * f, y0 + (y1 - y0) * f, x1 - x0, y1 - y0

    # ---- the fuse: the coil, then a tail down to the engine
    (sx, sy), (ex, ey) = pt(a0), pt(a0 + sweep)
    tail = ((ex, ey), (ex, ey + 44), (ex + 2, ry + noz - 3), (rx - 7, ry + noz - 3))
    fuse_d = (f"M {sx:.1f} {sy:.1f} A {r} {r} 0 1 1 {ex:.1f} {ey:.1f} C " + " ".join(f"{x:.1f} {y:.1f}" for x, y in tail[1:]))
    length = 2 * math.pi * r * sweep / 360 + _walk([tail[0]] + _cubic(*tail))[-1]
    seg = length / round(length / 10.6)  # cut into blocks

    # ---- the clock
    t0, burn = 0.45, 3.0           # the flame lights, and how long it takes to reach the engine
    end = t0 + burn
    lift = end + 0.5               # the engine runs for a moment first
    T, power = 2.0, 1.7            # the climb out of the card: distance goes as time to this power
    exit_y = 10                    # the banner takes over when the rocket's middle is this far under the top edge
    g = next(d for d in (k * fly_len / 4000 for k in range(4001)) if along(d)[1] <= exit_y) / fly_len
    hx, hy, hdx, hdy = along(g * fly_len)
    tg = g ** (1 / power)
    LAUNCH.clear()
    LAUNCH.update({
        "active": live,
        "enter": round(lift + T * tg, 3),                       # seconds after the card starts
        "x": round(hx / W, 4),                                  # where along the banner's width
        "below": round((exit_y + 15) / 260, 4),                 # how far under the banner's edge, in its heights (15: the gap)
        "lean": round(math.atan2(hdx, -hdy), 4),                # heading, clockwise from straight up
        "v": round(fly_len * power * tg ** (power - 1) / T / W, 4),  # speed, in banner widths a second
    })

    if live:
        hint = f"since {md(d(st['current_start']))}"
    elif st["last_active"]:
        hint = f"last active {md(d(st['last_active']))}"
    else:
        hint = "no activity yet"

    rnd = random.Random(st["current"] * 31 + 5)

    # ---- the flame that runs along the fuse: three drawings in turn, a glow, embers, and it grows as it goes
    spark = ""
    if live:
        embers = []
        for n in range(11):
            ang, far = rnd.uniform(-2.6, -0.5), rnd.uniform(16, 38)
            size = rnd.choice([2.5, 3, 3, 4])
            embers.append(
                f'<rect class="ember" x="{-size / 2 + rnd.uniform(-4, 4):.1f}" y="{-10 - size / 2:.1f}" width="{size}" height="{size}" '
                f'fill="{rnd.choice([BUTTER, BUTTER, CORAL, "#fff6dc"])}" style="--dx:{far * math.cos(ang):.1f}px;'
                f'--dy:{far * math.sin(ang):.1f}px;animation-duration:{rnd.uniform(0.5, 1.0):.2f}s;'
                f'animation-delay:-{rnd.uniform(0, 1):.2f}s"/>')
        frames = "".join(f'<g class="fr" style="animation-delay:{-0.36 + 0.12 * n if n else 0:.2f}s">{_flame(f, 4)}</g>' for n, f in enumerate(FLAMES))
        spark = ('<g class="spark"><g class="life"><g class="grow">'
                 '<circle class="glow" cx="0" cy="-8" r="24" fill="url(#heat)"/>'
                 + "".join(embers) + f'<g transform="translate(0 4)">{frames}</g>'
                 "</g></g></g>")

    # ---- the rocket, its engine's flame, the smoke it leaves on the pad and behind it
    pad = (block(rx - 23, ry + noz + 1, 46, 7, rx=3)
           + f'<rect x="{rx - 15}" y="{ry + noz + 3.5:.1f}" width="30" height="2" rx="1" fill="{BUTTER}" opacity="0.8"/>')
    jet = "".join(f'<g class="fr" style="animation-delay:{-0.3 + 0.1 * n if n else 0:.2f}s;animation-duration:.3s">{_flame(f, 4.4, up=False)}</g>'
                  for n, f in enumerate(FLAMES))
    rocket = (f'<g class="rk"><g class="rkb"><g class="jet" style="transform-origin:0 {noz:.1f}px"><g class="thrust" style="transform-origin:0 {noz:.1f}px">'
              f'<g transform="translate(0 {noz - 1:.1f}) scale(0.78 1)">{jet}</g></g></g>{art}</g></g>')
    smoke = ""
    if live:
        bits = []
        for n in range(14):  # billows along the ground, both ways
            side = -1 if n % 2 else 1
            size = rnd.choice([6, 7, 8, 10])
            bits.append(
                f'<rect class="fx smoke" x="{rx - size / 2:.1f}" y="{ry + noz - size / 2 - 1:.1f}" width="{size}" height="{size}" rx="1" '
                f'fill="{rnd.choice(["#f1f3fb", "#b9c1dc", "#fcecc6", "#8e98ba"])}" style="--dx:{side * rnd.uniform(14, 52):.1f}px;'
                f'--dy:{-rnd.uniform(0, 16):.1f}px;animation-delay:{end + rnd.uniform(0, 0.9):.2f}s"/>')
        for n in range(1, 15):  # and a trail where the rocket has been
            f = n / 15 * (g + 0.06)
            x, y, dx, dy = along(f * fly_len - noz - 6)
            size = rnd.choice([5, 6, 7, 8])
            bits.append(
                f'<rect class="fx puff" x="{x - size / 2 + rnd.uniform(-3, 3):.1f}" y="{y - size / 2:.1f}" width="{size}" height="{size}" rx="1" '
                f'fill="{rnd.choice(["#f1f3fb", "#fcecc6", "#b9c1dc", BUTTER])}" style="--dx:{rnd.uniform(-7, 7):.1f}px;'
                f'--dy:{rnd.uniform(4, 14):.1f}px;animation-delay:{lift + T * f ** (1 / power) + 0.05:.2f}s"/>')
        smoke = "".join(bits)

    badge = ""
    if record:  # where the rocket stood, once it has gone
        bx, by = rx, ry + noz - 20
        badge = ('<g class="badge">'
                 f'<rect x="{bx - 25}" y="{by - 10:.1f}" width="50" height="24" rx="6" fill="{DEEP}"/>'
                 f'<rect x="{bx - 25}" y="{by - 13:.1f}" width="50" height="24" rx="6" fill="{BUTTER}"/>'
                 f'<text x="{bx}" y="{by + 4.5:.1f}" font-size="14" letter-spacing="1" fill="{BG}" text-anchor="middle">BEST</text>'
                 "</g>")

    # ---- the number: it counts up while the fuse burns
    def num(text, cls, style=""):
        return (f'<text class="{cls}" x="{cx}" y="{cy + 14}" font-size="58" font-weight="700" fill="{INK}" text-anchor="middle"'
                f'{style}>{text}</text>')

    if live:
        steps = min(st["current"], 30)
        vals = sorted({round(st["current"] * k / steps) for k in range(steps)})  # every value shown on the way, the last left out
        vals = [v for v in vals if v < st["current"]]
        slot = burn / len(vals)
        count = "".join(
            num(v, "cnt", f' opacity="0" style="animation:on {slot + (t0 if k == 0 else 0):.3f}s steps(1) {0 if k == 0 else t0 + k * slot:.3f}s"')
            for k, v in enumerate(vals))
        number = f'<g class="numg">{count}{num(st["current"], "fin")}</g>'
    else:
        number = num(0, "still")

    ls, le = st["longest_span"]
    tiles = [
        ("LONGEST STREAK", f"{st['longest']}", "days", f"{md(d(ls))} to {md(d(le))}" if ls else "none yet"),
        ("WEEKLY STREAK", f"{st['week_streak']}", "week" if st["week_streak"] == 1 else "weeks", "weeks in a row with activity"),
        ("CONTRIBUTIONS", f"{st['total']:,}", "", f"{st['active_days']} active days, last 12 months"),
        ("BEST DAY", f"{st['best_day']['count']:,}", "contribution" if st["best_day"]["count"] == 1 else "contributions", mdy(d(st["best_day"]["date"]))),
    ]
    tx, ty, tw_, th, gap = 348, 28, 242, 106, 14  # the tiles stand clear of the pad: a lane on each side of the rocket
    tiles_svg = []
    for n, (name, big, small, sub) in enumerate(tiles):
        x = tx + (n % 2) * (tw_ + gap)
        y = ty + (n // 2) * (th + gap)
        bw = width(big, 34, bold=True)
        tiles_svg.append(
            f'<g class="tile" style="animation-delay:{0.15 + n * 0.12:.2f}s">'
            + block(x, y, tw_, th)
            + label(x + 18, y + 28, name, DIM)
            + f'<text x="{x + 17}" y="{y + 68}" font-size="34" font-weight="700" fill="{INK}">{esc(big)}</text>'
            f'<text x="{x + 24 + bw:.0f}" y="{y + 68}" font-size="15" fill="{MUTED}">{esc(small)}</text>'
            f'<text x="{x + 18}" y="{y + 90}" font-size="12.5" fill="{DIM}">{esc(clip(sub, 12.5, tw_ - 34))}</text>'
            "</g>")

    body = (
        f'<defs><linearGradient id="plume" gradientUnits="userSpaceOnUse" x1="{cx - r}" y1="{cy + r}" x2="{cx + r}" y2="{cy - r}">'
        f'<stop offset="0" stop-color="{CORAL}"/><stop offset="1" stop-color="{BUTTER}"/></linearGradient>'
        f'<radialGradient id="heat"><stop offset="0" stop-color="{BUTTER}" stop-opacity="0.6"/>'
        f'<stop offset="1" stop-color="{CORAL}" stop-opacity="0"/></radialGradient></defs>'
        + frame(h)
        + sign(40, 44, "STREAK", CORAL)
        + f'<path d="{fuse_d}" fill="none" stroke="{LINE}" stroke-width="10"/>'
        f'<path d="{fuse_d}" fill="none" stroke="{DIM}" stroke-width="3" stroke-dasharray="{seg * 0.42:.2f} {seg * 0.58:.2f}" opacity="0.55"/>'
        + (f'<path class="lit" d="{fuse_d}" fill="none" stroke="url(#plume)" stroke-width="10" stroke-dasharray="{length:.1f} {length + 10:.1f}"/>' if live else "")
        + f'<path d="{fuse_d}" fill="none" stroke="{BG}" stroke-width="12" stroke-dasharray="1.6 {seg - 1.6:.3f}"/>'
        + pad + number
        + f'<text x="{cx}" y="{cy + 38}" font-family="{MONO}" font-size="12" fill="{MUTED}" text-anchor="middle">day streak</text>'
        f'<text x="{cx}" y="{h - 20}" font-family="{MONO}" font-size="12" fill="{DIM}" text-anchor="middle">{esc(hint)}</text>'
        + "".join(tiles_svg) + badge + smoke + spark + rocket)

    style = ".tile{animation:up .5s ease-out both}@keyframes up{from{opacity:0;transform:translateY(10px)}}"
    if live:
        keys = "".join(f"{k * 5}%{{offset-distance:{(k / 20) ** power * 100:.3f}%}}" for k in range(21))
        style += (
            f".lit{{animation:draw {burn}s linear {t0}s both}}@keyframes draw{{from{{stroke-dasharray:0 {length + 10:.1f}}}}}"
            f'.spark{{offset-path:path("{fuse_d}");offset-rotate:0deg;animation:run {burn}s linear {t0}s both}}'
            "@keyframes run{from{offset-distance:0%}to{offset-distance:100%}}"
            f".life{{animation:ign .3s cubic-bezier(.2,1.6,.4,1) {t0}s both,out .2s ease-in {end}s forwards}}"
            "@keyframes ign{from{transform:scale(0)}}@keyframes out{to{transform:scale(.2);opacity:0}}"
            f".grow{{animation:grow {burn}s linear {t0}s both}}@keyframes grow{{from{{transform:scale(.8)}}to{{transform:scale(1.6)}}}}"
            ".fr{animation:fr .36s steps(1) infinite}@keyframes fr{0%{opacity:1}33.34%,100%{opacity:0}}"
            ".glow,.ember,.smoke,.puff,.badge{transform-box:fill-box;transform-origin:center}"
            ".glow{animation:gl .5s steps(3) infinite}@keyframes gl{50%{opacity:.55;transform:scale(1.3)}}"
            ".ember{animation:em .8s ease-out infinite}"
            "@keyframes em{0%{opacity:1;transform:translate(0,0)}100%{opacity:0;transform:translate(var(--dx),var(--dy)) scale(.4)}}"
            f".numg{{transform-origin:{cx}px {cy}px;animation:swell {burn}s linear {t0}s both}}@keyframes swell{{from{{transform:scale(.7)}}}}"
            "@keyframes on{from,to{opacity:1}}"
            f".fin{{transform-origin:{cx}px {cy}px;animation:pop .5s cubic-bezier(.2,1.7,.4,1) {end}s both}}"
            "@keyframes pop{0%{opacity:0;transform:scale(.8)}1%{opacity:1}100%{opacity:1;transform:scale(1)}}"
            f'.rk{{offset-path:path("{fly_d}");offset-rotate:auto 90deg;animation:fly {T}s linear {lift}s both}}'
            f"@keyframes fly{{{keys}}}"
            f".rkb{{animation:rumble .09s steps(2) {end}s {round((lift - end) / 0.09) + 3}}}@keyframes rumble{{50%{{transform:translate(.9px,-.5px)}}}}"
            f".jet{{animation:fire .35s ease-out {end}s both}}@keyframes fire{{from{{transform:scale(0)}}}}"
            f".thrust{{animation:thrust {T}s ease-in {lift}s both}}@keyframes thrust{{from{{transform:scale(.85,.3)}}to{{transform:scale(1.15,1.7)}}}}"
            ".smoke{animation:smoke 1.7s ease-out both}"
            "@keyframes smoke{0%{opacity:0;transform:translate(0,0) scale(.4)}14%{opacity:.85}"
            "100%{opacity:0;transform:translate(var(--dx),var(--dy)) scale(2.3)}}"
            ".puff{animation:puff 1.1s ease-out both}"
            "@keyframes puff{0%{opacity:0;transform:scale(.5)}12%{opacity:.8}100%{opacity:0;transform:translate(var(--dx),var(--dy)) scale(2.5)}}"
            f".badge{{animation:land .5s cubic-bezier(.2,1.6,.4,1) {lift + 1.15:.2f}s both}}@keyframes land{{from{{opacity:0;transform:scale(.5)}}}}"
            # a browser without motion paths gets the finished card: the number, the lit fuse, and the pad empty
            '@supports not (offset-path:path("M0 0L1 1")){.spark,.rk,.fx{display:none}}'
            "@media (prefers-reduced-motion: reduce){.spark,.rk,.fx,.cnt{display:none}}")
    else:
        style += f'.rk{{transform:translate({rx}px,{ry}px)}}.jet{{display:none}}'
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
    """The Recently card, cut into strips: [(address, alt text, svg)], top to bottom. An image in a README carries
    one link, so each repo is a strip of its own inside a link to that repo, and the README stacks the strips with
    nothing between them (see readme()). The first strip also holds the card's heading. Each cut is in the empty
    space above the line that divides two repos."""
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
    cuts = [0]
    for n, r in enumerate(repos):
        g = [f'<g class="row" style="animation-delay:{0.1 + n * 0.15:.2f}s">']
        if n:
            cuts.append(y - 30)
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
    cuts.append(h)

    head = (f'{sign(pad, 44, "RECENTLY", SKY)}\n<text x="{W - pad}" y="44" font-family="{MONO}" font-size="12" fill="{MUTED}" '
            f'text-anchor="end">last {days} days · {esc(summary)}</text>\n')
    style = ".row{animation:up .5s ease-out both}@keyframes up{from{opacity:0;transform:translateY(10px)}}"
    profile = f"https://github.com/{act.get('username') or 'MeagerPotato'}?tab=repositories"
    out = []
    for n, row in enumerate(rows):
        body = f"\n{frame(h)}\n{head if n == 0 else ''}{row}"
        url, alt = (repos[n]["url"], f"{repos[n]['name']}: recent work") if repos else (profile, "Nothing public recently")
        out.append((url, alt if n else f"Recently. {alt}", svg(cuts[n + 1] - cuts[n], body, style, top=cuts[n])))
    return out


def recent_file(n):
    return "recent.svg" if n == 0 else f"recent-{n + 1}.svg"


# ---------------------------------------------------------------- links

# An image in a README can carry one link. So the banner is cut into a column for each of these, and each
# column links to its own address: (key, address, the tag's text, the tag's colour, the column's alt text)
LINKS = [
    ("site", "https://allenkh.com", "allenkh.com", BUTTER, "Allen Hsieh, Aerospace Engineering at UC Berkeley. Website: allenkh.com"),
    ("linkedin", "https://www.linkedin.com/in/allenkhsieh", "in/allenkhsieh", SKY, "LinkedIn: in/allenkhsieh"),
    ("alai", "https://tryalai.app", "tryalai.app", MINT, "alai: tryalai.app"),
]


def banner_file(key):
    return "hero.svg" if key == "scene" else f"hero-{key}.svg"


# ---------------------------------------------------------------- readme

def readme(pieces, strips):
    """strips: the Recently card's pictures from activity(), top to bottom.
    pieces: the banner's pictures from hero(), left to right. They go on one line with nothing between them,
    not even a space, so that they stand edge to edge; their widths are shares of the banner's. The shares add
    up to a hair under 100% (a sixth of a pixel on a desktop), so that a browser that rounds each one up still
    has room for the last on the same line."""
    with open(os.path.join(OUT, "README.template.md")) as f:
        tpl = f.read()
    info = {key: (url, alt) for key, url, _, _, alt in LINKS}
    info["scene"] = (LINKS[0][1], "A voxel planet with a purple world and a rocket in orbit")
    banner = "".join(
        f'<a href="{esc(info[key][0])}"><img src="./profile/{banner_file(key)}" '
        f'width="{share // 1000}.{share % 1000:03d}%" alt="{esc(info[key][1])}" /></a>'
        for key, share, _ in pieces)
    # The Recently card's strips stack: each is the full width, so each takes a line. align="top" hangs a picture
    # from the top of its line, where the default stands it on the text's baseline and leaves room under it for
    # the tails of letters: a gap between every two strips.
    recent = "".join(
        f'<a href="{esc(url)}"><img src="./profile/{recent_file(n)}" width="100%" align="top" alt="{esc(alt)}" /></a>'
        for n, (url, alt, _) in enumerate(strips))
    return tpl.replace("{{BANNER}}", banner).replace("{{RECENT}}", recent)


def main():
    with open(os.path.join(DATA, "contributions.json")) as f:
        days = json.load(f)["days"]
    try:
        with open(os.path.join(DATA, "activity.json")) as f:
            act = json.load(f)
    except FileNotFoundError:
        act = {}

    st = stats(days)
    card = streak(st)  # first: it says where the rocket leaves, which the banner has to match
    if "--print-launch" in sys.argv:
        print(json.dumps({k: v for k, v in LAUNCH.items() if k != "active"}))
        return
    write("streak.svg", card)
    pieces = hero(st)
    for key, _, art in pieces:
        write(banner_file(key), art)
    write("contributions.svg", graph(days, st))
    strips = activity(act)
    for n, (_, _, art) in enumerate(strips):
        write(recent_file(n), art)
    for n in range(len(strips), 12):  # strips of repos that are no longer on the card
        stale = os.path.join(OUT, recent_file(n))
        if os.path.exists(stale):
            os.remove(stale)
    with open(os.path.join(ROOT, "README.md"), "w") as f:
        f.write(readme(pieces, strips))
    print(f"rendered: streak {st['current']}d (best {st['longest']}d), weekly {st['week_streak']}w, "
          f"{st['total']} contributions, {len(act.get('repos', []))} recent repos")


if __name__ == "__main__":
    main()
