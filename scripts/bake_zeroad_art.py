#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Bake the bundled 0 A.D. meshes into isometric PNG sprites for the Pocket Empires canvas game.

0 A.D. is a 3D game: its art is COLLADA meshes plus textures, with no sprite sheets anywhere. The
canvas game needs flat images, so this renders the meshes offline from the same isometric angle the
game projects its world at, and writes PNGs plus a manifest the page reads.

Two things make this more than a naive mesh dump:

* **Actors, not meshes, carry the texture binding.** A 0 A.D. actor keeps its ``baseTex`` in a
  separate ``<group>`` from the ``<mesh>``, so pairing them requires a file-level fallback. It also
  composes buildings out of several ``<props>`` actors -- rendering only the top-level mesh gives a
  fragmented shell (a barracks with holes in it).
* **The up-axis is not consistent across this asset set.** Units are Z-up with the soles at z=0;
  the oak is Y-up with the roots near y=0. Assuming one axis globally tilts half the models.

Requires Pillow and the ``assimp`` CLI (``brew install assimp``). The output is committed, so the
build never runs this -- it exists so the sprites can be regenerated and reviewed.

Original artwork is CC BY-SA 3.0, (C) Wildfire Games; see ios/ZeroADArt/LICENSE.txt. These baked
sprites are modified (rasterised) derivatives and stay under the same licence.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ART = os.path.join(ROOT, "ios", "ZeroADArt")
MESH_ROOT = os.path.join(ART, "meshes")
ACTOR_ROOT = os.path.join(ART, "actors")
SKIN_ROOT = os.path.join(ART, "textures", "skins")
OUT_DIR = os.path.join(ROOT, "ios", "WebGame", "sprites")
CACHE_DIR = os.path.join(tempfile.gettempdir(), "zeroad_bake_cache")

# A ground decal is painted onto terrain by 0 A.D.; baked into a building sprite it would render as
# a floating stain. Destruction variants are the rubble state, not the building.
SKIP_ACTOR = ("decals/", "destruction")

# Vegetation bundled into a building actor (the civic centre ships cypress trees and nature props).
# The game plants its own trees, and including them inflates the projected ground footprint, which
# is what the renderer uses to scale the sprite -- so the building itself ends up drawn too small.
SKIP_MESH = ("_trees", "_nature")

ISOMETRIC_YAW = 45.0  # matches the game's 2:1 diamond projection
ISOMETRIC_PITCH = 30.0
XYZ = "XYZ"

# 0 A.D. renders under a warm sun. Several of these building textures are close to neutral on their
# own (the civic centre roof tile map has a saturation of 0.06), so a white lambert term bakes them
# out as flat grey. A warm light and a touch of saturation restores what the engine's lighting does
# in game.
SUN_TINT = (1.10, 1.02, 0.90)
SATURATION = 1.12


# --------------------------------------------------------------------------------------
# actor resolution
# --------------------------------------------------------------------------------------

def clamp8(v):
    return 0 if v < 0 else (255 if v > 255 else v)


def _basetex_in(elem):
    """The file named by a baseTex <texture> directly inside elem, if any."""
    texs = elem.find("textures")
    if texs is None:
        return None
    for te in texs.findall("texture"):
        if te.get("name") == "baseTex":
            return te.get("file")
    return None


