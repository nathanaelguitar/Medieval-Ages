#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Turn single-building reference renders into game building sprites, without a 3D rebuild.

Input: one 1024x1024 PNG per building in ``art/source/buildings/gen/`` showing ONE building on a
square patch of packed earth (its footprint) on a flat grey studio background, seen from roughly
the game's camera (about 30-35 deg elevation, 45 deg yaw at a corner). Buildings never rotate in
the game, so the image can be used as the sprite directly once its footprint is put on the grid.

Stages (``--stage all`` runs them in order; each is idempotent):

  matte    scp the sources to the Spark, cut the grey background with BiRefNet (MIT weights,
           rembg ``birefnet-general`` in ~/hunyuan3d/.venv, niced; vLLM shares the box) and copy the
           RGBA results back to ``art/out/buildings/matte/``. Skips mattes that already exist.
  corners  find the earth patch's ground square in every matte: per column, the lowest opaque pixel
           gives a V-shaped bottom profile; a RANSAC line per side gives the front-left and
           front-right edges, their intersection is the front corner, and each edge's far end
           (where the profile leaves the line) is the left/right corner. The occluded back corner is
           left + right - front. Everything is written to ``art/out/buildings/corners.json`` and
           drawn on ``previews/corners.png`` for checking; put ``"L"``, ``"F"``, ``"R"`` (and
           optionally ``"B"``) under ``"manual"`` in that JSON to override a detection and rerun.
  segment  ground masks with SAM (facebook/sam-vit-huge, Apache-2.0; transformers in the same Spark
           venv): point prompts are derived from the corners (dirt points just inside the three
           visible corners and the two front edges, building points on the silhouette), prompted
           once for the building and once, labels swapped, for the earth patch. The three
           candidates of each are kept in ``art/out/buildings/masks/`` and the best one that
           contains none of the opposite points is used. Entries with ``"no_dirt": true`` in
           corners.json (TC, house_c: walls fill the footprint; farm) are skipped.
  build    warp each matte so the footprint lands on an ideal 2:1 diamond, feather the earth
           patch, write the sprites (@1x: 96 px per tile, @2x: 192), the manifest snippets, the
           mirrored wall variants, the per-sprite previews and the mock village.

The warp. A true homography is determined by the four ground corners, but only three are seen
(the back one is behind the building), so the fit is affine. The unconstrained affine (exact on
L, F, R) maps source verticals to a slightly leaning direction whenever the source yaw is not
exactly 45 deg (the left corner sits lower than the right); on a tall tower that lean is visible.
So the warp used is the *vertical-preserving* affine: x' = a*x + c, y' = d*x + e*y + f, solved by
least squares over the four corners. It is exact in y and leaves at most a couple of px of x
residual on the front corner; the lean the unconstrained fit would have had is reported per
building. A source elevation above 30 deg makes the fit squash the building (the ground diamond
is flattened to 2:1 and the building with it); ``ysq_exact`` printed per building is that
vertical factor. By default (``"warp": "auto"``) the exact fit is used when ysq is within
0.8..1.25, otherwise ``blend``: the vertical factor is sqrt(ysq), so the building is squashed or
stretched half as much and its ground diamond overshoots the 2:1 tile by the other half (the
overshoot is mostly dirt, which the feather removes). ``"warp": "uniform"`` keeps the source aspect
entirely (for images whose base geometry is not consistent with their roof, e.g. house_c);
``"homography"`` (with a manual ``"B"``) is a 4-point perspective warp; ``"affine"`` forces the
exact ground fit (always used for the farm, which is flat).

Resampling is done on premultiplied float RGBA so no grey fringe is reintroduced; the warp runs
at >= source resolution and the two output sizes are Lanczos reductions of it.

