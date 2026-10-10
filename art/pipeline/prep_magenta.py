#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Key Codex reference views shot on flat magenta (#FF00FF) into RGBA cut-outs for TRELLIS.2.

The animal references (art/source/animals/gen) are generated on solid magenta rather than the
grey studio of the unit A-poses, so a chroma key is cleaner than BiRefNet: alpha comes from the
pixel's magenta excess min(R,B)-G, the colour is despilled (min(R,B) pulled down to G where it
exceeds it, which leaves brown fur and cream fleece untouched), the matte is eroded by a pixel
to drop the fringe, and the result is tight-cropped and square-padded to 1024 as prep_views.py
does.

    python3 art/pipeline/prep_magenta.py --in art/source/animals/gen --out art/out/animals/prep \
        boar_right boar_left boar_front boar_back
"""
import argparse
import os

import numpy as np
from PIL import Image, ImageFilter


def key(rgb, lo=40.0, hi=150.0):
    a = rgb.astype(np.float32)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    m = np.minimum(r, b) - g                       # magenta excess: 255 on the backdrop
    alpha = 1.0 - np.clip((m - lo) / (hi - lo), 0, 1)
    spill = np.clip(np.minimum(r, b) - g, 0, None)
    out = a.copy()
    out[..., 0] -= spill
    out[..., 2] -= spill
    # unpremultiply the remaining half-transparent edge against the magenta it was mixed with
    edge = (alpha > 0.05) & (alpha < 0.95)
    for c, bg in ((0, 255.0), (1, 0.0), (2, 255.0)):
        ch = a[..., c]
        fg = (ch - (1 - alpha) * bg) / np.maximum(alpha, 0.05)
        out[..., c] = np.where(edge, np.clip(fg, 0, 255), out[..., c])
    # despill the unpremultiplied edge too
    e = out
    spill2 = np.clip(np.minimum(e[..., 0], e[..., 2]) - e[..., 1], 0, None)
    e[..., 0] -= spill2
    e[..., 2] -= spill2
    return np.clip(out, 0, 255).astype(np.uint8), (alpha * 255).astype(np.uint8)


def square_pad(rgba, margin=0.04, size=1024):
    a = np.asarray(rgba.getchannel("A"))
    ys, xs = np.where(a > 16)
    if len(xs):
        rgba = rgba.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    side = int(max(rgba.size) * (1 + 2 * margin))
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(rgba, ((side - rgba.width) // 2, (side - rgba.height) // 2))
    return canvas.resize((size, size), Image.LANCZOS)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("names", nargs="+", help="<name>[:mirror]")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for spec in a.names:
        name, _, flag = spec.partition(":")
        im = Image.open(os.path.join(a.src, name + ".png")).convert("RGB")
        if flag == "mirror":
            im = im.transpose(Image.FLIP_LEFT_RIGHT)
        rgb, alpha = key(np.asarray(im))
        am = Image.fromarray(alpha).filter(ImageFilter.MinFilter(3))   # 1px erosion: no magenta fringe
        # keep only the largest opaque blob's neighbourhood: drop stray specks of the backdrop
        rgba = Image.fromarray(rgb).convert("RGBA")
        rgba.putalpha(am)
        out = square_pad(rgba)
        out.save(os.path.join(a.out, name + ".png"))
        cov = (np.asarray(out.getchannel("A")) > 128).mean()
        print(f"{name}: coverage {cov:.2f}")


if __name__ == "__main__":
    main()
