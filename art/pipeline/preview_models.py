"""Contact sheet of one or more meshes seen from front / 3-4 / side / back.

    blender --background --python art/pipeline/preview_models.py -- \
        --out previews/body_compare.png --size 512 \
        --mesh "2mv front+back=work/shape_mv/white.obj" --mesh "single=work/shape_single/white.obj"

Each --mesh is "label=path" (.obj/.ply/.glb). Textured GLBs render in Cycles with their own
material; untextured meshes get a neutral clay. Meshes are recentred and scaled to unit height so
different sources can sit side by side. One row per mesh, one column per view.
"""
import argparse, math, os, sys
import bpy
from mathutils import Vector

VIEWS = [("front", 0), ("3/4", 45), ("side", 90), ("back", 180), ("3/4 back", 225)]


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--mesh", action="append", required=True, help="label=path")
    ap.add_argument("--out", required=True)
    ap.add_argument("--size", type=int, default=400)
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--views", default="front,3/4,side,back")
    ap.add_argument("--yup", action="store_true", help="source is Y-up (Hunyuan3D output); rotate to Z-up")
    return ap.parse_args(argv)


def import_mesh(path):
    before = set(bpy.data.objects)
    ext = os.path.splitext(path)[1].lower()
    if ext == ".glb" or ext == ".gltf":
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".obj":
        bpy.ops.wm.obj_export  # noqa (ensures io_scene present)
        bpy.ops.wm.obj_import(filepath=path)
    elif ext == ".ply":
        bpy.ops.wm.ply_import(filepath=path)
    else:
        sys.exit(f"unsupported mesh {path}")
    new = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    if not new:
        sys.exit(f"nothing imported from {path}")
    # merge into one object for simple framing
    bpy.ops.object.select_all(action="DESELECT")
    for o in new:
        o.select_set(True)
    bpy.context.view_layer.objects.active = new[0]
    if len(new) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    mw = obj.matrix_world.copy()
    obj.parent = None
    obj.matrix_world = mw
    for o in [o for o in bpy.data.objects if o not in before and o.type != "MESH" and o is not obj]:
        bpy.data.objects.remove(o, do_unlink=True)
    return obj


def clay(obj):
    if obj.data.materials and any(m and m.node_tree and any(n.type == "TEX_IMAGE" for n in m.node_tree.nodes)
                                  for m in obj.data.materials):
        return
    mat = bpy.data.materials.new("clay")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.75, 0.72, 0.68, 1)
    bsdf.inputs["Roughness"].default_value = 0.7
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def normalise(obj, yup):
    bpy.context.view_layer.update()
    if yup:
        from mathutils import Matrix
        obj.matrix_world = Matrix.Rotation(math.pi / 2, 4, "X") @ obj.matrix_world
        bpy.context.view_layer.update()
    # bake the transform so that scale/location below act in world space
    me = obj.data; me.transform(obj.matrix_world); obj.matrix_world.identity()
    bpy.context.view_layer.update()
    bb = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    lo = Vector((min(v.x for v in bb), min(v.y for v in bb), min(v.z for v in bb)))
    hi = Vector((max(v.x for v in bb), max(v.y for v in bb), max(v.z for v in bb)))
    h = max(hi.z - lo.z, 1e-6)
    s = 1.0 / h
    obj.scale = (s, s, s)
    bpy.context.view_layer.update()
    bb = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    lo = Vector((min(v.x for v in bb), min(v.y for v in bb), min(v.z for v in bb)))
    hi = Vector((max(v.x for v in bb), max(v.y for v in bb), max(v.z for v in bb)))
    obj.location = obj.location - Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    bpy.context.view_layer.update()


