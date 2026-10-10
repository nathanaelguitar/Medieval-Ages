# SPDX-License-Identifier: GPL-3.0-or-later
"""Blender: ground travel per walk cycle implied by a rig's walk action (no foot sliding).
Per sample, the body vertices within 0.02 units of the lowest point are the planted contact;
their displacement to the next sample (same vertex ids) is how far the ground slid under the
body. Summed over one loop = stride per cycle (rig units). Forward is -Y.
In the game (DIR_K = 35.75/144 on the @2x sprites baked at --px-per-unit 14.34) one rig unit is
14.34 * 2 * 35.75/144 = 7.12 px at zoom 1 and one tile is 64/sqrt(2) = 45.25 px of ground, so
tiles per cycle = units / 6.356; index.html's WALK_STRIDE holds that per sprite set.
   blender rig.blend --background --python art/pipeline/measure_stride.py -- walk [n_samples]"""
import sys, bpy, numpy as np
argv = sys.argv[sys.argv.index("--") + 1:]
clip = argv[0]; N = int(argv[1]) if len(argv) > 1 else 96
src = bpy.data.objects["Source"]; body = bpy.data.objects["Body"]
act = bpy.data.actions[f"clip_{clip}"]
src.animation_data.action = act
if hasattr(src.animation_data, "action_slot") and getattr(act, "slots", None):
    src.animation_data.action_slot = act.slots[0]
s, e = act.frame_range; sc = bpy.context.scene
def pts(f):
    sc.frame_set(int(f), subframe=f - int(f)); bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get(); ev = body.evaluated_get(dg); me = ev.to_mesh()
    a = np.empty(len(me.vertices) * 3); me.vertices.foreach_get("co", a); a = a.reshape(-1, 3)
    mw = np.array(ev.matrix_world); a = a @ mw[:3, :3].T + mw[:3, 3]; ev.to_mesh_clear(); return a
P = [pts(s + i * (e - s) / N) for i in range(N + 1)]
travel, slips = 0.0, []
for i in range(N):
    z = P[i][:, 2]; idx = np.where(z < z.min() + 0.02)[0]
    d = P[i + 1][idx] - P[i][idx]
    travel += float(np.mean(d[:, 1])); slips.append(float(np.mean(d[:, 1])))
h = float(P[0][:, 2].max() - P[0][:, 2].min())
print(f"STRIDE clip={clip} frames={e-s:.0f} travel_per_cycle={travel:.3f} units  body_height={h:.3f}  "
      f"per-sample min {min(slips):+.4f} max {max(slips):+.4f}")
