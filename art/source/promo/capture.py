#!/usr/bin/env python3
"""Deterministic gameplay capture for the promo cuts (runs on the Spark, Playwright WebKit).

The game's requestAnimationFrame is replaced by a manual clock, so each recorded frame is exactly
1/FPS of game time regardless of how slow headless rendering is. Frames are page screenshots
(canvas + any visible HUD) at a portrait 540x960 viewport with devicePixelRatio 2 = 1080x1920.

Usage: capture.py SCENE OUTDIR [--game DIR] [--fps 30] [--frames N] [--still]
Scenes live in scenes.py (setup JS, warm-up seconds, per-frame camera JS, timed events).
"""
import argparse, os, subprocess, sys, time, json
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scenes import SCENES, COMMON_JS

ap = argparse.ArgumentParser()
ap.add_argument("scene"); ap.add_argument("out")
ap.add_argument("--game", default=os.path.expanduser("~/ma_promo/WebGame"))
ap.add_argument("--fps", type=int, default=30)
ap.add_argument("--frames", type=int, default=0)
ap.add_argument("--still", action="store_true", help="only write a few stills, no video")
ap.add_argument("--w", type=int, default=540); ap.add_argument("--h", type=int, default=960)
a = ap.parse_args()
S = SCENES[a.scene]
nframes = a.frames or int(S.get("dur", 6) * a.fps)
os.makedirs(a.out, exist_ok=True)
fdir = os.path.join(a.out, "frames_" + a.scene); os.makedirs(fdir, exist_ok=True)

from capture_init import INIT
HIDE_HUD = """#hud,#resbar,#panel,#sword,#joyZone,#mmWrap,#toasts,#selBtn,#ppause,#tut,#wallBar,.ui{display:none!important}"""

with sync_playwright() as p:
    b = p.webkit.launch()
    ctx = b.new_context(viewport={"width": a.w, "height": a.h}, device_scale_factor=2, is_mobile=False, has_touch=True)
    ctx.add_init_script(INIT)
    pg = ctx.new_page(); pg.set_default_timeout(120000)
    pg.on("crash", lambda *_: (print("PAGE CRASHED", flush=True), os._exit(3)))
    pg.on("console", lambda m: m.type == "error" and print("console:", m.text[:200]))
    pg.on("pageerror", lambda e: print("pageerror:", str(e)[:300]))
    pg.goto("file://" + os.path.join(a.game, "index.html"))
    pg.wait_for_timeout(1500)
    pg.evaluate("document.getElementById('introOv') && (document.getElementById('introOv').style.display='none')")
    pg.click("#startBtn", force=True)
    pg.evaluate("window.__step(2, 33.33)")
    if not S.get("hud"): pg.add_style_tag(content=HIDE_HUD)
    if S.get("css"): pg.add_style_tag(content=S["css"])
    pg.evaluate(COMMON_JS)
    pg.evaluate(S["setup"]); print("setup ok, units", pg.evaluate("units.length"), flush=True)
    # preload every clip the scene could play, then let images decode in real time
    pg.evaluate("__preloadAll()")
    for _ in range(120):
        left = pg.evaluate("__pending()")
        if left == 0: break
        pg.wait_for_timeout(500)
    print("pending images after preload:", left, flush=True)
    dtms = 1000.0 / a.fps
    warm = int(S.get("warm", 2) * a.fps)
    for i in range(0, warm, 5):
        tt = time.time(); pg.evaluate(f"window.__step(5, {dtms})")
        if i % 30 == 0: print(f"warm {i}/{warm} {time.time()-tt:.2f}s/5f", flush=True)
    print("warm ok", flush=True)
    if S.get("after_warm"): pg.evaluate(S["after_warm"])
    events = {int(round(t * a.fps)): js for t, js in S.get("events", [])}
    cam = S.get("cam", "")
    t0 = time.time()
    picks = set(range(0, nframes, max(1, nframes // 4))) if a.still else None
    for f in range(nframes):
        if f in events: pg.evaluate(events[f])
        if cam: pg.evaluate(f"(f=>{{ {cam} }})({f / a.fps})")
        pg.evaluate(f"window.__step(1, {dtms})")
        if picks is None or f in picks:
            pg.screenshot(path=os.path.join(fdir, f"{f:05d}.jpg"), type="jpeg", quality=94)
        if f % 60 == 0: print(f"frame {f}/{nframes} {time.time()-t0:.0f}s", flush=True)
    b.close()

if not a.still:
    mp4 = os.path.join(a.out, a.scene + ".mp4")
    subprocess.run(["nice", "ffmpeg", "-y", "-v", "error", "-framerate", str(a.fps), "-i", os.path.join(fdir, "%05d.jpg"),
                    "-c:v", "libx264", "-preset", "slow", "-crf", "14", "-pix_fmt", "yuv420p", mp4], check=True)
    print("wrote", mp4)
