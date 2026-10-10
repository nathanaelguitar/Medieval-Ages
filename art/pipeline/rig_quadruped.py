#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Rig and animate a four-legged TRELLIS.2 body (boar, sheep) for bake_sprites.py.

rig_body.py is built around a biped skeleton and retargeted human clips; game animals have no such
source, so this builds a small armature from the mesh itself and keys the clips procedurally:

* legs are found from the vertices near the ground (split left/right, then front/hind), the belly
  line from the lowest height at which the body spans front to hind legs unbroken;
* bones: root (on the ground), pelvis and chest (spine halves), neck, head, and an upper + lower
  bone per leg; weights are geometric (smooth bands at the belly line, the knee, the shoulders and
  the poll), which is more predictable on a fur/fleece shell than bone heat;
* clips: ``walk`` (lateral-sequence walk in place: diagonal legs half a cycle apart, foot lift on
  the swing, a small double bob and roll), ``idle`` (grazing: the head goes down to the grass and
  nibbles, lifts to look about, goes down again; slow breathing) and ``dead`` (one frame: rolled
  onto its side, legs out, head down, lying on the ground).

The output matches what bake_sprites.py reads: an armature ``Source`` carrying the actions
``clip_<name>`` (with a ``loop`` custom property), the textured mesh ``Body`` skinned to it, and an
empty ``Rig`` (no props). The body faces -Y like the units, so bake direction d1 faces screen-right.

    docker run --rm -u $(id -u):$(id -g) -e HOME=/tmp -v ~/medieval:/work medieval-blender \
        nice -n 10 blender --background --python art/pipeline/rig_quadruped.py -- \
        --body art/models/animals_v1/boar.glb --height 2.5 \
        --out art/models/animals_v1/boar_rig.blend --diag art/out/animals_v1/previews/boar
