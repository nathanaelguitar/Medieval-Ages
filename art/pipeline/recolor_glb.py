#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Recolour one hue band of a GLB's embedded base-colour texture and write a new GLB (needs
numpy + Pillow; run in the Spark's ~/mp venv or any python with both).

    python3 art/pipeline/recolor_glb.py --in art/models/man_at_arms_v2/man_at_arms_blue.glb \\
        --out art/models/man_at_arms_v3/man_at_arms_blue.glb \\
        --hue 195,265 --target-hue 222 --sat-min 0.72 --val-mul 2.4 --val-max 0.6 \\
        --preview art/out/man_at_arms_v3/previews/blue_texture_recolor.png

Why: TRELLIS.2 painted the blue team's tabard a dark navy (V ~0.2); under the bake's warm sun it
reads maroon next to the leather straps. The mask is soft: a ramp over saturation
(``--mask-sat lo,hi``) so the blue-grey mail and steel (S < lo) are untouched and the cloth
(S ~0.65) is fully recoloured; the hue window is likewise feathered by 10 degrees. Inside the
mask the hue is moved to ``--target-hue``, saturation raised to at least ``--sat-min`` and value
multiplied by ``--val-mul`` (clamped at ``--val-max``), all blended by the mask weight. The
metallic-roughness map, geometry and every other GLB chunk are copied unchanged; only the image
bufferView is replaced (the BIN chunk is rebuilt with the offsets updated).
"""
import argparse
import io
import json
import os
import struct

import numpy as np
from PIL import Image


def read_glb(path):
    with open(path, "rb") as fh:
        data = fh.read()
    magic, version, length = struct.unpack_from("<4sII", data, 0)
    assert magic == b"glTF", path
    off, js, binchunk = 12, None, None
    while off + 8 <= min(length, len(data)):
        clen, ctype = struct.unpack_from("<I4s", data, off)
        chunk = data[off + 8: off + 8 + clen]
        if ctype == b"JSON":
            js = json.loads(chunk.decode("utf-8"))
        elif ctype == b"BIN\x00":
            binchunk = chunk
        off += 8 + clen
    return js, binchunk


def write_glb(path, js, binchunk):
    jbytes = json.dumps(js, separators=(",", ":")).encode("utf-8")
    jbytes += b" " * ((4 - len(jbytes) % 4) % 4)
    bpad = b"\x00" * ((4 - len(binchunk) % 4) % 4)
    bbytes = binchunk + bpad
    total = 12 + 8 + len(jbytes) + 8 + len(bbytes)
    with open(path, "wb") as fh:
        fh.write(struct.pack("<4sII", b"glTF", 2, total))
        fh.write(struct.pack("<I4s", len(jbytes), b"JSON")); fh.write(jbytes)
        fh.write(struct.pack("<I4s", len(bbytes), b"BIN\x00")); fh.write(bbytes)


def replace_bufferview(js, binchunk, bv_index, new_bytes):
    """Rebuild the BIN chunk with bufferView bv_index holding new_bytes (4-byte aligned views)."""
    views = js["bufferViews"]
    out, cursor = bytearray(), 0
    for i, bv in enumerate(views):
        if i == bv_index:
            payload = new_bytes
        else:
            o = bv.get("byteOffset", 0)
            payload = binchunk[o: o + bv["byteLength"]]
        pad = (4 - cursor % 4) % 4
        out += b"\x00" * pad
        cursor += pad
        bv["byteOffset"] = cursor
        bv["byteLength"] = len(payload)
        out += payload
        cursor += len(payload)
    js["buffers"][0]["byteLength"] = len(out)
    return bytes(out)


def smoothstep(lo, hi, x):
    t = np.clip((x - lo) / max(hi - lo, 1e-6), 0, 1)
    return t * t * (3 - 2 * t)


def recolor(im, hue_lo, hue_hi, target_hue, sat_min, val_mul, val_max, mask_sat, feather=10.0):
    rgb = np.asarray(im.convert("RGB"), dtype=np.float32) / 255.0
    hsv = np.asarray(im.convert("RGB").convert("HSV"), dtype=np.float32)
    H, S, V = hsv[..., 0] * 360 / 255, hsv[..., 1] / 255, hsv[..., 2] / 255
    w = smoothstep(mask_sat[0], mask_sat[1], S)
    w *= smoothstep(hue_lo - feather, hue_lo, H) * (1 - smoothstep(hue_hi, hue_hi + feather, H))
    H2 = np.where(w > 0, target_hue, H)
    S2 = np.maximum(S, sat_min)
    V2 = np.minimum(V * val_mul, val_max)
    Hn = H * (1 - w) + H2 * w
    Sn = S * (1 - w) + S2 * w
    Vn = V * (1 - w) + V2 * w
    hsv2 = np.stack([Hn * 255 / 360, Sn * 255, Vn * 255], axis=-1)
    out = Image.fromarray(np.clip(hsv2 + 0.5, 0, 255).astype(np.uint8), "HSV").convert("RGB")
    return out, w


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--hue", default="195,265", help="hue band to recolour, degrees")
    ap.add_argument("--target-hue", type=float, default=222.0)
    ap.add_argument("--sat-min", type=float, default=0.72)
    ap.add_argument("--val-mul", type=float, default=2.4)
    ap.add_argument("--val-max", type=float, default=0.6)
    ap.add_argument("--mask-sat", default="0.3,0.5", help="saturation ramp lo,hi for the mask weight")
    ap.add_argument("--preview", help="PNG: before / after / mask at 768px")
    a = ap.parse_args()
    hue_lo, hue_hi = (float(x) for x in a.hue.split(","))
    mask_sat = tuple(float(x) for x in a.mask_sat.split(","))

    js, binchunk = read_glb(a.inp)
    mat = js["materials"][0]
    tex = js["textures"][mat["pbrMetallicRoughness"]["baseColorTexture"]["index"]]
    img = js["images"][tex["source"]]
    bv_i = img["bufferView"]
    bv = js["bufferViews"][bv_i]
    o = bv.get("byteOffset", 0)
    im = Image.open(io.BytesIO(binchunk[o: o + bv["byteLength"]]))
    print(f"base colour image {im.size} {img.get('mimeType')} in bufferView {bv_i}")
    out, w = recolor(im, hue_lo, hue_hi, a.target_hue, a.sat_min, a.val_mul, a.val_max, mask_sat)
    print(f"mask covers {w.mean()*100:.2f}% of texels (fully: {(w > 0.99).mean()*100:.2f}%)")
    buf = io.BytesIO()
    if "jpeg" in img.get("mimeType", ""):
        out.save(buf, "JPEG", quality=95)
    else:
        out.save(buf, "PNG", optimize=True)
    binchunk = replace_bufferview(js, binchunk, bv_i, buf.getvalue())
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    write_glb(a.out, js, binchunk)
    print(f"wrote {a.out} ({os.path.getsize(a.out)/1e6:.1f} MB)")
    if a.preview:
        os.makedirs(os.path.dirname(os.path.abspath(a.preview)), exist_ok=True)
        s = 768
        sheet = Image.new("RGB", (3 * s, s))
        sheet.paste(im.convert("RGB").resize((s, s)), (0, 0))
        sheet.paste(out.resize((s, s)), (s, 0))
        sheet.paste(Image.fromarray((w * 255).astype(np.uint8)).convert("RGB").resize((s, s)), (2 * s, 0))
        sheet.save(a.preview)
        print("preview", a.preview)


if __name__ == "__main__":
    main()
