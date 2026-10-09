#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Rig a Hunyuan3D body to 0 A.D.'s biped skeleton and attach sword + shield. Runs inside Blender:

On the DGX Spark (no native Blender for Linux ARM64; Ubuntu's 4.0.2 runs in the image built from
art/pipeline/docker/Dockerfile, `docker build -t medieval-blender art/pipeline/docker`), with the
repo subset synced to ~/medieval:

    docker run --rm -u $(id -u):$(id -g) -e HOME=/tmp -v ~/medieval:/work medieval-blender \
        nice -n 10 blender --background --python art/pipeline/rig_body.py -- ...same arguments...

On the Mac:

    blender --background --python art/pipeline/rig_body.py -- \
        --body art/models/man_at_arms/man_at_arms_blue.glb \
        --alt red=art/models/man_at_arms/man_at_arms_red.glb \
        --shield art/models/man_at_arms/shield_blue.glb --shield-alt red=art/models/man_at_arms/shield_red.glb \
        --clip idle=art/source/zeroad_clips/biped/infantry/swordsman/idle_relax_shield_01.dae \
        --clip walk=art/source/zeroad_clips/biped/infantry/swordsman/walk_relax_shield.dae \
        --out art/models/man_at_arms/man_at_arms_rig.blend --diag art/out/man_at_arms/previews/rig_diag

v2 (TRELLIS.2 PBR bodies in art/models/man_at_arms_v2, same geometry for both teams, base colour +
metallic-roughness maps per team; smaller arming sword hanging down at rest):

    docker run --rm -u $(id -u):$(id -g) -e HOME=/tmp -v ~/medieval:/work medieval-blender \
        nice -n 10 blender --background --python art/pipeline/rig_body.py -- \
        --body art/models/man_at_arms_v2/man_at_arms_blue.glb \
        --alt red=art/models/man_at_arms_v2/man_at_arms_red.glb \
        --shield art/models/man_at_arms_v2/shield_blue.glb --shield-alt red=art/models/man_at_arms_v2/shield_red.glb \
        --clip idle=art/source/zeroad_clips/biped/infantry/swordsman/idle_relax_shield_01.dae \
        --clip walk=art/source/zeroad_clips/biped/infantry/swordsman/walk_relax_shield.dae \
        --sword-length 2.0 --sword-blade-w 0.11 --sword-guard-w 0.40 --sword-dir 0,0.15,-1 \
        --out art/models/man_at_arms_v2/man_at_arms_rig.blend --diag art/out/man_at_arms_v2/previews/rig_diag

Clips are a swappable module: ``--clip name=path.dae`` (0 A.D. biped, CC BY-SA, placeholder) are
converted with assimp and bound to the ``Source`` armature; ``--clip name=path.json`` is a
video-derived planar clip from video_to_clip.py (MediaPipe on a Veo side view), retargeted onto
Source by ``video_to_clip.build_action`` after the props are placed: its arms start from frame 1
of the first (.dae) clip, so give the idle first. v3 man-at-arms:

    ... --body art/models/man_at_arms_v3/man_at_arms_blue.glb --alt red=art/models/man_at_arms_v3/man_at_arms_red.glb \
        --shield art/models/man_at_arms_v3/shield_blue.glb --shield-alt red=art/models/man_at_arms_v3/shield_red.glb \
        --clip idle=art/source/zeroad_clips/biped/infantry/swordsman/idle_relax_shield_01.dae \
        --clip walk=art/out/man_at_arms_v2/motion/walk_clip.json \
        --sword-length 2.0 --sword-blade-w 0.11 --sword-guard-w 0.40 --sword-dir 0,0.15,-1 \
        --out art/models/man_at_arms_v3/man_at_arms_rig.blend --diag art/out/man_at_arms_v3/previews/rig_diag

(copy v2's ``_cache/*.glb`` next to the new .blend first: assimp 5.3 cannot convert the idle).
v4 adds one-shot clips from video_to_clip.py's ``oneshot`` mode (``--clip attack=...json
--clip death=...json``; see art/pipeline/run_v4.sh) and, with ``--diag``, a Workbench filmstrip
per video clip (``<clip>_strip.png``: ``--strip-frames`` frames x side/front/3-4 views) so the
motion is judged before any Cycles bake.
To move to Mixamo, export Mixamo FBX clips to glTF, import them as the Source armature instead
(``to_glb`` is skipped for .glb paths once added) and map bone names Biped_* -> mixamorig:* in
the COPY_TRANSFORMS block below.

Structure (so any future 0 A.D. clip retargets with no rework):

* ``Source`` armature: 0 A.D.'s biped exactly as imported (assimp -> glTF, 24 deform bones). The
  clips' actions are bound to it and it is never edited.
* ``Rig`` armature: a duplicate whose rest pose is fitted to the body (arms swung to the modelled
  A-pose angle, then "apply pose as rest"). The body is bound to it with automatic weights. Each
  bone copies its Source twin's world transform through a constraint, so playing a clip on Source
  drives the body.
* Props (sword, shield) are bone-parented to the Rig's hands.

The body is scaled so that it stands ``--height`` 0 A.D. units tall (the bundled biped is 3.95 to
the top of the head; helmets add a little), which keeps the sprites on the same scale as the
existing 0 A.D.-derived units without retuning the game's footprint scaling.

