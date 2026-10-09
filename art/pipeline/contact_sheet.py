#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compose the user-facing contact sheet for a unit: model turnaround per team + sprite strips.

    python3 art/pipeline/contact_sheet.py --name man_at_arms --out art/out/man_at_arms/previews/contact_sheet.png \
        --turnaround art/out/man_at_arms/previews/body_textured.png --rows "blue team,red team" \
        --sprites art/out/man_at_arms/sprites

The turnaround image is the preview_models.py sheet (one labelled row per mesh, 512px tiles with a
24px label band); the front, 3/4 and back tiles are picked from it. Sprite strips show direction 0..7
of the first frame, and the walk cycle for direction 0, at 3x nearest-neighbour.
"""
import argparse
import glob
import os

from PIL import Image, ImageDraw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--turnaround", required=True)
    ap.add_argument("--tile", type=int, default=512)
    ap.add_argument("--band", type=int, default=24)
    ap.add_argument("--rows", default="blue team,red team")
    ap.add_argument("--sprites", required=True)
    ap.add_argument("--size", type=int, default=72)
    a = ap.parse_args()

    turn = Image.open(a.turnaround).convert("RGB")
    rows = a.rows.split(",")
    T, B = a.tile, a.band
    cols = {"front": 0, "3/4": 1, "back": 3}
    tile_w = 360
    scale = tile_w / T
    z = 3
    S = a.size * z
    width = max(3 * tile_w + 40, 8 * S + 80)
    height = len(rows) * (int(T * scale) + 30) + 2 * (len(rows)) * (S + 30) + 60
    sheet = Image.new("RGB", (width, height), (38, 40, 36))
    d = ImageDraw.Draw(sheet)
    d.text((10, 8), f"{a.name}: pre-rendered 3D. Models (Cycles) and baked 72px sprites shown 3x.", fill=(240, 232, 210))
    y = 30
    for r, label in enumerate(rows):
        d.text((10, y), label, fill=(255, 220, 150))
        y += 14
        for c, (vname, cidx) in enumerate(cols.items()):
            box = (cidx * T, r * (T + B) + B, (cidx + 1) * T, (r + 1) * (T + B))
            im = turn.crop(box).resize((tile_w, int(T * scale)), Image.LANCZOS)
            sheet.paste(im, (10 + c * (tile_w + 10), y))
            d.text((14 + c * (tile_w + 10), y + 4), vname, fill=(255, 255, 255))
        y += int(T * scale) + 16
    team_names = [r.split()[0] for r in rows]
    for team in team_names:
        for clip, desc in (("idle", "idle, frame 0, directions d0..d7"), ("walk", "walk cycle, direction d0, all frames")):
            d.text((10, y), f"{team} {desc}", fill=(255, 220, 150))
            y += 14
            if clip == "idle":
                files = [os.path.join(a.sprites, f"{a.name}_{team}_idle_d{k}_0.png") for k in range(8)]
            else:
                files = sorted(glob.glob(os.path.join(a.sprites, f"{a.name}_{team}_walk_d0_*.png")),
                               key=lambda p: int(p.rsplit("_", 1)[1].split(".")[0]))
            x = 10
            for fn in files:
                if not os.path.exists(fn):
                    continue
                im = Image.open(fn).convert("RGBA").resize((S, S), Image.NEAREST)
                bg = Image.new("RGBA", (S, S), (96, 118, 76, 255))
                bg.alpha_composite(im)
                sheet.paste(bg.convert("RGB"), (x, y))
                x += S + 4
            y += S + 10
    sheet = sheet.crop((0, 0, width, y + 10))
    sheet.save(a.out)
    print("wrote", a.out, sheet.size)


if __name__ == "__main__":
    main()
