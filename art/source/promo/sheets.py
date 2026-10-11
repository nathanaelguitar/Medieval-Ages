#!/usr/bin/env python3
"""Contact sheet: one frame per second (or --fps), labelled with its timestamp, 10 per row.
Usage: sheets.py VIDEO OUT.jpg [--fps 1] [--w 216]"""
import argparse, glob, os, subprocess, tempfile
from PIL import Image, ImageDraw, ImageFont
ap = argparse.ArgumentParser(); ap.add_argument("video"); ap.add_argument("out")
ap.add_argument("--fps", type=float, default=1); ap.add_argument("--w", type=int, default=216); ap.add_argument("--cols", type=int, default=10)
a = ap.parse_args()
with tempfile.TemporaryDirectory() as td:
    # sample at t = 0.5/fps, 1.5/fps, ... (mid-second) so cuts on whole seconds do not hide a shot
    subprocess.run(["ffmpeg", "-v", "error", "-ss", str(0.5 / a.fps), "-i", a.video, "-vf", f"fps={a.fps},scale={a.w}:-2", os.path.join(td, "%04d.jpg")], check=True)
    fr = sorted(glob.glob(os.path.join(td, "*.jpg"))); im0 = Image.open(fr[0]); w, h = im0.size
    rows = (len(fr) + a.cols - 1) // a.cols; pad = 4
    sheet = Image.new("RGB", (a.cols * (w + pad) + pad, rows * (h + pad) + pad), (0, 0, 0))
    f = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 16); d = ImageDraw.Draw(sheet)
    for i, p in enumerate(fr):
        x, y = pad + (i % a.cols) * (w + pad), pad + (i // a.cols) * (h + pad); sheet.paste(Image.open(p), (x, y))
        t = (i + 0.5) / a.fps; d.rectangle([x, y, x + 52, y + 20], fill=(0, 0, 0)); d.text((x + 4, y + 2), f"{t:5.1f}s", font=f, fill=(255, 255, 255))
    sheet.save(a.out, quality=88); print(a.out, len(fr), "frames")
