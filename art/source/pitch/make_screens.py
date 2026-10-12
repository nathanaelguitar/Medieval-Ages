#!/usr/bin/env python3
"""The six pitch screenshots: PNG stills captured by capture.py --at T --png (1920x1080) are copied to
art/out/pitch/screenshots/1920x1080/ and downscaled (Lanczos) to 1280x720/, each as PNG and JPEG.

Usage: make_screens.py RAW_DIR     (RAW_DIR holds frames_<scene>/<frame>.png from the Spark)
The picks below name the scene and the frame index (30 fps) used for each screenshot.
"""
import os, sys
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, "../../.."))
OUT = os.path.join(ROOT, "art/out/pitch/screenshots")
PICKS = [  # (output name, scene, seconds into the scene)
    ("01_village_overview", "village", 7.5),
    ("02_battle", "battle", 3.0),
    ("03_mill_and_farms", "mill", 6.6),
    ("04_army_with_banners", "banners", 3.5),
    ("05_ui_placing_a_building", "place", 2.9),
    ("06_title_screen", "title", 0.1),
]

def main(raw):
    for d in ("1920x1080", "1280x720"): os.makedirs(os.path.join(OUT, d), exist_ok=True)
    for name, scene, t in PICKS:
        src = os.path.join(raw, f"frames_{scene}", f"{int(round(t * 30)):05d}.png")
        im = Image.open(src).convert("RGB"); assert im.size == (1920, 1080), (src, im.size)
        sm = im.resize((1280, 720), Image.LANCZOS)
        for d, x in (("1920x1080", im), ("1280x720", sm)):   # PNG (lossless) plus a JPEG for forms with size caps
            x.save(os.path.join(OUT, d, name + ".png"), optimize=True)
            x.save(os.path.join(OUT, d, name + ".jpg"), quality=92)
        print(name)

if __name__ == "__main__":
    main(sys.argv[1])