class ActorIndex:
    """Parsed actor XMLs, keyed by path relative to ios/ZeroADArt/actors."""

    def __init__(self, root=ACTOR_ROOT):
        self.trees = {}
        self.file_basetex = {}
        for dirpath, _, files in os.walk(root):
            for fn in files:
                if not fn.endswith(".xml"):
                    continue
                rel = os.path.relpath(os.path.join(dirpath, fn), root).replace(os.sep, "/")
                try:
                    tree = ET.parse(os.path.join(dirpath, fn))
                except ET.ParseError:
                    continue
                self.trees[rel] = tree
                # 0 A.D. splits the base texture into its own <group>, so a variant holding a mesh
                # frequently carries only aoTex. Remember any baseTex in the file as a fallback.
                fb = None
                for variant in tree.iter("variant"):
                    fb = fb or _basetex_in(variant)
                self.file_basetex[rel] = fb

    def pick_variant(self, rel, want=None):
        """Highest-frequency variant carrying a mesh, optionally matching a name substring."""
        tree = self.trees.get(rel)
        if tree is None:
            return None
        best, best_freq = None, -1
        for variant in tree.iter("variant"):
            mesh = variant.find("mesh")
            if mesh is None or not mesh.text:
                continue
            if want and want.lower() not in (variant.get("name") or "").lower():
                continue
            try:
                freq = int(variant.get("frequency") or 1)
            except ValueError:
                freq = 1
            if freq > best_freq:
                best, best_freq = variant, freq
        return best

    def expand(self, rel, want=None, _depth=0, _seen=None):
        """Yield (mesh_rel, skin_rel) for an actor and every prop beneath it, recursively."""
        if _depth > 6:
            return
        _seen = _seen if _seen is not None else set()
        if rel in _seen:
            return  # cycles are possible in actor graphs
        _seen.add(rel)

        variant = self.pick_variant(rel, want)
        if variant is None:
            return
        mesh = variant.find("mesh")
        if mesh is not None and mesh.text:
            skin = _basetex_in(variant) or self.file_basetex.get(rel)
            yield mesh.text.strip(), skin
        props = variant.find("props")
        if props is None:
            return
        for prop in props.findall("prop"):
            actor = prop.get("actor")
            if not actor or any(s in actor for s in SKIP_ACTOR):
                continue
            yield from self.expand(actor, None, _depth + 1, _seen)


def skin_path(ref):
    """Resolve a texture reference to a local file, preferring the PNG over a DDS sibling.

    Refs arrive in two shapes: relative to textures/skins (from actor XML) and as an absolute
    Windows path baked into the COLLADA/MTL (``...\\art\\textures\\skins\\structural\\x.png``).
    """
    if not ref:
        return None
    m = re.search(r"art[/\\]textures[/\\]skins[/\\](.+)$", ref)
    rel = m.group(1) if m else ref
    rel = rel.replace("\\", "/").lstrip("/")
    p = os.path.join(SKIN_ROOT, rel)
    png = os.path.splitext(p)[0] + ".png"
    if os.path.exists(png):
        return png
    return p if os.path.exists(p) else None


# --------------------------------------------------------------------------------------
# mesh loading
# --------------------------------------------------------------------------------------

def export_obj(mesh_rel):
    """assimp export preserves the map_Kd binding that the checked-in converted/*.mtl dropped."""
    dae = os.path.join(MESH_ROOT, mesh_rel)
    if not os.path.exists(dae):
        return None
    os.makedirs(CACHE_DIR, exist_ok=True)
    obj = os.path.join(CACHE_DIR, mesh_rel.replace("/", "_") + ".obj")
    if not os.path.exists(obj) or os.path.getmtime(obj) < os.path.getmtime(dae):
        try:
            r = subprocess.run(["assimp", "export", dae, obj],
                               capture_output=True, text=True, check=False)
        except FileNotFoundError:
            sys.exit("assimp not found on PATH -- install it with: brew install assimp")
        if r.returncode != 0:
            print(f"    assimp failed on {mesh_rel}", file=sys.stderr)
            return None
    return obj