Blender 5.2 has no COLLADA importer, so every .dae goes through ``assimp export`` first (the same
route scripts/blender_bake_animation.py takes).
"""
import argparse
import json
import math
import os
import subprocess
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)                 # video_to_clip.build_action for JSON clips
BIPED_DAE = os.path.join(ROOT, "ios", "ZeroADArt", "meshes", "skeletal", "new", "m_armor_tunic_short.dae")
PROP_BONES = os.path.join(HERE, "zeroad_prop_bones.json")

TEAM_PROP = "team_textures"   # custom property on the body object: {team: image name}
CACHE = [None]                # set in main(): directory for converted/extracted intermediates


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--body", required=True, help="textured body GLB (primary team)")
    ap.add_argument("--alt", action="append", default=[], help="team=glb: same mesh with another texture")
    ap.add_argument("--shield", help="textured shield GLB")
    ap.add_argument("--shield-alt", action="append", default=[], help="team=glb")
    ap.add_argument("--clip", action="append", required=True, help="name=path.dae")
    ap.add_argument("--out", required=True, help=".blend to write")
    ap.add_argument("--diag", help="directory for diagnostic renders")
    ap.add_argument("--strip-frames", type=int, default=12, help="frames per video-clip filmstrip in --diag")
    ap.add_argument("--height", type=float, default=4.2, help="body height in 0 A.D. units")
    ap.add_argument("--arm-delta", type=float, default=None,
                    help="degrees to swing the rig's upper arms outward (default: measured from the mesh)")
    ap.add_argument("--sword", default="auto", help="'auto' builds a procedural sword; 'none' skips it; or a GLB path")
    # v1 archer/villagers: generic props. Fields separated by ';' (vectors use ','):
    #   name=<kind or GLB path>  kind: bow, axe, pickaxe, hoe, hammer, basket, log
    #   bone=Biped_hand_R        clips=chop|carry (bake visibility; omit = every clip)
    #   at=chop:0.4              clip and phase the prop is placed at (default: base clip, frame 1)
    #   pos=x,y,z                world offset from the bone head
    #   dir=hand | x,y,z         the prop's long axis (local +Y): along the bone, or a world vector
    #   pitch=deg                extra rotation of dir about world X (+ tips the far end up)
    #   along=0..1               origin moved along the bone (0 = head, 1 = tail)
    #   edge=x,y,z               world direction of the prop's local +X (blade edge, hammer face, basket arc)
    #   size=..                  overall size in rig units (kind-specific default)
    ap.add_argument("--prop", action="append", default=[], help="name=kind;bone=..;clips=a|b;at=clip:phase;dir=hand;...")
    # prop placement knobs, in the hand bone's frame (x: across palm, y: along bone head->tail, z: out of palm)
    # Props are placed in WORLD terms at frame 1 of the first clip (the idle stance), then
    # bone-parented so they follow the hands. Offsets are from the hand bone's head.
    ap.add_argument("--sword-pos", default="0,-0.05,-0.1", help="grip centre offset from hand_R head (world)")
    ap.add_argument("--sword-dir", default="0,-0.3,-1", help="blade direction (world)")
    ap.add_argument("--sword-flat", default="1,0,0", help="direction the flat of the blade faces (world)")
    ap.add_argument("--shield-pos", default="0.35,-0.15,-0.3", help="shield centre offset from hand_L head (world)")
    ap.add_argument("--shield-normal", default="0.35,-0.94,0", help="direction the shield face points (world)")
    ap.add_argument("--shield-up", default="0,0,1", help="shield's top direction (world)")
    ap.add_argument("--shield-height", type=float, default=2.1, help="shield height in 0 A.D. units")
    ap.add_argument("--sword-length", type=float, default=2.2)
    ap.add_argument("--sword-blade-w", type=float, default=0.17, help="blade width at the guard")
    ap.add_argument("--sword-guard-w", type=float, default=0.55, help="cross-guard span")
    ap.add_argument("--sword-blade-t", type=float, default=0.035, help="blade thickness")
    # nearest-bone fallback skinning (only used when bone heat fails)
    ap.add_argument("--weight-bones", type=int, default=2, help="bones per vertex")
    ap.add_argument("--weight-power", type=float, default=4.0, help="inverse-distance falloff power")
    ap.add_argument("--weight-smooth", type=int, default=4, help="smoothing iterations")
    return ap.parse_args(argv)


def vec3(s):
    return [float(x) for x in s.split(",")]


def single_animation(dae, cache):
    """Rewrite a 0 A.D. clip so every assimp version exports it as one animation:

    * the clips nest one <animation> per bone under a container, all named "Biped"; assimp 5.3
      (Ubuntu 24.04) refuses to write a GLB from that ("Failed to write file"), while assimp 6
      exports it but as 103 one-animation actions. Unique names fix the former; merge_actions()
      handles the latter.
    * a file with several top-level <animation> elements is nested under one container.
    """
    import xml.etree.ElementTree as ET
    NS = "http://www.collada.org/2005/11/COLLADASchema"
    ET.register_namespace("", NS)
    tree = ET.parse(dae)
    lib = tree.getroot().find(f"{{{NS}}}library_animations")
    if lib is None:
        return dae
    kids = list(lib.findall(f"{{{NS}}}animation"))
    if len(kids) > 1:
        wrapper = ET.SubElement(lib, f"{{{NS}}}animation", {"id": "merged_clip"})
        for k in kids:
            lib.remove(k)
            wrapper.append(k)
    n = 0
    for anim in lib.iter(f"{{{NS}}}animation"):
        anim.set("name", f"anim{n}")
        n += 1
    out = os.path.join(cache, os.path.basename(dae))
    tree.write(out, xml_declaration=True, encoding="utf-8")
    print(f"   {os.path.basename(dae)}: {n} animation elements renamed" + (", top level nested" if len(kids) > 1 else ""))
    return out


def to_glb(dae, glb):
    """assimp export, cached: an existing GLB newer than its DAE is reused. That also lets a
    machine whose assimp cannot convert a clip (Ubuntu's 5.3.1 fails on idle_relax_shield_01)
    use a GLB converted elsewhere and copied into the cache directory."""
    if os.path.exists(glb) and os.path.getmtime(glb) >= os.path.getmtime(dae):
        print(f"   reusing cached {os.path.basename(glb)}")
        return glb
    dae = single_animation(dae, os.path.dirname(glb))
    r = subprocess.run(["assimp", "export", dae, glb], capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(glb):
        sys.exit(f"assimp failed on {dae}: {r.stderr}")
    return glb


def action_fcurves(action):
    direct = getattr(action, "fcurves", None)
    if direct:
        return list(direct)
    out = []
    for layer in getattr(action, "layers", []):
        for strip in layer.strips:
            for bag in getattr(strip, "channelbags", []):
                out.extend(bag.fcurves)
    return out


def merge_actions(acts, name):
    """assimp splits some clips into one animation per bone (idle_relax_shield_01 arrives as 103
    one-bone actions while walk_relax_shield arrives as one). Fold them into a single slotted
    action so the clip binds like any other."""
    bone_acts = [x for x in acts if any('pose.bones["' in fc.data_path for fc in action_fcurves(x))]
    # Always rebuild: the single-action walk clip also carries object-level location/rotation
    # curves for the armature root node, which would override the Y-up->Z-up object rotation
    # and lay the whole character flat.
    dst = bpy.data.actions.new(name)
    if hasattr(dst, "slots"):          # Blender 4.4+: slotted actions
        slot = dst.slots.new(id_type="OBJECT", name="Biped")
        layer = dst.layers.new("Layer")
        strip = layer.strips.new(type="KEYFRAME")
        curves = strip.channelbag(slot, ensure=True).fcurves
    else:                              # Blender <= 4.3 (e.g. Ubuntu's 4.0.2): legacy fcurves
        curves = dst.fcurves
    n_curves = 0
    for a in bone_acts:
        for fc in action_fcurves(a):
            if 'pose.bones["' not in fc.data_path:
                continue
            nfc = curves.new(fc.data_path, index=fc.array_index)
            n = len(fc.keyframe_points)
            nfc.keyframe_points.add(n)
            co = [0.0] * (2 * n)
            fc.keyframe_points.foreach_get("co", co)
            nfc.keyframe_points.foreach_set("co", co)
            for kp in nfc.keyframe_points:
                kp.interpolation = "LINEAR"
            nfc.update()
            n_curves += 1
    print(f"   rebuilt '{name}' from {len(bone_acts)} action(s): {n_curves} bone curves kept")
    return dst


def import_new(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    return [o for o in bpy.data.objects if o not in before]


def bounds(obj):
    """World-space bounds. Meshes are measured from their vertices (obj.bound_box lags behind
    mesh.transform until the depsgraph runs); other objects use the cached box."""
    if obj.type == "MESH":
        wv = world_verts(obj)
        return Vector(wv.min(axis=0).tolist()), Vector(wv.max(axis=0).tolist())
    bb = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    lo = Vector((min(v.x for v in bb), min(v.y for v in bb), min(v.z for v in bb)))
    hi = Vector((max(v.x for v in bb), max(v.y for v in bb), max(v.z for v in bb)))
    return lo, hi


def world_verts(obj):
    me = obj.data
    n = len(me.vertices)
    arr = np.empty(n * 3, dtype=np.float32)
    me.vertices.foreach_get("co", arr)
    arr = arr.reshape(n, 3)
    mw = np.array(obj.matrix_world)
    return arr @ mw[:3, :3].T + mw[:3, 3]


def freeze(obj):
    """Clear parenting and bake the world transform into the mesh data."""
    mw = obj.matrix_world.copy()
    obj.parent = None
    obj.matrix_world = mw
    obj.data.transform(obj.matrix_world)
    obj.matrix_world = Matrix.Identity(4)
    bpy.context.view_layer.update()


def glb_images(path):
    """Embedded images of a GLB by material role: {"base": bytes, "mr": bytes, ...}. Done by hand
    (a few lines of struct) because Blender 4.0's glTF importer leaves embedded textures as
    unloaded references into a temp directory, which is gone by the time a later session renders.
    "base" is the base colour map; "mr" the glTF metallic-roughness map (G roughness, B metallic),
    present on PBR exports (TRELLIS.2) and absent on v1's single-texture Hunyuan GLBs."""
    import struct
    with open(path, "rb") as fh:
        data = fh.read()
    magic, version, length = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF":
        return {}
    off, js, binchunk = 12, None, None
    while off + 8 <= min(length, len(data)):
        clen, ctype = struct.unpack_from("<I4s", data, off)
        chunk = data[off + 8: off + 8 + clen]
        if ctype == b"JSON":
            js = json.loads(chunk.decode("utf-8"))
        elif ctype == b"BIN\x00":
            binchunk = chunk
        off += 8 + clen
    if not js or not js.get("images") or binchunk is None:
        return {}

    def payload(img_index):
        img = js["images"][img_index]
        bv = js["bufferViews"][img["bufferView"]]
        ext = ".jpg" if "jpeg" in img.get("mimeType", "") else ".png"
        return binchunk[bv.get("byteOffset", 0): bv.get("byteOffset", 0) + bv["byteLength"]], ext

    out = {}
    mat = (js.get("materials") or [{}])[0]
    pbr = mat.get("pbrMetallicRoughness", {})
    for role, key in (("base", "baseColorTexture"), ("mr", "metallicRoughnessTexture")):
        if key in pbr:
            out[role] = payload(js["textures"][pbr[key]["index"]]["source"])
    if "base" not in out:               # no material roles: first image is the colour map
        out["base"] = payload(0)
    return out


def load_packed_images(path, name, cache):
    """{role: image datablock} for a GLB's embedded textures, packed into the .blend."""
    out = {}
    for role, (data, ext) in glb_images(path).items():
        fn = os.path.join(cache, f"{name}_{role}{ext}")
        with open(fn, "wb") as fh:
            fh.write(data)
        img = bpy.data.images.load(fn)
        img.name = f"{name}_{role}"
        if role != "base":
            img.colorspace_settings.name = "Non-Color"
        img.pack()
        img.use_fake_user = True     # the alternate team's texture has no users until bake time;
        out[role] = img              # without this it is dropped from the saved .blend
    return out


def image_nodes_by_role(obj):
    """{role: [TEX_IMAGE nodes]} of an object's materials, by what each node feeds: "base" when its
    colour reaches the BSDF's Base Color, "mr" when it feeds a channel-separating node (the glTF
    importer's metallic-roughness wiring). Unlinked or other nodes count as "base" for v1 GLBs."""
    roles = {"base": [], "mr": []}
    for mat in obj.data.materials:
        if not (mat and mat.node_tree):
            continue
        for n in mat.node_tree.nodes:
            if n.type != "TEX_IMAGE":
                continue
            role = "base"
            for link in mat.node_tree.links:
                if link.from_node is n:
                    if link.to_node.type in ("SEPARATE_COLOR", "SEPRGB", "SEPXYZ"):
                        role = "mr"
                    elif link.to_socket.name in ("Roughness", "Metallic"):
                        role = "mr"
            roles[role].append(n)
    return roles


def assign_images(obj, images):
    """Point each image node of obj at the right role's packed image."""
    for role, nodes in image_nodes_by_role(obj).items():
        img = images.get(role)
        for n in nodes:
            if img is not None:
                n.image = img


def team_spec(images):
    """What goes into the object's team_textures property: v1 wrote one image name per team;
    PBR GLBs record one name per role."""
    if not images:
        return None
    if set(images) == {"base"}:
        return images["base"].name
    return {role: img.name for role, img in images.items()}


def import_textured(path, name):
    """Import a textured GLB as one mesh object; returns (object, {role: image})."""
    new = import_new(path)
    meshes = [o for o in new if o.type == "MESH"]
    if not meshes:
        sys.exit(f"no mesh in {path}")
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    for o in new:
        if o is not obj and o.name in bpy.data.objects:
            bpy.data.objects.remove(o, do_unlink=True)
    freeze(obj)
    obj.name = name
    images = load_packed_images(path, f"{name}_tex", CACHE[0])
    assign_images(obj, images)
    for mat in obj.data.materials:      # pre-rendered sprites never need backface culling off
        if mat:
            mat.use_backface_culling = False
    return obj, images


def grab_image(path, name):
    """Only the textures of a GLB (the alternate team's paint of the same mesh)."""
    images = load_packed_images(path, name, CACHE[0])
    if not images:
        sys.exit(f"no embedded texture in {path}")
    return images


def material_image_node(obj):
    for mat in obj.data.materials:
        if mat and mat.node_tree:
            for n in mat.node_tree.nodes:
                if n.type == "TEX_IMAGE":
                    return n
    return None


def nearest_bone_weights(body, rig, bone_names, k=2, power=4.0, smooth=4):
    """Fallback skinning when bone heat refuses the mesh: each vertex is weighted to its k nearest
    bones (distance to the rest-pose bone segment, inverse-power falloff, normalised), then the
    groups are smoothed over the mesh a few times. Crude next to heat weights, but with 72 px
    sprites of an armoured figure (rigid plates, short limbs) the joints read fine."""
    bpy.context.view_layer.update()
    V = world_verts(body).astype(np.float64)
    heads, tails = [], []
    for n in bone_names:
        b = rig.pose.bones[n]
        heads.append(np.array(rig.matrix_world @ b.head)); tails.append(np.array(rig.matrix_world @ b.tail))
    H, T = np.array(heads), np.array(tails)
    D = np.empty((len(V), len(H)))
    for i in range(len(H)):
        d = T[i] - H[i]
        L2 = max(float(d @ d), 1e-9)
        t = np.clip(((V - H[i]) @ d) / L2, 0, 1)
        D[:, i] = np.linalg.norm(V - (H[i] + t[:, None] * d), axis=1)
    idx = np.argsort(D, axis=1)[:, :k]
    dk = np.take_along_axis(D, idx, axis=1)
    w = 1.0 / (dk + 1e-4) ** power
    w /= w.sum(axis=1, keepdims=True)
    body.vertex_groups.clear()
    groups = [body.vertex_groups.new(name=n) for n in bone_names]
    for j in range(k):
        for bi in np.unique(idx[:, j]):
            sel = np.where(idx[:, j] == bi)[0]
            for vi in sel:
                groups[bi].add([int(vi)], float(w[vi, j]), "ADD")
    if smooth > 0:
        bpy.ops.object.select_all(action="DESELECT")
        body.select_set(True); bpy.context.view_layer.objects.active = body
        bpy.ops.object.mode_set(mode="WEIGHT_PAINT")
        try:
            bpy.ops.object.vertex_group_smooth(group_select_mode="ALL", factor=0.5, repeat=smooth, expand=0.0)
        except Exception as e:
            print("   weight smoothing skipped:", e)
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.vertex_group_normalize_all(lock_active=False)


def weight_loose_to_nearest(body, rig, bone_names, indices):
    """Give the listed (unweighted) vertices weight 1 on the bone whose rest segment is nearest.
    Returns how many were bound."""
    bpy.context.view_layer.update()
    V = world_verts(body).astype(np.float64)[indices]
    heads, tails = [], []
    for n in bone_names:
        b = rig.pose.bones[n]
        heads.append(np.array(rig.matrix_world @ b.head)); tails.append(np.array(rig.matrix_world @ b.tail))
    H, T = np.array(heads), np.array(tails)
    D = np.empty((len(V), len(H)))
    for i in range(len(H)):
        d = T[i] - H[i]
        L2 = max(float(d @ d), 1e-9)
        t = np.clip(((V - H[i]) @ d) / L2, 0, 1)
        D[:, i] = np.linalg.norm(V - (H[i] + t[:, None] * d), axis=1)
    nearest = np.argmin(D, axis=1)
    groups = {g.name: g for g in body.vertex_groups}
    for vi, bi in zip(indices, nearest):
        name = bone_names[bi]
        if name not in groups:
            groups[name] = body.vertex_groups.new(name=name)
        groups[name].add([int(vi)], 1.0, "REPLACE")
    return len(indices)


def pose_rotate_world(arm, pbone, axis, degrees):
    """Rotate a pose bone about a world axis through its head; children follow."""
    bpy.context.view_layer.update()
    head = arm.matrix_world @ pbone.head
    R = Matrix.Translation(head) @ Matrix.Rotation(math.radians(degrees), 4, axis) @ Matrix.Translation(-head)
    pbone.matrix = arm.matrix_world.inverted() @ R @ arm.matrix_world @ pbone.matrix
    bpy.context.view_layer.update()


def build_sword(length, name="sword", blade_w=0.17, guard_w=0.55, blade_t=0.035):
    """Procedural arming sword along local +Y: pommel at the origin end, point at +length.
    v1 proportions are the defaults (blade 0.17 wide ~ 7.5 cm, guard 0.55 ~ 25 cm at 4.2 units per
    1.8 m); v2 passes a narrower blade and shorter guard so the sword reads as an arming sword."""
    import bmesh
    grip_len, guard_y = 0.28, 0.06
    blade_len = length - grip_len - guard_y - 0.08
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()

    def box(cx, cy, cz, sx, sy, sz, mat):
        res = bmesh.ops.create_cube(bm, size=1.0)
        verts = res["verts"]
        bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=verts)
        bmesh.ops.translate(bm, vec=(cx, cy, cz), verts=verts)
        for f in bm.faces:
            if f.material_index == 0 and all(v in verts for v in f.verts):
                f.material_index = mat
        return verts

    # materials: 0 steel, 1 leather, 2 brass
    # pommel (brass), grip (leather), guard (steel), blade (steel, tapered)
    box(0, 0.04, 0, 0.14, 0.08, 0.14, 2)
    box(0, 0.08 + grip_len / 2, 0, 0.09, grip_len, 0.11, 1)
    box(0, 0.08 + grip_len + guard_y / 2, 0, guard_w, guard_y, 0.1, 0)
    y0 = 0.08 + grip_len + guard_y
    bv = box(0, y0 + blade_len / 2, 0, blade_w, blade_len, blade_t, 0)
    # taper the blade toward the point and give it a slight fuller-less diamond section
    for v in bv:
        t = min(1.0, max(0.0, (v.co.y - y0) / blade_len))
        v.co.x *= (1.0 - 0.85 * t ** 2.2)
        v.co.z *= (1.0 - 0.5 * t)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    for mname, col, metal, rough in (("steel", (0.62, 0.62, 0.64, 1), 1.0, 0.32),
                                     ("leather", (0.20, 0.10, 0.05, 1), 0.0, 0.8),
                                     ("brass", (0.55, 0.42, 0.18, 1), 1.0, 0.4)):
        mat = bpy.data.materials.new(f"{name}_{mname}")
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes["Principled BSDF"]
        bsdf.inputs["Base Color"].default_value = col
        bsdf.inputs["Metallic"].default_value = metal
        bsdf.inputs["Roughness"].default_value = rough
        me.materials.append(mat)
    for p in me.polygons:
        p.use_smooth = False
    return obj


