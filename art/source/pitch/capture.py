#!/usr/bin/env python3
"""Deterministic landscape gameplay capture for the Poki pitch kit (runs on the Spark, Playwright WebKit).

Adapted from art/source/promo/capture.py. The game's requestAnimationFrame is replaced by a manual
clock (capture_init.py), so each recorded frame is exactly 1/FPS of game time however slowly
headless WebKit renders. Default viewport 960x540 CSS px at devicePixelRatio 2 = 1920x1080 frames,
so the HUD lays out as it would on a laptop/tablet. --phone switches to an 852x393 touch viewport
(a landscape phone) at DPR 2 = 1704x786, which make_phone.py later sets into a device bezel.

Per frame, after stepping the world:
  * CSS animations (the gold glow on an armed build button, the Select button pulse) are pinned to
    the game clock, so they pulse smoothly instead of jumping by however much wall time passed;
    CSS transitions are finished at once.
  * floating damage numbers (texts with plain:true) are dropped; "+10 wood" pickups stay, minus
    the doubled "+" the game currently draws on them.

Usage: capture.py SCENE OUTDIR [--url URL] [--fps 30] [--frames N] [--still] [--at 1.5,3.0 --png]
Scenes live in scenes.py.
"""
import argparse, os, subprocess, sys, time
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scenes import SCENES, COMMON_JS
from capture_init import INIT

ap = argparse.ArgumentParser()
ap.add_argument("scene"); ap.add_argument("out")
ap.add_argument("--url", default="http://127.0.0.1:8771/index.html", help="the committed game, served by serve.sh")
ap.add_argument("--fps", type=int, default=30)
ap.add_argument("--frames", type=int, default=0)
ap.add_argument("--still", action="store_true", help="only write 5 stills spread over the scene, no video")
ap.add_argument("--at", default="", help="comma list of seconds: write only these frames (as stills)")
ap.add_argument("--png", action="store_true", help="stills as PNG (for the screenshot deliverables)")
ap.add_argument("--css", default="", help="extra CSS for this run (e.g. hide the fingertip in a screenshot)")
a = ap.parse_args()
S = SCENES[a.scene]
phone = S.get("phone", False)
W, H = (852, 393) if phone else (960, 540)
nframes = a.frames or int(round(S.get("dur", 6) * a.fps))
os.makedirs(a.out, exist_ok=True)
fdir = os.path.join(a.out, "frames_" + a.scene); os.makedirs(fdir, exist_ok=True)

HIDE_HUD = "#hud,#resbar,#panel,#sword,#joyZone,#mmWrap,#toasts,#selBtn,#ppause,#tut,#wallBar,.ui{display:none!important}"
# game-clock CSS animations and no damage numbers; runs right after every world step
POST = """(() => {
  for (const an of document.getAnimations()) {
    if (typeof CSSTransition !== 'undefined' && an instanceof CSSTransition) { try { an.finish() } catch (e) {} continue; }
    try { an.pause(); an.currentTime = (window.__ts - 1000) % 600000; } catch (e) {}
  }
  if (!window.__keepDmg) texts = texts.filter(t => !t.plain);
  // the game prints '+' before a pickup whose str already starts with '+' ("++10"): show one
  for (const t of texts) if (t.ic && t.str[0] === '+') t.str = t.str.slice(1);
})()"""

with sync_playwright() as p:
    b = p.webkit.launch()
    ctx = b.new_context(viewport={"width": W, "height": H}, device_scale_factor=2, is_mobile=False, has_touch=True)
    ctx.add_init_script(INIT)
    if S.get("init"): ctx.add_init_script(S["init"])
    pg = ctx.new_page(); pg.set_default_timeout(180000)
    pg.on("crash", lambda *_: (print("PAGE CRASHED", flush=True), os._exit(3)))
    pg.on("console", lambda m: m.type == "error" and print("console:", m.text[:200]))
    pg.on("pageerror", lambda e: print("pageerror:", str(e)[:300]))
    pg.goto(a.url)
    pg.wait_for_timeout(1500)
    pg.evaluate("document.getElementById('introOv') && (document.getElementById('introOv').style.display='none')")
    if not S.get("title"):
        pg.click("#startBtn", force=True)
        pg.evaluate("window.__step(2, 33.33)")
    if not S.get("hud") and not S.get("title"): pg.add_style_tag(content=HIDE_HUD)
    if S.get("css"): pg.add_style_tag(content=S["css"])
    if a.css: pg.add_style_tag(content=a.css)
    pg.evaluate(COMMON_JS)
    pg.evaluate(S.get("setup", "0"))
    print("setup ok, units", pg.evaluate("units.length"), flush=True)
    pg.evaluate("__preloadAll()")
    left = 0
    for _ in range(160):
        left = pg.evaluate("__pending()")
        if left == 0: break
        pg.wait_for_timeout(500)
    print("pending images after preload:", left, flush=True)
    dtms = 1000.0 / a.fps
    warm = int(S.get("warm", 2) * a.fps)
    for i in range(0, warm, 5):
        pg.evaluate(f"window.__step(5, {dtms})")
    print("warm ok", flush=True)
    if S.get("after_warm"): pg.evaluate(S["after_warm"])
    events = {}
    for t, js in S.get("events", []): events.setdefault(int(round(t * a.fps)), []).append(js)
    cam = S.get("cam", "")
    speed = S.get("speed", 1)
    t0 = time.time()
    if a.at: picks = {int(round(float(x) * a.fps)) for x in a.at.split(",")}
    elif a.still: picks = set(range(0, nframes, max(1, nframes // 5)))
    else: picks = None
    ext = "png" if a.png else "jpg"
    for f in range(nframes):
        for js in events.get(f, []): pg.evaluate(js)
        if cam: pg.evaluate(f"(f=>{{ {cam} }})({f / a.fps})")
        sp = speed(f / a.fps) if callable(speed) else speed
        pg.evaluate(f"window.__step({sp}, {dtms})")
        pg.evaluate(POST)
        if picks is None or f in picks:
            path = os.path.join(fdir, f"{f:05d}.{ext}")
            if a.png: pg.screenshot(path=path, type="png")
            else: pg.screenshot(path=path, type="jpeg", quality=94)
        if f % 60 == 0: print(f"frame {f}/{nframes} {time.time()-t0:.0f}s", flush=True)
    b.close()

if picks is None:
    mp4 = os.path.join(a.out, a.scene + ".mp4")
    subprocess.run(["nice", "ffmpeg", "-y", "-v", "error", "-framerate", str(a.fps), "-i", os.path.join(fdir, "%05d.jpg"),
                    "-c:v", "libx264", "-preset", "slow", "-crf", "14", "-pix_fmt", "yuv420p", mp4], check=True)
    print("wrote", mp4)