"""
import argparse
import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
# rig_body.py's helpers (GLB import with packed PBR textures, bounds, workbench filmstrips); its
# module body ends in main(), so only the definitions are executed
_src = open(os.path.join(HERE, "rig_body.py")).read().rsplit("\nmain()", 1)[0]
RB = {"__name__": "rig_body", "__file__": os.path.join(HERE, "rig_body.py")}
exec(compile(_src, os.path.join(HERE, "rig_body.py"), "exec"), RB)
FPS = 24


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--body", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--height", type=float, default=2.5, help="bbox height in rig units (a man is 4.2)")
    ap.add_argument("--yaw", type=float, default=0.0, help="degrees about Z that turn the head to -Y")
    ap.add_argument("--walk-frames", type=int, default=18, help="Blender frames per walk cycle at 24 fps")
    ap.add_argument("--idle-frames", type=int, default=72)
    ap.add_argument("--stride", type=float, default=24.0, help="upper-leg swing amplitude, degrees")
    ap.add_argument("--lift", type=float, default=50.0, help="lower-leg fold on the swing, degrees")
    ap.add_argument("--poll", type=float, default=0.47,
                    help="head pivot as a fraction of the way from the front legs to the snout")
    ap.add_argument("--graze-max", type=int, default=36, help="cap on the grazing neck angle, degrees")
    ap.add_argument("--diag", default=None, help="prefix for workbench filmstrips")
    return ap.parse_args(argv)


def smooth(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def kmeans2(v):
    a, b = float(np.percentile(v, 20)), float(np.percentile(v, 80))
    for _ in range(30):
        lab = np.abs(v - a) > np.abs(v - b)
        if lab.all() or (~lab).all():
            break
        a, b = float(v[~lab].mean()), float(v[lab].mean())
    return a, b


def main():
    a = parse_args()
    cache = os.path.join(os.path.dirname(os.path.abspath(a.out)), "_cache")
    os.makedirs(cache, exist_ok=True)
    RB["CACHE"][0] = cache
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = FPS

    # ---- body: import, turn head to -Y, scale to height, feet at z=0, centred
    body, imgs = RB["import_textured"](os.path.abspath(a.body), "Body")
    body.data.transform(Matrix.Rotation(math.radians(a.yaw), 4, "Z"))
    lo, hi = RB["bounds"](body)
    s = a.height / (hi.z - lo.z)
    body.data.transform(Matrix.Scale(s, 4))
    lo, hi = RB["bounds"](body)
    body.data.transform(Matrix.Translation((-(lo.x + hi.x) / 2, -(lo.y + hi.y) / 2, -lo.z)))
    bpy.context.view_layer.update()
    body["team_textures"] = json.dumps({})
    # fur and fleece are dielectric: TRELLIS.2 sometimes predicts metallic ~1 for dark fur (the
    # boar's shape pass did), which renders as dull metal in Cycles. Unhook metallic, pin it to 0.
    for mat in body.data.materials:
        if not (mat and mat.node_tree):
            continue
        for nd in mat.node_tree.nodes:
            if nd.type == "BSDF_PRINCIPLED":
                for l in list(nd.inputs["Metallic"].links):
                    mat.node_tree.links.remove(l)
                nd.inputs["Metallic"].default_value = 0.0
    V = RB["world_verts"](body).astype(np.float64)
    lo, hi = V.min(0), V.max(0)
    H, L = hi[2], hi[1] - lo[1]
    print(f"== body x{s:.3f}: {len(V)} verts, length {L:.2f} width {hi[0]-lo[0]:.2f} height {H:.2f}")

    # ---- anatomy from the mesh
    low = V[V[:, 2] < 0.12 * H]
    cx = float(np.median(low[:, 0]))
    legs = {}
    for side, sel in (("L", low[:, 0] >= cx), ("R", low[:, 0] < cx)):
        pts = low[sel]
        yf, yh = kmeans2(pts[:, 1])                    # front (smaller y: the head is at -Y), hind
        for end, yc in (("F", yf), ("H", yh)):
            near = pts[np.abs(pts[:, 1] - yc) < 0.12 * L]
            legs[side + end] = (float(near[:, 0].mean()), float(near[:, 1].mean()),
                                float(np.sqrt(near[:, 0].var() + near[:, 1].var())))
    front_y = (legs["LF"][1] + legs["RF"][1]) / 2
    hind_y = (legs["LH"][1] + legs["RH"][1]) / 2
    if front_y > hind_y:
        sys.exit(f"front legs behind the hind legs (front {front_y:.2f}, hind {hind_y:.2f}): wrong --yaw?")
    mid_y = (front_y + hind_y) / 2
    # belly line: the lowest slice in which the body spans front to hind legs unbroken
    z_b = 0.5 * H
    for z in np.arange(0.12 * H, 0.85 * H, 0.01 * H):
        sl = V[(np.abs(V[:, 2] - z) < 0.015 * H) & (V[:, 1] > front_y) & (V[:, 1] < hind_y)]
        occ = np.unique(((sl[:, 1] - front_y) / (hind_y - front_y) * 24).astype(int)).size / 24
        if occ > 0.92:
            z_b = float(z)
            break
    z_knee = 0.5 * z_b
    top = V[(V[:, 1] > front_y) & (V[:, 1] < hind_y)][:, 2].max()
    z_spine = (z_b + top) / 2
    y_poll = front_y - a.poll * (front_y - lo[1])
    head_pts = V[V[:, 1] < y_poll]
    snout = head_pts[np.argmin(head_pts[:, 1])]
    z_poll = float(np.percentile(V[np.abs(V[:, 1] - y_poll) < 0.03 * L][:, 2], 60))
    print(f"   legs {{{', '.join(f'{k}: ({v[0]:+.2f},{v[1]:+.2f}) r{v[2]:.2f}' for k, v in legs.items())}}}")
    print(f"   belly z {z_b:.2f}, knee z {z_knee:.2f}, spine z {z_spine:.2f}, top {top:.2f}, "
          f"poll y {y_poll:.2f} z {z_poll:.2f}, snout {tuple(round(float(x), 2) for x in snout)}")

    # ---- armature
    arm_d = bpy.data.armatures.new("Source")
    arm = bpy.data.objects.new("Source", arm_d)
    scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm_d.edit_bones

    def bone(name, h, t, parent=None):
        b = eb.new(name)
        b.head, b.tail = Vector(h), Vector(t)
        b.roll = 0.0
        if parent:
            b.parent = eb[parent]
        return b
    bone("root", (0, mid_y, 0), (0, mid_y, 0.3 * H))
    bone("pelvis", (0, mid_y, z_spine), (0, hind_y, z_spine), "root")
    # the neck pivots a little ahead of and below the withers, so a lowered head swings out and down
    # instead of folding back into the chest
    y_neck, z_neck = front_y - 0.06 * L, z_spine - 0.08 * H
    bone("chest", (0, mid_y, z_spine), (0, y_neck, z_neck), "root")
    bone("neck", (0, y_neck, z_neck), (0, y_poll, z_poll), "chest")
    bone("head", (0, y_poll, z_poll), (0, float(snout[1]), float(snout[2])), "neck")
    for k, (lx, ly, _) in legs.items():
        par = "chest" if k[1] == "F" else "pelvis"
        bone(f"upper_{k}", (lx, ly, z_b + 0.04 * H), (lx, ly, z_knee), par)
        bone(f"lower_{k}", (lx, ly, z_knee), (lx, ly, 0.0), f"upper_{k}")
    bpy.ops.object.mode_set(mode="OBJECT")
    names = [b.name for b in arm_d.bones]

    # ---- geometric weights
    W = {n: np.zeros(len(V)) for n in names}
    leg_r = np.mean([v[2] for v in legs.values()])
    band = 0.06 * H
    t_leg = smooth(z_b + band, z_b - band, V[:, 2])
    side = np.where(V[:, 0] >= cx, "L", "R")
    end = np.where(V[:, 1] < mid_y, "F", "H")
    for k, (lx, ly, _) in legs.items():
        sel = (side == k[0]) & (end == k[1])
        d = np.hypot(V[:, 0] - lx, V[:, 1] - ly)
        t = t_leg * sel * smooth(3.0 * leg_r, 2.0 * leg_r, d)    # fleece hanging between the legs stays body
        lowf = smooth(z_knee + 0.05 * H, z_knee - 0.05 * H, V[:, 2])
        W[f"lower_{k}"] += t * lowf
        W[f"upper_{k}"] += t * (1 - lowf)
    rest = 1 - sum(W[f"{p}_{k}"] for p in ("upper", "lower") for k in legs)
    t_head = smooth(y_poll + 0.04 * L, y_poll - 0.04 * L, V[:, 1])
    t_neck = smooth(front_y + 0.02 * L, front_y - 0.10 * L, V[:, 1]) * (1 - t_head)
    # the throat and chest below the neck stay with the chest
    t_neck *= smooth(z_b, z_spine, V[:, 2]) * 0.6 + 0.4 * (V[:, 1] < front_y - 0.1 * L)
    t_body = 1 - t_head - t_neck
    t_pel = smooth(mid_y - 0.12 * L, mid_y + 0.12 * L, V[:, 1])
    W["head"] += rest * t_head
    W["neck"] += rest * t_neck
    W["pelvis"] += rest * t_body * t_pel
    W["chest"] += rest * t_body * (1 - t_pel)
    for n in names:
        if n == "root":
            continue
        vg = body.vertex_groups.new(name=n)
        for i in np.nonzero(W[n] > 1e-3)[0]:
            vg.add([int(i)], float(W[n][i]), "REPLACE")
    body.parent = arm
    mod = body.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    rig = bpy.data.objects.new("Rig", None)          # bake_sprites.py looks props up under "Rig"
    scene.collection.objects.link(rig)
    print(f"== weights: {sum(1 for v in body.data.vertices if v.groups)}/{len(V)} vertices, {len(names) - 1} groups")

    # ---- posing helpers: rotations given about WORLD axes in each bone's rest frame
    pbs = arm.pose.bones
    for pb in pbs:
        pb.rotation_mode = "QUATERNION"

    def rest3(n):
        return arm_d.bones[n].matrix_local.to_3x3()

    def rot(n, axis, deg):
        """Quaternion for a rotation about a world axis, expressed in bone n's local frame."""
        ax = rest3(n).inverted() @ Vector(axis)
        return Quaternion(ax.normalized(), math.radians(deg))

    def loc(n, world):
        return rest3(n).inverted() @ Vector(world)

    def key_pose(frame, pose):
        """pose: {bone: (quaternion or None, location or None)}"""
        for pb in pbs:
            q, l = pose.get(pb.name, (None, None))
            pb.rotation_quaternion = q if q is not None else Quaternion()
            pb.location = l if l is not None else Vector()
            pb.keyframe_insert("rotation_quaternion", frame=frame)
            pb.keyframe_insert("location", frame=frame)

    def new_action(name, loop):
        act = bpy.data.actions.new(f"clip_{name}")
        act.use_fake_user = True
        act["loop"] = bool(loop)
        arm.animation_data.action = act
        return act
    arm.animation_data_create()
    X, Y, Z = (1, 0, 0), (0, 1, 0), (0, 0, 1)
    HEAD_K = 0.9          # share of the dip taken at the poll, on top of the neck

    # rotating a downward leg about +X by +deg swings its foot back (+Y); forward is negative.
    # the neck/head point forward (-Y): +deg about +X lowers them.
    def head_down_angle():
        """Neck angle (with the head adding half again) at which the snout reaches the grass. Capped:
        a long-legged animal cannot reach the ground by the neck alone, and past ~60 degrees the
        head folds under the chest; at sprite scale a muzzle a little above the turf reads as grazing."""
        tip = Vector(snout)
        for deg in range(0, a.graze_max + 1, 2):
            pbs["neck"].rotation_quaternion = rot("neck", X, deg)
            pbs["head"].rotation_quaternion = rot("head", X, deg * HEAD_K)
            bpy.context.view_layer.update()
            hb = pbs["head"]
            w = arm.matrix_world @ hb.matrix @ arm_d.bones["head"].matrix_local.inverted() @ tip
            if w.z < 0.12 * H:
                break
        pbs["neck"].rotation_quaternion = Quaternion()
        pbs["head"].rotation_quaternion = Quaternion()
        return deg
    graze = head_down_angle()
    print(f"   grazing neck angle {graze} deg")

    # ---- walk: lateral sequence LH, LF, RH, RF a quarter cycle apart
    N = a.walk_frames
    new_action("walk", True)
    offs = {"LH": 0.0, "LF": 0.25, "RH": 0.5, "RF": 0.75}
    for f in range(N + 1):
        ph = f / N
        pose = {}
        for k, o in offs.items():
            p = 2 * math.pi * (ph - o)
            fwd = a.stride * math.sin(p)                      # >0: leg ahead of the hip
            lift = a.lift * max(0.0, math.cos(p)) ** 2        # fold while swinging forward
            if k[1] == "H":
                fwd *= 0.9
            pose[f"upper_{k}"] = (rot(f"upper_{k}", X, -fwd - 0.35 * lift), None)
            pose[f"lower_{k}"] = (rot(f"lower_{k}", X, lift), None)
        bob = 0.012 * H * math.cos(4 * math.pi * ph)
        roll = 2.0 * math.sin(2 * math.pi * ph)
        pose["pelvis"] = (rot("pelvis", Y, roll), loc("pelvis", (0, 0, bob)))
        pose["chest"] = (rot("chest", Y, -roll), loc("chest", (0, 0, bob)))
        pose["neck"] = (rot("neck", X, 4.0 + 3.0 * math.sin(4 * math.pi * ph + 0.6)), None)
        key_pose(f + 1, pose)

    # ---- idle: grazing. Head down nibbling, up to look about at mid-cycle, down again
    N = a.idle_frames
    new_action("idle", True)
    for f in range(N + 1):
        ph = f / N
        up = float(smooth(0.38, 0.5, ph) * (1 - smooth(0.66, 0.8, ph)))   # 0 grazing .. 1 looking up
        nib = 0.0 if up > 0.5 else 3.0 * math.sin(2 * math.pi * 6 * ph) * (1 - up)
        neck = graze * (1 - up) + 4.0 * up + nib
        head = HEAD_K * graze * (1 - up) - 6.0 * up * math.sin(math.pi * float(smooth(0.42, 0.74, ph)))
        breathe = 0.006 * H * math.sin(2 * math.pi * 2 * ph)
        look = 10.0 * up * math.sin(2 * math.pi * (ph - 0.4) * 1.5)
        pose = {"neck": (rot("neck", X, neck) @ rot("neck", Z, look), None),
                "head": (rot("head", X, head), None),
                "chest": (None, loc("chest", (0, 0, breathe))),
                "pelvis": (None, loc("pelvis", (0, 0, breathe * 0.5)))}
        # weight shifts onto the forelegs a little when grazing
        for k in legs:
            pose[f"upper_{k}"] = (rot(f"upper_{k}", X, (-4.0 if k[1] == "F" else 2.0) * (1 - up)), None)
        key_pose(f + 1, pose)

    # ---- dead: rolled onto the left side, legs out, head down, on the ground
    new_action("dead", False)

    def dead_pose(dz):
        pose = {"root": (rot("root", Y, -90.0), loc("root", (0, 0, dz))),
                "neck": (rot("neck", X, 12.0), None),
                "head": (rot("head", X, 8.0), None)}
        for k in legs:
            pose[f"upper_{k}"] = (rot(f"upper_{k}", X, -18.0 if k[1] == "F" else 22.0), None)
            pose[f"lower_{k}"] = (rot(f"lower_{k}", X, 12.0), None)
        return pose
    key_pose(1, dead_pose(0.0))
    key_pose(2, dead_pose(0.0))
    scene.frame_set(1)
    bpy.context.view_layer.update()
    zmin = float(RB["evaluated_points"]([body])[:, 2].min()) if "evaluated_points" in RB else None
    if zmin is None:
        dg = bpy.context.evaluated_depsgraph_get()
        ev = body.evaluated_get(dg)
        me = ev.to_mesh()
        zmin = min((ev.matrix_world @ v.co).z for v in me.vertices)
        ev.to_mesh_clear()
    # root rotates about its head on the ground; lift (in world z, which the -90 roll has not moved)
    for fr in (1, 2):
        pbs["root"].rotation_quaternion = rot("root", Y, -90.0)
        pbs["root"].location = loc("root", (0, 0, -zmin))
        pbs["root"].keyframe_insert("location", frame=fr)
    print(f"   dead: lowest point {zmin:+.2f} -> lifted {-zmin:.2f}")

    # ---- diagnostics: workbench filmstrips (side / front / 3-4)
    if a.diag:
        os.makedirs(os.path.dirname(a.diag) or ".", exist_ok=True)
        for name, n in (("walk", 12), ("idle", 12), ("dead", 1)):
            act = bpy.data.actions[f"clip_{name}"]
            arm.animation_data.action = act
            RB["diag_strip"](f"{a.diag}_{name}", [body], arm, act, n)

    for img in list(bpy.data.images):
        if img.users == 0 and not img.use_fake_user:
            bpy.data.images.remove(img)
            continue
        if img.packed_file is None and img.has_data:
            img.pack()
    arm.animation_data.action = bpy.data.actions["clip_idle"]
    scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(a.out))
    print(f"== wrote {a.out}")


main()
