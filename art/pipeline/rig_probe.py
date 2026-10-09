"""Probe the 0 A.D. biped rig: which bones survive the assimp->glTF hop, and what its rest pose looks like.

    blender --background --python art/pipeline/rig_probe.py -- --out /tmp/rigprobe

Writes bones.txt and rest_front.png / rest_side.png.
"""
import argparse, os, subprocess, sys, math
import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
MESH = os.path.join(ROOT, "ios/ZeroADArt/meshes/skeletal/new/m_armor_tunic_short.dae")
CLIP = os.path.join(ROOT, "art/source/zeroad_clips/biped/infantry/swordsman/walk_relax_shield.dae")

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True)
args = ap.parse_args(argv)
os.makedirs(args.out, exist_ok=True)


def to_glb(dae, glb):
    r = subprocess.run(["assimp", "export", dae, glb], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(r.stderr)
    return glb


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=to_glb(MESH, os.path.join(args.out, "mesh.glb")))
lines = []
for o in bpy.data.objects:
    lines.append(f"{o.type} {o.name} parent={o.parent.name if o.parent else None}")
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
body = next(o for o in bpy.data.objects if o.type == "MESH" and o.vertex_groups)
lines.append(f"armature {arm.name}: {len(arm.data.bones)} bones")
for b in arm.data.bones:
    h = arm.matrix_world @ b.head_local; t = arm.matrix_world @ b.tail_local
    lines.append(f"  bone {b.name:28s} parent={(b.parent.name if b.parent else "-"):28s} head=({h.x:.3f},{h.y:.3f},{h.z:.3f}) tail=({t.x:.3f},{t.y:.3f},{t.z:.3f}) deform={b.use_deform}")
lines.append(f"empties: {[o.name for o in bpy.data.objects if o.type == 'EMPTY']}")
bb = [body.matrix_world @ Vector(c) for c in body.bound_box]
lo = Vector((min(v.x for v in bb), min(v.y for v in bb), min(v.z for v in bb)))
hi = Vector((max(v.x for v in bb), max(v.y for v in bb), max(v.z for v in bb)))
lines.append(f"body bbox lo={tuple(round(x,3) for x in lo)} hi={tuple(round(x,3) for x in hi)} verts={len(body.data.vertices)}")
lines.append(f"armature matrix_world={[list(r) for r in arm.matrix_world]}")

# clip import: what comes across
before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=to_glb(CLIP, os.path.join(args.out, "clip.glb")))
new = [o for o in bpy.data.objects if o not in before]
lines.append("clip objects: " + ", ".join(f"{o.type}:{o.name}" for o in new))
for o in new:
    if o.type == "ARMATURE":
        lines.append(f"clip armature {o.name}: {len(o.data.bones)} bones; props: "
                     f"{[b.name for b in o.data.bones if 'prop' in b.name]}")
        lines.append(f"clip armature matrix_world={[list(r) for r in o.matrix_world]}")
acts = list(bpy.data.actions)
lines.append(f"actions: {[(a.name, tuple(a.frame_range)) for a in acts]}")
for o in new:
    bpy.data.objects.remove(o, do_unlink=True)

with open(os.path.join(args.out, "bones.txt"), "w") as fh:
    fh.write("\n".join(lines) + "\n")

# render rest pose, front and side, with bones drawn as sticks (workbench)
scene = bpy.context.scene
scene.render.engine = "BLENDER_WORKBENCH"
scene.render.resolution_x = scene.render.resolution_y = 600
scene.render.film_transparent = False
arm.show_in_front = True
arm.data.display_type = "STICK"
cam_data = bpy.data.cameras.new("c"); cam_data.type = "ORTHO"; cam_data.ortho_scale = (hi.z - lo.z) * 1.2
cam = bpy.data.objects.new("cam", cam_data); scene.collection.objects.link(cam); scene.camera = cam
c = (lo + hi) / 2
for name, pos, rot in (("front", (c.x, c.y - 10, c.z), (math.pi / 2, 0, 0)),
                       ("side", (c.x + 10, c.y, c.z), (math.pi / 2, 0, math.pi / 2)),
                       ("back", (c.x, c.y + 10, c.z), (math.pi / 2, 0, math.pi))):
    cam.location = pos; cam.rotation_euler = rot
    scene.render.filepath = os.path.join(args.out, f"rest_{name}.png")
    bpy.ops.render.render(write_still=True)
print("\n".join(lines[-12:]))