PROP_MATS = {"wood": ((0.42, 0.27, 0.13, 1), 0.0, 0.7), "iron": ((0.36, 0.36, 0.38, 1), 1.0, 0.45),
             "wicker": ((0.62, 0.45, 0.22, 1), 0.0, 0.85), "leather": ((0.22, 0.12, 0.06, 1), 0.0, 0.8),
             "string": ((0.75, 0.72, 0.6, 1), 0.0, 0.9), "bark": ((0.30, 0.20, 0.10, 1), 0.0, 0.9)}


def _prop_object(name, bm, mats):
    """Finish a procedural prop: bmesh -> object with the listed materials (in index order)."""
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    for mname in mats:
        col, metal, rough = PROP_MATS[mname]
        mat = bpy.data.materials.new(f"{name}_{mname}")
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes["Principled BSDF"]
        bsdf.inputs["Base Color"].default_value = col
        bsdf.inputs["Metallic"].default_value = metal
        bsdf.inputs["Roughness"].default_value = rough
        me.materials.append(mat)
    for p in me.polygons:
        p.use_smooth = False
    return obj


def _box(bm, cx, cy, cz, sx, sy, sz, mat):
    import bmesh
    res = bmesh.ops.create_cube(bm, size=1.0)
    verts = res["verts"]
    bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=verts)
    bmesh.ops.translate(bm, vec=(cx, cy, cz), verts=verts)
    for f in bm.faces:
        if all(v in verts for v in f.verts):
            f.material_index = mat
    return verts


