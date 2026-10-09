#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Animated GIF of a baked clip: the chosen directions side by side, zoomed (nearest), at the
clip's manifest fps.

    python3 art/pipeline/walk_gif.py --sprites art/out/man_at_arms_v3/sprites --name man_at_arms \\
        --team blue --clip walk --dirs 0,1,7 --zoom 3 --out art/out/man_at_arms_v3/previews/walk_blue.gif

``--fps`` overrides the manifest's (e.g. 7 to preview the game's fixed walk rate). A clip whose
manifest entry has ``loop: false`` (death) holds its last frame for ``--hold`` seconds before the
GIF repeats; an ``impact_frame`` is labelled.
"""
import argparse
import json
import os

from PIL import Image, ImageDraw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sprites", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--team", required=True)
    ap.add_argument("--clip", default="walk")
    ap.add_argument("--dirs", default="0,1,7")
    ap.add_argument("--zoom", type=int, default=3)
    ap.add_argument("--fps", type=float)
    ap.add_argument("--hold", type=float, default=1.0, help="seconds the last frame of a non-looping clip holds")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    with open(os.path.join(a.sprites, "manifest_snippet.json")) as fh:
        man = json.load(fh)
    dirs = [int(d) for d in a.dirs.split(",")]
    clips = [man[f"{a.name}_{a.team}_{a.clip}_d{d}"] for d in dirs]
    fps = a.fps or clips[0]["fps"]
    n = min(c["frames"] for c in clips)
    loop = clips[0].get("loop", True)
    impact = clips[0].get("impact_frame")
    size = man[f"{a.name}_{a.team}_{a.clip}_d{dirs[0]}_0"]["w"]
    S = size * a.zoom
    frames, durations = [], []
    for i in range(n):
        im = Image.new("RGBA", (len(dirs) * (S + 6) + 6, S + 24), (96, 118, 76, 255))
        d = ImageDraw.Draw(im)
        tag = " IMPACT" if impact is not None and i == impact else (" (held)" if not loop and i == n - 1 else "")
        d.text((6, 4), f"{a.name} {a.team} {a.clip} frame {i}/{n} @ {fps:.1f} fps (zoom {a.zoom}x){tag}",
               fill=(255, 230, 120) if tag else (255, 255, 255))
        for k, (dd, c) in enumerate(zip(dirs, clips)):
            sp = Image.open(os.path.join(a.sprites, c["files"][i])).convert("RGBA")
            im.alpha_composite(sp.resize((S, S), Image.NEAREST), (6 + k * (S + 6), 20))
            d.text((8 + k * (S + 6), 20 + S - 12), f"d{dd}", fill=(255, 255, 255))
        frames.append(im.convert("RGB").quantize(colors=255, dither=Image.Dither.NONE))
        durations.append(int(round(1000 / fps)) + (int(a.hold * 1000) if not loop and i == n - 1 else 0))
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    frames[0].save(a.out, save_all=True, append_images=frames[1:], duration=durations, loop=0)
    print(f"wrote {a.out}: {n} frames at {fps:.2f} fps, dirs {dirs}, loop={loop}")


if __name__ == "__main__":
    main()
