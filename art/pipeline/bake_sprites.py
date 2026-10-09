#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Bake a rigged character (.blend from rig_body.py) into 8-direction animated sprites with Cycles.

On the DGX Spark (Docker image from art/pipeline/docker/Dockerfile, repo subset in ~/medieval):

    docker run --rm -u $(id -u):$(id -g) -e HOME=/tmp -v ~/medieval:/work medieval-blender \
        nice -n 10 blender --background art/models/man_at_arms/man_at_arms_rig.blend \
        --python art/pipeline/bake_sprites.py -- ...same arguments...

On the Mac:

    blender --background art/models/man_at_arms/man_at_arms_rig.blend \
        --python art/pipeline/bake_sprites.py -- \
        --name man_at_arms --teams blue,red --clip idle=6 --clip walk=8 \
        --size 72 --supersample 2 --out art/out/man_at_arms

v2 (art/out/man_at_arms_v2; same --name so the keys and file names stay identical to v1): brighter
warm sun, cool fill, and the contact shadow rendered as its own pass and composited lighter, with
an in-frame falloff, by sprites_post.py (the game draws its own ellipse shadow as well):

    docker run --rm -u $(id -u):$(id -g) -e HOME=/tmp -v ~/medieval:/work medieval-blender \
        nice -n 10 blender --background art/models/man_at_arms_v2/man_at_arms_rig.blend \
        --python art/pipeline/bake_sprites.py -- \
        --name man_at_arms --teams blue,red --clip idle=6 --clip walk=8 --size 72 --supersample 2 \
        --out art/out/man_at_arms_v2 --sun-elev 52 --sun-energy 5.0 --sun-color 1.0,0.9,0.78 --sun-angle 9 \
        --world-strength 0.55 --world-color 0.6,0.72,0.95 --shadow-pass --shadow-samples 32 --shadow-opacity 0.4

Projection matches scripts/bake_zeroad_art.py (orthographic, yaw 45 + k*45 for direction k, pitch
30, the character filling 86% of the cell, feet 2px above the bottom), and so does the manifest:
per-frame ``{file, w, h, fill, fp_cx, fp_cy, fp_w}`` and per-clip ``{group: "animation", frames,
files, clip, duration, fps}``. One difference: the game scales a unit by ``targetW / fp_w``, and a
projected bounding rectangle changes width as the unit turns (sword and shield swing it from 16 to
38 px), so here the footprint is a disc under the BODY (props excluded) whose projected width is
the same from every direction: ``fp_w`` is constant across all frames of a unit and ``fp_cx/fp_cy``
is the body's ground point in the cell. Direction 0 is the facing the existing single-view units were baked
at; k increases counter-clockwise seen from above (the camera orbits by +45 deg per step).