def setup_scene(samples):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = samples
    if getattr(bpy.app.build_options, "openimagedenoise", False):
        scene.cycles.use_denoising = True
    else:
        scene.cycles.use_denoising = False
        scene.cycles.samples = max(samples, 128)
    scene.cycles.device = "CPU"
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        for backend in ("METAL", "OPTIX", "CUDA"):
            try:
                prefs.compute_device_type = backend
            except TypeError:
                continue
            prefs.get_devices()
            if [d for d in prefs.devices if d.type != "CPU"]:
                for d in prefs.devices:
                    d.use = True
                scene.cycles.device = "GPU"
                break
    except Exception as e:  # CPU fallback
        print("GPU probe failed:", e)
    scene.render.film_transparent = False
    world = bpy.data.worlds.new("w"); scene.world = world; world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.5, 0.5, 0.52, 1); bg.inputs[1].default_value = 0.6
    sun = bpy.data.lights.new("sun", "SUN"); sun.energy = 3.0; sun.angle = math.radians(8)
    sun.color = (1.0, 0.93, 0.82)
    so = bpy.data.objects.new("sun", sun); scene.collection.objects.link(so)
    so.rotation_euler = (math.radians(50), 0, math.radians(-35))
    cam_d = bpy.data.cameras.new("cam"); cam_d.type = "ORTHO"; cam_d.ortho_scale = 1.15
    cam = bpy.data.objects.new("cam", cam_d); scene.collection.objects.link(cam); scene.camera = cam
    return scene, cam


def main():
    a = parse()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene, cam = setup_scene(a.samples)
    scene.render.resolution_x = scene.render.resolution_y = a.size
    views = [(n, deg) for n, deg in VIEWS if n in a.views.split(",")]
    tmp = os.path.join(os.path.dirname(a.out) or ".", "_tiles")
    os.makedirs(tmp, exist_ok=True)
    tiles = []
    for spec in a.mesh:
        label, path = spec.split("=", 1)
        obj = import_mesh(os.path.abspath(path))
        clay(obj)
        normalise(obj, a.yup)
        row = []
        for name, deg in views:
            r = math.radians(deg)
            # camera orbits the model at a slight downward tilt
            dist, tilt = 5.0, math.radians(10)
            cam.location = (dist * math.sin(r) * math.cos(tilt), -dist * math.cos(r) * math.cos(tilt), 0.5 + dist * math.sin(tilt))
            cam.rotation_euler = (math.pi / 2 - tilt, 0, r)
            fn = os.path.join(tmp, f"{len(tiles)}_{len(row)}.png")
            scene.render.filepath = fn
            bpy.ops.render.render(write_still=True)
            row.append((name, fn))
        tiles.append((label, row))
        bpy.data.objects.remove(obj, do_unlink=True)

    # assemble + label with PIL in the system python (Blender's python has no PIL)
    import json, subprocess
    spec = {"size": a.size, "rows": [(label, [(n, fn) for n, fn in row]) for label, row in tiles], "out": os.path.abspath(a.out)}
    code = r"""
import json, sys
from PIL import Image, ImageDraw
s = json.load(open(sys.argv[1])); S = s["size"]; rows = s["rows"]; cols = len(rows[0][1])
sheet = Image.new("RGB", (S * cols, (S + 24) * len(rows)), (40, 40, 40))
d = ImageDraw.Draw(sheet)
for r, (label, row) in enumerate(rows):
    y = r * (S + 24)
    d.text((6, y + 5), label, fill=(240, 230, 200))
    for c, (name, fn) in enumerate(row):
        sheet.paste(Image.open(fn).convert("RGB"), (c * S, y + 24))
        d.text((c * S + 6, y + 28), name, fill=(255, 255, 255))
sheet.save(s["out"])
"""
    spec_path = os.path.join(tmp, "spec.json")
    with open(spec_path, "w") as fh:
        json.dump(spec, fh)
    subprocess.run(["/usr/bin/env", "python3", "-c", code, spec_path], check=True)
    print("rows:", [t[0] for t in tiles], "cols:", [v[0] for v in views])
    print("wrote", a.out)


main()
