#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Side-by-side lineup of baked units at the game's scale, so relative heights can be judged.

    python3 art/pipeline/lineup.py --out art/out/archer_v1/previews/lineup.png \\
        --unit "man_at_arms=art/out/man_at_arms_v4/sprites@2x" --unit "archer=art/out/archer_v1/sprites@2x"

The game draws every directional frame with DIR_K = 28.6/144 of its @2x pixel size, anchored at
the frame's footprint centre (fp_cx, fp_cy), so here each unit's idle frame 0 in d1 (facing
right), d7 (toward the camera) and d3 (away) is drawn at that scale on a common ground line,
plus the same at 4x nearest for inspection.
"""
import argparse
import json
import os

from PIL import Image, ImageDraw

DIR_K = 28.6 / 144


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--unit", action="append", required=True, help="name=sprites@2x dir")
    ap.add_argument("--team", default="blue")
    ap.add_argument("--clip", default="idle")
    ap.add_argument("--dirs", default="1,7,3")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    units = []
    for spec in a.unit:
        name, d = spec.split("=", 1)
        with open(os.path.join(d, "manifest_snippet.json")) as fh:
            units.append((name, d, json.load(fh)))
    dirs = [int(x) for x in a.dirs.split(",")]
    for zoom, suffix in ((1, ""), (4, "_4x")):
        slot = int(64 * zoom)
        W = 20 + len(units) * len(dirs) * slot + 20
        H = int(70 * zoom) + 40
        ground = H - 20
        im = Image.new("RGB", (W, H), (96, 118, 76))
        dr = ImageDraw.Draw(im)
        dr.line((0, ground, W, ground), fill=(70, 90, 55))
        x = 20
        for name, d, man in units:
            for k in dirs:
                key = f"{name}_{a.team}_{a.clip}_d{k}_0"
                m = man[key]
                sp = Image.open(os.path.join(d, m["file"])).convert("RGBA")
                s = DIR_K * zoom
                w, h = int(round(sp.width * s)), int(round(sp.height * s))
                sp = sp.resize((w, h), Image.LANCZOS if zoom == 1 else Image.NEAREST)
                px = int(round(x + slot / 2 - m["fp_cx"] * s))
                py = int(round(ground - m["fp_cy"] * s))
                im.alpha_composite(sp, (px, py)) if im.mode == "RGBA" else im.paste(sp, (px, py), sp)
                dr.text((x + 2, ground + 4), f"{name} d{k}", fill=(255, 255, 255))
                x += slot
        dr.text((6, 4), f"game scale x{zoom}: {a.clip} frame 0, {a.team}; footprint centres on the ground line",
                fill=(255, 255, 255))
        out = a.out if not suffix else a.out.replace(".png", f"{suffix}.png")
        im.save(out)
        print("wrote", out, im.size)


if __name__ == "__main__":
    main()