One framing (scale) is shared by every team, clip, direction and frame, so the unit never changes
size as it turns or moves. Renders happen at size*supersample and are reduced with Lanczos by a
system-python step (Blender's python has no PIL), which also writes the manifest snippet.

Lighting: one warm, low sun (late afternoon) with a soft angular size plus a dim cool sky fill; a
shadow-catcher ground plane puts a soft contact shadow into the alpha channel.

v4: ``--px-per-unit`` pins the shared scale (so idle/walk stay the size v3 baked them at) and a
clip may ask for a larger cell, ``--clip attack=10:88``: same scale, same footprint disc, more
canvas for a sword wound up overhead or a body lying on the ground. The game draws every frame
from its own w/h/fp_cx/fp_cy, so cells of different sizes mix freely. The camera is also placed
per clip (x centred on that clip's frames, its lowest point 2px above the bottom), and
``--dry-run`` reports the tightest cell margin per clip without rendering.
"""
import argparse
import json
import math
import os
import subprocess
import sys
import time

import bpy
import numpy as np
from mathutils import Matrix, Vector

TEAM_PROP = "team_textures"
ISO_YAW, ISO_PITCH, FILL, FPS = 45.0, 30.0, 0.86, 24


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", required=True)
    ap.add_argument("--teams", default="blue,red")
    ap.add_argument("--clip", action="append", required=True, help="clipname=frames[:cellsize]")
    ap.add_argument("--dirs", type=int, default=8)
    ap.add_argument("--size", type=int, default=72)
    ap.add_argument("--supersample", type=int, default=2)
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", help="debug: 'team,clip,dir,frame' to render a single tile")
    ap.add_argument("--no-resume", action="store_true",
                    help="re-render tiles that already exist (default: skip them, so a crashed run resumes)")
    ap.add_argument("--sun-elev", type=float, default=48.0)
    ap.add_argument("--sun-azim", type=float, default=200.0,
                    help="degrees, compass-style from +Y; 200 lights the front-left of direction 0")
    # v2 lighting knobs; the defaults reproduce v1
    ap.add_argument("--sun-energy", type=float, default=4.0)
    ap.add_argument("--sun-color", default="1.0,0.87,0.70")
    ap.add_argument("--sun-angle", type=float, default=7.0, help="sun angular size in degrees (shadow softness)")
    ap.add_argument("--world-strength", type=float, default=0.8)
    ap.add_argument("--world-color", default="0.55,0.65,0.85")
    ap.add_argument("--shadow-pass", action="store_true",
                    help="render the contact shadow as a separate low-sample tile (<tile>_shadow.png) with the "
                         "character hidden from the camera, so sprites_post.py can lighten/shape it")
    ap.add_argument("--shadow-samples", type=int, default=32)
    ap.add_argument("--shadow-opacity", type=float, default=0.45, help="sprites_post.py shadow density")
    ap.add_argument("--shadow-inner", type=float, default=0.5, help="where the in-frame shadow fade starts")
    ap.add_argument("--shadow-blur", type=float, default=0.75, help="shadow blur in sprite pixels")
    ap.add_argument("--contrast", type=float, default=0.0, help="sprites_post.py S-curve strength (v3: 0.35)")
    ap.add_argument("--saturation", type=float, default=1.0, help="sprites_post.py chroma scale")
    ap.add_argument("--dry-run", action="store_true", help="sample, report scale and margins, render nothing")
    ap.add_argument("--px-per-unit", type=float, default=None,
                    help="pin the shared scale (v3 baked at 14.34) instead of fitting the largest frame; "
                         "frames that then exceed the cell are reported per clip")
    return ap.parse_args(argv)


def action_range(act):
    return act.frame_range


def bind(source, act):
    source.animation_data.action = act
    if hasattr(source.animation_data, "action_slot"):
        slots = list(getattr(act, "slots", []))
        if slots:
            source.animation_data.action_slot = slots[0]


def evaluated_points(objs):
    dg = bpy.context.evaluated_depsgraph_get()
    out = []
    for o in objs:
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        n = len(me.vertices)
        arr = np.empty(n * 3, dtype=np.float64)
        me.vertices.foreach_get("co", arr)
        arr = arr.reshape(n, 3)
        mw = np.array(ev.matrix_world)
        out.append(arr @ mw[:3, :3].T + mw[:3, 3])
        ev.to_mesh_clear()
    return np.concatenate(out)


def cam_basis(yaw_deg, pitch_deg):
    """Right / up / back (toward camera) unit vectors for the isometric projection."""
    yr, pr = math.radians(yaw_deg), math.radians(pitch_deg)
    fwd_h = Vector((math.sin(yr), math.cos(yr), 0.0))          # horizontal view direction
    right = Vector((math.cos(yr), -math.sin(yr), 0.0))
    view = fwd_h * math.cos(pr) - Vector((0, 0, 1)) * math.sin(pr)   # looking down by pitch
    up = right.cross(view).normalized()
    return right, up, -view


def set_texture(obj, team):
    """Swap the object's textures to a team's. The rig stores either one image name per team (v1,
    single colour map) or {"base": name, "mr": name} (v2 PBR: base colour + metallic-roughness);
    each image node is matched to its role by what it feeds, as rig_body.py does."""
    spec = json.loads(obj.get(TEAM_PROP, "{}"))
    entry = spec.get(team)
    if not entry:
        return False
    if isinstance(entry, str):
        entry = {"base": entry, "mr": None}
    for mat in obj.data.materials:
        if not (mat and mat.node_tree):
            continue
        for n in mat.node_tree.nodes:
            if n.type != "TEX_IMAGE":
                continue
            role = "base"
            for link in mat.node_tree.links:
                if link.from_node is n and (link.to_node.type in ("SEPARATE_COLOR", "SEPRGB", "SEPXYZ")
                                            or link.to_socket.name in ("Roughness", "Metallic")):
                    role = "mr"
            name = entry.get(role)
            if name:
                n.image = bpy.data.images.get(name)
    return True


def setup_render(a):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = a.samples
    scene.cycles.use_adaptive_sampling = True
    if getattr(bpy.app.build_options, "openimagedenoise", False):
        scene.cycles.use_denoising = True
    else:   # Ubuntu's blender package is built without OIDN: trade denoising for more samples
        scene.cycles.use_denoising = False
        scene.cycles.samples = max(a.samples, 160)
        print(f"   no OpenImageDenoise in this build; denoising off, {scene.cycles.samples} samples")
    # GPU if any backend has a device (Metal on the Mac, OptiX/CUDA on Linux); CPU otherwise.
    scene.cycles.device = "CPU"
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        for backend in ("METAL", "OPTIX", "CUDA"):
            try:
                prefs.compute_device_type = backend
            except TypeError:
                continue
            prefs.get_devices()
            gpus = [d for d in prefs.devices if d.type != "CPU"]
            if gpus:
                for d in prefs.devices:
                    d.use = True
                scene.cycles.device = "GPU"
                print(f"   Cycles on {backend}: {[d.name for d in gpus]}")
                break
    except Exception as e:
        print("GPU probe failed:", e)
    if scene.cycles.device == "CPU":
        scene.render.threads_mode = "AUTO"
        print(f"   Cycles on CPU ({os.cpu_count()} threads)")
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.resolution_x = scene.render.resolution_y = a.size * a.supersample
    scene.render.resolution_percentage = 100
    scene.render.filter_size = 1.2
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.render.fps = FPS

    world = bpy.data.worlds.get("SpriteWorld") or bpy.data.worlds.new("SpriteWorld")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    wc = [float(x) for x in a.world_color.split(",")]
    bg.inputs[0].default_value = (*wc, 1)          # cool sky fill (v1: 0.55,0.65,0.85)
    bg.inputs[1].default_value = a.world_strength  # strong enough fill that the contact shadow stays soft

    for o in [o for o in bpy.data.objects if o.name.startswith("Sprite_")]:
        bpy.data.objects.remove(o, do_unlink=True)
    sun_d = bpy.data.lights.new("Sprite_sun", "SUN")
    sun_d.energy = a.sun_energy
    sun_d.color = tuple(float(x) for x in a.sun_color.split(","))   # late afternoon
    sun_d.angle = math.radians(a.sun_angle)                          # soft shadow edge
    sun = bpy.data.objects.new("Sprite_sun", sun_d)
    scene.collection.objects.link(sun)
    el, az = math.radians(a.sun_elev), math.radians(a.sun_azim)
    from_dir = Vector((math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)))
    sun.rotation_euler = (-from_dir).to_track_quat("-Z", "Y").to_euler()

    bpy.ops.mesh.primitive_plane_add(size=60, location=(0, 0, 0))
    ground = bpy.context.active_object
    ground.name = "Sprite_ground"
    ground.is_shadow_catcher = True
    ground.visible_glossy = False
    ground.visible_diffuse = False

    cam_d = bpy.data.cameras.new("Sprite_cam")
    cam_d.type = "ORTHO"
    cam_d.clip_start, cam_d.clip_end = 0.1, 200
    cam = bpy.data.objects.new("Sprite_cam", cam_d)
    scene.collection.objects.link(cam)
    scene.camera = cam
    return scene, cam, ground


def main():
    a = parse_args()
    t_start = time.time()
    scene = bpy.context.scene
    source = bpy.data.objects["Source"]
    rig = bpy.data.objects["Rig"]
    body = bpy.data.objects["Body"]
    props = [o for o in bpy.data.objects if o.type == "MESH" and o.parent is rig and o is not body]
    for p in props:
        print(f"   prop {p.name}: clips {p.get('clips', 'all')}")
    renderables = [body] + props
    # v1: a prop may carry a "clips" property (rig_body.py --prop ... clips=a|b): it is rendered,
    # framed and shadow-cast only in those clips, hidden otherwise
    def props_for(clip):
        return [p for p in props if not p.get("clips") or clip in str(p["clips"]).split(",")]

    def show_props(clip):
        for p in props:
            p.hide_render = p not in props_for(clip)
    teams = a.teams.split(",")
    clips = []
    for spec in a.clip:
        name, n = spec.split("=")
        n, _, cell = n.partition(":")
        act = bpy.data.actions[f"clip_{name}"]
        clips.append((name, int(n), act, int(cell) if cell else a.size))
    # per-clip metadata written by video_to_clip.build_action (one-shot clips)
    clip_meta = {}
    for name, n, act, cell in clips:
        loop = bool(act.get("loop", True))
        imp = act.get("impact_phase", None)
        clip_meta[name] = {"loop": loop, "size": cell,
                           "impact_frame": int(round(float(imp) * n)) % n if imp is not None else None}
        print(f"   clip {name}: {n} frames, {cell}px cell, loop={loop}, impact_frame={clip_meta[name]['impact_frame']}")
    scene, cam, ground = setup_render(a)
    full_samples = scene.cycles.samples
    size, ss = a.size, a.supersample
    tiles_dir = os.path.join(a.out, "_tiles")
    os.makedirs(tiles_dir, exist_ok=True)

    # ---- sample every frame once: deformed points for framing and footprints
    samples = []   # (clip, i, frame_float, points, duration)
    for name, n, act, _ in clips:
        bind(source, act)
        start, end = action_range(act)
        span = end - start
        for i in range(n):
            f = start + i * span / n
            scene.frame_set(int(f), subframe=f - int(f))
            bpy.context.view_layer.update()
            samples.append((name, i, f, evaluated_points([body] + props_for(name)), span / FPS,
                            evaluated_points([body])))
    allpts = np.concatenate([s[3] for s in samples])
    # the ground is the lowest BODY point over every frame (v1: a prop that dips below the feet,
    # e.g. a bow lying across a corpse, must not lower the footprint disc of every clip)
    ground_z = float(np.concatenate([s[5] for s in samples])[:, 2].min())
    for name, n, act, _ in clips:
        rows = [(s[1], float(s[3][:, 2].min())) for s in samples if s[0] == name]
        low = min(rows, key=lambda r: r[1])
        if low[1] < ground_z - 0.05:
            print(f"   clip {name}: lowest point {low[1]:+.2f} at frame {low[0]} is {ground_z - low[1]:.2f} below the ground (a prop)")
    # sword tip per frame of the one-shot clips (forward is -Y): a check that the designed impact
    # frame is where the blade is furthest forward / lowest
    sword = bpy.data.objects.get("Sword")
    if sword is not None:
        tip_i = int(np.argmax([v.co.y for v in sword.data.vertices]))
        for name, n, act, _ in clips:
            if clip_meta[name]["impact_frame"] is None and clip_meta[name]["loop"]:
                continue
            bind(source, act)
            start, end = action_range(act)
            rows = []
            for i in range(n):
                f = start + i * (end - start) / n
                scene.frame_set(int(f), subframe=f - int(f))
                bpy.context.view_layer.update()
                dg = bpy.context.evaluated_depsgraph_get()
                ev = sword.evaluated_get(dg)
                tip = ev.matrix_world @ ev.data.vertices[tip_i].co
                rows.append(f"{i}:(fwd {-tip.y:+.2f}, z {tip.z:.2f})")
            print(f"   sword tip, clip {name}: " + " ".join(rows))
    body0 = samples[0][5]
    foot_d = float(max(body0[:, 0].max() - body0[:, 0].min(), body0[:, 1].max() - body0[:, 1].min()))
    print(f"== {len(samples)} frames sampled, {len(allpts)} points, ground z={ground_z:.3f}, "
          f"footprint disc diameter {foot_d:.3f}")

    # ---- one scale for everything: max projected span over all frames and directions
    yaws = [ISO_YAW + k * (360.0 / a.dirs) for k in range(a.dirs)]
    bases = [cam_basis(y, ISO_PITCH) for y in yaws]
    span = 0.0
    for right, up, _ in bases:
        R = np.array([right, up])
        p = allpts @ R.T
        span = max(span, p[:, 0].max() - p[:, 0].min(), p[:, 1].max() - p[:, 1].min())
    px_per_unit = size * FILL / span
    if a.px_per_unit:
        print(f"   span {span:.3f} units would give {px_per_unit:.2f} px/unit; pinned to {a.px_per_unit:.2f}")
        px_per_unit = a.px_per_unit
    ortho = size / px_per_unit            # world units across the default cell
    cam.data.ortho_scale = ortho
    print(f"   span {span:.3f} units -> {px_per_unit:.2f} px/unit, ortho_scale {ortho:.3f}")
    cell_of = {name: cell for name, n, act, cell in clips}
    ortho_of = {name: cell / px_per_unit for name, cell in cell_of.items()}

    # ---- per-direction camera placement, per CLIP (v4): x centred on the clip's frames, the
    # clip's lowest projected point 2px above the bottom edge. v3 placed every clip together; a
    # corpse lying toward the camera or a sword wound up behind the head would push the other
    # clips off centre or over the top. The game places every frame by its own fp_cx/fp_cy, so
    # the cell position may differ per clip.
    placements = {}
    for name, n, act, cell in clips:
        cpts = np.concatenate([s[3] for s in samples if s[0] == name])
        for k, (right, up, back) in enumerate(bases):
            R = np.array([right, up])
            p = cpts @ R.T
            ox = (p[:, 0].max() + p[:, 0].min()) / 2
            oy = p[:, 1].min() - 2.0 / px_per_unit + ortho_of[name] / 2     # camera centre in the up axis
            centre = Vector(right) * ox + Vector(up) * oy
            cam_pos = centre + Vector(back) * 60.0
            rot = Matrix((right, up, back)).transposed().to_4x4().to_euler()
            placements[(name, k)] = (cam_pos, rot, right, up)

    def project(points, name, k):
        cam_pos, _, right, up = placements[(name, k)]
        R = np.array([right, up])
        p = points @ R.T
        cp = np.array(cam_pos) @ R.T
        cell = cell_of[name]
        x = (p[:, 0] - cp[0]) * px_per_unit + cell / 2
        y = cell / 2 - (p[:, 1] - cp[1]) * px_per_unit
        return x, y

    # ---- per clip: how close every frame comes to the cell edge in every direction (a sword
    # overhead or a lying body can exceed a pinned scale; report rather than silently clip)
    clipped = False
    for name, n, act, cell in clips:
        margin, where = 1e9, None
        for (cname, i, f, pts, _, _) in [s for s in samples if s[0] == name]:
            for k in range(a.dirs):
                x, y = project(pts, name, k)
                # the bottom edge is 2 px by construction (camera placement); report the others
                edges = {"left": x.min(), "top": y.min(), "right": cell - x.max()}
                e = min(edges, key=edges.get)
                if edges[e] < margin:
                    j = int(np.argmin(x) if e == "left" else np.argmax(x) if e == "right" else np.argmin(y))
                    margin, where = edges[e], (i, k, e, pts[j])
        clipped |= margin < 0
        print(f"   clip {name}: tightest margin {margin:.1f} px of a {cell}px cell (frame {where[0]}, d{where[1]}, {where[2]} edge, "
              f"point {tuple(round(float(v), 2) for v in where[3])}){'  ** CLIPS THE CELL **' if margin < 0 else ''}")
    if a.dry_run:
        print("== dry run: stopping before the render" + (" (something clips)" if clipped else ""))
        return

    # ---- render
    meta = {"name": a.name, "size": size, "supersample": ss, "dirs": a.dirs, "yaw0": ISO_YAW,
            "pitch": ISO_PITCH, "frames": []}
    n_done = 0
    only = a.only.split(",") if a.only else None
    for team in teams:
        set_texture(body, team)
        for p in props:
            set_texture(p, team)
        for name, n, act, cell in clips:
            bind(source, act)
            show_props(name)
            scene.render.resolution_x = scene.render.resolution_y = cell * ss
            cam.data.ortho_scale = ortho_of[name]
            dur = next(s[4] for s in samples if s[0] == name)
            for (cname, i, f, pts, _, bpts) in [s for s in samples if s[0] == name]:
                scene.frame_set(int(f), subframe=f - int(f))
                bpy.context.view_layer.update()
                blo, bhi = bpts.min(axis=0), bpts.max(axis=0)
                cx, cy = (blo[0] + bhi[0]) / 2, (blo[1] + bhi[1]) / 2
                # disc of diameter foot_d around the body's ground point: 16 rim points
                ang = np.linspace(0, 2 * np.pi, 16, endpoint=False)
                corners = np.stack([cx + foot_d / 2 * np.cos(ang), cy + foot_d / 2 * np.sin(ang),
                                    np.full(16, ground_z)], axis=1)
                for k in range(a.dirs):
                    if only and [team, name, str(k), str(i)] != only:
                        continue
                    cam_pos, rot, _, _ = placements[(name, k)]
                    cam.location, cam.rotation_euler = cam_pos, rot
                    fx, fy = project(corners, name, k)
                    fn = f"{a.name}_{team}_{name}_d{k}_{i}.png"
                    shadow_fn = fn[:-4] + "_shadow.png" if a.shadow_pass else None
                    scene.render.filepath = os.path.join(tiles_dir, fn)
                    t0 = time.time()
                    if a.no_resume or not os.path.exists(scene.render.filepath):
                        if a.shadow_pass:
                            # character only (no ground), then the ground's shadow with the
                            # character invisible to the camera but still casting
                            ground.hide_render = True
                            scene.cycles.samples = full_samples
                            bpy.ops.render.render(write_still=True)
                            ground.hide_render = False
                            for o in [body] + props_for(name):
                                o.visible_camera = False
                            scene.cycles.samples = a.shadow_samples
                            scene.render.filepath = os.path.join(tiles_dir, shadow_fn)
                            bpy.ops.render.render(write_still=True)
                            for o in [body] + props_for(name):
                                o.visible_camera = True
                            scene.cycles.samples = full_samples
                        else:
                            bpy.ops.render.render(write_still=True)
                        n_done += 1
                    meta["frames"].append({
                        "team": team, "clip": name, "dir": k, "frame": i, "file": fn,
                        "shadow": shadow_fn,
                        "duration": round(dur, 4), "nframes": n,
                        "loop": clip_meta[name]["loop"], "impact_frame": clip_meta[name]["impact_frame"],
                        "size": cell,
                        "fp_w": round(float(fx.max() - fx.min()), 2),
                        "fp_cx": round(float((fx.max() + fx.min()) / 2), 2),
                        "fp_cy": round(float((fy.max() + fy.min()) / 2), 2)})
                    if n_done % 16 == 1:
                        print(f"   [{n_done}] {fn} {time.time()-t0:.1f}s", flush=True)
    with open(os.path.join(tiles_dir, "tiles.json"), "w") as fh:
        json.dump(meta, fh, indent=1)
    print(f"== {n_done} tiles rendered in {time.time()-t_start:.0f}s -> {tiles_dir}")

    # ---- downsample + manifest in the system python
    post = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sprites_post.py")
    subprocess.run(["/usr/bin/env", "python3", post, "--tiles", tiles_dir, "--out", a.out,
                    "--shadow-opacity", str(a.shadow_opacity), "--shadow-inner", str(a.shadow_inner),
                    "--shadow-blur", str(a.shadow_blur), "--contrast", str(a.contrast),
                    "--saturation", str(a.saturation)], check=True)


main()
