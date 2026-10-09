#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Contact strip of one clip for both teams: rows = the 8 directions, columns = frames, shown at
3x nearest-neighbour on the game's green, with the manifest's impact frame outlined and the
direction legend (d1 faces right, d5 left, d7 toward the camera, d3 away) written on the sheet.

    python3 art/pipeline/clip_contact.py --name man_at_arms --sprites art/out/man_at_arms_v4/sprites \\
        --clip attack --out art/out/man_at_arms_v4/previews/attack_contact.png
"""
import argparse
import json
import os

from PIL import Image, ImageDraw

FACING = {1: "faces right (sword side)", 5: "faces left (shield side)", 7: "toward camera", 3: "away"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--sprites", required=True)
    ap.add_argument("--clip", required=True)
    ap.add_argument("--teams", default="blue,red")
    ap.add_argument("--zoom", type=int, default=3)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    with open(os.path.join(a.sprites, "manifest_snippet.json")) as fh:
        man = json.load(fh)
    teams = a.teams.split(",")
    hdr = man[a.name]
    dirs = hdr["dirs"]
    first = man[f"{a.name}_{teams[0]}_{a.clip}_d0"]
    n = first["frames"]
    size = man[f"{a.name}_{teams[0]}_{a.clip}_d0_0"]["w"]
    z = a.zoom
    S = size * z
    label_w = 150
    W = label_w + n * S + 10
    H = 30 + len(teams) * (dirs * S + 30)
    sheet = Image.new("RGB", (W, H), (96, 118, 76))
    d = ImageDraw.Draw(sheet)
    imp = first.get("impact_frame")
    loop = first.get("loop", True)
    d.text((8, 6), f"{a.name} {a.clip}: {n} frames @ {first['fps']:.2f} fps, {first['duration']:.2f} s, "
                   f"{'looping' if loop else 'one-shot (last frame held)'}"
                   + (f", impact frame {imp} outlined" if imp is not None else "") + f"; shown {z}x",
           fill=(255, 255, 255))
    y = 30
    for team in teams:
        d.text((8, y), f"{team} team: rows d0..d{dirs-1}, columns frame 0..{n-1}", fill=(255, 220, 150))
        y += 16
        for k in range(dirs):
            d.text((8, y + S // 2 - 6), f"d{k} {FACING.get(k, 'diagonal')}", fill=(255, 255, 255))
            for i in range(n):
                fn = os.path.join(a.sprites, f"{a.name}_{team}_{a.clip}_d{k}_{i}.png")
                if not os.path.exists(fn):
                    continue
                im = Image.open(fn).convert("RGBA").resize((S, S), Image.NEAREST)
                sheet.paste(im, (label_w + i * S, y), im)
                if imp is not None and i == imp:
                    d.rectangle((label_w + i * S, y, label_w + (i + 1) * S - 1, y + S - 1),
                                outline=(255, 220, 80), width=2)
            y += S
        y += 14
    sheet.save(a.out)
    print("wrote", a.out, sheet.size)


if __name__ == "__main__":
    main()