def _tube(bm, points, radii, mat, sides=6):
    """Swept tube through `points` (list of Vector) with per-point radius; closed ends."""
    rings = []
    n = len(points)
    for i, p in enumerate(points):
        t = (points[min(i + 1, n - 1)] - points[max(i - 1, 0)]).normalized()
        a = Vector((0, 0, 1)) if abs(t.z) < 0.9 else Vector((1, 0, 0))
        u = t.cross(a).normalized(); v = t.cross(u).normalized()
        ring = []
        for k in range(sides):
            ang = 2 * math.pi * k / sides
            ring.append(bm.verts.new(p + radii[i] * (math.cos(ang) * u + math.sin(ang) * v)))
        rings.append(ring)
    faces = []
    for r0, r1 in zip(rings[:-1], rings[1:]):
        for k in range(sides):
            faces.append(bm.faces.new((r0[k], r0[(k + 1) % sides], r1[(k + 1) % sides], r1[k])))
    faces.append(bm.faces.new(rings[0][::-1]))
    faces.append(bm.faces.new(rings[-1]))
    for f in faces:
        f.material_index = mat
    return faces


def _handle(bm, length, grip, r0, r1, mat=0):
    """Straight wooden haft along local +Y, origin at the grip point (fraction `grip` from the
    butt), radius r0 at the butt to r1 at the head end."""
    y0, y1 = -grip * length, (1 - grip) * length
    pts = [Vector((0, y0 + (y1 - y0) * t, 0)) for t in (0, 0.5, 1)]
    _tube(bm, pts, [r0, (r0 + r1) / 2, r1], mat, sides=6)
    return y1


