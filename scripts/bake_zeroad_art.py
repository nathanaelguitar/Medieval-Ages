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

from PIL import Image, ImageChops, ImageFilter

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


# --------------------------------------------------------------------------------------
# skeleton: resolving bone rest matrices, so unit props can be attached
# --------------------------------------------------------------------------------------
# 0 A.D. attaches a unit's helmet, shield, spear and greaves to named skeleton bones, and authors
# those prop meshes flat in the bone's local space. Merging them at identity (correct for buildings,
# whose props all attach at the root) therefore drops a helmet at knee height. These helpers walk
# the COLLADA visual scene to recover each bone's rest transform.

def m4_identity():
    return [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0]


def m4_mul(a, b):
    """Row-major 4x4 product a*b."""
    out = [0.0] * 16
    for r in range(4):
        for c in range(4):
            out[r * 4 + c] = sum(a[r * 4 + k] * b[k * 4 + c] for k in range(4))
    return out


def m4_apply(m, p):
    x, y, z = p
    w = m[12] * x + m[13] * y + m[14] * z + m[15]
    if abs(w) < 1e-12:
        w = 1.0
    return ((m[0] * x + m[1] * y + m[2] * z + m[3]) / w,
            (m[4] * x + m[5] * y + m[6] * z + m[7]) / w,
            (m[8] * x + m[9] * y + m[10] * z + m[11]) / w)


def m4_translate(x, y, z):
    return [1.0, 0, 0, x, 0, 1.0, 0, y, 0, 0, 1.0, z, 0, 0, 0, 1.0]


def m4_scale(x, y, z):
    return [x, 0, 0, 0, 0, y, 0, 0, 0, 0, z, 0, 0, 0, 0, 1.0]


def m4_rotate(ax, ay, az, deg):
    n = math.sqrt(ax * ax + ay * ay + az * az)
    if n < 1e-12:
        return m4_identity()
    ax, ay, az = ax / n, ay / n, az / n
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    t = 1.0 - c
    return [t * ax * ax + c, t * ax * ay - s * az, t * ax * az + s * ay, 0,
            t * ax * ay + s * az, t * ay * ay + c, t * ay * az - s * ax, 0,
            t * ax * az - s * ay, t * ay * az + s * ax, t * az * az + c, 0,
            0, 0, 0, 1.0]


def m4_from_collada(text, row_major=True):
    """COLLADA <matrix> is row-major: the 16 values are m00 m01 m02 m03 m10 ...

    This is already the internal layout, so the values map straight across -- transposing here
    (an easy mistake, since the same numbers *look* like a column-major dump) puts every bone in
    the wrong place. The tell is the last row: `0 0 0 1` with the translation in the last column
    of rows 0-2 means row-major.
    """
    v = [float(x) for x in text.split()]
    if len(v) != 16:
        return m4_identity()
    if row_major:
        return v
    return [v[0], v[4], v[8], v[12],
            v[1], v[5], v[9], v[13],
            v[2], v[6], v[10], v[14],
            v[3], v[7], v[11], v[15]]


def m4_transpose(m):
    return [m[0], m[4], m[8], m[12],
            m[1], m[5], m[9], m[13],
            m[2], m[6], m[10], m[14],
            m[3], m[7], m[11], m[15]]


# assimp converts the COLLADA Z-up frame to Y-up on export, so anything read from the DAE -- a bone
# rest matrix, say -- has to be conjugated by this before it can act on exported vertices, or on the
# armature Blender imported from that same export. Skip it and props scatter instead of attaching.
AXIS_ZUP_TO_YUP = [1, 0, 0, 0,
                   0, 0, 1, 0,
                   0, -1, 0, 0,
                   0, 0, 0, 1]
AXIS_ZUP_TO_YUP_T = m4_transpose(AXIS_ZUP_TO_YUP)


def m4_to_converted(m):
    return m4_mul(m4_mul(AXIS_ZUP_TO_YUP, m), AXIS_ZUP_TO_YUP_T)


