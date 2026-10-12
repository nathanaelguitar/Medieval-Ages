#!/usr/bin/env python3
"""Render the trailer and the 30 s cut end to end (run in ~/ma_pitch/edit on the Spark).

Pipeline (art/source/pitch): make_text.py on the Mac (cards, captions, phone bezel, icons, thumbnail)
-> on the Spark: `git archive HEAD ios/WebGame` unpacked to ~/ma_pitch/WebGame, run.sh SCENES (capture.py
+ scenes.py -> ~/ma_pitch/clips/*.mp4) -> render.py here (make_edl.py + assemble.py) -> shots.sh for the
PNG screenshots -> make_screens.py on the Mac.

For each cut: write the EDL (make_edl.py), assemble it, measure integrated loudness and, while it
is more than 0.4 LU off -14 LUFS, shift the music level by the difference and re-mix (segments are
cached). Then a 1 fps contact sheet, and a report of the loudest sample-to-sample jump (clicks) and
the level of the last 300 ms (a clean fade ends near silence).
Usage: render.py [trailer] [30s]
Outputs: medieval_ages_trailer.mp4, medieval_ages_30s.mp4 (CRF 17 masters), upload/<same> (2-pass
size-capped copies for upload forms: trailer <= 50 MB, 30 s <= 20 MB), sheet_<name>_1fps.jpg
"""
import json, os, re, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
HERE = os.getcwd(); sys.path.insert(0, HERE)
import make_edl as M

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode: print(" ".join(cmd)); print(r.stdout[-2000:], r.stderr[-3000:]); sys.exit(1)
    return r

def lufs(p):
    r = subprocess.run(["ffmpeg", "-nostats", "-i", p, "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True)
    s = r.stderr[r.stderr.rfind("Summary"):]
    return float(re.search(r"I:\s+(-?[\d.]+) LUFS", s).group(1)), float(re.search(r"Peak:\s+(-?[\d.]+) dBFS", s).group(1))

def clicks(p):
    x = np.frombuffer(subprocess.run(["ffmpeg", "-v", "error", "-i", p, "-ac", "1", "-ar", "48000", "-f", "f32le", "-"], capture_output=True).stdout, np.float32)
    j = np.abs(np.diff(x)); i = int(j.argmax())
    return f"max sample jump {j.max():.3f} at {i/48000:.2f}s, last 300 ms peak {20*np.log10(np.abs(x[-14400:]).max()+1e-9):.0f} dBFS"

def sheet(video, out, fps=1, w=320, cols=10):
    d = out + ".tmp"; os.makedirs(d, exist_ok=True)
    for f in os.listdir(d): os.remove(os.path.join(d, f))
    run(["ffmpeg", "-v", "error", "-ss", str(0.5 / fps), "-i", video, "-vf", f"fps={fps},scale={w}:-2", os.path.join(d, "%04d.jpg")])
    fr = sorted(os.listdir(d)); im0 = Image.open(os.path.join(d, fr[0])); fw, fh = im0.size; pad = 4
    rows = (len(fr) + cols - 1) // cols
    sh = Image.new("RGB", (cols * (fw + pad) + pad, rows * (fh + pad) + pad))
    try: font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
    except OSError: font = ImageFont.load_default()
    dr = ImageDraw.Draw(sh)
    for i, f in enumerate(fr):
        x, y = pad + (i % cols) * (fw + pad), pad + (i // cols) * (fh + pad); sh.paste(Image.open(os.path.join(d, f)), (x, y))
        dr.rectangle([x, y, x + 56, y + 20], fill=(0, 0, 0)); dr.text((x + 4, y + 2), f"{(i + 0.5) / fps:5.1f}s", font=font, fill=(255, 255, 255))
    sh.save(out, quality=88)
    for f in fr: os.remove(os.path.join(d, f))
    os.rmdir(d)

def upload(src, dst, mb):
    d = float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", src]).stdout)
    vb = int((mb * 0.97e6 * 8 / d - 160000) / 1000); log = dst + ".2pass"
    base = ["nice", "ffmpeg", "-y", "-v", "error", "-i", src, "-c:v", "libx264", "-preset", "veryslow", "-profile:v", "high", "-pix_fmt", "yuv420p",
            "-b:v", f"{vb}k", "-maxrate", f"{int(vb*1.6)}k", "-bufsize", f"{vb*2}k", "-g", "60", "-passlogfile", log]
    run(base + ["-pass", "1", "-an", "-f", "mp4", "/dev/null"])
    run(base + ["-pass", "2", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-movflags", "+faststart", dst])
    for f in os.listdir(os.path.dirname(dst) or "."):
        if f.startswith(os.path.basename(log)): os.remove(os.path.join(os.path.dirname(dst) or ".", f))
    return os.path.getsize(dst) / 1e6, vb

DB = "music_db.json"
names = sys.argv[1:] or ["trailer", "30s"]
for n in names:
    db = json.load(open(DB)) if os.path.exists(DB) else {}
    out = f"medieval_ages_{n}.mp4"
    for attempt in range(4):
        M.build(n, M.TRAILER if n == "trailer" else M.SHORT, (4.0, 0.8) if n == "trailer" else (3.0, 0.6), db.get(n, 0.0), 3.0 if n == "trailer" else 2.2)
        run([sys.executable, "assemble.py", f"edl_{n}.json", out])
        I, pk = lufs(out)
        if abs(I + 14) <= 0.4: break
        db[n] = round(db.get(n, 0) + (-14 - I), 1); json.dump(db, open(DB, "w"), indent=1)
        print(f"  {n}: {I} LUFS -> music {db[n]:+.1f} dB, re-mixing", flush=True)
    sheet(out, f"sheet_{n}_1fps.jpg")
    os.makedirs("upload", exist_ok=True)
    size, vb = upload(out, os.path.join("upload", out), 50 if n == "trailer" else 20)
    print(f"  upload copy {size:.1f} MB at {vb} kb/s", flush=True)
    dur = float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", out]).stdout)
    print(f"{n}: {dur:.2f}s  {I:.1f} LUFS  true peak {pk:.1f} dBFS  {clicks(out)}", flush=True)
