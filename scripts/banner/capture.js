// Renders the banner's 3D scene (scene.html) into the layers that scripts/render.py composes into
// profile/hero.svg, and writes them with banner.json to profile/banner/.
//
//   node scripts/banner/capture.js
//
// Needs Playwright with its Chromium, and the network once (three.js comes from a CDN). Run it after changing
// the scene, or when render.py warns that the streak card launches the rocket somewhere else: the place and the
// moment the rocket comes up through the banner's bottom edge are read from the card (render.py --print-launch).
//
// What it writes:
//   sky.webp      the sky alone, opaque
//   planet.webp   the planet with its clouds and its belt
//   moon.webp     the purple world, once: the banner slides and scales this one picture round its orbit
//   o000.webp ..  the rocket with its exhaust at N moments of one orbit, each cropped to what is drawn
//   a00.webp ..   the rocket's arrival from the bottom edge to its place in orbit
//   banner.json   where and when each of them goes
const { chromium } = require("playwright");
const { execFileSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "../..");
const OUT = path.join(ROOT, "profile", "banner");
const W = 880, H = 260;
const MEET = 2.6;   // where on its orbit the rocket arrives, in radians
const JOIN = 1.3;   // seconds from the bottom edge to the orbit
const N = 96;       // pictures of the rocket in one orbit
const ARRIVE = 30;  // pictures of the arrival
const MOON = 72;    // places of the purple world in one orbit
const REST = 0.56;  // the moment of the loop shown to someone who has asked for no motion

