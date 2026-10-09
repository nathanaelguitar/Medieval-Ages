#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Post-process bake_sprites.py tiles: Lanczos-reduce to the sprite size, write a @2x set, the
manifest snippet, and preview strips. Runs in the system python (needs Pillow).

    python3 art/pipeline/sprites_post.py --tiles art/out/man_at_arms/_tiles --out art/out/man_at_arms

``--contrast a`` (v3: 0.35) applies a gentle S-curve to the character's sRGB values,
``x - a*sin(2*pi*x)/(2*pi)``, which deepens quarter-tones by about a/6 and leaves black and white
where they are, so bright steel highlights do not clip; ``--saturation`` scales chroma about luma.
"""
import argparse
import json
import os

from PIL import Image, ImageDraw


def composite_shadow(body, shadow_png, fp_cx, fp_cy, size, ss, opacity, inner, blur):
    """Put a separately rendered contact shadow (alpha = shadow density) under the character,
    lightened to `opacity` and faded out with an elliptical falloff centred on the footprint so
    it reaches zero before the cell edge instead of being clipped into a hard rectangle. `inner`
    is the fraction of the available radius where the fade starts. Coordinates are sprite pixels;
    the tiles are ss times larger."""
    import numpy as np
    from PIL import ImageFilter
    sh = Image.open(shadow_png).convert("RGBA").getchannel("A")
    if blur > 0:
        sh = sh.filter(ImageFilter.GaussianBlur(blur * ss))
    alpha = np.asarray(sh, dtype=np.float32) / 255.0
    n = alpha.shape[0]
    cx, cy = fp_cx * ss, fp_cy * ss
    ys, xs = np.mgrid[0:n, 0:n].astype(np.float32) + 0.5
    rx = max(min(cx, n - cx) - ss, 1.0)
    ry_up, ry_down = max(cy - ss, 1.0), max(n - cy - ss, 1.0)
    dy = np.where(ys < cy, (cy - ys) / ry_up, (ys - cy) / ry_down)
    r = np.sqrt(((xs - cx) / rx) ** 2 + dy ** 2)
    t = np.clip((r - inner) / max(1e-6, 1.0 - inner), 0, 1)
    fade = 1.0 - t * t * (3 - 2 * t)
    alpha = alpha * fade * opacity
    layer = np.zeros((n, n, 4), dtype=np.uint8)
    layer[..., 3] = np.clip(alpha * 255, 0, 255).astype(np.uint8)
    out = Image.fromarray(layer, "RGBA")
    out.alpha_composite(body)
    return out


def tone(im, contrast, saturation):
    """S-curve contrast and chroma scaling on the RGB of a straight-alpha RGBA image."""
    import numpy as np
    if contrast == 0 and saturation == 1:
        return im
    a = np.asarray(im, dtype=np.float32) / 255.0
    rgb = a[..., :3]
    if saturation != 1:
        luma = rgb @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
        rgb = luma[..., None] + (rgb - luma[..., None]) * saturation
    if contrast:
        rgb = rgb - contrast * np.sin(2 * np.pi * rgb) / (2 * np.pi)
    a[..., :3] = np.clip(rgb, 0, 1)
    return Image.fromarray((a * 255 + 0.5).astype(np.uint8), "RGBA")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tiles", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--shadow-opacity", type=float, default=0.45)
    ap.add_argument("--shadow-inner", type=float, default=0.5)
    ap.add_argument("--shadow-blur", type=float, default=0.75, help="sprite pixels")
    ap.add_argument("--contrast", type=float, default=0.0, help="S-curve strength (0 = off, v3 uses 0.35)")
    ap.add_argument("--saturation", type=float, default=1.0)
    a = ap.parse_args()
    with open(os.path.join(a.tiles, "tiles.json")) as fh:
        meta = json.load(fh)
    size, ss, name = meta["size"], meta["supersample"], meta["name"]
    sprites = os.path.join(a.out, "sprites")
    sprites2x = os.path.join(a.out, "sprites@2x")
    os.makedirs(sprites, exist_ok=True)
    os.makedirs(sprites2x, exist_ok=True)

    manifest, manifest2x = {}, {}
    clips = {}
    for fr in meta["frames"]:
        src = tone(Image.open(os.path.join(a.tiles, fr["file"])).convert("RGBA"), a.contrast, a.saturation)
        if fr.get("shadow"):
            src = composite_shadow(src, os.path.join(a.tiles, fr["shadow"]), fr["fp_cx"], fr["fp_cy"],
                                   size, ss, a.shadow_opacity, a.shadow_inner, a.shadow_blur)
        big = src.resize((size * 2, size * 2), Image.LANCZOS) if ss != 2 else src
        small = src.resize((size, size), Image.LANCZOS)
        key = f"{name}_{fr['team']}_{fr['clip']}_d{fr['dir']}"
        fn = f"{key}_{fr['frame']}.png"
        small.save(os.path.join(sprites, fn))
        big.save(os.path.join(sprites2x, fn))
        alpha = small.getchannel("A")
        opaque = sum(1 for v in alpha.getdata() if v > 128)
        manifest[f"{key}_{fr['frame']}"] = {
            "file": fn, "w": size, "h": size, "fill": round(opaque / (size * size), 4),
            "fp_w": fr["fp_w"], "fp_cx": fr["fp_cx"], "fp_cy": fr["fp_cy"]}
        manifest2x[f"{key}_{fr['frame']}"] = {
            "file": fn, "w": size * 2, "h": size * 2, "fill": round(opaque / (size * size), 4),
            "fp_w": round(fr["fp_w"] * 2, 2), "fp_cx": round(fr["fp_cx"] * 2, 2), "fp_cy": round(fr["fp_cy"] * 2, 2)}
        c = clips.setdefault(key, {"clip": fr["clip"], "duration": fr["duration"], "files": [],
                                   "team": fr["team"], "dir": fr["dir"]})
        c["files"].append((fr["frame"], fn))
    for key, c in clips.items():
        files = [fn for _, fn in sorted(c["files"])]
        entry = {"group": "animation", "frames": len(files), "files": files, "clip": c["clip"],
                 "duration": c["duration"], "fps": round(len(files) / c["duration"], 3),
                 "team": c["team"], "dir": c["dir"]}
        manifest[key] = entry
        manifest2x[key] = dict(entry)
    # a small header describing the direction convention
    header = {"group": "directional_unit", "dirs": meta["dirs"], "yaw0": meta["yaw0"],
              "pitch": meta["pitch"], "teams": sorted({c["team"] for c in clips.values()}),
              "clips": sorted({c["clip"] for c in clips.values()}),
              "key_format": f"{name}_<team>_<clip>_d<dir>[_<frame>]",
              "note": "direction k = camera yaw 45 + 45*k deg (counter-clockwise from above); "
                      "d0 matches the single facing the existing 0 A.D. units were baked at"}
    manifest[name] = header
    manifest2x[name] = header
    for path, m in ((os.path.join(sprites, "manifest_snippet.json"), manifest),
                    (os.path.join(sprites2x, "manifest_snippet.json"), manifest2x)):
        with open(path, "w") as fh:
            json.dump(m, fh, indent=1, sort_keys=True)
            fh.write("\n")

    # ---- preview strips: each team, each clip: row = direction, column = frame (shown 3x nearest)
    prev_dir = os.path.join(a.out, "previews")
    os.makedirs(prev_dir, exist_ok=True)
    teams = sorted({c["team"] for c in clips.values()})
    clipnames = sorted({c["clip"] for c in clips.values()})
    z = 3
    for team in teams:
        for clip in clipnames:
            keys = sorted([k for k, c in clips.items() if c["team"] == team and c["clip"] == clip],
                          key=lambda k: clips[k]["dir"])
            if not keys:
                continue
            nf = max(len(clips[k]["files"]) for k in keys)
            W, H = size * z * nf + 60, size * z * len(keys) + 24
            sheet = Image.new("RGBA", (W, H), (96, 118, 76, 255))
            d = ImageDraw.Draw(sheet)
            d.text((6, 4), f"{name} {team} {clip}: rows = direction d0..d{len(keys)-1}, columns = frames; shown {z}x", fill=(255, 255, 255))
            for r, k in enumerate(keys):
                d.text((6, 24 + r * size * z + 4), f"d{clips[k]['dir']}", fill=(255, 255, 255))
                for cidx, (_, fn) in enumerate(sorted(clips[k]["files"])):
                    im = Image.open(os.path.join(sprites, fn)).convert("RGBA")
                    im = im.resize((size * z, size * z), Image.NEAREST)
                    sheet.alpha_composite(im, (60 + cidx * size * z, 24 + r * size * z))
            out = os.path.join(prev_dir, f"sprites_{team}_{clip}.png")
            sheet.save(out)
            print("preview", out)
    print(f"wrote {len(manifest)} manifest entries, {len(meta['frames'])} sprites -> {sprites}")


if __name__ == "__main__":
    main()