def build_prop(kind, name, size=None):
    """Procedural props in the rig's units (4.2 = 1.8 m). Local +Y is the long axis (bow tip to tip,
    tool butt to head, basket handle top to bottom), local +X the 'edge' (axe blade, hoe blade,
    hammer face, basket handle arc plane). Materials: 0 wood, 1 iron/wicker, 2 extras."""
    import bmesh
    bm = bmesh.new()
    if kind == "bow":                        # longbow, origin at the grip; back bulges to +X, string at -X
        L = size or 4.0
        depth = 0.32
        n = 17
        pts, radii = [], []
        for i in range(n):
            t = -1 + 2 * i / (n - 1)
            pts.append(Vector((-depth * t * t, t * L / 2, 0)))
            radii.append(0.06 - 0.035 * abs(t))
        _tube(bm, pts, radii, 0, sides=6)
        _box(bm, 0, 0, 0, 0.12, 0.42, 0.12, 2)                                   # leather grip
        _box(bm, -depth, 0, 0, 0.02, L, 0.02, 1)                                 # string
        return _prop_object(name, bm, ["wood", "string", "leather"])
    if kind == "axe":                        # felling axe, handle 0.85 m, head beyond the far end
        L = size or 2.0
        y1 = _handle(bm, L, 0.25, 0.055, 0.045)
        head = _box(bm, 0.16, y1 - 0.2, 0, 0.5, 0.36, 0.09, 1)                 # blade, edge at +X
        for v in head:
            if v.co.x > 0.3:
                v.co.z *= 0.25; v.co.y *= 1.0
            if v.co.x > 0.3 and v.co.y > y1 - 0.2:
                v.co.y += 0.08
        _box(bm, -0.08, y1 - 0.2, 0, 0.14, 0.2, 0.11, 1)                          # eye / poll
        return _prop_object(name, bm, ["wood", "iron"])
    if kind == "pickaxe":
        L = size or 2.0
        y1 = _handle(bm, L, 0.25, 0.055, 0.05)
        head = _box(bm, 0, y1 - 0.08, 0, 1.2, 0.11, 0.11, 1)
        for v in head:
            if abs(v.co.x) > 0.5:
                v.co.y = y1 - 0.08 + (v.co.y - (y1 - 0.08)) * 0.3
                v.co.z *= 0.3
                v.co.y -= 0.12 if v.co.x > 0 else 0.12
        return _prop_object(name, bm, ["wood", "iron"])
    if kind == "hoe":
        L = size or 3.3
        y1 = _handle(bm, L, 0.25, 0.045, 0.04)
        blade = _box(bm, 0.22, y1 - 0.02, 0, 0.42, 0.04, 0.36, 1)              # flat blade pointing +X
        for v in blade:
            if v.co.x > 0.3:
                v.co.y -= 0.12                                                 # angled ~75 deg to the haft
        _box(bm, 0.0, y1 - 0.04, 0, 0.1, 0.16, 0.1, 1)
        return _prop_object(name, bm, ["wood", "iron"])
    if kind == "hammer":
        L = size or 0.85
        y1 = _handle(bm, L, 0.35, 0.045, 0.04)
        head = _box(bm, 0.02, y1 - 0.07, 0, 0.5, 0.14, 0.14, 1)
        for v in head:
            if v.co.x < -0.2:
                v.co.y = y1 - 0.07 + (v.co.y - (y1 - 0.07)) * 0.35            # peen
                v.co.z *= 0.6
        return _prop_object(name, bm, ["wood", "iron"])
    if kind == "basket":                      # origin where the handle hangs; basket below along +Y
        R, h = (size or 0.9) / 2, 0.5
        n = 10
        pts = [Vector((math.sin(a) * R * 0.95, (1 - math.cos(a)) * R * 0.95, 0))
               for a in [-math.pi / 2 + math.pi * i / (n - 1) for i in range(n)]]
        _tube(bm, pts, [0.035] * n, 1, sides=5)                                 # handle arc in X-Y
        cy = R * 0.95 + h / 2
        res = bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=12, radius1=R, radius2=R * 0.75,
                                    depth=h)
        bmesh.ops.rotate(bm, verts=res["verts"], cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 2, 3, "X"))
        bmesh.ops.translate(bm, vec=(0, cy, 0), verts=res["verts"])
        for f in bm.faces:
            if all(v in res["verts"] for v in f.verts):
                f.material_index = 1
        return _prop_object(name, bm, ["wood", "wicker"])
    if kind == "log":
        L = size or 1.6
        res = bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=8, radius1=0.2, radius2=0.18, depth=L)
        bmesh.ops.rotate(bm, verts=res["verts"], cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 2, 3, "X"))
        for f in bm.faces:
            f.material_index = 1
        return _prop_object(name, bm, ["wood", "bark"])
    sys.exit(f"unknown prop kind {kind}")


def parse_prop(spec):
    d = {}
    for item in spec.split(";"):
        if item.strip():
            k, v = item.split("=", 1)
            d[k.strip()] = v.strip()
    if "name" not in d or "bone" not in d:
        sys.exit(f"--prop needs name= and bone=: {spec}")
    return d


def basis_matrix(origin, y_dir, x_hint):
    """World matrix whose local +Y points along y_dir and local +X as close to x_hint as possible."""
    y = Vector(y_dir).normalized()
    x = Vector(x_hint) - Vector(x_hint).dot(y) * y
    x = x.normalized()
    z = x.cross(y).normalized()
    m = Matrix.Identity(4)
    m.col[0][:3] = x; m.col[1][:3] = y; m.col[2][:3] = z; m.col[3][:3] = Vector(origin)
    return m


def bone_parent(obj, arm, bone_name, world_matrix):
    """Parent obj to a bone at the current pose, keeping the given world matrix."""
    bpy.context.view_layer.update()
    obj.parent = arm
    obj.parent_type = "BONE"
    obj.parent_bone = bone_name
    obj.matrix_world = world_matrix
    bpy.context.view_layer.update()


