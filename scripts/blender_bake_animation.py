#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Bake an animated 0 A.D. character into per-frame OBJ meshes.

    blender --background --python scripts/blender_bake_animation.py -- \
        --character villager --clip walk --frames 12 --out /tmp/unitcache

Writes `frame_000.obj` … plus `meta.json`. Those feed `bake_zeroad_art.py`, which rasterises
them with the same isometric renderer used for the buildings.

Why this split: applying a skin to an animated skeleton means linear blend skinning, which Blender
already does well. Re-implementing glTF animation sampling and LBS in the bake tool would be a
second, worse renderer. Blender exports the *deformed geometry* per frame, and the existing
rasteriser keeps units lit and projected exactly like everything else.

Two things this has to work around, both established by probing:

* Blender 5.2 has no COLLADA importer, so both the mesh and the clip come in via assimp -> glTF.
* The clip files carry their own base-biped mesh and armature. Only the **action** is wanted; it is
  moved onto the character's armature and the clip's objects are discarded. This works because the
  bundled rigs and the clips share 0 A.D.'s `Biped_*` bone naming (102 of 103 channel targets match
  exactly; the odd one out is the armature root object, not a bone).

Original artwork is CC BY-SA 3.0, (C) Wildfire Games; see ios/ZeroADArt/LICENSE.txt.
"""

import argparse
import json
import os
import struct
import subprocess
import sys

import bpy
from mathutils import Matrix


def m4(floats):
    """Row-major 16 floats -> mathutils Matrix (which is also row-major indexed)."""
    return Matrix([list(floats[0:4]), list(floats[4:8]), list(floats[8:12]), list(floats[12:16])])

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ART = os.path.join(ROOT, "ios", "ZeroADArt")
MESH_ROOT = os.path.join(ART, "meshes")
SKIN_ROOT = os.path.join(ART, "textures", "skins")
ANIM_ROOT = os.path.join(ART, "animations")

CHARACTERS = {
    "villager": {
        "mesh": "skeletal/new/f_dress.dae",
        "skin": "skeletal/hele/dress_female_01.png",
        "clips": {"walk": "biped/citizen/walk_relax_f.dae",
                  "idle": "biped/citizen/idle_relax_f.dae"},
    },
    "soldier": {
        "mesh": "skeletal/new/m_armor_tunic_short.dae",
        "skin": "skeletal/athen/linothorax_lamellar_01_03.png",
        # Relax rather than ready. These props are not rendered (see the prop note in
        # bake_zeroad_art.py), so the weapon-ready stance reads as a wide brace holding nothing:
        # measured content width swings 30/46/30px against relax's 24/32/22, and the villager's
        # natural walk is 32/20/30. The shield variants are worse still, holding an arm out for a
        # shield that is not there.
        "clips": {"walk": "biped/infantry/spearman/walk_relax.dae",
                  "idle": "biped/infantry/spearman/idle_relax.dae",
                  # alternates, kept so the stance can be compared without re-downloading
                  "walk_ready": "biped/infantry/spearman/walk_ready.dae",
                  "idle_ready": "biped/infantry/spearman/idle_ready.dae"},
    },
    "boar": {
        "mesh": "skeletal/animal_boar.dae",
        "skin": "skeletal/animal_boar_01.png",
        "clips": {"walk": "quadraped/animal_boar_walk_01.dae",
                  "idle": "quadraped/animal_boar_idle_02.dae"},
    },
    "sheep": {
        "mesh": "skeletal/sheep.dae",
        "skin": "skeletal/animal_sheep_a.dds",
        "clips": {"walk": "quadraped/sheep_walk.dae",
                  "idle": "quadraped/sheep_idle_01.dae"},
    },
}

FPS = 24


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--character", default="villager", choices=sorted(CHARACTERS))
    ap.add_argument("--clip", default="walk",
                    help="clip name; which are available depends on --character "
                         f"({', '.join(sorted({c for v in CHARACTERS.values() for c in v['clips']}))})")
    ap.add_argument("--frames", type=int, default=12, help="frames to sample across the clip")
    ap.add_argument("--out", required=True)
    ap.add_argument("--props", help="JSON list of {mesh, skin, bone} props to attach, written by "
                                    "bake_zeroad_art.py from the actor's <props> graph")
    args = ap.parse_args(argv)
    if args.clip not in CHARACTERS[args.character]["clips"]:
        sys.exit(f"{args.character} has no '{args.clip}' clip; "
                 f"available: {sorted(CHARACTERS[args.character]['clips'])}")
    return args


def action_fcurves(action):
    """Blender 4.4 replaced `action.fcurves` with slotted actions, where curves live under
    layers -> strips -> channelbags. Support both so this does not silently see zero curves."""
    direct = getattr(action, "fcurves", None)
    if direct:
        return list(direct)
    out = []
    for layer in getattr(action, "layers", []):
        for strip in layer.strips:
            for bag in getattr(strip, "channelbags", []):
                out.extend(bag.fcurves)
    return out


def deformed_points(obj):
    """World-space vertices of obj with modifiers (i.e. the armature) evaluated."""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    pts = [ev.matrix_world @ v.co for v in me.vertices]
    ev.to_mesh_clear()
    return pts


def to_gltf(dae, glb):
    if not os.path.exists(dae):
        sys.exit(f"missing source: {dae}")
    r = subprocess.run(["assimp", "export", dae, glb], capture_output=True, text=True, check=False)
    if r.returncode != 0 or not os.path.exists(glb):
        sys.exit(f"assimp failed on {dae}:\n{r.stderr}")
    # Assimp 6 writes one boar animation ID as a Latin-1 byte in its GLB JSON chunk, even though
    # the DAE is valid UTF-8. Repair malformed UTF-8 in the JSON chunk only; this keeps the binary
    # vertex/animation buffers byte-for-byte intact and gives Blender valid glTF input.
    with open(glb, "rb") as fh:
        data = fh.read()
    if data[:4] == b"glTF" and len(data) >= 20:
        total = struct.unpack_from("<I", data, 8)[0]
        offset, chunks, changed = 12, [], False
        while offset + 8 <= min(total, len(data)):
            length, kind = struct.unpack_from("<I4s", data, offset)
            start, end = offset + 8, offset + 8 + length
            if end > len(data):
                break
            chunk = data[start:end]
            if kind == b"JSON":
                fixed = chunk.decode("utf-8", errors="replace").encode("utf-8")
                fixed += b" " * ((-len(fixed)) % 4)
                changed |= fixed != chunk
                chunk = fixed
            chunks.append((kind, chunk))
            offset = end
        if changed:
            body = b"".join(struct.pack("<I4s", len(chunk), kind) + chunk
                             for kind, chunk in chunks)
            with open(glb, "wb") as fh:
                fh.write(struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body)
    return glb


def main():
    args = parse_args()
    spec = CHARACTERS[args.character]
    mesh_rel, skin_rel = spec["mesh"], spec["skin"]
    clip_rel = spec["clips"][args.clip]
    mesh_dae = os.path.join(MESH_ROOT, mesh_rel)
    clip_dae = os.path.join(ANIM_ROOT, clip_rel)
    skin = os.path.join(SKIN_ROOT, skin_rel)

    os.makedirs(args.out, exist_ok=True)
    cache = os.path.join(args.out, "_glb")
    os.makedirs(cache, exist_ok=True)
    mesh_glb = to_gltf(mesh_dae, os.path.join(cache, "mesh.glb"))
    clip_glb = to_gltf(clip_dae, os.path.join(cache, "clip.glb"))

    # ---- the character: armature + skinned mesh, plus the base colour map the DAE cannot resolve
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=mesh_glb)
    for obj in [o for o in bpy.data.objects if o.type == "MESH" and not o.vertex_groups]:
        bpy.data.objects.remove(obj, do_unlink=True)
    arm = next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
    body = next((o for o in bpy.data.objects if o.type == "MESH" and o.vertex_groups), None)
    if arm is None or body is None:
        sys.exit("mesh import did not yield a skinned armature + mesh pair")

    img = bpy.data.images.load(skin)
    for mat in bpy.data.materials:
        if mat.node_tree is None:
            continue
        bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if bsdf is None:
            continue
        tex = mat.node_tree.nodes.new("ShaderNodeTexImage")
        tex.image = img
        mat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])

    rig_bones = {b.name for b in arm.data.bones}

    # ---- the clip: take only its action, then throw the rest of it away
    before = set(bpy.data.actions)
    bpy.ops.import_scene.gltf(filepath=clip_glb)
    new_actions = [a for a in bpy.data.actions if a not in before]
    if not new_actions:
        sys.exit("clip import produced no action -- assimp may not have carried the animation")
    action = max(new_actions, key=lambda a: len(action_fcurves(a)))

    # drop the clip's own objects; its action survives because it is now referenced by us
    for obj in list(bpy.data.objects):
        if obj is not arm and obj is not body:
            bpy.data.objects.remove(obj, do_unlink=True)

    if arm.animation_data is None:
        arm.animation_data_create()
    arm.animation_data.action = action
    # 4.4+ actions are inert until a slot is bound. Assigning the action alone leaves the rig
    # static, which is silent: every sampled frame comes out identical.
    if hasattr(arm.animation_data, "action_slot"):
        slots = list(getattr(action, "slots", []))
        if slots:
            arm.animation_data.action_slot = slots[0]
            print(f"   bound action slot '{slots[0].identifier}'")

    # ---- verify the action actually drives this rig before writing anything
    curves = action_fcurves(action)
    driven = {fc.data_path.split('"')[1] for fc in curves if 'pose.bones["' in fc.data_path}
    matched = driven & rig_bones
    print(f"== {args.character} / {args.clip}")
    print(f"   action '{action.name}': {len(curves)} curves, "
          f"{len(driven)} bones driven, {len(matched)} of them exist on this rig")
    if not matched:
        sys.exit("action drives no bones present on this rig -- refusing to write empty frames")

    # ---- bone-attached props: helmet, shield, spear, greaves. Each keeps its own texture, so each
    # is exported as its own OBJ per frame rather than merged into the body's. The rig arrives
    # pruned to its deform bones, so a prop whose own bone was dropped follows the nearest ancestor
    # that survived, offset by the difference between the two rest matrices.
    prop_objs = []
    if args.props and os.path.exists(args.props):
        with open(args.props) as fh:
            spec = json.load(fh)
        for i, p in enumerate(spec):
            try:
                glb = to_gltf(os.path.join(MESH_ROOT, p["mesh"]),
                              os.path.join(cache, f"prop{i}.glb"))
            except SystemExit:
                continue
            known = set(bpy.data.objects)
            bpy.ops.import_scene.gltf(filepath=glb)
            added = [o for o in bpy.data.objects if o not in known]
            mesh_obj = next((o for o in added if o.type == "MESH"), None)
            for o in added:            # drop any armature or stray the prop file brought along
                if o is not mesh_obj:
                    bpy.data.objects.remove(o, do_unlink=True)
            if mesh_obj is None:
                continue
            present = [b for b in p["chain"] if b in arm.pose.bones]
            if not present:
                print(f"   prop {p['mesh']}: none of {p['chain']} survive on this rig, skipped")
                bpy.data.objects.remove(mesh_obj, do_unlink=True)
                continue
            follow = present[0]
            offset = m4(p["rests"][follow]).inverted() @ m4(p["rests"][p["target"]])
            if follow != p["target"]:
                print(f"   prop {os.path.basename(p['mesh'])}: {p['target']} dropped by the glTF "
                      f"hop, following {follow}")
            prop_objs.append({"obj": mesh_obj, "follow": follow, "offset": offset,
                              "skin": p["skin"], "i": i})
        print(f"   {len(prop_objs)} of {len(spec)} props attached")

    start, end = action.frame_range
    scene = bpy.context.scene
    scene.render.fps = FPS
    print(f"   clip spans frames {start:.0f}..{end:.0f} at {FPS}fps "
          f"({(end - start) / FPS:.2f}s)")

    # ---- sample the cycle. Frame `end` is the same pose as `start` in a loop, so use half-open
    # sampling and let the game wrap; including it would double the last pose.
    span = end - start
    step = span / args.frames
    written = []
    prop_files = []
    reference = None
    max_delta = 0.0

    def export_one(obj, path):
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.wm.obj_export(filepath=path, export_selected_objects=True,
                              apply_modifiers=True, export_materials=False,
                              export_uv=True, export_normals=True)

    for i in range(args.frames):
        f = start + i * step
        scene.frame_set(int(f), subframe=f - int(f))
        bpy.context.view_layer.update()
        pts = deformed_points(body)
        if reference is None:
            reference = pts
        else:
            max_delta = max(max_delta,
                            max((a - b).length for a, b in zip(pts, reference)))
        name = f"frame_{i:03d}.obj"
        export_one(body, os.path.join(args.out, name))
        written.append(name)
        for p in prop_objs:
            # The prop geometry is authored in its bone's local space, so the *pose* matrix of the
            # bone it follows places it -- at rest that equals the rest matrix, which is what the
            # static bake resolves straight from the COLLADA scene.
            p["obj"].matrix_world = (arm.matrix_world
                                     @ arm.pose.bones[p["follow"]].matrix
                                     @ p["offset"])
            pname = f"frame_{i:03d}_p{p['i']}.obj"
            export_one(p["obj"], os.path.join(args.out, pname))
            if i == 0:
                prop_files.append({"index": p["i"], "texture": p["skin"],
                                   "target": p["follow"], "bone": p["follow"]})
        print(f"   frame {i:3d}  t={(f - start) / FPS:.3f}s -> {name}"
              + (f" + {len(prop_objs)} props" if prop_objs else ""))

    # A rig that never moves produces a flawless-looking sprite sheet of one frozen pose, so this
    # is checked rather than assumed.
    print(f"   max vertex movement across the cycle: {max_delta:.4f}")
    if max_delta < 1e-4:
        sys.exit("frames are identical -- the action is not driving this rig; "
                 "check the action slot binding and the bone names")

    with open(os.path.join(args.out, "meta.json"), "w") as fh:
        json.dump({"character": args.character, "clip": args.clip, "frames": args.frames,
                   "fps": FPS, "duration": round(span / FPS, 4),
                   "texture": os.path.relpath(skin, ART), "files": written,
                   "props": prop_files}, fh, indent=1)
        fh.write("\n")
    print(f"   wrote {len(written)} frames + meta.json to {args.out}")


main()
