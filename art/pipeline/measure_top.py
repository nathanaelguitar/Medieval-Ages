#!/usr/bin/env python3
"""Z-profile of a GLB's top (inside Blender): how wide the horizontal cross-section is in each 2%
slab from the top down, so a thin feature above the head (arrow fletching, a hoe handle) can be
told from the head/helmet when choosing rig_body.py --height (which scales the bounding box).

    docker run ... medieval-blender blender --background --python art/pipeline/measure_top.py -- model.glb
"""
import sys

import bpy
import numpy as np

path = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=path)
pts = []
for o in bpy.data.objects:
    if o.type == "MESH":
        n = len(o.data.vertices)
        a = np.empty(n * 3)
        o.data.vertices.foreach_get("co", a)
        a = a.reshape(n, 3)
        mw = np.array(o.matrix_world)
        pts.append(a @ mw[:3, :3].T + mw[:3, 3])
P = np.concatenate(pts)
lo, hi = P.min(0), P.max(0)
H = hi[2] - lo[2]
print("bbox", np.round(lo, 3), np.round(hi, 3), "height", round(float(H), 3))
for k in range(0, 16):
    z1 = hi[2] - k * 0.02 * H
    z0 = z1 - 0.02 * H
    s = P[(P[:, 2] >= z0) & (P[:, 2] < z1)]
    if len(s):
        print(f"  top-{k*2:2d}%..{k*2+2:2d}%: n={len(s):6d} x-span {s[:, 0].max()-s[:, 0].min():.3f} "
              f"y-span {s[:, 1].max()-s[:, 1].min():.3f}")
