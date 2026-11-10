# The banner

`profile/hero.svg` is a 3D voxel scene shown as a stack of flat pictures that CSS moves. GitHub shows a
README's pictures as images: no script runs in them, so the scene is rendered ahead of time, here.

- `scene.html` is the scene itself (three.js): the planet, the purple world that circles it, the rocket.
- `capture.js` opens it in headless Chromium, renders it in layers and writes them, with `banner.json`,
  to `profile/banner/`.
- `scripts/render.py` reads that folder and composes `profile/hero.svg` on every run of the workflow.
  The layers do not change between runs, so neither does the banner.

## Render it again

```
node scripts/banner/capture.js
python scripts/render.py
```

`capture.js` needs Playwright with its Chromium (`npm i playwright && npx playwright install chromium`),
and the network once: three.js comes from a CDN. It takes a few minutes on a machine without a GPU.

Do it after changing the scene, and when `render.py` prints this warning:

```
warning: the streak card now launches the rocket somewhere else than the banner catches it.
```

The streak card and the banner are two pictures that cannot talk to each other. They share only the
moment the page loaded, so the rocket's handoff is arithmetic: the card works out when, where, how fast
and at what lean the rocket leaves through its top edge (`LAUNCH` in `render.py`), and the banner was
rendered with the rocket coming up through its bottom edge at that same moment and place
(`launch` in `banner.json`). Change the card's fuse, its clock or its flight path, and the banner has
to be rendered again to match.

## What is in `profile/banner/`

| File | What |
| --- | --- |
| `sky.webp` | the sky alone |
| `planet.webp` | the planet with its clouds and belt |
| `moon.webp` | the purple world, once; the banner slides and scales it round its orbit |
| `o000.webp` ... | the rocket and its exhaust at 96 moments of one orbit |
| `a00.webp` ... | the rocket's arrival, from the bottom edge to its place in orbit |
| `banner.json` | where and when each of them goes |

With a streak of 0 there is no launch, and the banner has no rocket.
