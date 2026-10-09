#!/usr/bin/env python
"""Prepare the high-res A-pose reference views for TRELLIS.2 (v2 pipeline).

For every requested view: optionally mirror it horizontally (the generated back views have the
tabard's colour split on the same screen side as the front, which is physically wrong: seen from
behind the cream/colour halves must swap), remove the grey studio background with BiRefNet
(ZhengPeng7/BiRefNet via rembg's `birefnet-general`, MIT weights; nothing from bria/RMBG, whose
licence is non-commercial), tight-crop on the alpha, pad to a square with a margin and write an
RGBA PNG. TRELLIS.2 uses the alpha channel directly when one is present, so its own (gated)
background remover is never needed.

On the Spark, in the Hunyuan venv (it has rembg + onnxruntime) or inside the trellis2 image:

    ~/hunyuan3d/.venv/bin/python art/pipeline/prep_views.py \
        --in ~/hunyuan3d/inputs/man_at_arms/gen --out ~/trellis2/work/man_at_arms/prep \
        blue_apose_front_hr blue_apose_back_hr:mirror blue_apose_left blue_apose_right \
        red_apose_front_hr red_apose_back_hr:mirror

Each positional argument is ``<name>[:mirror]``; the output is ``<name>.png`` (1024x1024 RGBA).
Shield crops (small, from the parent folder): add ``--upscale``:

    ~/hunyuan3d/.venv/bin/python art/pipeline/prep_views.py --upscale \
        --in ~/hunyuan3d/inputs/man_at_arms --out ~/trellis2/work/man_at_arms/prep blue_shield red_shield
"""
import argparse
import os
import time

import numpy as np
from PIL import Image, ImageOps


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
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--size", type=int, default=1024)
    ap.add_argument("--model", default="birefnet-general")
    ap.add_argument("--upscale", action="store_true",
                    help="Real-ESRGAN x4 (BSD-3 weights, vendored net in prep_images.py) before cutting; for the "
                         "small shield/sword crops, not the 1024x1536 views")
    ap.add_argument("names", nargs="+")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    from rembg import new_session, remove
    session = new_session(a.model)
    net = None
    if a.upscale:
        import sys
        import torch
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import prep_images
        net = prep_images.load_esrgan("cuda" if torch.cuda.is_available() else "cpu")
    for spec in a.names:
        name, _, flag = spec.partition(":")
        t0 = time.time()
        im = Image.open(os.path.join(a.inp, name + ".png")).convert("RGB")
        if net is not None:
            im = prep_images.upscale(im, net, "cuda" if torch.cuda.is_available() else "cpu")
        if flag == "mirror":
            im = ImageOps.mirror(im)
        rgba = remove(im, session=session, alpha_matting=False, post_process_mask=True)
        sq = square_pad(rgba, size=a.size)
        sq.save(os.path.join(a.out, name + ".png"))
        cov = np.asarray(sq.getchannel("A")).mean() / 255
        print(f"{name}{' (mirrored)' if flag else ''}: {im.size} -> {sq.size} alpha coverage {cov:.2f} "
              f"{time.time() - t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