def node_local_matrix(node, row_major=True):
    """Compose a node's transform elements in document order, per the COLLADA spec."""
    m = m4_identity()
    for child in node:
        tag = child.tag.split("}")[-1]
        txt = (child.text or "").split()
        if tag == "matrix" and txt:
            m = m4_mul(m, m4_from_collada(" ".join(txt), row_major))
        elif tag == "translate" and len(txt) >= 3:
            m = m4_mul(m, m4_translate(*[float(x) for x in txt[:3]]))
        elif tag == "rotate" and len(txt) >= 4:
            m = m4_mul(m, m4_rotate(*[float(x) for x in txt[:4]]))
        elif tag == "scale" and len(txt) >= 3:
            m = m4_mul(m, m4_scale(*[float(x) for x in txt[:3]]))
    return m


def parse_skeleton(dae_path, row_major=True, with_parents=False):
    """bone id -> rest world matrix (and optionally its parent), from the COLLADA visual scene."""
    NS = "{http://www.collada.org/2005/11/COLLADASchema}"
    try:
        root = ET.parse(dae_path).getroot()
    except (ET.ParseError, OSError):
        return {}
    scene = root.find(f"{NS}library_visual_scenes")
    if scene is None:
        return {}
    out, parents = {}, {}

    def walk(node, parent, parent_id):
        nid = node.get("id")
        world = m4_mul(parent, node_local_matrix(node, row_major))
        if nid and nid not in out:   # the tree lists some bones twice; keep the first
            out[nid] = world
            parents[nid] = parent_id
        for child in node.findall(f"{NS}node"):
            walk(child, world, nid)

    for vs in scene.findall(f"{NS}visual_scene"):
        for node in vs.findall(f"{NS}node"):
            walk(node, m4_identity(), None)
    return (out, parents) if with_parents else out


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

    def expand(self, rel, want=None, _depth=0, _seen=None, props=True, attachpoint="root"):
        """Yield (mesh_rel, skin_rel, attachpoint) for an actor and its props, recursively.

        `attachpoint` names the skeleton bone a prop hangs off. Buildings use `root` throughout, so
        their props merge at identity. Units use bone names (`helmet`, `shield_arm`, `weapon_R`),
        and those prop meshes are authored in the bone's local space -- merging them at identity
        drops a helmet at knee height instead of on the head.
        """
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
            yield mesh.text.strip(), skin, attachpoint
        if not props:
            return
        props_elem = variant.find("props")
        if props_elem is None:
            return
        for prop in props_elem.findall("prop"):
            actor = prop.get("actor")
            if not actor or any(s in actor for s in SKIP_ACTOR):
                continue
            yield from self.expand(actor, None, _depth + 1, _seen,
                                   attachpoint=prop.get("attachpoint") or "root")


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