def load_obj(path):
    """Return (verts, uvs, faces) where each face is (vi0,vti0,vi1,vti1,vi2,vti2, texture)."""
    verts, uvs, faces = [], [], []
    mtl_tex, cur, mtllib = {}, None, None
    for line in open(path, errors="replace"):
        tok = line.split()
        if not tok:
            continue
        k = tok[0]
        if k == "v":
            verts.append((float(tok[1]), float(tok[2]), float(tok[3])))
        elif k == "vt":
            uvs.append((float(tok[1]), float(tok[2])))
        elif k == "mtllib":
            mtllib = tok[1]
        elif k == "usemtl":
            cur = tok[1]
        elif k == "f":
            corners = []
            for t in tok[1:]:
                parts = t.split("/")
                vi = int(parts[0]) - 1
                vti = int(parts[1]) - 1 if len(parts) > 1 and parts[1] else None
                corners.append((vi, vti))
            for i in range(1, len(corners) - 1):  # fan-triangulate any n-gon
                faces.append((corners[0], corners[i], corners[i + 1]))

    if mtllib:
        mp = os.path.join(os.path.dirname(path), mtllib)
        if os.path.exists(mp):
            name = None
            for line in open(mp, errors="replace"):
                tok = line.split()
                if not tok:
                    continue
                if tok[0] == "newmtl":
                    name = tok[1]
                elif tok[0] == "map_Kd" and name:
                    mtl_tex[name] = skin_path(" ".join(tok[1:]))

    out = []
    for (a, b, c) in faces:
        out.append((a[0], a[1], b[0], b[1], c[0], c[1], mtl_tex.get(cur)))
    return verts, uvs, out


# --------------------------------------------------------------------------------------
# geometry assembly
# --------------------------------------------------------------------------------------

def detect_up_axis(vals):
    """The up-axis is the one whose minimum sits closest to zero: models stand on the ground.

    Units are Z-up (z spans 0..3.86) while the oak is Y-up (y spans -0.26..19.77), so this has to
    be per-mesh. Returns 0/1/2 for X/Y/Z.
    """
    best, best_score = 2, None
    for axis in range(3):
        lo = min(v[axis] for v in vals)
        hi = max(v[axis] for v in vals)
        span = hi - lo
        if span <= 1e-9:
            continue
        score = abs(lo) / span
        if best_score is None or score < best_score:
            best, best_score = axis, score
    return best


class Piece:
    """One mesh, already reordered into (right, depth, up) with its own texture."""

    def __init__(self, verts, uvs, faces, texpath):
        self.verts, self.uvs, self.faces, self.texpath = verts, uvs, faces, texpath
        self.image = None
        if texpath:
            try:
                self.image = Image.open(texpath).convert("RGB")
            except Exception:
                self.image = None


def reorder(p, up):
    """Map a model-space point to (right, depth, up) for the given up-axis."""
    if up == 2:
        return p[0], p[1], p[2]
    if up == 1:
        return p[0], p[2], p[1]
    return p[1], p[2], p[0]


def build_pieces(index, actor_rel, want=None, verbose=True):
    """Load every mesh in an actor composite and put them in one shared coordinate frame.

    The up-axis is decided once, from the mesh with the most vertices, and applied to all parts.
    Detecting it per mesh looks tempting but misfires on small flat props -- the barracks decor
    mesh reports Z-up while the structure it sits on is Y-up -- and mixing axes within one building
    tears the composite apart.
    """
    raw = []
    for mesh_rel, skin_rel in index.expand(actor_rel, want):
        if any(s in mesh_rel for s in SKIP_MESH):
            if verbose:
                print(f"    {mesh_rel}  skipped (vegetation, not structure)")
            continue
        obj = export_obj(mesh_rel)
        if not obj:
            continue
        verts, uvs, faces = load_obj(obj)
        if not verts or not faces:
            continue
        raw.append((mesh_rel, verts, uvs, faces, skin_path(skin_rel)))
    if not raw:
        return []

    dominant = max(raw, key=lambda r: len(r[1]))
    up = detect_up_axis(dominant[1])
    if verbose:
        print(f"    up-axis '{XYZ[up]}' taken from {dominant[0]} ({len(dominant[1])} verts)")

    pieces = []
    for mesh_rel, verts, uvs, faces, texpath in raw:
        own = detect_up_axis(verts)
        note = "" if own == up else f"  (own guess {XYZ[own]}, overridden)"
        if verbose:
            print(f"    {mesh_rel}  verts={len(verts)} tris={len(faces)} "
                  f"tex={os.path.basename(texpath) if texpath else 'NONE'}{note}")
        pieces.append(Piece([reorder(v, up) for v in verts], uvs, faces, texpath))
    return pieces


# --------------------------------------------------------------------------------------
# rasteriser
# --------------------------------------------------------------------------------------

