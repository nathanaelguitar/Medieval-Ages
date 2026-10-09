#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Derive a clip JSON from another one without re-tracking (system python, numpy only).

Used for clips that have no Veo video: the villagers' hammering (from the chop clip: the stance is
held at one phase, the arms are hand-keyed) and the optional carry walk (the walk with the left
arm raised to hold a bundle).

    python3 art/pipeline/derive_clip.py --base art/out/villager_male_v1/motion/chop_clip.json \\
        --out art/out/villager_male_v1/motion/build_clip.json --cycle 0.6 --loop --impact-phase 0.5 \\
        --hold-phase 0.0 --curve "upperarm_R=0:105,0.5:70,1:105" --curve "elbow_R=0:70,0.5:20,1:70" \\
        --curve "upperarm_L=0:15,1:15" --curve "elbow_L=0:15,1:15" --set retarget.foot_lock=false

``--hold-phase p`` freezes every base curve at phase p (a static stance); without it the base
curves are kept. ``--curve name=phase:value,...`` replaces or adds a curve (smoothstep between
keys, as video_to_clip's phase curves). ``--set a.b=json`` edits any field (retarget options).
"""
import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from video_to_clip import eval_phase_curve, parse_phase_curve  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cycle", type=float)
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--no-loop", action="store_true")
    ap.add_argument("--impact-phase", type=float)
    ap.add_argument("--hold-phase", type=float)
    ap.add_argument("--curve", action="append", default=[])
    ap.add_argument("--set", action="append", default=[], help="dotted.key=json value")
    a = ap.parse_args()
    with open(a.base) as fh:
        clip = json.load(fh)
    S = clip["samples"]
    phs = np.arange(S) / S
    curves = {k: np.asarray(v, dtype=np.float64) for k, v in clip["curves"].items() if v is not None}
    if a.hold_phase is not None:
        for k, v in curves.items():
            x = (a.hold_phase % 1.0) * S
            i, f = int(np.floor(x)) % S, x - np.floor(x)
            curves[k] = np.full(S, v[i] * (1 - f) + v[(i + 1) % S] * f)
    for spec in a.curve:
        name, pts = parse_phase_curve(spec)
        curves[name] = eval_phase_curve(pts, phs)
    clip["curves"] = {k: [round(float(x), 3) for x in v] for k, v in curves.items()}
    clip.pop("curves_raw", None)
    clip.pop("fourier", None)
    if a.cycle is not None:
        clip["cycle_s"] = a.cycle
    if a.loop:
        clip["loop"] = True
    if a.no_loop:
        clip["loop"] = False
    if a.impact_phase is not None:
        clip["impact_phase"] = a.impact_phase
    for spec in a.set:
        key, val = spec.split("=", 1)
        d = clip
        parts = key.split(".")
        for p in parts[:-1]:
            d = d.setdefault(p, {})
        try:
            d[parts[-1]] = json.loads(val)
        except json.JSONDecodeError:
            d[parts[-1]] = val
    clip["derived_from"] = {"base": os.path.relpath(a.base), "hold_phase": a.hold_phase, "curves": a.curve, "set": a.set}
    clip["stats"] = {k: {"min": round(float(v.min()), 1), "max": round(float(v.max()), 1)} for k, v in curves.items()}
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w") as fh:
        json.dump(clip, fh, indent=1)
    print(f"wrote {a.out}: cycle {clip['cycle_s']} s, loop {clip.get('loop')}, impact {clip.get('impact_phase')}, "
          f"curves {sorted(curves)}")


if __name__ == "__main__":
    main()