def build_pieces(index, actor_rel, want=None, verbose=True, include_props=True):
    """Load every mesh in an actor composite and put them in one shared coordinate frame.

    The up-axis is decided once, from the mesh with the most vertices, and applied to all parts.
    Detecting it per mesh looks tempting but misfires on small flat props -- the barracks decor
    mesh reports Z-up while the structure it sits on is Y-up -- and mixing axes within one building
    tears the composite apart.
    """
    raw = []
    for mesh_rel, skin_rel, attachpoint in index.expand(actor_rel, want, props=include_props):
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
        raw.append((mesh_rel, verts, uvs, faces, skin_path(skin_rel), attachpoint))
    if not raw:
        return []

    dominant = max(raw, key=lambda r: len(r[1]))
    up = detect_up_axis(dominant[1])
    if verbose:
        print(f"    up-axis '{XYZ[up]}' taken from {dominant[0]} ({len(dominant[1])} verts)")

    # Bone rest matrices come from the body mesh's own skeleton. Prop geometry arrives via assimp
    # in Y-up while the COLLADA scene is Z-up, so the bone matrix is conjugated by that axis change
    # before it can act on these vertices.
    skeleton = parse_skeleton(os.path.join(MESH_ROOT, dominant[0]))
    dlo = [min(v[i] for v in dominant[1]) for i in range(3)]
    dhi = [max(v[i] for v in dominant[1]) for i in range(3)]
    # Assimp exports the biped as Y-up, not Z-up. Measure along the axis selected for the body;
    # using Z here makes a 3.85-unit soldier look only 0.84 units tall and wrongly filters helmets.
    body_h = dhi[up] - dlo[up]

    pieces = []
    for mesh_rel, verts, uvs, faces, texpath, attachpoint in raw:
        own = detect_up_axis(verts)
        note = "" if own == up else f"  (own guess {XYZ[own]}, overridden)"
        if attachpoint and attachpoint != "root":
            piece, why = place_prop(mesh_rel, skin_rel, attachpoint, skeleton, up, body_h)
            if piece is None:
                # Better to drop a prop than to drop it at the origin or smear it across the feet.
                if verbose:
                    print(f"    {mesh_rel}  skipped ({why})")
                continue
            note += f"  [{why}]"
            pieces.append(piece)
            continue
        if verbose:
            print(f"    {mesh_rel}  verts={len(verts)} tris={len(faces)} "
                  f"tex={os.path.basename(texpath) if texpath else 'NONE'}{note}")
        pieces.append(Piece([reorder(v, up) for v in verts], uvs, faces, texpath))
    return pieces


# --------------------------------------------------------------------------------------
# rasteriser
# --------------------------------------------------------------------------------------

def project_fit(vertsets, size, yaw=ISOMETRIC_YAW, pitch=ISOMETRIC_PITCH):
    """Camera framing shared by a whole set of meshes.

    Called with every frame of a clip at once so the framing is identical across them. Fitting each
    frame separately makes the character change size whenever a limb -- or a spear -- swings wide.
    Returns (cx, cy, ground, scale, ox, oz).
    """
    allv = [v for vs in vertsets for v in vs]
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

    proj = [cam(v) for v in allv]
    span_x = max(p[0] for p in proj) - min(p[0] for p in proj)
    span_z = max(p[2] for p in proj) - min(p[2] for p in proj)
    scale = (size * 0.86) / max(span_x, span_z, 1e-6)
    ox = (min(p[0] for p in proj) + max(p[0] for p in proj)) / 2
    oz = min(p[2] for p in proj)
    return cx, cy, ground, scale, ox, oz


def render(pieces, size, yaw=ISOMETRIC_YAW, pitch=ISOMETRIC_PITCH, bg=(0, 0, 0, 0), fit=None):
    """Orthographic isometric render with a z-buffer and barycentric UV texture sampling."""
    allv = [v for p in pieces for v in p.verts]
    if not allv:
        raise SystemExit("no geometry")

    cx, cy, ground, scale, ox, oz = fit if fit else project_fit([allv], size, yaw, pitch)

    yr, pr = math.radians(yaw), math.radians(pitch)
    cyw, syw = math.cos(yr), math.sin(yr)
    cp, sp = math.cos(pr), math.sin(pr)

    def cam(v):
        x, y, z = v[0] - cx, v[1] - cy, v[2] - ground
        x, y = x * cyw - y * syw, x * syw + y * cyw
        y, z = y * cp - z * sp, y * sp + z * cp
        return x, y, z  # x = screen-right, y = depth, z = screen-up

    # Ground footprint: the model's base rectangle. The canvas side scales the sprite so this maps
    # onto the building's tile diamond, which keeps every sprite on the same grid.
    lo = [min(v[i] for v in allv) for i in range(3)]
    hi = [max(v[i] for v in allv) for i in range(3)]
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
    ("animal_boar", "fauna/boar.xml", 72),
    ("animal_sheep", "fauna/sheep1.xml", 72),
]