def diag_render(path, objs, arm, label, size=640):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "TEXTURE"
    scene.render.resolution_x, scene.render.resolution_y = size * 3, size
    scene.render.film_transparent = False
    arm.show_in_front = True
    arm.data.display_type = "STICK"
    lo, hi = bounds(objs[0])
    for o in objs[1:]:
        l2, h2 = bounds(o)
        lo = Vector((min(lo.x, l2.x), min(lo.y, l2.y), min(lo.z, l2.z)))
        hi = Vector((max(hi.x, h2.x), max(hi.y, h2.y), max(hi.z, h2.z)))
    c = (lo + hi) / 2
    cam_d = bpy.data.cameras.new("diag"); cam_d.type = "ORTHO"; cam_d.ortho_scale = (hi.z - lo.z) * 1.15
    cam = bpy.data.objects.new("diag_cam", cam_d); scene.collection.objects.link(cam); scene.camera = cam
    tiles = []
    for name, pos, rot in (("front", (c.x, c.y - 20, c.z), (math.pi / 2, 0, 0)),
                           ("side", (c.x + 20, c.y, c.z), (math.pi / 2, 0, math.pi / 2)),
                           ("3/4", (c.x - 14, c.y - 14, c.z), (math.pi / 2, 0, -math.pi / 4))):
        cam.location = pos; cam.rotation_euler = rot
        scene.render.resolution_x = size
        fn = f"{path}_{name}.png"
        scene.render.filepath = fn
        bpy.ops.render.render(write_still=True)
        tiles.append(fn)
    bpy.data.objects.remove(cam, do_unlink=True)
    print(f"   diag {label}: {tiles}")
    return tiles


def diag_strip(path, objs, arm, act, n, size=320):
    """Workbench filmstrip of a clip: n evenly spaced frames (the bake's sampling, start inclusive)
    as columns, side / front / 3-4 views as rows, so motion is judged before any Cycles render.
    Writes <path>.png."""
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "TEXTURE"
    scene.render.resolution_x = scene.render.resolution_y = size
    scene.render.film_transparent = False
    arm.show_in_front = True
    arm.data.display_type = "STICK"
    start, end = act.frame_range
    frames = [start + i * (end - start) / n for i in range(n)]
    # one framing for the whole strip: union of bounds over the sampled frames, ground at the bottom
    lo, hi = None, None
    for f in frames:
        scene.frame_set(int(f), subframe=f - int(f))
        bpy.context.view_layer.update()
        for o in objs:
            l2, h2 = bounds(o)
            lo = l2 if lo is None else Vector((min(lo.x, l2.x), min(lo.y, l2.y), min(lo.z, l2.z)))
            hi = h2 if hi is None else Vector((max(hi.x, h2.x), max(hi.y, h2.y), max(hi.z, h2.z)))
    ext = max(hi.x - lo.x, hi.y - lo.y, hi.z - lo.z) * 1.1
    c = (lo + hi) / 2
    cam_d = bpy.data.cameras.new("strip"); cam_d.type = "ORTHO"; cam_d.ortho_scale = ext
    cam = bpy.data.objects.new("strip_cam", cam_d); scene.collection.objects.link(cam); scene.camera = cam
    views = (("side", (c.x + 20, c.y, c.z), (math.pi / 2, 0, math.pi / 2)),
             ("front", (c.x, c.y - 20, c.z), (math.pi / 2, 0, 0)),
             ("3/4", (c.x - 14, c.y - 14, c.z), (math.pi / 2, 0, -math.pi / 4)))
    tmp = os.path.join(os.path.dirname(path), "_strip_tmp.png")
    tiles = {}
    for vname, pos, rot in views:
        cam.location = pos; cam.rotation_euler = rot
        for i, f in enumerate(frames):
            scene.frame_set(int(f), subframe=f - int(f))
            scene.render.filepath = tmp
            bpy.ops.render.render(write_still=True)
            img = bpy.data.images.load(tmp)
            px = np.array(img.pixels[:], dtype=np.float32).reshape(size, size, 4)
            bpy.data.images.remove(img)
            tiles[(vname, i)] = px[::-1]
    bpy.data.objects.remove(cam, do_unlink=True)
    sheet = np.zeros((size * len(views), size * n, 4), dtype=np.float32)
    for r, (vname, _, _) in enumerate(views):
        for i in range(n):
            sheet[r * size:(r + 1) * size, i * size:(i + 1) * size] = tiles[(vname, i)]
    out = bpy.data.images.new("strip_out", width=size * n, height=size * len(views), alpha=True)
    out.pixels = sheet[::-1].ravel().tolist()
    out.filepath_raw = path + ".png"
    out.file_format = "PNG"
    out.save()
    bpy.data.images.remove(out)
    if os.path.exists(tmp):
        os.remove(tmp)
    print(f"   strip {path}.png: {n} frames x {len(views)} views (frames {[round(f, 1) for f in frames]})")