def render(pieces, size, yaw=ISOMETRIC_YAW, pitch=ISOMETRIC_PITCH, bg=(0, 0, 0, 0)):
    """Orthographic isometric render with a z-buffer and barycentric UV texture sampling."""
    allv = [v for p in pieces for v in p.verts]
    if not allv:
        raise SystemExit("no geometry")

    lo = [min(v[i] for v in allv) for i in range(3)]
    hi = [max(v[i] for v in allv) for i in range(3)]
    cx, cy = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2
    ground = lo[2]

    yr, pr = math.radians(yaw), math.radians(pitch)
    cyw, syw = math.cos(yr), math.sin(yr)
    cp, sp = math.cos(pr), math.sin(pr)

    def cam(v):
        x, y, z = v[0] - cx, v[1] - cy, v[2] - ground
        x, y = x * cyw - y * syw, x * syw + y * cyw
        y, z = y * cp - z * sp, y * sp + z * cp
        return x, y, z  # x = screen-right, y = depth, z = screen-up

    # projected extent drives the fit
    proj = [cam(v) for v in allv]
    span_x = max(p[0] for p in proj) - min(p[0] for p in proj)
    span_z = max(p[2] for p in proj) - min(p[2] for p in proj)
    scale = (size * 0.86) / max(span_x, span_z, 1e-6)
    ox = (min(p[0] for p in proj) + max(p[0] for p in proj)) / 2
    oz = min(p[2] for p in proj)

    # Ground footprint: the model's base rectangle. The canvas side scales the sprite so this maps
    # onto the building's tile diamond, which keeps every sprite on the same grid.
    corners = []
    for ux in (lo[0], hi[0]):
        for uy in (lo[1], hi[1]):
            corners.append(cam((ux, uy, ground)))
    fp_x = [(c[0] - ox) * scale + size / 2 for c in corners]
    fp_y = [-(c[2] - oz) * scale + size - 2 for c in corners]
    fp_w = max(fp_x) - min(fp_x)
    fp_cx = (max(fp_x) + min(fp_x)) / 2
    fp_cy = (max(fp_y) + min(fp_y)) / 2

    img = Image.new("RGBA", (size, size), bg)
    px = img.load()
    zbuf = [[-1e18] * size for _ in range(size)]

    sun = (-0.45, -0.5, 0.74)
    sl = math.sqrt(sum(c * c for c in sun)) or 1.0
    sun = tuple(c / sl for c in sun)

    for piece in pieces:
        texpx = piece.image.load() if piece.image else None
        tw, th = piece.image.size if piece.image else (1, 1)
        cv = [cam(v) for v in piece.verts]
        for (a, at, b, bt, c, ct, _tex) in piece.faces:
            if a >= len(cv) or b >= len(cv) or c >= len(cv):
                continue
            pa, pb, pc = cv[a], cv[b], cv[c]
            # `oz` must be subtracted here as well as `ox`: without it the model is pushed below
            # the canvas by its own lowest point and the front of every sprite is clipped off.
            x0 = (pa[0] - ox) * scale + size / 2
            y0 = -(pa[2] - oz) * scale + size - 2
            x1 = (pb[0] - ox) * scale + size / 2
            y1 = -(pb[2] - oz) * scale + size - 2
            x2 = (pc[0] - ox) * scale + size / 2
            y2 = -(pc[2] - oz) * scale + size - 2
            area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
            if abs(area) < 1e-9:
                continue

            # lambert term from the model-space normal
            va, vb, vc = piece.verts[a], piece.verts[b], piece.verts[c]
            e1 = (vb[0] - va[0], vb[1] - va[1], vb[2] - va[2])
            e2 = (vc[0] - va[0], vc[1] - va[1], vc[2] - va[2])
            nx = e1[1] * e2[2] - e1[2] * e2[1]
            ny = e1[2] * e2[0] - e1[0] * e2[2]
            nz = e1[0] * e2[1] - e1[1] * e2[0]
            nl = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
            lam = abs((nx * sun[0] + ny * sun[1] + nz * sun[2]) / nl)
            shade = min(1.30, 0.44 + 0.72 * lam)

            uva = piece.uvs[at] if (at is not None and at < len(piece.uvs)) else (0.0, 0.0)
            uvb = piece.uvs[bt] if (bt is not None and bt < len(piece.uvs)) else (0.0, 0.0)
            uvc = piece.uvs[ct] if (ct is not None and ct < len(piece.uvs)) else (0.0, 0.0)

            minx = max(0, int(min(x0, x1, x2)))
            maxx = min(size - 1, int(max(x0, x1, x2)) + 1)
            miny = max(0, int(min(y0, y1, y2)))
            maxy = min(size - 1, int(max(y0, y1, y2)) + 1)
            if minx > maxx or miny > maxy:
                continue

            inv = 1.0 / area
            for yy in range(miny, maxy + 1):
                pyc = yy + 0.5
                row_z = zbuf[yy]
                for xx in range(minx, maxx + 1):
                    pxc = xx + 0.5
                    w0 = ((x1 - pxc) * (y2 - pyc) - (x2 - pxc) * (y1 - pyc)) * inv
                    w1 = ((x2 - pxc) * (y0 - pyc) - (x0 - pxc) * (y2 - pyc)) * inv
                    w2 = 1.0 - w0 - w1
                    if w0 < -0.002 or w1 < -0.002 or w2 < -0.002:
                        continue
                    depth = w0 * pa[1] + w1 * pb[1] + w2 * pc[1]
                    if depth <= row_z[xx]:
                        continue
                    if texpx:
                        uu = w0 * uva[0] + w1 * uvb[0] + w2 * uvc[0]
                        vv = w0 * uva[1] + w1 * uvb[1] + w2 * uvc[1]
                        vv = 1.0 - vv  # OBJ is bottom-left origin, PNG is top-left
                        r, g, bl = texpx[int(uu % 1.0 * tw) % tw, int(vv % 1.0 * th) % th]
                    else:
                        r = g = bl = 185
                    row_z[xx] = depth
                    # push away from the pixel's own luminance to restore the warmth that a
                    # neutral lambert term flattens out of these desaturated textures
                    lum = (r * 0.299 + g * 0.587 + bl * 0.114)
                    px[xx, yy] = (
                        clamp8(int((lum + (r - lum) * SATURATION) * shade * SUN_TINT[0])),
                        clamp8(int((lum + (g - lum) * SATURATION) * shade * SUN_TINT[1])),
                        clamp8(int((lum + (bl - lum) * SATURATION) * shade * SUN_TINT[2])),
                        255)
    return img, {"fp_w": round(fp_w, 2), "fp_cx": round(fp_cx, 2), "fp_cy": round(fp_cy, 2)}