# A 0 A.D. surface used as a detail overlay on land tiles. The raw decal does not survive being
# repeated on screen: it carries a painted vignette (slow shading drift), and after the resize its
# opposite edges disagree by up to ~30 levels, so every repeat drew a box-grid of seams with odd
# corner junctions across the map. Bake it into pure grain instead -- keep only detail finer than
# GROUND_LOWPASS (the vignette and its edge step are far coarser), make that grain wrap by
# cross-fading toward its half-turn roll near the borders, and park the result in a narrow bright
# band: multiplying by ~255 is a no-op, so the terrain keeps its flat grass/dirt/water colour and
# gains only a faint 0 A.D. tooth.
GROUND_SRC = "props/decal_struct_sand_medium.png"
GROUND_SIZE = 256
GROUND_LOWPASS = 8    # px; detail coarser than this is vignette, not tooth
GROUND_BLEND = 48     # px; border margin over which the grain cross-fades to its rolled self
GROUND_FLOOR = 210    # darkest value the grain may reach (255 = no effect)
GROUND_GAIN = 0.55    # how strongly surviving grain darkens: 255 - |detail| * GAIN


def bake_ground(out_dir):
    src = os.path.join(SKIN_ROOT, GROUND_SRC)
    if not os.path.exists(src):
        print(f"  ground source missing: {GROUND_SRC}")
        return
    im = Image.open(src).convert("L").resize((GROUND_SIZE, GROUND_SIZE), Image.LANCZOS)
    grain = ImageChops.subtract(im, im.filter(ImageFilter.GaussianBlur(GROUND_LOWPASS)), 1, 128)
    rolled = ImageChops.offset(grain, GROUND_SIZE // 2, GROUND_SIZE // 2)
    mask = Image.new("L", (GROUND_SIZE, GROUND_SIZE), 255)
    mp = mask.load()
    for j in range(GROUND_SIZE):
        row_edge = min(j, GROUND_SIZE - 1 - j)
        for i in range(GROUND_SIZE):
            d = min(row_edge, i, GROUND_SIZE - 1 - i)
            if d < GROUND_BLEND:
                mp[i, j] = (255 * d) // GROUND_BLEND
    grain = Image.composite(grain, rolled, mask)
    im = grain.point([max(GROUND_FLOOR, 255 - int(abs(v - 128) * GROUND_GAIN)) for v in range(256)])
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
    ("unit_spear_walk", "soldier", "walk", 8, 72),
    ("unit_spear_idle", "soldier", "idle", 6, 72),
    # The weapon-raised stances the page plays while a unit is in a fight. The bundle ships these
    # for the hoplite and nothing else -- there is no attack clip and no archer or bow mesh at all
    # -- so this is what "shooting" has to look like on the ranged units, which draw as spearmen.
    ("unit_spear_ready_walk", "soldier", "walk_ready", 8, 72),
    ("unit_spear_ready_idle", "soldier", "idle_ready", 6, 72),
    ("animal_boar_walk", "boar", "walk", 8, 72),
    ("animal_boar_idle", "boar", "idle", 6, 72),
    ("animal_sheep_walk", "sheep", "walk", 8, 72),
    ("animal_sheep_idle", "sheep", "idle", 6, 72),
]
BLENDER_SCRIPT = os.path.join(HERE, "blender_bake_animation.py")

# Base colour map per character, relative to textures/skins. Kept in step with the same table in
# blender_bake_animation.py, which is what actually attaches it during the Blender pass.
CHARACTER_SKINS = {
    "villager": "skeletal/hele/dress_female_01.png",
    "soldier": "skeletal/athen/linothorax_lamellar_01_03.png",
    "boar": "skeletal/animal_boar_01.png",
    "sheep": "skeletal/animal_sheep_a.dds",
}