def main():
    a = parse_args()
    cache = os.path.join(os.path.dirname(os.path.abspath(a.out)), "_cache")
    os.makedirs(cache, exist_ok=True)
    CACHE[0] = cache
    if a.diag:
        os.makedirs(a.diag, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene

    # ---- Source armature: 0 A.D. biped, verbatim
    new = import_new(to_glb(BIPED_DAE, os.path.join(cache, "biped.glb")))
    source = next(o for o in new if o.type == "ARMATURE")
    bpy.context.view_layer.update()
    mw = source.matrix_world.copy()      # the glTF scene node carries the Y-up -> Z-up rotation
    source.parent = None
    source.matrix_world = mw
    for o in new:
        if o is not source:
            bpy.data.objects.remove(o, do_unlink=True)
    bpy.context.view_layer.update()
    source.name = "Source"
    rig_bones = {b.name for b in source.data.bones}
    print(f"== source rig: {len(rig_bones)} bones")

    # ---- clips -> actions on Source (import, keep the action, drop the rest)
    actions = {}
    json_clips = []
    for spec in a.clip:
        name, dae = spec.split("=", 1)
        if dae.endswith(".json"):
            json_clips.append((name, os.path.abspath(dae)))
            continue
        before = set(bpy.data.actions)
        new = import_new(to_glb(os.path.abspath(dae), os.path.join(cache, f"clip_{name}.glb")))
        acts = [x for x in bpy.data.actions if x not in before]
        if not acts:
            sys.exit(f"clip {name}: no action imported")
        def nbones(x):
            return len({fc.data_path.split('"')[1] for fc in action_fcurves(x) if 'pose.bones["' in fc.data_path})
        print(f"   clip {name}: {len(acts)} imported actions, "
              f"{sum(len(action_fcurves(x)) for x in acts)} curves, {sum(nbones(x) for x in acts)} bone bindings")
        act = merge_actions(acts, f"clip_{name}")
        for x in acts:
            if x is not act:
                bpy.data.actions.remove(x)
        act.name = f"clip_{name}"
        act.use_fake_user = True
        for o in new:
            bpy.data.objects.remove(o, do_unlink=True)
        driven = {fc.data_path.split('"')[1] for fc in action_fcurves(act) if 'pose.bones["' in fc.data_path}
        print(f"   clip {name}: frames {act.frame_range[0]:.0f}..{act.frame_range[1]:.0f}, "
              f"{len(driven & rig_bones)}/{len(driven)} driven bones exist on the rig")
        actions[name] = act
    if source.animation_data is None:
        source.animation_data_create()

    def bind(act):
        source.animation_data.action = act
        if hasattr(source.animation_data, "action_slot"):
            slots = list(getattr(act, "slots", []))
            if slots:
                source.animation_data.action_slot = slots[0]

    # ---- body: import, scale to height, feet on the ground, centred over the rig
    body, body_imgs = import_textured(os.path.abspath(a.body), "Body")
    lo, hi = bounds(body)
    s = a.height / (hi.z - lo.z)
    body.data.transform(Matrix.Scale(s, 4))
    lo, hi = bounds(body)
    # the rig stands with its hips at x=0; its y centre is slightly behind 0 (the tunic bbox was
    # -0.43..0.40), so centre the body on the rig's own bounding box centre in y
    slo, shi = bounds(source)
    body.data.transform(Matrix.Translation((-(lo.x + hi.x) / 2, -(lo.y + hi.y) / 2 + 0.0, -lo.z)))
    bpy.context.view_layer.update()
    lo, hi = bounds(body)
    print(f"== body scaled x{s:.3f}: bbox {tuple(round(v, 2) for v in lo)} .. {tuple(round(v, 2) for v in hi)}")
    textures = {"blue": team_spec(body_imgs)}
    for spec in a.alt:
        team, path = spec.split("=", 1)
        textures[team] = team_spec(grab_image(os.path.abspath(path), f"Body_{team}_tex"))
    body[TEAM_PROP] = json.dumps(textures)
    print(f"   team textures: {textures}")

    # ---- Rig armature: duplicate of Source, arms swung to the body's A-pose angle, applied as rest
    rig = source.copy()
    rig.data = source.data.copy()
    rig.name = "Rig"; rig.data.name = "Rig"
    scene.collection.objects.link(rig)
    rig.animation_data_clear()
    bpy.context.view_layer.update()

    # measure the body's arm angle: left hand tip = max-x vertex above the knees
    wv = world_verts(body)
    cand = wv[wv[:, 2] > 0.35 * a.height]
    tip = cand[np.argmax(cand[:, 0])]
    arm_head = rig.matrix_world @ rig.pose.bones["Biped_arm_L"].head
    hand_tail = rig.matrix_world @ rig.pose.bones["Biped_hand_L"].tail
    rig_ang = math.degrees(math.atan2(hand_tail.z - arm_head.z, hand_tail.x - arm_head.x))
    body_ang = math.degrees(math.atan2(tip[2] - arm_head.z, tip[0] - arm_head.x))
    print(f"   arm_L head {tuple(round(v, 3) for v in arm_head)}, hand_L tail {tuple(round(v, 3) for v in hand_tail)}")
    delta = a.arm_delta if a.arm_delta is not None else (body_ang - rig_ang)
    print(f"== arm fit: rig arm angle {rig_ang:.1f} deg, body hand tip at ({tip[0]:.2f},{tip[2]:.2f}) "
          f"-> {body_ang:.1f} deg, swinging arms by {delta:.1f} deg")
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True); bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="POSE")
    # rotate about the world Y axis (front/back axis): +delta raises the left arm outward, mirror for right
    pose_rotate_world(rig, rig.pose.bones["Biped_arm_L"], "Y", -delta)
    pose_rotate_world(rig, rig.pose.bones["Biped_arm_R"], "Y", delta)
    bpy.ops.pose.armature_apply(selected=False)
    bpy.ops.object.mode_set(mode="OBJECT")

    # ---- bind body to Rig with automatic weights.
    # The textured body carries xatlas seam splits (24k verts for an 18k-vertex surface), which
    # leaves open boundaries that bone heat refuses. So: weight a merged, watertight proxy of the
    # same surface, then copy the groups across by nearest vertex (the positions are identical).
    proxy = body.copy(); proxy.data = body.data.copy(); proxy.name = "BodyProxy"
    scene.collection.objects.link(proxy)
    bpy.ops.object.select_all(action="DESELECT")
    proxy.select_set(True); bpy.context.view_layer.objects.active = proxy
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.remove_doubles(threshold=1e-5)
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    print(f"   proxy: {len(proxy.data.vertices)} verts after merging seams")
    bpy.ops.object.select_all(action="DESELECT")
    proxy.select_set(True); rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    pz = sum(1 for v in proxy.data.vertices if v.groups)
    print(f"   proxy auto weights: {pz}/{len(proxy.data.vertices)} weighted")
    # transfer to the real body by nearest vertex (the seam duplicates sit exactly on proxy verts)
    from mathutils import kdtree
    kd = kdtree.KDTree(len(proxy.data.vertices))
    for v in proxy.data.vertices:
        kd.insert(v.co, v.index)
    kd.balance()
    for vg in proxy.vertex_groups:
        body.vertex_groups.new(name=vg.name)
    pgroups = {g.index: g.name for g in proxy.vertex_groups}
    for v in body.data.vertices:
        _, idx, _ = kd.find(v.co)
        for g in proxy.data.vertices[idx].groups:
            body.vertex_groups[pgroups[g.group]].add([v.index], g.weight, "REPLACE")
    bpy.data.objects.remove(proxy, do_unlink=True)
    body.parent = rig
    body.matrix_parent_inverse = rig.matrix_world.inverted()
    mod = body.modifiers.new("Armature", "ARMATURE"); mod.object = rig
    nz = sum(1 for v in body.data.vertices if v.groups)
    print(f"== auto weights: {nz}/{len(body.data.vertices)} vertices weighted, "
          f"{len(body.vertex_groups)} groups")
    if nz < 0.95 * len(body.data.vertices):
        print("   bone heat failed on most of the mesh (TRELLIS bodies are many loose armour "
              "pieces); falling back to nearest-bone weights + smoothing")
        nearest_bone_weights(body, rig, sorted(rig_bones), k=a.weight_bones, power=a.weight_power,
                             smooth=a.weight_smooth)
        nz = sum(1 for v in body.data.vertices if v.groups)
        print(f"== nearest-bone weights: {nz}/{len(body.data.vertices)} vertices weighted")
    # bone heat leaves a few hundred vertices of the TRELLIS body unweighted (loose slivers); they
    # would stay at their rest position and float as specks once the body crouches or lies down
    # (v4 attack/death), so bind each to its nearest bone
    loose = [v.index for v in body.data.vertices if not v.groups]
    if loose:
        n_loose = weight_loose_to_nearest(body, rig, sorted(rig_bones), loose)
        print(f"   {n_loose} unweighted vertices bound to their nearest bone")

    # ---- constraints: Rig bones follow Source bones in world space
    for pb in rig.pose.bones:
        if pb.name in rig_bones:
            c = pb.constraints.new("COPY_TRANSFORMS")
            c.target = source
            c.subtarget = pb.name
            c.target_space = "WORLD"; c.owner_space = "WORLD"
    source.hide_render = True
    bpy.context.view_layer.update()

    # ---- props, placed at the idle stance (frame 1 of the first clip)
    first = actions[next(iter(actions))]
    bind(first)
    scene.frame_set(1)
    bpy.context.view_layer.update()
    hand_R = rig.matrix_world @ rig.pose.bones["Biped_hand_R"].head
    hand_L = rig.matrix_world @ rig.pose.bones["Biped_hand_L"].head
    print(f"== idle frame 1: hand_R {tuple(round(v, 2) for v in hand_R)}, hand_L {tuple(round(v, 2) for v in hand_L)}")
    props = []
    if a.sword != "none":
        if a.sword == "auto":
            sword = build_sword(a.sword_length, blade_w=a.sword_blade_w, guard_w=a.sword_guard_w,
                                blade_t=a.sword_blade_t)
        else:
            sword, _ = import_textured(os.path.abspath(a.sword), "sword")
        sword.name = "Sword"
        # the sword's local origin is the pommel end; the grip centre sits ~0.2 along +Y
        m = basis_matrix(hand_R + Vector(vec3(a.sword_pos)), vec3(a.sword_dir), vec3(a.sword_flat))
        bone_parent(sword, rig, "Biped_hand_R", m @ Matrix.Translation((0, -0.2, 0)))
        props.append(sword)
    shield = None
    if a.shield:
        shield, shield_imgs = import_textured(os.path.abspath(a.shield), "Shield")
        lo2, hi2 = bounds(shield)
        sc = a.shield_height / (hi2.z - lo2.z)
        shield.data.transform(Matrix.Scale(sc, 4) @ Matrix.Translation(-(lo2 + hi2) / 2))
        stex = {"blue": team_spec(shield_imgs)}
        for spec in a.shield_alt:
            team, path = spec.split("=", 1)
            stex[team] = team_spec(grab_image(os.path.abspath(path), f"Shield_{team}_tex"))
        shield[TEAM_PROP] = json.dumps(stex)
        # shield mesh: height along +Z, face toward -Y. Local +Y must point opposite the normal.
        n = Vector(vec3(a.shield_normal)).normalized()
        up = Vector(vec3(a.shield_up))
        m = basis_matrix(hand_L + Vector(vec3(a.shield_pos)), -n, up.cross(-n))
        # basis_matrix gives local X = x_hint; we want local Z = up: rotate so that Z = up
        x = up.cross(-n).normalized(); z = x.cross(-n).normalized()
        m = Matrix.Identity(4)
        m.col[0][:3] = x; m.col[1][:3] = -n; m.col[2][:3] = -z if z.dot(up) < 0 else z
        m.col[3][:3] = hand_L + Vector(vec3(a.shield_pos))
        bone_parent(shield, rig, "Biped_hand_L", m)
        props.append(shield)

    # ---- video-derived clips: retargeted now that the body is bound (ground clamp uses the mesh)
    for name, path in json_clips:
        import video_to_clip
        act = video_to_clip.build_action(source, path, f"clip_{name}", base_action=first, base_frame=1,
                                         ground_objs=[body], prop_objs=props)
        actions[name] = act

    # ---- generic props (v1): built or imported, placed at a chosen clip/phase in world terms,
    # bone-parented; `clips` is stamped on the object so bake_sprites.py renders each prop only
    # in the clips that use it
    for spec in a.prop:
        d = parse_prop(spec)
        kind = d["name"]
        pname = d.get("as", kind if not kind.endswith(".glb") else os.path.splitext(os.path.basename(kind))[0])
        if kind.endswith(".glb"):
            obj, _ = import_textured(os.path.abspath(kind), pname)
            if "size" in d:
                lo2, hi2 = bounds(obj)
                obj.data.transform(Matrix.Scale(float(d["size"]) / (hi2 - lo2).length, 4) @ Matrix.Translation(-(lo2 + hi2) / 2))
        else:
            obj = build_prop(kind, pname, float(d["size"]) if "size" in d else None)
        obj.name = pname
        if "clips" in d:
            obj["clips"] = ",".join(d["clips"].split("|"))
        # pose at the placement frame
        if "at" in d:
            cname, ph = d["at"].split(":")
            act = actions[cname]
            f0, f1 = act.frame_range
            bind(act)
            fr = f0 + float(ph) * (f1 - f0)
            scene.frame_set(int(fr), subframe=fr - int(fr))
        else:
            bind(first)
            scene.frame_set(1)
        bpy.context.view_layer.update()
        pb = rig.pose.bones[d["bone"]]
        head = rig.matrix_world @ pb.head
        tail = rig.matrix_world @ pb.tail
        if d.get("dir", "hand") == "hand":
            ydir = (tail - head).normalized()
        else:
            ydir = Vector(vec3(d["dir"])).normalized()
        if "pitch" in d:    # rotation about world +X tips a forward-pointing axis down, so negate
            ydir = Matrix.Rotation(math.radians(-float(d["pitch"])), 3, "X") @ ydir
        edge = Vector(vec3(d.get("edge", "0,1,0")))
        if abs(edge.normalized().dot(ydir)) > 0.95:
            edge = Vector((1, 0, 0))
        origin = head + (tail - head) * float(d.get("along", 0.0)) + Vector(vec3(d.get("pos", "0,0,0")))
        m = basis_matrix(origin, ydir, edge)
        bone_parent(obj, rig, d["bone"], m)
        props.append(obj)
        print(f"   prop {pname} ({kind}) on {d['bone']} at {d.get('at', 'base frame 1')}: origin "
              f"{tuple(round(v, 2) for v in origin)}, dir {tuple(round(v, 2) for v in ydir)}, "
              f"clips {obj.get('clips', 'all')}")

    # ---- diagnostics: rest, then first frame of each clip, then a filmstrip per video clip
    # (props are shown only in the clips they belong to, as bake_sprites.py renders them)
    def props_for(clip):
        return [p for p in props if not p.get("clips") or clip in str(p["clips"]).split(",")]

    def show_props(clip):
        for p in props:
            p.hide_render = p not in props_for(clip)
    if a.diag:
        first_name = next(iter(actions))
        bind(first)
        scene.frame_set(1)
        show_props(first_name)
        diag_render(os.path.join(a.diag, "clip0_f1"), [body] + props_for(first_name), rig, "clip frame 1")
        for name, act in actions.items():
            bind(act)
            show_props(name)
            mid = int((act.frame_range[0] + act.frame_range[1]) / 2)
            scene.frame_set(mid)
            diag_render(os.path.join(a.diag, f"{name}_mid"), [body] + props_for(name), rig, f"{name} mid")
        for name, _ in json_clips:
            bind(actions[name])
            show_props(name)
            diag_strip(os.path.join(a.diag, f"{name}_strip"), [body] + props_for(name), rig, actions[name], a.strip_frames)
        for p in props:
            p.hide_render = False

    # ---- prop GLBs per team (the sword is team-neutral; both files are written for symmetry)
    out_dir = os.path.dirname(os.path.abspath(a.out))
    for p in props:
        if p.name == "Sword":
            for team in textures:
                bpy.ops.object.select_all(action="DESELECT")
                p.select_set(True)
                bpy.ops.export_scene.gltf(filepath=os.path.join(out_dir, f"sword_{team}.glb"),
                                          use_selection=True, export_apply=True, export_animations=False)
                print(f"   wrote sword_{team}.glb")

    # ---- save. Every texture must live inside the .blend: Blender 4.0's glTF importer leaves
    # embedded images pointing at files it extracted to a temp dir, which will not exist in the
    # next (container) session that renders the sprites.
    for img in list(bpy.data.images):
        if img.users == 0 and not img.use_fake_user:
            bpy.data.images.remove(img)      # importer leftovers
            continue
        if img.packed_file is None and img.has_data:
            img.pack()
    for img in bpy.data.images:
        print(f"   image {img.name}: {tuple(img.size)} packed={img.packed_file is not None} "
              f"{'OK' if img.packed_file is not None or img.name.startswith('Render') else 'NOT PACKED'}")
    bind(actions["idle"] if "idle" in actions else next(iter(actions.values())))
    scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(a.out))
    print(f"== wrote {a.out}")


main()
