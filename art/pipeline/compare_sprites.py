#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Side-by-side sheet of two sprite sets (e.g. v1 vs v2) at native size and zoomed.

    python3 art/pipeline/compare_sprites.py --name man_at_arms \
        --a "v1=art/out/man_at_arms/sprites" --b "v2=art/out/man_at_arms_v2/sprites" \
        --out art/out/man_at_arms_v2/previews/compare_v1_v2.png

Rows: for each team, idle frame 0 in all 8 directions and the walk cycle (``--walk-dirs``, all
frames of each set, so sets with different frame counts compare), each shown once at 1x (72 px)
and once at --zoom (nearest neighbour) so the pixel-level edges and the in-frame shadow can be
judged. Both sets must use the same key scheme ``<name>_<team>_<clip>_d<dir>_<frame>.png``.
"""
import argparse
import glob
import os

from PIL import Image, ImageDraw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--a", required=True, help="label=sprites dir")
    ap.add_argument("--b", required=True, help="label=sprites dir")
    ap.add_argument("--out", required=True)
    ap.add_argument("--zoom", type=int, default=3)
    ap.add_argument("--teams", default="blue,red")
    ap.add_argument("--size", type=int, default=72)
    ap.add_argument("--walk-dirs", default="0", help="directions whose walk cycle is shown, e.g. 0,1,7")
    a = ap.parse_args()
    sets = [s.split("=", 1) for s in (a.a, a.b)]
    S, z = a.size, a.zoom
    bg = (96, 118, 76, 255)
    strips = []   # (label, [files])
    def walk_files(sdir, team, k):
        fs = glob.glob(os.path.join(sdir, f"{a.name}_{team}_walk_d{k}_*.png"))
        return sorted((os.path.basename(f) for f in fs), key=lambda f: int(f.rsplit("_", 1)[1].split(".")[0]))
    nwalk = max(len(walk_files(sdir, t, 0)) for _, sdir in sets for t in a.teams.split(","))
    for team in a.teams.split(","):
        strips.append((f"{team} idle f0 d0..d7", [f"{a.name}_{team}_idle_d{k}_0.png" for k in range(8)]))
        for k in a.walk_dirs.split(","):
            strips.append((f"{team} walk d{k}, all frames", {sdir: walk_files(sdir, team, k) for _, sdir in sets}))
    cols = max(8, nwalk)
    row_h = S + S * z + 8
    gap = 18
    W = (cols * S * z) + 120
    H = 30 + len(strips) * (len(sets) * (row_h + gap) + 24)
    sheet = Image.new("RGBA", (W, H), bg)
    d = ImageDraw.Draw(sheet)
    d.text((8, 8), f"{a.name}: {sets[0][0]} vs {sets[1][0]}; each strip at 1x ({S}px) and {z}x nearest", fill=(255, 255, 255))
    y = 30
    for label, files in strips:
        d.text((8, y), label, fill=(255, 225, 160))
        y += 16
        for slabel, sdir in sets:
            d.text((8, y + 4), slabel, fill=(255, 255, 255))
            for c, fn in enumerate(files[sdir] if isinstance(files, dict) else files):
                p = os.path.join(sdir, fn)
                if not os.path.exists(p):
                    continue
                im = Image.open(p).convert("RGBA")
                sheet.alpha_composite(im, (110 + c * S * z, y))
                sheet.alpha_composite(im.resize((S * z, S * z), Image.NEAREST), (110 + c * S * z, y + S + 4))
            y += row_h + gap
        y += 8
    sheet.convert("RGB").save(a.out)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