# The actor a character bakes from, so its bone-attached props can be resolved and handed to
# Blender -- otherwise an animated unit would visibly shed its helmet and spear the moment it walks.
CHARACTER_ACTORS = {
    "villager": "units/athenians/female_citizen.xml",
    "soldier": "units/athenians/hero_infantry_spearman_pericles.xml",
    "boar": "fauna/boar.xml",
    "sheep": "fauna/sheep1.xml",
}

# ...and the body mesh, which is the skeleton props are resolved against.
CHARACTER_MESHES = {
    "villager": "skeletal/new/f_dress.dae",
    "soldier": "skeletal/new/m_armor_tunic_short.dae",
    "boar": "skeletal/animal_boar.dae",
    "sheep": "skeletal/sheep.dae",
}


def mesh_extent(verts):
    """Bounding-box diagonal of a mesh, in its own space."""
    if not verts:
        return 0.0
    lo = [min(v[i] for v in verts) for i in range(3)]
    hi = [max(v[i] for v in verts) for i in range(3)]
    return math.sqrt(sum((hi[i] - lo[i]) ** 2 for i in range(3)))


# A unit prop is only kept if it is a plausible thing to hang off a bone. Two failure modes, both
# measured rather than guessed:
#   * Too small. Props authored flat at the origin (the soldier's cape spans 0.07 on a 3.85 body,
#     the villager's head prop 0.01) are meant to be placed by a bone that this pipeline does not
#     always have. Left in, they smear a sliver across the feet.
#   * Too long. A spear is 3.4 units on a 3.85 body. Its own bone is dropped by the glTF hop, so it
#     ends up following the hand -- and a walk cycle swings the hand hard, turning the spear into a
#     thin diagonal line across the whole sprite and shrinking the figure to fit.
# Compact, bone-attached gear (helmet, shield, greaves) rides along correctly.
PROP_MIN_EXTENT = 0.05
PROP_MAX_EXTENT_FRAC = 0.5


def prop_extent_ok(extent, body_height):
    return PROP_MIN_EXTENT <= extent <= PROP_MAX_EXTENT_FRAC * body_height


def collada_unit(mesh_rel):
    """The COLLADA unit a mesh is authored in, as a factor onto its own vertices.

    A composite mixes units: the biped bodies, helmets, sheaths and greaves declare metres, while
    the face props declare centimetres (dudette_head_b) or inches (head_beard). Dividing each prop
    by its own declared unit is what makes them agree -- the villager's head lands at 0.99 units and
    the beard at 0.93 on a 3.86-unit body, and every metre-authored prop is left untouched. Skipping
    it is what made the villager headless: at its authored 0.0099 units the extent floor below read
    the head as debris and dropped it, and f_dress.dae carries no head of its own (its topmost band
    is a broad 0.72-unit hood, not a skull), so the bake produced a robe with nothing above the
    shoulders. Blender has always applied this -- it is where the 6.16-unit spear came from -- so the
    rest-placement path has to as well or the two disagree about the same mesh.
    """
    try:
        with open(os.path.join(MESH_ROOT, mesh_rel), encoding="utf-8", errors="ignore") as fh:
            head = fh.read(4096)
    except OSError:
        return 1.0
    m = re.search(r'<unit\b[^>]*meter="([0-9.eE+-]+)"', head)
    if not m:
        return 1.0
    meter = float(m.group(1))
    return 1.0 / meter if meter > 0 else 1.0