# --------------------------------------------------------------------------------------
# targets
# --------------------------------------------------------------------------------------

# name, actor path (relative to ios/ZeroADArt/actors), variant-name hint, sprite size in px
BUILDINGS = [
    ("bld_tc", "structures/athenians/civil_centre.xml", None, 300),
    ("bld_barracks", "structures/athenians/barracks.xml", None, 260),
    ("bld_house_a", "structures/hellenes/house.xml", "House A", 200),
    ("bld_house_b", "structures/hellenes/house.xml", "House B", 200),
    ("bld_house_c", "structures/hellenes/house.xml", "House C", 200),
    ("bld_house_d", "structures/hellenes/house.xml", "House D", 200),
    ("bld_house_e", "structures/hellenes/house.xml", "House E", 200),
    ("bld_store", "structures/hellenes/storehouse.xml", None, 200),
    ("bld_tower", "structures/athenians/wall_tower.xml", None, 210),
    # No gate or wall segment here on purpose. `props/hele_fortress_up_gate.dae` is a prop authored
    # to sit inside a fortress wall, not a standalone gateway: it is 0.39 units tall with its lintel
    # and posts projecting diagonally apart, and bakes into two disconnected fragments. The game
    # keeps its own procedural gate, which already draws a working portcullis.
]

TREES = [
    ("tree_oak_1", "flora/trees/oak.xml", "tree_1", 160),
    ("tree_oak_2", "flora/trees/oak.xml", "tree_4", 160),
    ("tree_pine_1", "flora/trees/aleppo_pine.xml", "Aleppo-1", 160),
    ("tree_pine_2", "flora/trees/aleppo_pine.xml", "Aleppo-2", 160),
]