(async () => {
  const launch = JSON.parse(execFileSync("python3", [path.join(ROOT, "scripts", "render.py"), "--print-launch"], { encoding: "utf8" }));
  launch.join = Math.round((launch.enter + JOIN) * 1000) / 1000;

  const browser = await chromium.launch({ args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
  const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 2 });
  page.on("pageerror", (e) => { console.error(e.message); process.exitCode = 1; });
  // the exhaust is scattered by Math.random: seed it, so that two runs draw the same pictures
  await page.addInitScript(() => { let s = 20261110; Math.random = () => { s |= 0; s = s + 0x6D2B79F5 | 0; let t = Math.imul(s ^ s >>> 15, 1 | s); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; });
  await page.goto("file://" + path.join(__dirname, "scene.html"));
  await page.waitForFunction(() => window.banner && window.banner.scene, null, { timeout: 120000 });

  await page.evaluate(({ launch, MEET }) => {
    const w = window.banner, THREE = window.THREE_;
    const draw = w.ren.render.bind(w.ren);
    w.ren.render = () => {};  // frame() then only moves things: drawing is asked for by name, below
    w.opts.orbitPhase = MEET + launch.join * window.ORBIT_W;  // so that the rocket is at MEET when it arrives
    const background = w.scene.background;
    const parts = { planet: [w.planet, w.belt], moon: [w.moonPivot], rocket: [w.rocketHolder] };
    const flat = document.createElement("canvas"), ctx = flat.getContext("2d", { willReadFrequently: true });
    const px = (v) => { const p = v.clone().project(w.cam); return [(p.x + 1) / 2 * 880, (1 - p.y) / 2 * 260]; };
    const depth = (v) => -v.clone().applyMatrix4(w.cam.matrixWorldInverse).z;
    const r1 = (x) => Math.round(x * 10) / 10;
    window.cap = {
      // move the scene to time t without the exhaust (for the layers that have none)
      at(t) { w.paused = true; w.t = t; w.frame(0); },
      // run the scene from where it is by n steps of dt seconds, exhaust and all
      run(n, dt) { w.paused = false; w.clock = null; for (let i = 0; i < n; i++) w.frame(dt); },
      clearExhaust() { w.puffs.forEach((p) => { p.life = 0; p.m.visible = false; }); },
      launch(on) { w.launch = on ? launch : null; },
      // draw only the named parts ("sky" is the background and the stars) and hand the picture back
      shot(names, quality) {
        const sky = names.includes("sky");
        w.scene.background = sky ? background : null;
        if (w.skyMesh) w.skyMesh.visible = sky;
        const seen = w.puffs.map((p) => p.m.visible);
        Object.keys(parts).forEach((k) => parts[k].forEach((o) => { o.visible = o.visible && names.includes(k); }));
        if (!names.includes("rocket")) w.puffs.forEach((p) => { p.m.visible = false; });
        draw(w.scene, w.cam);
        Object.keys(parts).forEach((k) => parts[k].forEach((o) => { o.visible = true; }));
        w.puffs.forEach((p, i) => { p.m.visible = seen[i]; });
        const c = w.canvas;
        flat.width = c.width; flat.height = c.height;
        ctx.clearRect(0, 0, c.width, c.height); ctx.drawImage(c, 0, 0);
        let x0 = 0, y0 = 0, x1 = c.width, y1 = c.height;
        if (!sky) {  // crop to what was drawn, on whole CSS pixels
          const d = ctx.getImageData(0, 0, c.width, c.height).data;
          x0 = c.width; y0 = c.height; x1 = 0; y1 = 0;
          for (let y = 0; y < c.height; y++) for (let x = 0; x < c.width; x++) if (d[(y * c.width + x) * 4 + 3] > 2) { if (x < x0) x0 = x; if (x >= x1) x1 = x + 1; if (y < y0) y0 = y; if (y >= y1) y1 = y + 1; }
          if (x1 <= x0) return null;
          x0 = Math.max(0, (x0 - 2) & ~1); y0 = Math.max(0, (y0 - 2) & ~1); x1 = Math.min(c.width, (x1 + 3) & ~1); y1 = Math.min(c.height, (y1 + 3) & ~1);
        }
        const cut = document.createElement("canvas"); cut.width = x1 - x0; cut.height = y1 - y0;
        cut.getContext("2d").drawImage(flat, x0, y0, cut.width, cut.height, 0, 0, cut.width, cut.height);
        return { x: x0 / 2, y: y0 / 2, w: cut.width / 2, h: cut.height / 2, data: cut.toDataURL("image/webp", quality).split(",")[1] };
      },
      rocket() { const p = w.rocketHolder.position; return { at: px(p).map(r1), front: depth(p) < depth(new THREE.Vector3()) }; },
      moon() { const p = w.moon.getWorldPosition(new THREE.Vector3()); return { at: px(p), depth: depth(p), front: depth(p) < depth(new THREE.Vector3()) }; },
    };
  }, { launch, MEET });

  fs.mkdirSync(OUT, { recursive: true });
  for (const f of fs.readdirSync(OUT)) if (/\.(webp|json)$/.test(f)) fs.unlinkSync(path.join(OUT, f));
  const save = (name, shot) => { fs.writeFileSync(path.join(OUT, name), Buffer.from(shot.data, "base64")); return name; };
  const P = Math.round(2 * Math.PI / (await page.evaluate(() => window.ORBIT_W)) * 1000) / 1000;
  const out = { period: P, launch, rest: REST };

  // ---- the sky, and the planet as it stands when the page opens
  await page.evaluate(() => window.cap.at(0));
  out.sky = save("sky.webp", await page.evaluate(() => window.cap.shot(["sky"], 0.86)));
  const planet = await page.evaluate(() => window.cap.shot(["planet"], 0.9));
  out.planet = { x: planet.x, y: planet.y, w: planet.w, h: planet.h, file: save("planet.webp", planet) };
  console.log("sky, planet");

  // ---- the purple world: its places, then one picture of it where it is nearest
  const keys = [];
  for (let k = 0; k < MOON; k++) keys.push(await page.evaluate((t) => { window.cap.at(t); return window.cap.moon(); }, k * P / MOON));
  const near = keys.reduce((a, b, i) => (b.depth < keys[a].depth ? i : a), 0);
  const moon = await page.evaluate((t) => { window.cap.at(t); return window.cap.shot(["moon"], 0.9); }, near * P / MOON);
  out.moon = {
    file: save("moon.webp", moon), w: moon.w, h: moon.h,
    keys: keys.map((m) => [Math.round(m.at[0] * 10) / 10, Math.round(m.at[1] * 10) / 10, Math.round(keys[near].depth / m.depth * 1000) / 1000, m.front]),
  };
  // the picture is placed by its middle, so move each key from the world's middle to the picture's
  const off = [moon.x + moon.w / 2 - keys[near].at[0], moon.y + moon.h / 2 - keys[near].at[1]];
  out.moon.keys.forEach((r) => { r[0] = Math.round((r[0] + off[0] * r[2]) * 10) / 10; r[1] = Math.round((r[1] + off[1] * r[2]) * 10) / 10; });
  console.log("moon");

  // ---- the rocket round its orbit. The scene runs for a moment first, so that the first picture has its exhaust.
  const step = P / N, sub = 9, lead = 12;
  await page.evaluate(({ t }) => { window.cap.launch(false); window.cap.clearExhaust(); window.cap.at(t); }, { t: -lead * step });
  out.orbit = { path: [], frames: [] };
  for (let k = -lead; k < N; k++) {
    if (k > -lead) await page.evaluate(({ n, dt }) => window.cap.run(n, dt), { n: sub, dt: step / sub });
    if (k < 0) continue;
    const r = await page.evaluate(() => ({ shot: window.cap.shot(["rocket"], 0.82), ...window.cap.rocket() }));
    out.orbit.path.push(r.at);
    out.orbit.frames.push({ file: save("o" + String(k).padStart(3, "0") + ".webp", r.shot), dx: Math.round((r.shot.x - r.at[0]) * 10) / 10, dy: Math.round((r.shot.y - r.at[1]) * 10) / 10, w: r.shot.w, h: r.shot.h, front: r.front });
    if (k % 12 === 0) console.log("orbit", k, "/", N);
  }

  // ---- the arrival: each picture is taken in the middle of the time it is shown for
  const slot = JOIN / ARRIVE;
  await page.evaluate(({ t }) => { window.cap.launch(true); window.cap.clearExhaust(); window.cap.at(t); }, { t: launch.enter });
  out.arrive = { fps: Math.round(ARRIVE / JOIN * 10000) / 10000, frames: [] };
  for (let k = 0; k < ARRIVE; k++) {
    await page.evaluate(({ dt }) => window.cap.run(2, dt), { dt: slot / 4 });
    const shot = await page.evaluate(() => window.cap.shot(["rocket"], 0.82));
    await page.evaluate(({ dt }) => window.cap.run(2, dt), { dt: slot / 4 });
    out.arrive.frames.push({ file: save("a" + String(k).padStart(2, "0") + ".webp", shot), x: shot.x, y: shot.y, w: shot.w, h: shot.h });
  }
  console.log("arrival");

  fs.writeFileSync(path.join(OUT, "banner.json"), JSON.stringify(out) + "\n");
  const bytes = fs.readdirSync(OUT).reduce((a, f) => a + fs.statSync(path.join(OUT, f)).size, 0);
  console.log(`wrote ${fs.readdirSync(OUT).length} files, ${(bytes / 1024).toFixed(0)} KiB, to ${path.relative(ROOT, OUT)}`);
  await browser.close();
})();