def place_prop(mesh_rel, skin_rel, attachpoint, skeleton, up, body_h):
    """Load a bone-attached prop and transform it onto its bone. Returns (Piece, note) or (None, why).

    Shared by the static and animated unit bakes so a unit looks the same whether it is standing or
    walking. In the animated bake the props stay at this rest placement rather than following the
    animation: Blender's bone space and the COLLADA rest space this transform is derived in do not
    agree -- a prop placed through Blender's pose matrices came out 6.16 units where the rest
    placement gives 0.16, a scale mismatch -- and rather than mix the two, the placement that is
    known correct is used for both. A helmet, shield or greave barely moves in a walk anyway.
    """
    bone = f"Biped_{attachpoint}"
    m = skeleton.get(bone)
    if m is None:
        return None, f"no bone '{bone}'"
    obj = export_obj(mesh_rel)
    if not obj:
        return None, "assimp failed"
    verts, uvs, faces = load_obj(obj)
    if not verts or not faces:
        return None, "no geometry"
    unit = collada_unit(mesh_rel)
    note_unit = ""
    if abs(unit - 1.0) > 1e-6:
        verts = [tuple(c * unit for c in v) for v in verts]
        note_unit = f", unit x{unit:g} ({XYZ[up]}-up source)"
    verts = [m4_apply(m4_to_converted(m), v) for v in verts]
    # Measured AFTER attaching, because bones carry scale: the spear mesh is 0.16 units in its own
    # space but larger once the bone's scale applies, and measuring before made it look small enough
    # to keep. See PROP_MIN_EXTENT for why both extremes are dropped.
    ext = mesh_extent(verts)
    if not prop_extent_ok(ext, body_h):
        return None, f"placed extent {ext:.2f} vs body {body_h:.2f}"
    return (Piece([reorder(v, up) for v in verts], uvs, faces, skin_path(skin_rel)),
            f"on {bone}{note_unit}")


def unit_prop_pieces(index, actor_rel, skeleton_dae, want=None):
    """Bone-placed props for a unit, at rest, in canonical (right, depth, up) form.

    Derives its own up-axis rather than taking the caller's. The animated bake merges these with
    geometry Blender exported -- and Blender writes Z-up OBJ while assimp writes Y-up -- so passing
    the body's axis in here reordered the props into the wrong frame. That mismatch is what turned
    the spear into a 6-unit streak across the sprite. Reordering each source by its own up axis puts
    both in the same canonical frame, which is what makes them merge cleanly.
    """
    skeleton = parse_skeleton(skeleton_dae)
    body = load_obj(export_obj(os.path.relpath(skeleton_dae, MESH_ROOT)))
    if not body[0]:
        return []
    aup = detect_up_axis(body[0])          # assimp's frame, for anything loaded through it
    hv = [reorder(v, aup) for v in body[0]]
    body_h = max(v[2] for v in hv) - min(v[2] for v in hv)
    out = []
    for mesh_rel, skin_rel, ap in index.expand(actor_rel, want):
        if not ap or ap == "root":
            continue
        piece, note = place_prop(mesh_rel, skin_rel, ap, skeleton, aup, body_h)
        if piece:
            out.append(piece)
    return out


def unit_prop_spec(index, actor_rel, want=None, skeleton_dae=None):
    """Props to attach in Blender, as dicts carrying everything it needs to place them.

    The glTF hop prunes the armature to its deform bones -- a 102-joint rig arrives in Blender as
    24 -- so `Biped_helmet`, `Biped_weapon_R` and `Biped_shield_arm` may simply not exist there.
    Each prop therefore carries its ancestor chain and those bones' rest matrices, letting Blender
    pick the nearest ancestor it actually has and offset from it, which keeps the helmet on the
    head and the spear in the hand even though their own bones were dropped.
    """
    if not skeleton_dae:
        return []
    rests, parents = parse_skeleton(skeleton_dae, with_parents=True)
    body = load_obj(export_obj(os.path.relpath(skeleton_dae, MESH_ROOT)))
    body_up = detect_up_axis(body[0]) if body[0] else 1
    body_h = (max(v[body_up] for v in body[0]) - min(v[body_up] for v in body[0])) if body[0] else 1.0
    out = []
    for mesh_rel, skin_rel, ap in index.expand(actor_rel, want):
        if not ap or ap == "root":
            continue
        target = f"Biped_{ap}"
        if target not in rests:
            continue
        pobj = export_obj(mesh_rel)
        if not pobj:
            continue
        pv = load_obj(pobj)[0]
        # Measure where the prop ends up, not where it is authored -- bones carry scale. Blender
        # loads the mesh itself and applies the COLLADA unit on the way in (that is where the
        # 6.16-unit spear came from), so the check has to apply it too or the spec drops props that
        # Blender would happily place -- the villager's head among them.
        placed = [m4_apply(m4_to_converted(rests[target]), v) for v in pv]
        if not prop_extent_ok(mesh_extent(placed) * collada_unit(mesh_rel), body_h):
            continue
        chain, node = [], target
        while node and len(chain) < 8:
            chain.append(node)
            node = parents.get(node)
        # Conjugated, because Blender's armature and the prop geometry both arrived through the
        # assimp Y-up conversion while these rest matrices are still in the DAE's Z-up frame.
        out.append({"mesh": mesh_rel, "skin": skin_rel, "target": target, "chain": chain,
                    "rests": {b: m4_to_converted(rests[b]) for b in chain}})
    return out