Earth patch: the game draws its own ground tiles, so the outer band of the patch is feathered
(alpha ramps from 1 at 55% of the half-diagonal to 0 just past the patch edge). The ramp only
applies to pixels in the SAM ground mask, so walls, posts and props standing on the patch edge
stay opaque; without a mask a Lab colour model of the dirt is the fallback (it cannot tell
sandstone from packed earth, which is why SAM is used). Wall segments feather only across the
wall (so the dirt strip runs on under a wall line) and the farm keeps its field edge (the field
is the footprint). Dirt outside the diamond (the slab's side lip, the overshoot of a blend warp)
is removed; nothing above the left/right corners or further than 25% outside is ever touched.

Walls: the game places 1x1 wall segments in lines along either tile axis. w2s(1,0) = (+TW2,+TH2),
so world +x runs upper-left -> lower-right on screen; a segment drawn along that direction is
``axis: "x"``. Its horizontal mirror (``*_b``) runs along world y. Mirroring also mirrors the
lighting (sun from the upper right on the mirrored copy).

Outputs (all under art/out/buildings/):
  sprites/med_*.png, sprites2x/med_*.png, manifest_snippet.json, manifest_snippet_2x.json
  previews/<name>.png (sprite on grass with its footprint diamond), previews/sheet.png,
  previews/village.png and previews/village_small.png (game projection, TW=64 and TW=44)

Per-building knobs in corners.json: ``manual`` corners, ``warp``, ``no_dirt``, ``fp_scale``
(declare a wider footprint so the game draws the building smaller in its tiles; 1.3 on the mill,
whose sails span twice its base), ``axis`` for walls (default "x").

Setup (Mac):  uv venv .bvenv -p 3.12 && uv pip install -p .bvenv/bin/python numpy pillow opencv-python-headless
Run:          .bvenv/bin/python art/pipeline/buildings_from_images.py --stage all
Add a building: drop bld_<x>.png into the source folder, add it to BUILDINGS, run ``--stage matte``
and ``--stage corners``, check previews/corners.png (fix corners.json and rerun corners if a patch
edge was missed), then ``--stage segment`` and ``--stage build``. ``--debug`` writes the ground
masks used (warped) to art/out/buildings/debug/.
"""
import argparse
import json
import math
import os
import subprocess
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = os.path.join(ROOT, "art", "source", "buildings", "gen")
OUT = os.path.join(ROOT, "art", "out", "buildings")
MATTE = os.path.join(OUT, "matte")
SPARK_DIR = "~/medieval/buildings"
SPARK_PY = "~/hunyuan3d/.venv/bin/python"

TILE1 = 96          # px per tile, @1x output (the game's TW is 64; it rescales by fp_w)
TILE2 = 192         # @2x
GAME_TW, GAME_TH = 64, 32

# name -> (source file, footprint tiles, kind)   kind: bld | wall | farm
BUILDINGS = {
    "med_tc": ("bld_tc", 3, "bld"),
    "med_house_a": ("bld_house", 2, "bld"),
    "med_house_b": ("bld_house_b", 2, "bld"),
    "med_house_c": ("bld_house_c", 2, "bld"),
    "med_barracks": ("bld_barracks", 3, "bld"),
    "med_tower": ("bld_tower", 2, "bld"),
    "med_mill": ("bld_mill", 2, "bld"),
    "med_woodyard": ("bld_woodyard", 2, "bld"),
    "med_mine": ("bld_mine", 2, "bld"),
    "med_market": ("bld_market", 2, "bld"),
    "med_farm": ("bld_farm", 2, "farm"),
    "med_palisade": ("bld_palisade", 1, "wall"),
    "med_stonewall": ("bld_stonewall", 1, "wall"),
    "med_gate": ("bld_gate", 1, "wall"),
}

FEATHER_START = 0.55     # alpha ramp starts here (fraction of the half-diagonal) ...
FEATHER_END = 1.02       # ... and reaches 0 here (just past the edge, to kill the slab lip)


# ----------------------------------------------------------------------------- matte (Spark)
def stage_matte(names, force=False):
    todo = [n for n in names if force or not os.path.exists(os.path.join(MATTE, n + ".png"))]
    if not todo:
        print("matte: nothing to do")
        return
    os.makedirs(MATTE, exist_ok=True)
    run = lambda *c: subprocess.run(c, check=True)
    run("ssh", "spark", f"mkdir -p {SPARK_DIR}/gen {SPARK_DIR}/matte")
    run("scp", "-q", *[os.path.join(SRC, n + ".png") for n in todo], f"spark:{SPARK_DIR}/gen/")
    script = r'''
import sys, os, time
from PIL import Image
from rembg import new_session, remove
s = new_session("birefnet-general")
d = os.path.expanduser("%s")
for n in sys.argv[1:]:
    t = time.time()
    im = Image.open(f"{d}/gen/{n}.png").convert("RGB")
    remove(im, session=s, alpha_matting=False, post_process_mask=False).save(f"{d}/matte/{n}.png")
    print(n, f"{time.time()-t:.1f}s", flush=True)
''' % SPARK_DIR
    subprocess.run(["ssh", "spark", f"cat > {SPARK_DIR}/matte_job.py"], input=script.encode(), check=True)
    run("ssh", "spark", f"cd {SPARK_DIR} && nice -n 10 {SPARK_PY} matte_job.py " + " ".join(todo))
    run("scp", "-q", *[f"spark:{SPARK_DIR}/matte/{n}.png" for n in todo], MATTE + "/")
    print("matte:", ", ".join(todo))


# ----------------------------------------------------------------------------- segment (Spark)
SAM_MODEL = "facebook/sam-vit-huge"      # Apache-2.0

def sam_prompts(rgba, c):
    """Point prompts for SAM: negatives on the dirt just inside the three visible patch corners
    and the two front edges, positives on the building (silhouette top, upper-body centroid,
    mid-height extremes)."""
    a = rgba[..., 3] > 0.5
    H, W = a.shape
    ctr = ((c["L"][0] + c["R"][0]) / 2, (c["L"][1] + c["R"][1]) / 2)
    neg = []
    for p in (c["L"], c["F"], c["R"],
              ((c["L"][0] + c["F"][0]) / 2, (c["L"][1] + c["F"][1]) / 2),
              ((c["F"][0] + c["R"][0]) / 2, (c["F"][1] + c["R"][1]) / 2)):
        q = (p[0] + 0.1 * (ctr[0] - p[0]), p[1] + 0.1 * (ctr[1] - p[1]))
        xi, yi = int(round(q[0])), int(round(q[1]))
        if 0 <= xi < W and 0 <= yi < H and a[yi, xi]:
            neg.append([xi, yi])
    ys, xs = np.where(a)
    y_top, y_bot = ys.min(), ys.max()
    x_top = int(np.round(np.mean(xs[ys <= y_top + 3])))
    pos = [[x_top, int(y_top + 0.05 * (y_bot - y_top))]]
    band = a[y_top:int(y_top + 0.55 * (y_bot - y_top))]
    by, bx = np.where(band)
    cy, cx = int(by.mean()) + y_top, int(bx.mean())
    if a[cy, cx]:
        pos.append([cx, cy])
    ym = int(y_top + 0.45 * (y_bot - y_top))
    row = np.where(a[ym])[0]
    if len(row) > 20:
        pos.append([int(row.min() + 0.12 * (row.max() - row.min())), ym])
        pos.append([int(row.max() - 0.12 * (row.max() - row.min())), ym])
    return pos, neg


def stage_segment(names, force=False):
    """Building-vs-dirt masks with SAM on the Spark. `masks/<name>.png`: R,G,B = the three
    candidate masks prompted for the building, `masks/<name>_dirt.png`: the same prompted for the
    earth patch (labels swapped), `masks/<name>.json`: predicted IoUs and the prompts."""
    data = json.load(open(os.path.join(OUT, "corners.json")))
    mdir = os.path.join(OUT, "masks")
    os.makedirs(mdir, exist_ok=True)
    jobs = {}
    for n in names:
        if data[n].get("no_dirt") or (not force and os.path.exists(os.path.join(mdir, n + ".png"))):
            continue
        pos, neg = sam_prompts(clean_alpha(load_matte(n)), corners_of(data[n]))
        jobs[n] = {"pos": [[int(x), int(y)] for x, y in pos], "neg": [[int(x), int(y)] for x, y in neg]}
    if not jobs:
        print("segment: nothing to do")
        return
    script = r'''
import sys, os, json, time
import numpy as np, torch
from PIL import Image
from transformers import SamModel, SamProcessor
d = os.path.expanduser("%s")
jobs = json.load(open(f"{d}/sam_jobs.json"))
model = SamModel.from_pretrained("%s").to("cuda").eval()
proc = SamProcessor.from_pretrained("%s")
os.makedirs(f"{d}/masks", exist_ok=True)
for n, j in jobs.items():
    t = time.time()
    im = Image.open(f"{d}/gen/{n}.png").convert("RGB")
    res = dict(j)
    for tag, P, N in (("", j["pos"], j["neg"]), ("_dirt", j["neg"], j["pos"])):   # building, then the patch
        pts = P + N; lab = [1] * len(P) + [0] * len(N)
        inp = proc(im, input_points=[[pts]], input_labels=[[lab]], return_tensors="pt").to("cuda")
        with torch.no_grad():
            out = model(**inp, multimask_output=True)
        m = proc.image_processor.post_process_masks(out.pred_masks.cpu(), inp["original_sizes"].cpu(), inp["reshaped_input_sizes"].cpu())[0][0]
        arr = np.stack([m[i].numpy().astype(np.uint8) * 255 for i in range(3)], axis=2)
        Image.fromarray(arr).save(f"{d}/masks/{n}{tag}.png")
        res["iou" + tag] = out.iou_scores[0, 0].tolist()
    json.dump(res, open(f"{d}/masks/{n}.json", "w"))
    print(n, f"{time.time()-t:.1f}s", res["iou"], res["iou_dirt"], flush=True)
''' % (SPARK_DIR, SAM_MODEL, SAM_MODEL)
    subprocess.run(["ssh", "spark", f"mkdir -p {SPARK_DIR}/gen && cat > {SPARK_DIR}/sam_jobs.json"], input=json.dumps(jobs).encode(), check=True)
    subprocess.run(["ssh", "spark", f"cat > {SPARK_DIR}/sam_job.py"], input=script.encode(), check=True)
    subprocess.run(["scp", "-q", *[os.path.join(SRC, n + ".png") for n in jobs], f"spark:{SPARK_DIR}/gen/"], check=True)
    subprocess.run(["ssh", "spark", f"cd {SPARK_DIR} && nice -n 10 {SPARK_PY} sam_job.py"], check=True)
    subprocess.run(["scp", "-q", *[f"spark:{SPARK_DIR}/masks/{n}{x}" for n in jobs for x in (".png", "_dirt.png", ".json")], mdir + "/"], check=True)


def pick_mask(masks, iou, must_exclude):
    """Best SAM candidate (highest predicted IoU) that contains none of `must_exclude` points."""
    best, best_iou = None, -1
    for i in range(3):
        m = masks[..., i] > 127
        if any(m[max(0, y - 2):y + 3, max(0, x - 2):x + 3].any() for x, y in must_exclude):
            continue
        if iou[i] > best_iou:
            best, best_iou = m, iou[i]
    return best


def load_dirt_mask(src_name):
    """Dirt-patch mask (bool, source pixels) from the SAM stage, or None."""
    mdir = os.path.join(OUT, "masks")
    jp = os.path.join(mdir, src_name + ".json")
    if not os.path.exists(jp):
        return None
    j = json.load(open(jp))
    dirt = pick_mask(np.asarray(Image.open(os.path.join(mdir, src_name + "_dirt.png"))), j["iou_dirt"], j["pos"])
    bld = pick_mask(np.asarray(Image.open(os.path.join(mdir, src_name + ".png"))), j["iou"], j["neg"])
    if dirt is None:
        return None
    if bld is not None:
        dirt = dirt & ~bld
    return dirt


# ----------------------------------------------------------------------------- corners
def load_matte(src_name):
    im = Image.open(os.path.join(MATTE, src_name + ".png")).convert("RGBA")
    return np.asarray(im).astype(np.float32) / 255.0


def clean_alpha(rgba, min_frac=0.002):
    """Drop stray specks: keep connected components that hold >= min_frac of the opaque area."""
    a = (rgba[..., 3] > 0.5).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(a, connectivity=8)
    total = a.sum()
    keep = np.zeros(n, bool)
    for i in range(1, n):
        keep[i] = stats[i, cv2.CC_STAT_AREA] >= min_frac * total
    mask = keep[lab]
    mask = cv2.dilate(mask.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    out = rgba.copy()
    out[~mask, 3] = 0
    return out


def ransac_line(xs, ys, tol=3.0, iters=400, seed=0):
    rng = np.random.default_rng(seed)
    best, best_n = None, -1
    n = len(xs)
    for _ in range(iters):
        i, j = rng.choice(n, 2, replace=False)
        if xs[i] == xs[j]:
            continue
        m = (ys[j] - ys[i]) / (xs[j] - xs[i])
        b = ys[i] - m * xs[i]
        inl = np.abs(ys - (m * xs + b)) < tol
        k = inl.sum()
        if k > best_n:
            best_n, best = k, inl
    m, b = np.polyfit(xs[best], ys[best], 1)
    return m, b


def detect_corners(rgba, tol=4.0, gap=8):
    """Front-left / front / front-right corners of the ground patch from the alpha's bottom profile."""
    a = rgba[..., 3] > 0.5
    H, W = a.shape
    has = a.any(axis=0)
    ybot = np.where(has, H - 1 - np.argmax(a[::-1, :], axis=0), -1).astype(np.float64)
    xs = np.where(has)[0]
    fx = int(np.round(np.mean(xs[ybot[xs] >= ybot.max() - 1])))     # lowest point(s) -> front x
    left = xs[(xs < fx) & (xs > fx - (fx - xs.min()) * 0.95)]
    right = xs[(xs > fx) & (xs < fx + (xs.max() - fx) * 0.95)]
    mL, bL = ransac_line(left.astype(float), ybot[left], tol)
    mR, bR = ransac_line(right.astype(float), ybot[right], tol)
    Fx = (bR - bL) / (mL - mR)
    F = (Fx, mL * Fx + bL)

    def walk(m, b, step):
        x, last, miss = int(round(Fx)), int(round(Fx)), 0
        while 0 <= x < W:
            if has[x] and abs(ybot[x] - (m * x + b)) < tol:
                last, miss = x, 0
            else:
                miss += 1
                if miss > gap:
                    break
            x += step
        return (float(last), m * last + b)
    L = walk(mL, bL, -1)
    R = walk(mR, bR, +1)
    B = (L[0] + R[0] - F[0], L[1] + R[1] - F[1])
    return {"L": L, "F": F, "R": R, "B": B}


def corners_of(entry):
    """Effective corners: manual overrides on top of the detection."""
    c = dict(entry["auto"])
    c.update(entry.get("manual", {}))
    if "B" not in entry.get("manual", {}):
        c["B"] = (c["L"][0] + c["R"][0] - c["F"][0], c["L"][1] + c["R"][1] - c["F"][1])
    return {k: (float(v[0]), float(v[1])) for k, v in c.items()}


def stage_corners(names):
    path = os.path.join(OUT, "corners.json")
    data = json.load(open(path)) if os.path.exists(path) else {}
    for n in names:
        rgba = clean_alpha(load_matte(n))
        c = detect_corners(rgba)
        e = data.setdefault(n, {})
        e["auto"] = {k: [round(v[0], 1), round(v[1], 1)] for k, v in c.items()}
        border = float(rgba[0, :, 3].max()), float(rgba[-1, :, 3].max()), float(rgba[:, 0, 3].max()), float(rgba[:, -1, 3].max())
        e["border_alpha"] = [round(b, 2) for b in border]   # top, bottom, left, right: >0 means clipped
        eff = corners_of(e)
        w = eff["R"][0] - eff["L"][0]
        h = 2 * (eff["F"][1] - (eff["L"][1] + eff["R"][1]) / 2)
        print(f"{n:14s} L={eff['L'][0]:.0f},{eff['L'][1]:.0f} F={eff['F'][0]:.0f},{eff['F'][1]:.0f} "
              f"R={eff['R'][0]:.0f},{eff['R'][1]:.0f} B={eff['B'][0]:.0f},{eff['B'][1]:.0f} "
              f"aspect {w / h:.2f}  border {e['border_alpha']}" + ("  (manual)" if e.get("manual") else ""))
    json.dump(data, open(path, "w"), indent=1)
    draw_corner_sheet(data, names)


def draw_corner_sheet(data, names):
    os.makedirs(os.path.join(OUT, "previews"), exist_ok=True)
    cell, cols = 400, 5
    rows = (len(names) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * cell), (30, 30, 30))
    for i, n in enumerate(names):
        im = Image.open(os.path.join(MATTE, n + ".png")).convert("RGBA")
        bg = Image.new("RGBA", im.size, (50, 140, 60, 255))
        bg.alpha_composite(im)
        d = ImageDraw.Draw(bg)
        c = corners_of(data[n])
        for key, col in (("auto", (255, 60, 60)), ("manual", (60, 120, 255))):
            if key in data[n]:
                cc = corners_of({"auto": data[n]["auto"], "manual": data[n].get(key, {})}) if key == "manual" else corners_of({"auto": data[n]["auto"]})
                d.polygon([cc["L"], cc["F"], cc["R"], cc["B"]], outline=col, width=3)
                for k in "LFRB":
                    x, y = cc[k]
                    d.ellipse([x - 6, y - 6, x + 6, y + 6], outline=col, width=3)
        d.text((10, 10), n, fill=(255, 255, 255))
        sheet.paste(bg.convert("RGB").resize((cell - 8, cell - 8), Image.LANCZOS), ((i % cols) * cell + 4, (i // cols) * cell + 4))
    sheet.save(os.path.join(OUT, "previews", "corners.png"))


# ----------------------------------------------------------------------------- warp
def fit_warp(src, dst, mode):
    """src/dst: dict L,F,R,B -> (x,y). Returns (2x3 or 3x3 matrix, info)."""
    keys = ["L", "F", "R", "B"]
    S = np.array([src[k] for k in keys], float)
    D = np.array([dst[k] for k in keys], float)
    A_free = cv2.getAffineTransform(S[:3].astype(np.float32), D[:3].astype(np.float32))
    lean = math.degrees(math.atan2(A_free[0, 1], A_free[1, 1]))
    info = {"lean_unconstrained_deg": round(lean, 2)}
    if mode == "homography":
        M = cv2.getPerspectiveTransform(S.astype(np.float32), D.astype(np.float32))
        info["warp"] = "homography"
        return M, info
    # vertical-preserving affine: x' = a x + c ; y' = d x + e y + f
    Ax = np.c_[S[:, 0], np.ones(4)]
    a, c = np.linalg.lstsq(Ax, D[:, 0], rcond=None)[0]
    Ay = np.c_[S[:, 0], S[:, 1], np.ones(4)]
    d, e, f = np.linalg.lstsq(Ay, D[:, 1], rcond=None)[0]
    ysq = e / a               # vertical factor the exact ground fit applies to the building
    if mode == "auto":
        mode = "affine" if 0.8 <= ysq <= 1.25 else "blend"
    if mode in ("uniform", "blend"):
        # uniform keeps the source aspect (vertical scale = horizontal scale); blend splits the
        # difference, so the building is squashed/stretched half as much and its ground
        # diamond overshoots the 2:1 tile by half as much. d, f are refitted with e fixed.
        e = a if mode == "uniform" else a * math.sqrt(ysq)
        d, f = np.linalg.lstsq(np.c_[S[:, 0], np.ones(4)], D[:, 1] - e * S[:, 1], rcond=None)[0]
    M = np.array([[a, 0, c], [d, e, f]], float)
    P = (M @ np.c_[S, np.ones(4)].T).T
    info.update({"warp": {"affine": "affine_vertical", "uniform": "affine_uniform", "blend": "affine_blend"}[mode],
                 "xscale": round(a, 4), "ysq_exact": round(ysq, 3), "ysq_used": round(e / a, 3),
                 "max_corner_residual_px": round(float(np.abs(P - D).max()), 2)})
    return M, info


def apply_warp(img, M, size):
    flags = cv2.INTER_CUBIC
    if M.shape[0] == 3:
        return cv2.warpPerspective(img, M, size, flags=flags, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    return cv2.warpAffine(img, M, size, flags=flags, borderMode=cv2.BORDER_CONSTANT, borderValue=0)


def warp_point(M, p):
    v = np.array([p[0], p[1], 1.0])
    if M.shape[0] == 3:
        w = M @ v
        return (w[0] / w[2], w[1] / w[2])
    w = M @ v
    return (w[0], w[1])


# ----------------------------------------------------------------------------- earth feather
def earth_likelihood(prgb, alpha, s, t, tile_px):
    """Per-pixel likelihood [0,1] that a pixel is the packed-earth patch, from a Lab colour model
    sampled in the diamond's front region (near the front corner, surely ground)."""
    rgb = prgb / np.maximum(alpha, 1e-4)[..., None]
    lab = cv2.cvtColor(np.clip(rgb, 0, 1).astype(np.float32), cv2.COLOR_RGB2LAB)
    d = np.abs(s) + np.abs(t)
    samp = (alpha > 0.9) & (d > 0.55) & (d < 0.95) & (t > 0.25)
    if samp.sum() < 200:
        samp = (alpha > 0.9) & (d < 0.98) & (t > 0.4)
    ref = lab[samp]
    med = np.median(ref, axis=0)
    mad = np.median(np.abs(ref - med), axis=0) * 1.4826 + 1e-3
    sig = np.maximum(mad * 1.5, [6.0, 2.5, 3.0])
    sig[0] = max(sig[0], 14.0)                           # shadowed dirt is darker, same chroma
    z2 = (((lab - med) / sig) ** 2).sum(axis=2)
    e = np.exp(-0.5 * z2) * (alpha > 0.01)
    # region-level decision: pebbly dirt is a dense speckle of matches, a wall a sparse one, so a
    # blur over ~1.5% of a tile followed by a contrast curve makes dirt solid and walls ~0
    e = cv2.GaussianBlur(e.astype(np.float32), (0, 0), max(2.0, 0.015 * tile_px))
    e = np.clip((e - 0.18) / 0.45, 0, 1)
    e = e * e * (3 - 2 * e)
    return e, med


def feather_mask(s, t, kind, axis="x"):
    """Alpha multiplier for ground pixels, in diamond coordinates (|s|+|t|<=1 inside)."""
    if kind == "farm":
        d = np.abs(s) + np.abs(t)
        return np.clip((1.015 - d) / 0.03, 0, 1)
    if kind == "wall":
        v = t - s if axis == "x" else t + s        # across-the-wall coordinate, |v|<=1 inside
        u = t + s if axis == "x" else t - s
        m = np.clip((FEATHER_END - np.abs(v)) / (FEATHER_END - FEATHER_START), 0, 1)
        return m * np.clip((1.03 - np.abs(u)) / 0.04, 0, 1)   # hard-ish cut at the shared edge
    d = np.abs(s) + np.abs(t)
    return np.clip((FEATHER_END - d) / (FEATHER_END - FEATHER_START), 0, 1)


# ----------------------------------------------------------------------------- build
def premul(rgba):
    out = rgba.copy()
    out[..., :3] *= out[..., 3:4]
    return out


def unpremul_u8(prgba):
    a = prgba[..., 3:4]
    rgb = prgba[..., :3] / np.maximum(a, 1e-4)
    out = np.concatenate([np.clip(rgb, 0, 1), np.clip(a, 0, 1)], axis=2)
    return (out * 255 + 0.5).astype(np.uint8)


def resize_premul(img, scale):
    """Lanczos resize of a float premultiplied RGBA array by `scale` (<=1 expected)."""
    h, w = img.shape[:2]
    nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    chans = [np.asarray(Image.fromarray(img[..., i], mode="F").resize((nw, nh), Image.LANCZOS)) for i in range(4)]
    return np.clip(np.stack(chans, axis=2), 0, 1)


def build_one(name, src_name, n_tiles, kind, entry, out1, out2, debug_dir):
    rgba = clean_alpha(load_matte(src_name))
    c = corners_of(entry)
    mode = entry.get("warp", "affine" if kind == "farm" else "auto")   # a field is flat: exact ground fit
    src_w = c["R"][0] - c["L"][0]
    Tw = max(TILE2, int(math.ceil(src_w / n_tiles)))           # work px per tile (no downsampling in the warp)
    W, Hd = n_tiles * Tw, n_tiles * Tw / 2.0
    dst0 = {"L": (-W / 2, 0), "F": (0, Hd / 2), "R": (W / 2, 0), "B": (0, -Hd / 2)}
    M, info = fit_warp(c, dst0, mode)
    # canvas: bbox of the warped alpha bbox, plus margin
    a = rgba[..., 3] > 0.002
    ys, xs = np.where(a)
    corners = [(xs.min(), ys.min()), (xs.max(), ys.min()), (xs.max(), ys.max()), (xs.min(), ys.max())]
    wp = np.array([warp_point(M, p) for p in corners])
    pad = 8
    x0, y0 = math.floor(wp[:, 0].min()) - pad, math.floor(wp[:, 1].min()) - pad
    x1, y1 = math.ceil(wp[:, 0].max()) + pad, math.ceil(wp[:, 1].max()) + pad
    T = np.array([[1, 0, -x0], [0, 1, -y0], [0, 0, 1]], float)
    M3 = np.vstack([M, [0, 0, 1]]) if M.shape[0] == 2 else M
    Mt = T @ M3
    Mt = Mt if mode == "homography" else Mt[:2]
    cw, ch = x1 - x0, y1 - y0
    cx, cy = -x0, -y0
    warped = apply_warp(premul(rgba), Mt, (cw, ch))
    warped = np.clip(warped, 0, 1)
    warped[..., :3] = np.minimum(warped[..., :3], warped[..., 3:4])
    alpha = warped[..., 3]
    # diamond coordinates
    yy, xx = np.mgrid[0:ch, 0:cw].astype(np.float32)
    s = (xx + 0.5 - cx) / (W / 2)
    t = (yy + 0.5 - cy) / (Hd / 2)
    dirt = None if entry.get("no_dirt") else load_dirt_mask(src_name)
    if dirt is not None:                               # SAM ground mask, warped like the image
        dm = apply_warp(dirt.astype(np.float32), Mt, (cw, ch))
        e = cv2.GaussianBlur(np.clip(dm, 0, 1), (0, 0), max(1.5, 0.006 * Tw)) * (alpha > 0.01)
        earth_lab = None
    elif entry.get("no_dirt"):
        e, earth_lab = np.zeros_like(alpha), None
    else:                                              # fallback: colour model
        e, earth_lab = earth_likelihood(warped[..., :3], alpha, s, t, Tw)
    axis = entry.get("axis", "x")
    m = feather_mask(s, t, kind, axis)
    mult = 1.0 - (1.0 - m) * e
    # Dirt can only lie on the footprint: the patch maps onto the diamond (plus the slab lip and,
    # for blend/uniform warps, a front overshoot). Everything well outside it, and anything above
    # the left/right corners, is building and is never touched, whatever its colour (thatch).
    d = np.abs(s) + np.abs(t)
    mult[(d > 1.0) & ((d > 1.25) | (t < -0.1))] = 1.0
    if kind == "farm":
        mult = m                                   # the field is the footprint: plain edge
    warped *= mult[..., None]
    if debug_dir:
        Image.fromarray((e * 255).astype(np.uint8)).save(os.path.join(debug_dir, f"{name}_earth.png"))
    # outputs
    f1, f2 = TILE1 / Tw, TILE2 / Tw
    im1 = resize_premul(warped, f1)
    im2 = resize_premul(warped, f2)
    a1 = im1[..., 3] > 0.5 / 255
    ys, xs = np.where(a1)
    bx0, by0 = max(0, xs.min() - 2), max(0, ys.min() - 2)
    bx1, by1 = min(im1.shape[1], xs.max() + 3), min(im1.shape[0], ys.max() + 3)
    crop1 = im1[by0:by1, bx0:bx1]
    crop2 = im2[2 * by0:2 * by1, 2 * bx0:2 * bx1]
    if crop2.shape[0] != 2 * crop1.shape[0] or crop2.shape[1] != 2 * crop1.shape[1]:
        pad2 = np.zeros((2 * crop1.shape[0], 2 * crop1.shape[1], 4), np.float32)
        pad2[:crop2.shape[0], :crop2.shape[1]] = crop2
        crop2 = pad2
    # fp_scale > 1 declares a footprint wider than the patch, so the game draws the building
    # smaller inside its tiles (the windmill's sails span twice its footprint)
    fp_cx, fp_cy, fp_w = cx * f1 - bx0, cy * f1 - by0, W * f1 * entry.get("fp_scale", 1.0)
    u1, u2 = unpremul_u8(crop1), unpremul_u8(crop2)
    fill = round(float((u1[..., 3] > 128).mean()), 4)
    ent = {"file": name + ".png", "w": int(u1.shape[1]), "h": int(u1.shape[0]), "fill": fill,
           "fp_w": round(fp_w, 2), "fp_cx": round(fp_cx, 2), "fp_cy": round(fp_cy, 2)}
    ent2 = dict(ent, w=2 * ent["w"], h=2 * ent["h"], fp_w=round(2 * fp_w, 2), fp_cx=round(2 * fp_cx, 2), fp_cy=round(2 * fp_cy, 2))
    if kind == "wall":
        ent["axis"] = ent2["axis"] = axis
    Image.fromarray(u1).save(os.path.join(out1, name + ".png"))
    Image.fromarray(u2).save(os.path.join(out2, name + ".png"))
    res = {name: (ent, ent2)}
    if kind == "wall":
        other = "y" if axis == "x" else "x"
        m1, m2 = np.ascontiguousarray(u1[:, ::-1]), np.ascontiguousarray(u2[:, ::-1])
        e1 = dict(ent, file=name + "_b.png", fp_cx=round(ent["w"] - fp_cx, 2), axis=other)
        e2 = dict(ent2, file=name + "_b.png", fp_cx=round(2 * (ent["w"] - fp_cx), 2), axis=other)
        Image.fromarray(m1).save(os.path.join(out1, name + "_b.png"))
        Image.fromarray(m2).save(os.path.join(out2, name + "_b.png"))
        res[name + "_b"] = (e1, e2)
    info.update({"work_px_per_tile": Tw, "src_fp_w_px": round(src_w, 1),
                 "ground": "sam" if dirt is not None else ("none" if entry.get("no_dirt") else "colour"),
                 "earth_lab": None if earth_lab is None else [round(float(v), 1) for v in earth_lab]})
    return res, info


# ----------------------------------------------------------------------------- previews
def grass(w, h, seed=1, tw=GAME_TW, th=GAME_TH):
    rng = np.random.default_rng(seed)
    base = np.array([86, 142, 58], np.float32)
    img = np.tile(base, (h, w, 1))
    noise = rng.normal(0, 4, (h // 4 + 1, w // 4 + 1, 1)).repeat(4, 0).repeat(4, 1)[:h, :w]
    img = np.clip(img + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(img).convert("RGBA")


def diamond_pts(cx, cy, w):
    return [(cx - w / 2, cy), (cx, cy + w / 4), (cx + w / 2, cy), (cx, cy - w / 4)]


def preview_sprite(name, ent, sprite_dir, prev_dir):
    im = Image.open(os.path.join(sprite_dir, ent["file"])).convert("RGBA")
    pad = 24
    bg = grass(im.width + 2 * pad, im.height + 2 * pad)
    bg.alpha_composite(im, (pad, pad))
    d = ImageDraw.Draw(bg)
    d.polygon(diamond_pts(ent["fp_cx"] + pad, ent["fp_cy"] + pad, ent["fp_w"]), outline=(255, 255, 0), width=1)
    d.text((4, 2), f"{name} {ent['w']}x{ent['h']} fp_w {ent['fp_w']}" + (f" axis {ent['axis']}" if "axis" in ent else ""), fill=(255, 255, 255))
    bg.save(os.path.join(prev_dir, name + ".png"))
    return bg


def draw_village(manifest, sprite_dir, path, tw=GAME_TW):
    """Mock village with the game's own placement arithmetic (drawBuilding): kk = s*TW/fp_w,
    sprite origin = tile-centre screen point minus (fp_cx, fp_cy)*kk."""
    th = tw / 2
    tw2, th2 = tw / 2, th / 2
    w2s = lambda x, y: ((x - y) * tw2, (x + y) * th2)
    layout = [  # (sprite, tx, ty, size)
        ("med_tc", 6, 6, 3),
        ("med_house_a", 2, 3, 2), ("med_house_b", 2, 6, 2), ("med_house_c", 2, 9, 2),
        ("med_barracks", 10, 2, 3), ("med_tower", 13, 6, 2), ("med_mill", 6, 11, 2),
        ("med_woodyard", 10, 10, 2), ("med_mine", 13, 10, 2), ("med_market", 6, 2, 2),
        ("med_farm", 10, 6, 2), ("med_farm", 10, 13, 2),
    ]
    for i in range(4):
        layout.append(("med_palisade", 1 + i, 13, 1))       # x-axis run
    layout.append(("med_gate", 5, 13, 1))
    for i in range(2):
        layout.append(("med_palisade", 6 + i, 13, 1))
    for i in range(3):
        layout.append(("med_stonewall_b", 16, 1 + i, 1))    # y-axis run (mirrored variant)
    layout.append(("med_gate_b", 16, 4, 1))
    for i in range(3):
        layout.append(("med_stonewall_b", 16, 5 + i, 1))
    for i in range(3):
        layout.append(("med_stonewall", 13 + i, 14, 1))
    N = 18
    pts = [w2s(0, 0), w2s(N, 0), w2s(N, N), w2s(0, N)]
    minx = min(p[0] for p in pts) - 40
    maxx = max(p[0] for p in pts) + 40
    maxy = max(p[1] for p in pts) + 40
    ox, oy = -minx, 120
    canvas = Image.new("RGBA", (int(maxx - minx), int(maxy + oy)), (40, 60, 90, 255))
    d = ImageDraw.Draw(canvas)
    rng = np.random.default_rng(3)
    for ty in range(N):
        for tx in range(N):
            g = int(rng.normal(0, 5))
            col = (86 + g, 142 + g, 58 + g, 255)
            pts = [w2s(tx, ty), w2s(tx + 1, ty), w2s(tx + 1, ty + 1), w2s(tx, ty + 1)]
            d.polygon([(x + ox, y + oy) for x, y in pts], fill=col, outline=(78 + g, 128 + g, 52 + g))
    cache = {}
    for key, tx, ty, s in sorted(layout, key=lambda b: (b[1] + b[3] + b[2] + b[3], b[1])):
        ent = manifest[key]
        if key not in cache:
            cache[key] = Image.open(os.path.join(sprite_dir, ent["file"])).convert("RGBA")
        im = cache[key]
        kk = s * tw / ent["fp_w"]
        ccx, ccy = w2s(tx + s / 2, ty + s / 2)
        dx, dy = ccx - ent["fp_cx"] * kk + ox, ccy - ent["fp_cy"] * kk + oy
        dw, dh = max(1, int(round(im.width * kk))), max(1, int(round(im.height * kk)))
        sc = im.resize((dw, dh), Image.LANCZOS)
        canvas.alpha_composite(sc, (int(round(dx)), int(round(dy))))
    d = ImageDraw.Draw(canvas)
    d.text((8, 8), f"mock village, TW={tw}: 2x2 house = {2 * tw}px wide footprint", fill=(255, 255, 255))
    canvas.convert("RGB").save(path)


def stage_build(names_filter=None, debug=False):
    data = json.load(open(os.path.join(OUT, "corners.json")))
    out1, out2 = os.path.join(OUT, "sprites"), os.path.join(OUT, "sprites2x")
    prev = os.path.join(OUT, "previews")
    dbg = os.path.join(OUT, "debug") if debug else None
    for p in (out1, out2, prev, dbg):
        if p:
            os.makedirs(p, exist_ok=True)
    man1, man2, infos = {}, {}, {}
    for name, (src_name, n, kind) in BUILDINGS.items():
        if names_filter and name not in names_filter:
            continue
        res, info = build_one(name, src_name, n, kind, data[src_name], out1, out2, dbg)
        infos[name] = info
        for k, (e1, e2) in res.items():
            man1[k], man2[k] = e1, e2
        print(f"{name:14s} {info}")
    json.dump(man1, open(os.path.join(OUT, "manifest_snippet.json"), "w"), indent=1, sort_keys=True)
    json.dump(man2, open(os.path.join(OUT, "manifest_snippet_2x.json"), "w"), indent=1, sort_keys=True)
    json.dump(infos, open(os.path.join(OUT, "build_info.json"), "w"), indent=1)
    # previews
    tiles = [preview_sprite(k, e, out1, prev) for k, e in man1.items()]
    cols = 5
    rows = [tiles[i:i + cols] for i in range(0, len(tiles), cols)]
    sheet_w = max(sum(t.width for t in r) + 8 * len(r) for r in rows)
    sheet_h = sum(max(t.height for t in r) + 8 for r in rows)
    sheet = Image.new("RGB", (sheet_w, sheet_h), (20, 20, 20))
    y = 4
    for r in rows:
        x = 4
        for t in r:
            sheet.paste(t.convert("RGB"), (x, y))
            x += t.width + 8
        y += max(t.height for t in r) + 8
    sheet.save(os.path.join(prev, "sheet.png"))
    draw_village(man1, out1, os.path.join(prev, "village.png"), tw=GAME_TW)
    draw_village(man1, out1, os.path.join(prev, "village_small.png"), tw=44)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", choices=["matte", "corners", "segment", "build", "all"], default="all")
    ap.add_argument("--only", nargs="*", help="sprite names (med_*) to build")
    ap.add_argument("--force", action="store_true", help="redo mattes / SAM masks that already exist")
    ap.add_argument("--debug", action="store_true", help="write the warped ground masks to art/out/buildings/debug/")
    a = ap.parse_args()
    src_names = sorted({v[0] for v in BUILDINGS.values()})
    if a.stage in ("matte", "all"):
        stage_matte(src_names, a.force)
    if a.stage in ("corners", "all"):
        stage_corners(src_names)
    if a.stage in ("segment", "all"):
        stage_segment(src_names, a.force)
    if a.stage in ("build", "all"):
        stage_build(a.only, a.debug)


if __name__ == "__main__":
    main()