# Units bake one neutral sheet per facing; the page tints per team with a multiply composite, which
# keeps the sprite count down and preserves the baked shading.
UNITS = [
    ("unit_vill", "units/athenians/female_citizen.xml", 72),
    ("unit_spear", "units/athenians/hero_infantry_spearman_pericles.xml", 72),
]


# A seamless 0 A.D. surface used as a detail overlay on land tiles. decal_struct_sand_medium.png
# measures an edge delta of 0.0 (genuinely tileable), unlike the 2048px terrain blend textures,
# which are 9 MB and do not wrap. Flattened to a narrow light band so the canvas can multiply it
# over the existing terrain colours -- the game keeps its grass/dirt/water semantics and gains
# 0 A.D.'s surface character, rather than being repainted wholesale.
GROUND_SRC = "props/decal_struct_sand_medium.png"
GROUND_SIZE = 256
GROUND_FLOOR, GROUND_CEIL = 190, 255


def bake_ground(out_dir):
    src = os.path.join(SKIN_ROOT, GROUND_SRC)
    if not os.path.exists(src):
        print(f"  ground source missing: {GROUND_SRC}")
        return
    im = Image.open(src).convert("L").resize((GROUND_SIZE, GROUND_SIZE), Image.LANCZOS)
    span = GROUND_CEIL - GROUND_FLOOR
    im = im.point(lambda v: GROUND_FLOOR + (v * span) // 255)
    fn = os.path.join(out_dir, "ground.png")
    im.convert("RGB").save(fn, optimize=True)
    print(f"  -> ground.png  {GROUND_SIZE}x{GROUND_SIZE}  {os.path.getsize(fn) // 1024}K")


# Animated characters. The bundled rigs ship with no clips of their own, so these apply 0 A.D.'s
# own animation files (same project, same `Biped_*` bone names) via Blender, which handles the
# skinning, and then rasterise the deformed result here so units stay lit and projected exactly
# like the buildings. Requires Blender; skipped unless --with-animation is passed.
ANIMATED_UNITS = [
    # sprite name, character, clip, frames sampled across the cycle, sprite size
    ("unit_vill_walk", "villager", "walk", 8, 72),
    ("unit_vill_idle", "villager", "idle", 6, 72),
]
BLENDER_SCRIPT = os.path.join(HERE, "blender_bake_animation.py")

# Base colour map per character, relative to textures/skins. Kept in step with the same table in
# blender_bake_animation.py, which is what actually attaches it during the Blender pass.
CHARACTER_SKINS = {
    "villager": "skeletal/hele/dress_female_01.png",
    "soldier": "skeletal/athen/linothorax_lamellar_01_03.png",
}


def blender_frame_cache(character, clip, frames, cache_root):
    """Run Blender to write deformed per-frame OBJs, and return the cache directory."""
    out = os.path.join(cache_root, f"{character}_{clip}")
    meta = os.path.join(out, "meta.json")
    if os.path.exists(meta):
        return out
    blender = shutil.which("blender")
    if not blender:
        print("    blender not found on PATH -- skipping animated units "
              "(install it with: brew install --cask blender)")
        return None
    print(f"    running blender for {character}/{clip} ({frames} frames)...")
    r = subprocess.run([blender, "--background", "--python", BLENDER_SCRIPT, "--",
                        "--character", character, "--clip", clip,
                        "--frames", str(frames), "--out", out],
                       capture_output=True, text=True, check=False)
    if not os.path.exists(meta):
        tail = "\n".join(r.stdout.splitlines()[-12:])
        print(f"    blender failed for {character}/{clip}:\n{tail}\n{r.stderr[-600:]}")
        return None
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="bake only targets whose name contains this substring")
    # The game tracks only a mirrored facing (u.face, +/-1), so one bake is all it can use; raise
    # this if the renderer ever gains a real direction vector.
    ap.add_argument("--facings", type=int, default=1, help="unit facings (default 1)")
    ap.add_argument("--out", default=OUT_DIR)
    ap.add_argument("--with-animation", action="store_true",
                    help="also bake the animated character cycles (needs Blender on PATH)")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    index = ActorIndex()
    print(f"actor files parsed: {len(index.trees)}")

    manifest = {}

    def wanted(name):
        return not args.only or args.only in name

    def bake_one(name, actor, want, size, yaw=ISOMETRIC_YAW):
        print(f"  [{name}] {actor}" + (f" ({want})" if want else ""))
        pieces = build_pieces(index, actor, want)
        if not pieces:
            print("    -- no geometry, skipped")
            return False
        img, meta = render(pieces, size, yaw=yaw)
        fn = f"{name}.png"
        img.save(os.path.join(args.out, fn))
        opaque = sum(1 for v in img.split()[3].get_flattened_data() if v > 128)
        manifest[name] = {"file": fn, "w": size, "h": size, "fill": round(opaque / (size * size), 4),
                          **meta}
        print(f"    -> {fn}  fill={opaque / (size * size) * 100:.1f}%  fp_w={meta['fp_w']}")
        return True

    print("\n== buildings ==")
    for name, actor, want, size in BUILDINGS:
        if wanted(name):
            bake_one(name, actor, want, size)

    print("\n== trees ==")
    for name, actor, want, size in TREES:
        if wanted(name):
            bake_one(name, actor, want, size)

    print("\n== units ==")
    for name, actor, size in UNITS:
        if not wanted(name):
            continue
        for i in range(args.facings):
            suffix = f"_{i}" if args.facings > 1 else ""
            bake_one(f"{name}{suffix}", actor, None, size,
                     yaw=ISOMETRIC_YAW + i * (360.0 / args.facings))

    if args.with_animation:
        print("\n== animated units ==")
        cache_root = os.path.join(tempfile.gettempdir(), "zeroad_anim_cache")
        for name, character, clip, nframes, size in ANIMATED_UNITS:
            if not wanted(name):
                continue
            print(f"  [{name}] {character} / {clip}")
            cache = blender_frame_cache(character, clip, nframes, cache_root)
            if cache is None:
                continue
            tex = skin_path(CHARACTER_SKINS[character])
            files = []
            for i in range(nframes):
                obj = os.path.join(cache, f"frame_{i:03d}.obj")
                if not os.path.exists(obj):
                    print(f"    missing {obj}")
                    continue
                verts, uvs, faces = load_obj(obj)
                if not verts or not faces:
                    continue
                # one axis decision per frame; a skinned character bakes consistently
                up = detect_up_axis(verts)
                piece = Piece([reorder(v, up) for v in verts], uvs, faces, tex)
                img, meta = render([piece], size)
                fn = f"{name}_{i}.png"
                img.save(os.path.join(args.out, fn))
                opaque = sum(1 for v in img.split()[3].get_flattened_data() if v > 128)
                manifest[f"{name}_{i}"] = {"file": fn, "w": size, "h": size,
                                           "fill": round(opaque / (size * size), 4), **meta}
                files.append(fn)
            if files:
                # Playback rate, not the source framerate: N frames sampled across `duration`
                # seconds must advance at N/duration per second to run at the clip's real speed.
                try:
                    with open(os.path.join(cache, "meta.json")) as fh:
                        duration = json.load(fh).get("duration") or 1.0
                except Exception:
                    duration = 1.0
                manifest[name] = {"group": "animation", "frames": len(files), "files": files,
                                  "clip": clip, "duration": duration,
                                  "fps": round(len(files) / duration, 3)}
                print(f"    -> {len(files)} frames over {duration}s "
                      f"(plays at {len(files) / duration:.2f} fps)")

    print("\n== ground ==")
    bake_ground(args.out)

    with open(os.path.join(args.out, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
        f.write("\n")
    print(f"\nwrote {len(manifest)} sprites + manifest.json to {os.path.relpath(args.out, ROOT)}")


if __name__ == "__main__":
    main()