def blender_frame_cache(character, clip, frames, cache_root, index=None):
    """Run Blender to write deformed per-frame OBJs, and return the cache directory.

    The cache is keyed on the Blender script's contents as well as the character and clip. Without
    that, editing the script (say, to start exporting props) silently reuses frames produced by the
    old one -- and the bake then reports success from stale geometry.
    """
    out = os.path.join(cache_root, f"{character}_{clip}")
    meta = os.path.join(out, "meta.json")
    try:
        stamp = str(os.path.getmtime(BLENDER_SCRIPT)) + ":" + str(os.path.getsize(BLENDER_SCRIPT))
    except OSError:
        stamp = "0"
    if os.path.exists(meta):
        try:
            with open(meta) as fh:
                cached = json.load(fh)
        except Exception:
            cached = {}
        if cached.get("script_stamp") == stamp and cached.get("frames") == frames:
            return out
        print("    cache is stale (script or frame count changed), re-running blender")
    blender = shutil.which("blender")
    if not blender:
        print("    blender not found on PATH -- skipping animated units "
              "(install it with: brew install --cask blender)")
        return None
    os.makedirs(out, exist_ok=True)
    # Hand Blender the bone-attached props so an animated unit keeps its helmet and spear.
    props_file = os.path.join(out, "_props.json")
    actor = CHARACTER_ACTORS[character]
    dae = os.path.join(MESH_ROOT, CHARACTER_MESHES[character])
    with open(props_file, "w") as fh:
        json.dump(unit_prop_spec(index, actor, skeleton_dae=dae) if index else [], fh)
    print(f"    running blender for {character}/{clip} ({frames} frames)...")
    r = subprocess.run([blender, "--background", "--python", BLENDER_SCRIPT, "--",
                        "--character", character, "--clip", clip,
                        "--frames", str(frames), "--out", out,
                        "--props", props_file],
                       capture_output=True, text=True, check=False)
    if not os.path.exists(meta):
        tail = "\n".join(r.stdout.splitlines()[-12:])
        print(f"    blender failed for {character}/{clip}:\n{tail}\n{r.stderr[-600:]}")
        return None
    try:
        with open(meta) as fh:
            data = json.load(fh)
        data["script_stamp"] = stamp
        with open(meta, "w") as fh:
            json.dump(data, fh, indent=1)
    except Exception:
        pass
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
    # A filtered bake writes the manifest too, so starting from an empty one would drop every
    # sprite it did not touch -- `--only ready` once left the page with sixteen entries and no
    # buildings, trees or villagers at all. Carry the existing table forward and let the bake
    # overwrite only the entries it actually rebuilds.
    if args.only:
        try:
            with open(os.path.join(args.out, "manifest.json")) as fh:
                manifest = json.load(fh)
            print(f"merging into the existing manifest ({len(manifest)} entries)")
        except (OSError, ValueError):
            pass

    def wanted(name):
        return not args.only or args.only in name

    def bake_one(name, actor, want, size, yaw=ISOMETRIC_YAW, include_props=True):
        print(f"  [{name}] {actor}" + (f" ({want})" if want else ""))
        pieces = build_pieces(index, actor, want, include_props=include_props)
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
            cache = blender_frame_cache(character, clip, nframes, cache_root, index)
            if cache is None:
                continue
            tex = skin_path(CHARACTER_SKINS[character])
            try:
                with open(os.path.join(cache, "meta.json")) as fh:
                    cmeta = json.load(fh)
            except Exception:
                cmeta = {}
            duration = cmeta.get("duration") or 1.0

            files = []
            frames = []
            prop_pieces = None
            for i in range(nframes):
                obj = os.path.join(cache, f"frame_{i:03d}.obj")
                if not os.path.exists(obj):
                    print(f"    missing {obj}")
                    continue
                verts, uvs, faces = load_obj(obj)
                if not verts or not faces:
                    continue
                # The body decides the axis; props share its frame, exactly as in the composite
                # path -- letting a prop guess for itself tilts it.
                up = detect_up_axis(verts)
                if prop_pieces is None:
                    # Built once, from the same rest placement the static bake uses, so a unit
                    # looks the same standing as walking.
                    prop_pieces = unit_prop_pieces(
                        index, CHARACTER_ACTORS[character],
                        os.path.join(MESH_ROOT, CHARACTER_MESHES[character]))
                    if prop_pieces:
                        print(f"    {len(prop_pieces)} props placed at rest")
                pieces = [Piece([reorder(v, up) for v in verts], uvs, faces, tex)] + prop_pieces
                frames.append(pieces)

            # One framing for the whole clip. Fitting each frame on its own makes the character
            # visibly change size as a limb or a spear swings wide.
            allv = [v for ps in frames for p in ps for v in p.verts]
            fit = project_fit([allv], size) if allv else None

            # A re-bake merged over an older manifest must not leave the previous frame count
            # behind -- sampling the same clip at fewer frames would otherwise keep the extra
            # entries alive and the page would play frames that no longer match the clip. Purged
            # here, before the new frames are written, so it cannot take them with it.
            for stale in [k for k in manifest if k.startswith(f"{name}_")]:
                del manifest[stale]

            for i, pieces in enumerate(frames):
                if not pieces:
                    continue
                img, meta = render(pieces, size, fit=fit)
                fn = f"{name}_{i}.png"
                img.save(os.path.join(args.out, fn))
                opaque = sum(1 for v in img.split()[3].get_flattened_data() if v > 128)
                manifest[f"{name}_{i}"] = {"file": fn, "w": size, "h": size,
                                           "fill": round(opaque / (size * size), 4), **meta}
                files.append(fn)
            if files:
                # Playback rate, not the source framerate: N frames sampled across `duration`
                # seconds must advance at N/duration per second to run at the clip's real speed.
                manifest[name] = {"group": "animation", "frames": len(files), "files": files,
                                  "clip": clip, "duration": duration,
                                  "fps": round(len(files) / duration, 3)}
                print(f"    -> {len(files)} frames over {duration}s "
                      f"(plays at {len(files) / duration:.2f} fps)"
                      + (f", {len(prop_pieces)} props" if prop_pieces else ""))

    print("\n== ground ==")
    bake_ground(args.out)

    manifest_json = json.dumps(manifest, indent=1, sort_keys=True)
    with open(os.path.join(args.out, "manifest.json"), "w") as f:
        f.write(manifest_json + "\n")
    # A script asset works in WKWebView's bundled file:// origin, where fetch() of a local JSON
    # file is rejected by WebKit's origin rules. index.html loads this before its game script.
    with open(os.path.join(args.out, "manifest.js"), "w") as f:
        f.write("window.POCKET_EMPIRES_SPRITES = " + manifest_json + ";\n")
    print(f"\nwrote {len(manifest)} sprites + manifest.json to {os.path.relpath(args.out, ROOT)}")


if __name__ == "__main__":
    main()
