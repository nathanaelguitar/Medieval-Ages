#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Turn a side-view reference video (e.g. a Veo walk) into a looping clip for the biped rig.

Two stages in one file, so later units (archer, villager; attack/death clips) reuse it:

1. ``extract`` (system python with mediapipe, scipy, matplotlib; the Spark's ~/mp venv):
   MediaPipe Pose Landmarker (Apache-2.0; the "heavy" model) on every frame, then a planar
   (sagittal) analysis of the 2D landmarks: per-frame joint angles in the side plane (thigh,
   knee, foot pitch, upper arm, elbow, torso pitch, pelvis height). Monocular depth from a side
   view is unreliable, so nothing 3D is used. The far-side limbs, which the tracker loses behind
   the body, are taken from the near side shifted by half a cycle (``--far mirror``, default);
   ``--far track`` uses the tracked far side instead when it is well visible.

   For a cyclic clip (``--loop``, the default) one gait cycle is found from the near thigh angle
   (period by autocorrelation, heel strikes = thigh-angle maxima), each curve is low-passed
   (Savitzky-Golay) and fitted with a short Fourier series at that period, so the loop closes
   seamlessly, then resampled to ``--samples`` phases with phase 0 at the near heel strike.
   Readability gains for small sprites (``--gain``) scale the hip and arm swing about their
   means and the knee lift about its minimum.

       python3 art/pipeline/video_to_clip.py extract \\
           --video art/source/man_at_arms/video/veo_walk_side.mp4 --start 1.5 --end 8.0 \\
           --facing right --model ~/mp/models/pose_landmarker_heavy.task \\
           --out art/out/man_at_arms_v2/motion/walk_clip.json \\
           --previews art/out/man_at_arms_v2/previews/motion \\
           --gain hip=1.2,knee=1.2,arm=1.2,foot=1.0,bob=1.0 --shield-arm L --shield-arm-gain 0.3

   Inputs: the video, the trim range (seconds; Veo clips morph out of a reference image for the
   first second or so), which way the figure faces. Outputs: the clip JSON (curves in degrees per
   phase sample, Fourier coefficients, retarget options, statistics) plus diagnostics in
   ``--previews``: ``landmarks_overlay.gif`` (skeleton over the source frames), ``joint_angles.png``
   (every frame, trim and chosen cycle marked) and ``cycle_curves.png`` (the loop, raw vs. gained).

   ``oneshot`` (v4: attack, death) is the non-cyclic variant: no gait period, an explicit trim,
   both legs as tracked (a lunge does not alternate), and a piecewise-linear time warp given as
   ``--keys src_seconds=phase,...`` so a slow Veo wind-up and a fast slash each get the screen
   time they need and the impact lands on a known bake sample. Beyond the last tracked key the
   pose is synthesized from ``--synth phase:curve=value,...`` keys (smoothstep between keys;
   ``*=start`` copies the phase-0 pose, which is how the attack recovers into a seamless loop and
   the death is carried from the tracked hit reaction through a buckle and fall to the supine
   end pose). Side-plane angles that pass through "straight up" (an overhead sword) are unwrapped
   so 180 deg is no discontinuity. Legs whose MediaPipe left/right labels swap for a frame are
   swapped back (nearest ankle continuity), spikes are median-filtered before smoothing.
   Extra synthesized curves (``--phase-curve name=phase:value,...``): ``wrist_R`` (sword pitch
   relative to the forearm), ``arm_yaw_R`` (sword arm swung outward about the vertical, for the
   front/back views), ``chest_yaw`` / ``pelvis_yaw`` (torso twist), ``upperarm_L`` / ``elbow_L``
   as a shield-arm raise, ``root_fwd`` (horizontal root travel in rig units).

       python3 art/pipeline/video_to_clip.py oneshot \\
           --video art/source/man_at_arms/video/veo_attack_side.mp4 --start 0.9 --end 3.05 \\
           --keys 0.95=0,1.1=0.14,2.05=0.3,2.3=0.36,2.54=0.5,3.0=0.64 --synth "1.0:*=start" \\
           --cycle 1.0 --impact-phase 0.5 --loop --out art/out/man_at_arms_v4/motion/attack_clip.json

2. ``build_action`` (inside Blender; called by rig_body.py for ``--clip name=path.json``):
   retargets the curves onto the 0 A.D. biped ``Source`` armature as a new action, in place.
   Legs and torso are set to the absolute planar angles (world-X rotations through each joint,
   parents first); the arms start from a base pose (idle frame 1, where the props were placed)
   and get the video's swing added relative to it, the shield arm at a reduced gain; a small
   pelvis yaw / shoulder counter-yaw is added for the front and back views; the root is lowered
   each frame so the lowest body vertex sits on the same ground as the idle (no sinking, and the
   vertical bob falls out of the stance-leg geometry). Every bone is keyed on every frame
   (linear) so switching clips in the bake never carries a pose over.

   The clip's ``retarget`` block selects the v4 variants: ``arm_mode`` "relative" (walk) or
   "absolute" (sword arm set to the unwrapped planar angles, plus ``wrist_R`` and ``arm_yaw_R``);
   ``shield_mode`` "relative", "offset" (raise from the base pose by the curve values) or
   "absolute"; ``torso_mode`` "oscillation" (about the mean) or "absolute" (about ``torso_ref``,
   the video's standing lean) with ``head_counter`` keeping the head level; ``foot_lock`` shifts
   the root horizontally so the planted feet do not slide (weighted by how low each foot is),
   until ``foot_lock_until`` (phase); ``loop`` false pads ``hold_s`` of the final pose instead of
   closing the cycle. Yaw curves in the clip replace the walk's cosine model. ``impact_phase``
   and ``loop`` are stored on the action for bake_sprites.py.
"""
import argparse
import json
import math
import os
import sys
import time

import numpy as np

# MediaPipe Pose landmark indices
LM = {"nose": 0,
      "shoulder_L": 11, "shoulder_R": 12, "elbow_L": 13, "elbow_R": 14, "wrist_L": 15, "wrist_R": 16,
      "hip_L": 23, "hip_R": 24, "knee_L": 25, "knee_R": 26, "ankle_L": 27, "ankle_R": 28,
      "heel_L": 29, "heel_R": 30, "toe_L": 31, "toe_R": 32}
SIDES = ("R", "L")


# ----------------------------------------------------------------------------------------------
# stage 1: extraction (no bpy)
# ----------------------------------------------------------------------------------------------
def track(video, model, start, end, min_conf=0.3):
    """Run the Pose Landmarker over the video. Returns (pts[N,33,2] pixels, vis[N,33], fps, W, H,
    frames[list of BGR frames inside the trim range for the overlay])."""
    import cv2
    import mediapipe as mp
    from mediapipe.tasks import python as mpp
    from mediapipe.tasks.python import vision
    opts = vision.PoseLandmarkerOptions(
        base_options=mpp.BaseOptions(model_asset_path=model), running_mode=vision.RunningMode.VIDEO,
        num_poses=1, min_pose_detection_confidence=min_conf, min_tracking_confidence=min_conf)
    lm = vision.PoseLandmarker.create_from_options(opts)
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    W, H = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    pts, vis, frames = [], [], []
    n = 0
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        img = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(fr, cv2.COLOR_BGR2RGB))
        r = lm.detect_for_video(img, int(round(n * 1000.0 / fps)))
        if r.pose_landmarks:
            L = r.pose_landmarks[0]
            pts.append([[p.x * W, p.y * H] for p in L])
            vis.append([p.visibility for p in L])
        else:
            pts.append([[np.nan, np.nan]] * 33)
            vis.append([0.0] * 33)
        if start <= n / fps <= end:
            frames.append((n, fr))
        n += 1
    cap.release()
    try:
        lm.close()
    except Exception:
        pass
    return np.array(pts, dtype=np.float64), np.array(vis, dtype=np.float64), fps, W, H, frames


def fill_nan(a):
    """Linear interpolation over missing frames, per column."""
    a = a.copy()
    idx = np.arange(len(a))
    for j in range(a.shape[1] if a.ndim > 1 else 1):
        col = a[:, j] if a.ndim > 1 else a
        bad = np.isnan(col)
        if bad.any() and (~bad).any():
            col[bad] = np.interp(idx[bad], idx[~bad], col[~bad])
    return a


def planar_angles(P, facing):
    """Per-frame side-plane angles (degrees) from pixel landmarks P[N,33,2] (y down).
    Forward is +x after flipping for ``facing``. Conventions (all "positive = forward/up"):
      thigh_S, shank_S, upperarm_S, forearm_S: segment angle from the downward vertical, positive
          when the distal end is forward;  knee_S = thigh - shank (flexion >= 0 normally);
          elbow_S = forearm - upperarm (flexion);
      foot_S: heel->toe pitch from horizontal, positive toes up;
      torso: mid-hip -> mid-shoulder from the upward vertical, positive leaning forward;
      pelvis_y: mid-hip height in leg lengths, positive up, mean removed later."""
    sgn = 1.0 if facing == "right" else -1.0
    x = P[:, :, 0] * sgn
    y = P[:, :, 1]

    def down(a, b):      # a proximal, b distal, segment hangs down
        return np.degrees(np.arctan2(x[:, b] - x[:, a], y[:, b] - y[:, a]))

    out = {}
    for s in SIDES:
        hip, knee, ank = LM[f"hip_{s}"], LM[f"knee_{s}"], LM[f"ankle_{s}"]
        sho, elb, wri = LM[f"shoulder_{s}"], LM[f"elbow_{s}"], LM[f"wrist_{s}"]
        heel, toe = LM[f"heel_{s}"], LM[f"toe_{s}"]
        th, sh = down(hip, knee), down(knee, ank)
        ua, fa = down(sho, elb), down(elb, wri)
        out[f"thigh_{s}"] = th
        out[f"knee_{s}"] = th - sh
        out[f"foot_{s}"] = np.degrees(np.arctan2(y[:, heel] - y[:, toe], x[:, toe] - x[:, heel]))
        out[f"upperarm_{s}"] = ua
        out[f"elbow_{s}"] = fa - ua
    mhx = (x[:, LM["hip_L"]] + x[:, LM["hip_R"]]) / 2
    mhy = (y[:, LM["hip_L"]] + y[:, LM["hip_R"]]) / 2
    msx = (x[:, LM["shoulder_L"]] + x[:, LM["shoulder_R"]]) / 2
    msy = (y[:, LM["shoulder_L"]] + y[:, LM["shoulder_R"]]) / 2
    out["torso"] = np.degrees(np.arctan2(msx - mhx, mhy - msy))
    leg = np.nanmean(np.hypot(x[:, LM["knee_R"]] - x[:, LM["hip_R"]], y[:, LM["knee_R"]] - y[:, LM["hip_R"]])
                     + np.hypot(x[:, LM["ankle_R"]] - x[:, LM["knee_R"]], y[:, LM["ankle_R"]] - y[:, LM["knee_R"]]))
    out["pelvis_y"] = -(mhy - np.nanmean(mhy)) / leg
    return out, leg


def smooth(a, fps, window_s=0.3, order=3):
    from scipy.signal import savgol_filter
    w = int(round(window_s * fps)) | 1
    w = max(w, order + 2)
    return savgol_filter(a, w, order)


def find_period(sig, fps, min_s=0.5, max_s=2.5):
    """Fundamental period in frames from the autocorrelation's first peak."""
    s = sig - sig.mean()
    n = len(s)
    ac = np.correlate(s, s, mode="full")[n - 1:]
    ac /= ac[0] + 1e-12
    lo, hi = int(min_s * fps), min(int(max_s * fps), n - 2)
    k = lo + int(np.argmax(ac[lo:hi]))
    # parabolic refinement
    if 0 < k < len(ac) - 1:
        y0, y1, y2 = ac[k - 1], ac[k], ac[k + 1]
        d = (y0 - y2) / (2 * (y0 - 2 * y1 + y2) + 1e-12)
        k = k + float(np.clip(d, -1, 1))
    return float(k), float(ac[int(round(k))])


def local_maxima(sig, min_sep):
    from scipy.signal import find_peaks
    pk, _ = find_peaks(sig, distance=max(1, int(min_sep)), prominence=(sig.max() - sig.min()) * 0.3)
    return pk


def fourier_fit(t, y, T, K):
    """Least-squares a0 + sum a_k cos(2 pi k t/T) + b_k sin(...)."""
    w = 2 * np.pi / T
    cols = [np.ones_like(t)]
    for k in range(1, K + 1):
        cols += [np.cos(k * w * t), np.sin(k * w * t)]
    A = np.stack(cols, axis=1)
    c, *_ = np.linalg.lstsq(A, y, rcond=None)
    return {"a0": float(c[0]), "a": [float(v) for v in c[1::2]], "b": [float(v) for v in c[2::2]]}


def fourier_eval(coef, phase):
    """phase in cycles (0..1), array ok."""
    ph = np.asarray(phase, dtype=np.float64) * 2 * np.pi
    y = np.full_like(ph, coef["a0"])
    for k, (a, b) in enumerate(zip(coef["a"], coef["b"]), start=1):
        y = y + a * np.cos(k * ph) + b * np.sin(k * ph)
    return y


def shift_coef(coef, dphase):
    """Coefficients of f(phase + dphase)."""
    out = {"a0": coef["a0"], "a": [], "b": []}
    for k, (a, b) in enumerate(zip(coef["a"], coef["b"]), start=1):
        d = 2 * np.pi * k * dphase
        out["a"].append(float(a * np.cos(d) + b * np.sin(d)))
        out["b"].append(float(-a * np.sin(d) + b * np.cos(d)))
    return out


def parse_kv(s, cast=float):
    out = {}
    for item in (s or "").split(","):
        if item.strip():
            k, v = item.split("=")
            out[k.strip()] = cast(v)
    return out


def extract(a):
    t0 = time.time()
    pts, vis, fps, W, H, frames = track(a.video, a.model, a.start, a.end, a.min_conf)
    n = len(pts)
    print(f"== tracked {n} frames at {fps:.0f} fps ({W}x{H}) in {time.time()-t0:.1f}s; "
          f"{int(np.sum(~np.isnan(pts[:, 0, 0])))} with a pose")
    i0, i1 = int(math.ceil(a.start * fps)), min(n - 1, int(math.floor(a.end * fps)))
    near = "R" if a.facing == "right" else "L"
    far = "L" if near == "R" else "R"
    vr = {name: float(np.nanmean(vis[i0:i1 + 1, idx])) for name, idx in LM.items()}
    print("   mean visibility in trim:", {k: round(v, 2) for k, v in vr.items()})
    for j in ("knee", "ankle", "elbow", "wrist"):
        if vr[f"{j}_{near}"] + 0.05 < vr[f"{j}_{far}"]:
            print(f"   WARNING: {j}: the far side ({far}) is more visible than the near side ({near}); "
                  f"check --facing / MediaPipe's left-right assignment")
    P = fill_nan(pts.reshape(n, -1)).reshape(n, 33, 2)
    raw, leg_px = planar_angles(P, a.facing)
    sm = {k: smooth(v, fps) for k, v in raw.items()}
    seg = {k: v[i0:i1 + 1] for k, v in sm.items()}
    t = (np.arange(i0, i1 + 1) - i0) / fps

    # ---- cycle: period from the near thigh, heel strikes from its maxima
    T_fr, ac_peak = find_period(seg[f"thigh_{near}"], fps)
    T_s = T_fr / fps
    peaks = local_maxima(seg[f"thigh_{near}"], T_fr * 0.6)
    strikes = (peaks + i0) / fps
    gaps = np.diff(strikes)
    print(f"== period {T_s:.3f} s ({T_fr:.1f} frames, autocorr {ac_peak:.2f}); near heel strikes at "
          f"{np.round(strikes, 2).tolist()} s, intervals {np.round(gaps, 2).tolist()}")
    far_peaks = local_maxima(seg[f"thigh_{far}"], T_fr * 0.6)
    if len(far_peaks) and len(peaks):
        # far-side strikes should sit half a cycle from the near ones
        offs = [((fp - peaks[np.argmin(np.abs(peaks - fp))]) / T_fr) % 1.0 for fp in far_peaks]
        print(f"   far-side thigh maxima offset from nearest near-side maximum: "
              f"{np.round(offs, 2).tolist()} cycles (0.5 = clean alternation)")
    # the cycle whose length is closest to the period
    if len(peaks) >= 2:
        j = int(np.argmin(np.abs(np.diff(peaks) - T_fr)))
        cyc = (int(peaks[j]), int(peaks[j + 1]))
        drift = float(np.max(np.abs(gaps - T_s)) / T_s) if len(gaps) else 0.0
    else:
        cyc = (0, int(round(T_fr)))
        drift = 0.0
    print(f"   chosen cycle: frames {cyc[0]+i0}..{cyc[1]+i0} ({(cyc[0]+i0)/fps:.2f}..{(cyc[1]+i0)/fps:.2f} s, "
          f"{(cyc[1]-cyc[0])/fps:.3f} s); tempo drift {drift*100:.0f}%")
    fit_all = drift <= a.max_drift and a.fit == "all"
    if fit_all:
        tf, yf = t, lambda k: seg[k]
        T_fit = T_s
        print(f"   Fourier fit over the whole trim ({len(t)} frames, K={a.harmonics})")
    else:
        sl = slice(cyc[0], cyc[1] + 1)
        tf, yf = t[sl], lambda k: seg[k][sl]
        T_fit = (cyc[1] - cyc[0]) / fps
        print(f"   Fourier fit over the chosen cycle only (K={a.harmonics}), T={T_fit:.3f} s")
    coef = {k: fourier_fit(tf, yf(k), T_fit, a.harmonics) for k in seg}
    # phase 0 = near heel strike = maximum of the fitted near thigh angle
    ph = np.linspace(0, 1, 720, endpoint=False)
    p0 = float(ph[np.argmax(fourier_eval(coef[f"thigh_{near}"], ph))])
    coef = {k: shift_coef(c, p0) for k, c in coef.items()}
    # far-side check: phase offset of the far thigh maximum vs the near one
    far_p = float(ph[np.argmax(fourier_eval(coef[f"thigh_{far}"], ph))])
    far_rms = float(np.sqrt(np.mean((fourier_eval(coef[f"thigh_{far}"], ph)
                                     - fourier_eval(coef[f"thigh_{near}"], (ph + 0.5) % 1)) ** 2)))
    print(f"   far thigh (tracked) peaks at phase {far_p:.2f}; RMS vs near shifted by 0.5: {far_rms:.1f} deg")

    # ---- curves per phase sample
    S = a.samples
    phs = np.arange(S) / S
    curves = {}
    for j in ("thigh", "knee", "foot", "upperarm", "elbow"):
        nearc = fourier_eval(coef[f"{j}_{near}"], phs)
        if a.far == "mirror":
            farc = fourier_eval(coef[f"{j}_{near}"], (phs + 0.5) % 1)
        else:
            farc = fourier_eval(coef[f"{j}_{far}"], phs)
        curves[f"{j}_{near}"], curves[f"{j}_{far}"] = nearc, farc
    curves["torso"] = fourier_eval(coef["torso"], phs)
    curves["pelvis_y"] = fourier_eval(coef["pelvis_y"], phs)
    # foot pitch zero = flat foot: reference at mid-stance (thigh crosses zero while descending)
    for s in SIDES:
        th = curves[f"thigh_{s}"]
        cross = [i for i in range(S) if th[i] >= 0 > th[(i + 1) % S]]
        ref = float(curves[f"foot_{s}"][cross[0]]) if cross else float(np.median(curves[f"foot_{s}"]))
        curves[f"foot_{s}"] = curves[f"foot_{s}"] - ref
    curves["knee_R"] = np.maximum(curves["knee_R"], 0)
    curves["knee_L"] = np.maximum(curves["knee_L"], 0)
    raw_curves = {k: v.copy() for k, v in curves.items()}

    # ---- readability gains
    g = {"hip": 1.0, "knee": 1.0, "arm": 1.0, "foot": 1.0, "bob": 1.0, "torso": 1.0}
    g.update(parse_kv(a.gain))
    for s in SIDES:
        c = curves[f"thigh_{s}"]; curves[f"thigh_{s}"] = c.mean() + g["hip"] * (c - c.mean())
        c = curves[f"knee_{s}"]; curves[f"knee_{s}"] = c.min() + g["knee"] * (c - c.min())
        curves[f"foot_{s}"] = g["foot"] * curves[f"foot_{s}"]
        c = curves[f"upperarm_{s}"]; curves[f"upperarm_{s}"] = c.mean() + g["arm"] * (c - c.mean())
        c = curves[f"elbow_{s}"]; curves[f"elbow_{s}"] = c.mean() + g["arm"] * (c - c.mean())
    c = curves["torso"]; curves["torso"] = c.mean() + g["torso"] * (c - c.mean())

    def stats(cv):
        return {k: {"min": round(float(v.min()), 1), "max": round(float(v.max()), 1),
                    "range": round(float(v.max() - v.min()), 1)} for k, v in cv.items()}
    st_raw, st_out = stats(raw_curves), stats(curves)
    print("== joint ranges (deg; pelvis_y in leg lengths), raw -> gained:")
    for k in curves:
        r0, r1 = st_raw[k], st_out[k]
        print(f"   {k:12s} {r0['min']:7.1f}..{r0['max']:6.1f} (range {r0['range']:5.1f})  ->  "
              f"{r1['min']:7.1f}..{r1['max']:6.1f} (range {r1['range']:5.1f})")

    retarget = {"near": near, "shield_arm": a.shield_arm, "shield_arm_gain": a.shield_arm_gain,
                "elbow_gain": a.elbow_gain, "pelvis_yaw_deg": a.pelvis_yaw, "chest_yaw_deg": a.chest_yaw,
                "bob_gain": g["bob"], "torso_mode": "oscillation"}
    clip = {"source": os.path.relpath(a.video), "trim_s": [a.start, a.end], "facing": a.facing,
            "video_fps": fps, "cycle_s": round(T_fit, 4), "cycle_frames": [cyc[0] + i0, cyc[1] + i0],
            "heel_strikes_s": [round(float(v), 3) for v in strikes], "tempo_drift": round(drift, 3),
            "fit": "all" if fit_all else "cycle", "harmonics": a.harmonics, "far": a.far,
            "far_check": {"far_thigh_peak_phase": round(far_p, 3), "rms_vs_mirror_deg": round(far_rms, 1)},
            "phase0": f"heel strike of the near ({near}) foot", "samples": S, "loop": True,
            "gains": g, "retarget": retarget,
            "curves": {k: [round(float(x), 3) for x in v] for k, v in curves.items()},
            "curves_raw": {k: [round(float(x), 3) for x in v] for k, v in raw_curves.items()},
            "fourier": coef, "stats": {"raw": st_raw, "gained": st_out},
            "visibility": {k: round(v, 2) for k, v in vr.items()}}
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w") as fh:
        json.dump(clip, fh, indent=1)
    print(f"== wrote {a.out}")

    if a.previews:
        os.makedirs(a.previews, exist_ok=True)
        write_plots(a, sm, i0, i1, cyc, fps, near, far, phs, raw_curves, curves, coef, strikes, T_fit)
        write_overlay(a, frames, P, vis, fps, near, far, cyc, i0, T_fr)
    print(f"== extract done in {time.time()-t0:.1f}s")


def write_plots(a, sm, i0, i1, cyc, fps, near, far, phs, raw_curves, curves, coef, strikes, T_fit):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    n = len(next(iter(sm.values())))
    tt = np.arange(n) / fps
    rows = [("thigh", "hip flexion (deg, + forward)"), ("knee", "knee flexion (deg)"),
            ("foot", "foot pitch (deg, + toes up)"), ("upperarm", "shoulder flexion (deg)"),
            ("elbow", "elbow flexion (deg)")]
    fig, axes = plt.subplots(len(rows) + 1, 1, figsize=(13, 2.2 * (len(rows) + 1)), sharex=True)
    for ax, (j, label) in zip(axes, rows):
        ax.plot(tt, sm[f"{j}_{near}"], color="#1f77b4", lw=1.4, label=f"{j}_{near} (near)")
        ax.plot(tt, sm[f"{j}_{far}"], color="#d62728", lw=1.0, alpha=0.7, label=f"{j}_{far} (far, tracked)")
        ax.set_ylabel(label, fontsize=8)
        ax.legend(loc="upper right", fontsize=7)
    axes[-1].plot(tt, sm["torso"], color="#2ca02c", lw=1.2, label="torso pitch (deg)")
    axes[-1].plot(tt, sm["pelvis_y"] * 100, color="#9467bd", lw=1.2, label="pelvis height (% leg)")
    axes[-1].legend(loc="upper right", fontsize=7)
    axes[-1].set_xlabel("video time (s)")
    for ax in axes:
        ax.axvspan(0, i0 / fps, color="k", alpha=0.08)
        ax.axvspan(i1 / fps, tt[-1], color="k", alpha=0.08)
        ax.axvspan((cyc[0] + i0) / fps, (cyc[1] + i0) / fps, color="#ffcc00", alpha=0.18)
        for s in strikes:
            ax.axvline(s, color="k", lw=0.5, ls=":")
        ax.grid(alpha=0.3)
    fig.suptitle(f"{os.path.basename(a.video)}: MediaPipe planar joint angles (Savitzky-Golay); "
                 f"grey = outside trim, yellow = chosen cycle, dotted = near heel strikes")
    fig.tight_layout()
    p = os.path.join(a.previews, "joint_angles.png")
    fig.savefig(p, dpi=110)
    plt.close(fig)
    print("   plot", p)

    fig, axes = plt.subplots(2, 4, figsize=(15, 6.5))
    fine = np.linspace(0, 1, 200)
    items = [(f"thigh_{near}", "hip flexion"), (f"knee_{near}", "knee flexion"), (f"foot_{near}", "foot pitch"),
             (f"upperarm_{near}", "shoulder flexion"), (f"elbow_{near}", "elbow flexion"),
             ("torso", "torso pitch"), ("pelvis_y", "pelvis height (leg lengths)"),
             (f"thigh_{far}", f"hip {far} (far: {a.far})")]
    for ax, (k, label) in zip(axes.flat, items):
        if k in coef and not (a.far == "mirror" and k.endswith(far) and k != "torso"):
            ax.plot(fine, fourier_eval(coef[k], fine), color="#999", lw=1, label="Fourier fit")
        ax.plot(phs, raw_curves[k], "o-", ms=3, color="#1f77b4", lw=1, label="loop (raw)")
        if np.any(np.abs(curves[k] - raw_curves[k]) > 1e-6):
            ax.plot(phs, curves[k], "s-", ms=3, color="#d62728", lw=1, label="loop (gained)")
        ax.set_title(label, fontsize=9)
        ax.set_xlabel("phase (0 = near heel strike)", fontsize=8)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=7)
    fig.suptitle(f"one cycle = {a.samples} samples, T = {T_fit:.3f} s; gains {a.gain}")
    fig.tight_layout()
    p = os.path.join(a.previews, "cycle_curves.png")
    fig.savefig(p, dpi=110)
    plt.close(fig)
    print("   plot", p)


def write_overlay(a, frames, P, vis, fps, near, far, cyc, i0, T_fr, width=640, step=2):
    """GIF of the tracked skeleton over the source frames: two cycles from the chosen cycle start,
    near side green, far side red, faint when visibility is low."""
    import cv2
    from PIL import Image
    f0 = cyc[0] + i0
    f1 = min(f0 + int(round(2 * T_fr)), frames[-1][0])
    bones = [("shoulder", "elbow"), ("elbow", "wrist"), ("hip", "knee"), ("knee", "ankle"),
             ("ankle", "heel"), ("heel", "toe"), ("ankle", "toe"), ("shoulder", "hip")]
    sel = [(n, fr) for n, fr in frames if f0 <= n <= f1][::step]
    sc = width / frames[0][1].shape[1]
    ims = []
    for n, fr in sel:
        im = cv2.resize(fr, (width, int(fr.shape[0] * sc)))
        for s, col in ((far, (60, 60, 230)), (near, (60, 200, 60))):
            for b0, b1 in bones:
                p, q = LM[f"{b0}_{s}"], LM[f"{b1}_{s}"]
                v = min(vis[n, p], vis[n, q])
                c = tuple(int(x * (0.35 + 0.65 * v)) for x in col)
                cv2.line(im, tuple(np.round(P[n, p] * sc).astype(int)), tuple(np.round(P[n, q] * sc).astype(int)),
                         c, 2 if s == near else 1, cv2.LINE_AA)
        cv2.line(im, tuple(np.round((P[n, LM["hip_L"]] + P[n, LM["hip_R"]]) / 2 * sc).astype(int)),
                 tuple(np.round((P[n, LM["shoulder_L"]] + P[n, LM["shoulder_R"]]) / 2 * sc).astype(int)),
                 (230, 200, 60), 1, cv2.LINE_AA)
        cv2.putText(im, f"f{n} {n/fps:.2f}s  phase {((n-f0)/T_fr)%1:.2f}", (8, 20), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, (255, 255, 255), 1, cv2.LINE_AA)
        ims.append(Image.fromarray(cv2.cvtColor(im, cv2.COLOR_BGR2RGB)).quantize(colors=128))
    p = os.path.join(a.previews, "landmarks_overlay.gif")
    ims[0].save(p, save_all=True, append_images=ims[1:], duration=int(1000 * step / fps), loop=0)
    print(f"   overlay {p} ({len(ims)} frames)")


# ----------------------------------------------------------------------------------------------
# stage 1b: one-shot clips (attack, death)
# ----------------------------------------------------------------------------------------------
LEG_LM = ("knee", "ankle", "heel", "toe")


def unswap_legs(P, i0, i1):
    """MediaPipe occasionally swaps the left/right leg labels for a frame or two when the legs
    overlap. Inside the trim, swap a frame's leg landmarks back when that keeps the ankles closer
    to the previous (corrected) frame's. Returns the number of frames swapped."""
    n = 0
    for i in range(i0 + 1, i1 + 1):
        aR, aL = P[i, LM["ankle_R"]], P[i, LM["ankle_L"]]
        pR, pL = P[i - 1, LM["ankle_R"]], P[i - 1, LM["ankle_L"]]
        keep = np.hypot(*(aR - pR)) + np.hypot(*(aL - pL))
        swap = np.hypot(*(aL - pR)) + np.hypot(*(aR - pL))
        if swap + 1e-6 < keep * 0.6:
            for j in LEG_LM:
                r, l = LM[f"{j}_R"], LM[f"{j}_L"]
                P[i, r], P[i, l] = P[i, l].copy(), P[i, r].copy()
            n += 1
    return n


def arm_angles_unwrapped(P, facing, side):
    """Upper arm and forearm absolute side-plane angles (deg, 0 = hanging, + forward, continuing
    through 180 = straight up and 270 = pointing back), unwrapped over time so an overhead
    wind-up is continuous. Returns (upperarm, forearm)."""
    sgn = 1.0 if facing == "right" else -1.0
    x, y = P[:, :, 0] * sgn, P[:, :, 1]
    sho, elb, wri = LM[f"shoulder_{side}"], LM[f"elbow_{side}"], LM[f"wrist_{side}"]
    ua = np.arctan2(x[:, elb] - x[:, sho], y[:, elb] - y[:, sho])
    fa = np.arctan2(x[:, wri] - x[:, elb], y[:, wri] - y[:, elb])
    return np.degrees(np.unwrap(ua)), np.degrees(np.unwrap(fa))


def despike(a, k=5):
    from scipy.signal import medfilt
    return medfilt(a, k)


def smoothstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def parse_keys(s):
    """'0.95=0,1.1=0.14,...' -> [(src_s, phase), ...] sorted by phase."""
    out = []
    for item in s.split(","):
        a, b = item.split("=")
        out.append((float(a), float(b)))
    return sorted(out, key=lambda kv: kv[1])


def parse_synth(items):
    """['0.55:thigh_R=60,knee_R=120', '1.0:*=start'] -> [(phase, {curve: value|'start'})]."""
    out = []
    for s in items or []:
        ph, rest = s.split(":", 1)
        vals = {}
        for kv in rest.split(","):
            if kv.strip():
                k, v = kv.split("=")
                vals[k.strip()] = v.strip() if v.strip() in ("start", "hold") else float(v)
        out.append((float(ph), vals))
    return sorted(out, key=lambda kv: kv[0])


def parse_phase_curve(s):
    """'wrist_R=0:0,0.3:45,1:0' -> (name, [(phase, value), ...])."""
    name, rest = s.split("=", 1)
    pts = sorted((float(p), float(v)) for p, v in (kv.split(":") for kv in rest.split(",")))
    return name.strip(), pts


def eval_phase_curve(pts, phs, loop=True):
    """Smoothstep interpolation between (phase, value) keys; constant outside the key range."""
    out = np.empty(len(phs))
    for i, p in enumerate(phs):
        if p <= pts[0][0]:
            out[i] = pts[0][1]
        elif p >= pts[-1][0]:
            out[i] = pts[-1][1]
        else:
            for (p0, v0), (p1, v1) in zip(pts[:-1], pts[1:]):
                if p0 <= p <= p1:
                    out[i] = v0 + (v1 - v0) * smoothstep((p - p0) / max(p1 - p0, 1e-9))
                    break
    return out


def extract_oneshot(a):
    """Attack / death: tracked segment with a time warp, then synthesized keys (see docstring)."""
    t0 = time.time()
    pts, vis, fps, W, H, frames = track(a.video, a.model, a.start, a.end, a.min_conf)
    n = len(pts)
    print(f"== tracked {n} frames at {fps:.0f} fps ({W}x{H}) in {time.time()-t0:.1f}s; "
          f"{int(np.sum(~np.isnan(pts[:, 0, 0])))} with a pose")
    i0, i1 = int(math.ceil(a.start * fps)), min(n - 1, int(math.floor(a.end * fps)))
    near = "R" if a.facing == "right" else "L"
    far = "L" if near == "R" else "R"
    vr = {name: float(np.nanmean(vis[i0:i1 + 1, idx])) for name, idx in LM.items()}
    print("   mean visibility in trim:", {k: round(v, 2) for k, v in vr.items()})
    P = fill_nan(pts.reshape(n, -1)).reshape(n, 33, 2)
    nsw = unswap_legs(P, max(1, i0 - 2), i1)
    print(f"   leg label swaps undone: {nsw}")
    raw, leg_px = planar_angles(P, a.facing)
    ua_n, fa_n = arm_angles_unwrapped(P, a.facing, near)
    raw[f"upperarm_{near}"] = ua_n
    raw[f"elbow_{near}"] = fa_n - ua_n
    win = a.smooth_s
    sm = {k: smooth(despike(v), fps, window_s=win) for k, v in raw.items()}
    tt = np.arange(n) / fps

    keys = parse_keys(a.keys)
    synth = parse_synth(a.synth)
    if a.loop and not any(p >= 1.0 for p, _ in synth):
        synth.append((1.0, {"*": "start"}))
    ks, kp = [k[0] for k in keys], [k[1] for k in keys]
    if not (a.start <= min(ks) and max(ks) <= a.end):
        sys.exit(f"--keys must lie inside --start/--end ({a.start}..{a.end}): {keys}")
    p_track = kp[-1]
    S = a.samples
    phs = np.arange(S) / S
    tracked = phs <= p_track + 1e-9
    src_t = np.interp(phs[tracked], kp, ks)       # piecewise-linear time warp
    print(f"== warp keys (src s -> phase): {[(round(s, 2), round(p, 3)) for s, p in keys]}; "
          f"{int(tracked.sum())}/{S} samples tracked, synth keys at {[p for p, _ in synth]}")

    names = ([f"{j}_{s}" for j in ("thigh", "knee", "foot") for s in SIDES]
             + [f"upperarm_{near}", f"elbow_{near}", "torso"])
    curves = {k: np.zeros(S) for k in names}
    for k in names:
        curves[k][tracked] = np.interp(src_t, tt, sm[k])
    # the unwrapped arm angles may sit on any 360-degree branch: bring the phase-0 values into
    # (-180, 180] so synthesized keys (plain degrees) do not make the arm spin a full turn
    ua = curves[f"upperarm_{near}"]
    fa = ua + curves[f"elbow_{near}"]
    ua = ua - 360.0 * np.round(ua[0] / 360.0)
    fa = fa - 360.0 * np.round(fa[0] / 360.0)
    curves[f"upperarm_{near}"], curves[f"elbow_{near}"] = ua, fa - ua
    # foot pitch: zero = the pitch at the phase-0 stance (planted feet), per foot
    for s in SIDES:
        curves[f"foot_{s}"] -= curves[f"foot_{s}"][0]
    for s in SIDES:
        curves[f"knee_{s}"] = np.maximum(curves[f"knee_{s}"], 0)
    # torso reference: the standing lean (first --torso-ref-window seconds of the video)
    if a.torso_ref == "auto":
        w = int(a.torso_ref_window * fps)
        torso_ref = float(np.mean(sm["torso"][:max(w, 1)]))
    else:
        torso_ref = float(a.torso_ref)
    raw_curves = {k: v.copy() for k, v in curves.items()}

    # ---- readability gains, about the phase-0 pose (the guard)
    g = {"arm": 1.0, "crouch": 1.0, "stance": 1.0, "foot": 1.0, "torso": 1.0}
    g.update(parse_kv(a.gain))
    for s in SIDES:
        for j in ("thigh", "knee"):
            c = curves[f"{j}_{s}"] * g["stance"]          # whole stance about standing straight
            curves[f"{j}_{s}"] = c[0] + g["crouch"] * (c - c[0])   # excursion about the phase-0 stance
        curves[f"foot_{s}"] = g["foot"] * curves[f"foot_{s}"]
    for j in ("upperarm", "elbow"):
        c = curves[f"{j}_{near}"]; curves[f"{j}_{near}"] = c[0] + g["arm"] * (c - c[0])
    c = curves["torso"]; curves["torso"] = torso_ref + g["torso"] * (c - torso_ref)
    for s in SIDES:
        curves[f"knee_{s}"] = np.maximum(curves[f"knee_{s}"], 0)

    # ---- synthesized keys after the tracked range (smoothstep between consecutive keys)
    extra = {}
    for spec in a.phase_curve or []:
        name, pts_ = parse_phase_curve(spec)
        extra[name] = pts_
    last_vals = {k: float(curves[k][tracked][-1]) for k in names}
    key_list = [(p_track, dict(last_vals))]
    for ph, vals in synth:
        prev = dict(key_list[-1][1])
        if vals.get("*") == "start":
            prev = {k: float(curves[k][0]) for k in names}
        for k, v in vals.items():
            if k == "*":
                continue
            if k not in names:
                if k not in extra:
                    sys.exit(f"--synth: unknown curve {k}")
                continue
            prev[k] = float(curves[k][0]) if v == "start" else (prev[k] if v == "hold" else v)
        key_list.append((ph, prev))
    for k in names:
        pts_ = [(ph, vals[k]) for ph, vals in key_list]
        if len(pts_) > 1:
            curves[k][~tracked] = eval_phase_curve(pts_, phs[~tracked])
    for name, pts_ in extra.items():
        curves[name] = eval_phase_curve(pts_, phs)

    def stats(cv):
        return {k: {"min": round(float(v.min()), 1), "max": round(float(v.max()), 1),
                    "range": round(float(v.max() - v.min()), 1)} for k, v in cv.items()}
    st = stats(curves)
    print("== output curve ranges (deg; root_fwd in units):")
    for k, v in st.items():
        print(f"   {k:12s} {v['min']:7.1f}..{v['max']:6.1f} (range {v['range']:5.1f})")
    print(f"   torso ref {torso_ref:.1f} deg; gains {g}")

    retarget = {"near": near, "sword_arm": near, "shield_arm": far, "arm_mode": a.arm_mode,
                "shield_mode": a.shield_mode, "torso_mode": "absolute", "torso_ref": torso_ref,
                "head_counter": a.head_counter, "foot_lock": a.foot_lock, "foot_lock_until": a.foot_lock_until,
                "bob_gain": 1.0, "clamp_props": a.clamp_props, "hold_s": a.hold_s}
    clip = {"mode": "oneshot", "source": os.path.relpath(a.video), "trim_s": [a.start, a.end],
            "facing": a.facing, "video_fps": fps, "cycle_s": a.cycle, "loop": bool(a.loop),
            "impact_phase": a.impact_phase, "keys": keys, "synth": [[p, v] for p, v in synth],
            "samples": S, "gains": g, "retarget": retarget,
            "curves": {k: [round(float(x), 3) for x in v] for k, v in curves.items()},
            "curves_raw": {k: [round(float(x), 3) for x in v] for k, v in raw_curves.items()},
            "stats": st, "visibility": {k: round(v, 2) for k, v in vr.items()}}
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w") as fh:
        json.dump(clip, fh, indent=1)
    print(f"== wrote {a.out}")
    if a.previews:
        os.makedirs(a.previews, exist_ok=True)
        write_oneshot_plots(a, sm, i0, i1, fps, near, far, keys, phs, curves, tracked, torso_ref)
        write_overlay(a, frames, P, vis, fps, near, far, (0, i1 - i0), i0, (i1 - i0) / 2.0)
    print(f"== oneshot done in {time.time()-t0:.1f}s")


def write_oneshot_plots(a, sm, i0, i1, fps, near, far, keys, phs, curves, tracked, torso_ref):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    n = len(next(iter(sm.values())))
    tt = np.arange(n) / fps
    rows = [("thigh", "hip flexion (deg, + forward)"), ("knee", "knee flexion (deg)"),
            ("foot", "foot pitch (deg, + toes up)")]
    fig, axes = plt.subplots(len(rows) + 2, 1, figsize=(13, 2.2 * (len(rows) + 2)), sharex=True)
    for ax, (j, label) in zip(axes, rows):
        ax.plot(tt, sm[f"{j}_{near}"], color="#1f77b4", lw=1.4, label=f"{j}_{near} (near)")
        ax.plot(tt, sm[f"{j}_{far}"], color="#d62728", lw=1.0, alpha=0.8, label=f"{j}_{far} (far, tracked)")
        ax.set_ylabel(label, fontsize=8)
        ax.legend(loc="upper right", fontsize=7)
    axes[-2].plot(tt, sm[f"upperarm_{near}"], color="#1f77b4", lw=1.4, label=f"upper arm {near} (abs, unwrapped)")
    axes[-2].plot(tt, sm[f"upperarm_{near}"] + sm[f"elbow_{near}"], color="#ff7f0e", lw=1.2, label="forearm (abs)")
    axes[-2].set_ylabel("sword arm (deg; 90 fwd, 180 up, 270 back)", fontsize=8)
    axes[-2].legend(loc="upper right", fontsize=7)
    axes[-1].plot(tt, sm["torso"], color="#2ca02c", lw=1.2, label="torso pitch (deg, + forward)")
    axes[-1].axhline(torso_ref, color="#2ca02c", lw=0.6, ls="--", label="torso ref")
    axes[-1].plot(tt, sm["pelvis_y"] * 100, color="#9467bd", lw=1.2, label="pelvis height (% leg)")
    axes[-1].legend(loc="upper right", fontsize=7)
    axes[-1].set_xlabel("video time (s)")
    for ax in axes:
        ax.axvspan(0, i0 / fps, color="k", alpha=0.08)
        ax.axvspan(i1 / fps, tt[-1], color="k", alpha=0.08)
        for s, p in keys:
            ax.axvline(s, color="k", lw=0.6, ls=":")
            ax.text(s, ax.get_ylim()[1], f"{p:.2f}", fontsize=6, va="top")
        ax.grid(alpha=0.3)
    fig.suptitle(f"{os.path.basename(a.video)}: planar joint angles (median + Savitzky-Golay); "
                 f"grey = outside trim, dotted = warp keys (labelled with the output phase)")
    fig.tight_layout()
    p = os.path.join(a.previews, "joint_angles.png")
    fig.savefig(p, dpi=110)
    plt.close(fig)
    print("   plot", p)

    items = [k for k in curves]
    cols = 4
    rws = int(math.ceil(len(items) / cols))
    fig, axes = plt.subplots(rws, cols, figsize=(15, 2.6 * rws))
    for ax, k in zip(axes.flat, items):
        ax.plot(phs, curves[k], "o-", ms=3, lw=1, color="#1f77b4")
        ax.axvspan(phs[tracked][-1], 1.0, color="#ffcc00", alpha=0.18)
        if a.impact_phase is not None:
            ax.axvline(a.impact_phase, color="#d62728", lw=0.8, ls="--")
        ax.set_title(k, fontsize=9)
        ax.grid(alpha=0.3)
    for ax in list(axes.flat)[len(items):]:
        ax.axis("off")
    fig.suptitle(f"{os.path.basename(a.out)}: {a.samples} samples over {a.cycle:.2f} s; yellow = synthesized, "
                 f"red = impact phase {a.impact_phase}; gains {a.gain}")
    fig.tight_layout()
    p = os.path.join(a.previews, "cycle_curves.png")
    fig.savefig(p, dpi=110)
    plt.close(fig)
    print("   plot", p)


# ----------------------------------------------------------------------------------------------
# stage 2: Blender-side retarget (imported by rig_body.py; needs bpy)
# ----------------------------------------------------------------------------------------------
def _interp_loop(samples, phase):
    s = np.asarray(samples, dtype=np.float64)
    n = len(s)
    x = (phase % 1.0) * n
    i = int(math.floor(x)) % n
    f = x - math.floor(x)
    return float(s[i] * (1 - f) + s[(i + 1) % n] * f)


def _interp_hold(samples, phase):
    """Like _interp_loop but the last sample holds (non-looping clips)."""
    s = np.asarray(samples, dtype=np.float64)
    n = len(s)
    x = min(max(phase, 0.0), 1.0) * (n - 1)
    i = min(int(math.floor(x)), n - 2)
    f = x - i
    return float(s[i] * (1 - f) + s[i + 1] * f)


def build_action(source, clip_path, name, base_action=None, base_frame=1, fps=24, ground_objs=(),
                 ground_z=None, log=print, prop_objs=()):
    """Create action ``name`` on the Source armature from a clip JSON (see module docstring).
    ``base_action``/``base_frame``: pose whose arm, neck and head transforms are the starting
    point (props were placed there). ``ground_objs``: meshes whose lowest evaluated vertex is
    kept at ``ground_z`` (default: their lowest point at the base pose)."""
    import bpy
    from mathutils import Matrix, Vector
    with open(clip_path) as fh:
        clip = json.load(fh)
    cv = clip["curves"]
    rt = clip.get("retarget", {})
    near = rt.get("near", "R")
    shield = rt.get("shield_arm", "L")
    sword = rt.get("sword_arm", "R")
    arm_mode = rt.get("arm_mode", "relative")          # sword arm: relative | absolute
    shield_mode = rt.get("shield_mode", "relative")    # relative | offset | absolute
    torso_mode = rt.get("torso_mode", "oscillation")
    head_counter = rt.get("head_counter", 0.0)
    foot_lock = rt.get("foot_lock", False)
    foot_lock_until = rt.get("foot_lock_until", 1.0)
    loop = clip.get("loop", True)
    hold_s = rt.get("hold_s", 0.0) if not loop else 0.0
    arm_gain = {"L": 1.0, "R": 1.0}
    arm_gain[shield] = rt.get("shield_arm_gain", 0.3)
    elbow_gain = {"L": rt.get("elbow_gain", 0.5), "R": rt.get("elbow_gain", 0.5)}
    elbow_gain[shield] = 0.0
    pelvis_yaw = rt.get("pelvis_yaw_deg", 0.0)
    chest_yaw = rt.get("chest_yaw_deg", 0.0)
    bob_gain = rt.get("bob_gain", 1.0)
    for k in (f"upperarm_{shield}", f"elbow_{shield}", "wrist_R", "wrist_L", "arm_yaw_R", "arm_yaw_L",
              "root_fwd", "chest_yaw", "pelvis_yaw"):
        cv.setdefault(k, None)
    F = max(4, int(round(clip["cycle_s"] * fps)))
    H = int(round(hold_s * fps))
    log(f"== clip {name} from {os.path.basename(clip_path)}: cycle {clip['cycle_s']:.3f} s -> {F} frames @ {fps}"
        f"{'' if loop else f' + {H} hold frames (non-looping)'}; arm {arm_mode}, shield {shield_mode}, "
        f"torso {torso_mode}, foot lock {foot_lock}")

    scene = bpy.context.scene
    mw = source.matrix_world
    bones = [pb.name for pb in source.pose.bones]
    arm_bones = [b for b in bones if any(b.startswith(f"Biped_{p}") for p in
                                        ("shoulder", "arm", "forearm", "hand", "finger", "neck", "head"))]

    def dep_update():
        bpy.context.view_layer.update()

    # ---- base pose (arms etc.) from the base action
    base = {}
    if base_action is not None:
        source.animation_data.action = base_action
        scene.frame_set(base_frame)
        dep_update()
        for b in arm_bones:
            pb = source.pose.bones[b]
            base[b] = (pb.location.copy(), pb.rotation_quaternion.copy(), pb.scale.copy())
        if ground_z is None and ground_objs:
            ground_z = _lowest_z(ground_objs)
    source.animation_data.action = None       # no fcurves fighting the hand-set pose
    if ground_z is None:
        ground_z = 0.0

    def reset():
        for pb in source.pose.bones:
            pb.location = (0, 0, 0)
            pb.rotation_quaternion = (1, 0, 0, 0)
            pb.scale = (1, 1, 1)
        for b, (loc, rot, sc) in base.items():
            pb = source.pose.bones[b]
            pb.location, pb.rotation_quaternion, pb.scale = loc, rot, sc
        dep_update()

    def rotate_world(pb, axis, deg):
        """Rotate a pose bone (and children) about a world axis through its head."""
        if abs(deg) < 1e-6:
            return
        head = mw @ pb.head
        R = Matrix.Translation(head) @ Matrix.Rotation(math.radians(deg), 4, axis) @ Matrix.Translation(-head)
        pb.matrix = mw.inverted() @ R @ mw @ pb.matrix
        dep_update()

    def cvi(key, ph, default=0.0):
        if cv.get(key) is None:
            return default
        return _interp_loop(cv[key], ph) if loop else _interp_hold(cv[key], ph)

    def direction(pb):
        d = (mw @ pb.tail) - (mw @ pb.head)
        return Vector((0.0, d.y, d.z))      # sagittal projection; forward is -Y, up +Z

    def set_abs(pb, kind, deg):
        """Set a bone's absolute sagittal angle. kind: 'down' (thigh/shank/arm: 0 = hanging,
        + forward), 'fwd' (foot: 0 = horizontal forward, + toes up), 'up' (spine: + forward)."""
        r = math.radians(deg)
        if kind == "down":
            tgt = Vector((0, -math.sin(r), -math.cos(r)))
        elif kind == "fwd":
            tgt = Vector((0, -math.cos(r), math.sin(r)))
        else:
            tgt = Vector((0, -math.sin(r), math.cos(r)))
        cur = direction(pb)
        if cur.length < 1e-9:
            return
        ang = math.atan2(cur.cross(tgt).x, cur.dot(tgt))     # signed about +X
        rotate_world(pb, "X", math.degrees(ang))

    def abs_angle(pb, kind):
        d = direction(pb)
        if kind == "down":
            return math.degrees(math.atan2(-d.y, -d.z))
        if kind == "fwd":
            return math.degrees(math.atan2(d.z, -d.y))
        return math.degrees(math.atan2(-d.y, d.z))

    # rest-pose reference angles (the model's own flat foot / spine lean)
    reset()
    rest_foot = {s: abs_angle(source.pose.bones[f"Biped_foot_{s}"], "fwd") for s in SIDES}
    rest_thigh = {s: abs_angle(source.pose.bones[f"Biped_thigh_{s}"], "down") for s in SIDES}
    log(f"   rest: thigh {rest_thigh}, foot pitch {rest_foot}, ground z {ground_z:.3f}")
    ua_mean = {s: float(np.mean(cv[f"upperarm_{s}"])) if cv.get(f"upperarm_{s}") else 0.0 for s in SIDES}
    el_mean = {s: float(np.mean(cv[f"elbow_{s}"])) if cv.get(f"elbow_{s}") else 0.0 for s in SIDES}
    torso_ref = float(np.mean(cv["torso"])) if torso_mode == "oscillation" else float(rt.get("torso_ref", 0.0))
    yaw_curves = cv.get("chest_yaw") is not None

    def pose(frame):
        ph = frame / F
        reset()
        hip = source.pose.bones["Biped_hip"]
        if yaw_curves:
            # synthesized twist curves (one-shot clips): + brings the right shoulder forward
            rotate_world(hip, "Z", cvi("pelvis_yaw", ph))
            rotate_world(source.pose.bones["Biped_spine1"], "Z", cvi("chest_yaw", ph))
        else:
            # pelvis yaw: the leg that is forward brings its hip forward. Sign: right thigh forward
            # at phase 0 (near = R) -> rotate so the -X (right) side moves to -Y (forward):
            # about +Z, (-1,0,0) -> (-cos, -sin, 0): y goes negative for +yaw. Good.
            yaw_phase = math.cos(2 * math.pi * ph) * (1 if near == "R" else -1)
            if pelvis_yaw:
                rotate_world(hip, "Z", pelvis_yaw * yaw_phase)
            if chest_yaw:
                rotate_world(source.pose.bones["Biped_spine1"], "Z", chest_yaw * yaw_phase)
        tor = cvi("torso", ph) - torso_ref
        rotate_world(source.pose.bones["Biped_spine"], "X", tor)    # +X rotation tips an up vector forward (-Y)
        if head_counter:
            rotate_world(source.pose.bones["Biped_head"], "X", -tor * head_counter)
        for s in SIDES:
            th = cvi(f"thigh_{s}", ph)
            kn = max(0.0, cvi(f"knee_{s}", ph))
            ft = cvi(f"foot_{s}", ph)
            set_abs(source.pose.bones[f"Biped_thigh_{s}"], "down", th)
            set_abs(source.pose.bones[f"Biped_leg_{s}"], "down", th - kn)
            set_abs(source.pose.bones[f"Biped_foot_{s}"], "fwd", rest_foot[s] + ft)
            mode = arm_mode if s == sword else shield_mode
            if mode == "relative":
                ua = (cvi(f"upperarm_{s}", ph) - ua_mean[s]) * arm_gain[s]
                el = (cvi(f"elbow_{s}", ph) - el_mean[s]) * elbow_gain[s]
                rotate_world(source.pose.bones[f"Biped_arm_{s}"], "X", -ua)   # -X swings a hanging bone forward
                rotate_world(source.pose.bones[f"Biped_forearm_{s}"], "X", -el)
            elif mode == "offset":
                rotate_world(source.pose.bones[f"Biped_arm_{s}"], "X", -cvi(f"upperarm_{s}", ph))
                rotate_world(source.pose.bones[f"Biped_forearm_{s}"], "X", -cvi(f"elbow_{s}", ph))
            else:   # absolute planar angles, as the legs
                ua = cvi(f"upperarm_{s}", ph)
                set_abs(source.pose.bones[f"Biped_arm_{s}"], "down", ua)
                set_abs(source.pose.bones[f"Biped_forearm_{s}"], "down", ua + cvi(f"elbow_{s}", ph))
            # sword pitch relative to the forearm (+ continues the forearm's angle: forward->up->back)
            rotate_world(source.pose.bones[f"Biped_hand_{s}"], "X", -cvi(f"wrist_{s}", ph))
            # whole arm swung about the vertical through the shoulder (+ = the arm's far end moves
            # to the figure's right when it points back, to its left when it points forward)
            rotate_world(source.pose.bones[f"Biped_arm_{s}"], "Z", cvi(f"arm_yaw_{s}", ph))

    def ankles():
        return {s: (mw @ source.pose.bones[f"Biped_foot_{s}"].head) for s in SIDES}

    # ---- pass 1: pose every frame, measure how far the feet are from the ground (and, with
    # the foot lock, how far the planted feet drift horizontally)
    dz, lock = [], []
    clamp_objs = list(ground_objs) + (list(prop_objs) if rt.get("clamp_props") else [])
    ank0 = None
    for f in range(F):
        pose(f)
        low = _lowest_z(clamp_objs) if clamp_objs else ground_z
        dz.append(ground_z - low)
        if foot_lock:
            an = ankles()
            zmin = min(v.z for v in an.values())
            w = {s: math.exp(-(an[s].z - zmin) / 0.15) for s in SIDES}
            y = sum(w[s] * an[s].y for s in SIDES) / sum(w.values())
            if ank0 is None:
                ank0 = y
            lock.append(ank0 - y if f / F <= foot_lock_until + 1e-9 else lock[-1])
        else:
            lock.append(0.0)
    dz = np.array(dz)
    dy = np.array(lock) - np.array([cvi("root_fwd", f / F) for f in range(F)])    # forward is -Y
    bob = dz - dz.mean()
    dz = dz.mean() + bob * bob_gain
    log(f"   ground clamp: root shift {dz.min():+.3f}..{dz.max():+.3f} (bob amplitude "
        f"{(bob.max()-bob.min())/2:.3f} units peak, gain {bob_gain}); horizontal root shift "
        f"{dy.min():+.3f}..{dy.max():+.3f}")

    # ---- pass 2: pose again with the root shift and record every bone's basis
    rec = {b: [] for b in bones}
    tip_log = []
    for f in range(F):
        pose(f)
        hip = source.pose.bones["Biped_hip"]
        hip.matrix = mw.inverted() @ Matrix.Translation((0, float(dy[f]), float(dz[f]))) @ mw @ hip.matrix
        dep_update()
        for b in bones:
            pb = source.pose.bones[b]
            rec[b].append((tuple(pb.location), tuple(pb.rotation_quaternion)))
        if f in (0, F // 4, F // 2, 3 * F // 4, F - 1):
            th = {s: round(abs_angle(source.pose.bones[f"Biped_thigh_{s}"], "down"), 1) for s in SIDES}
            kn = {s: round(abs_angle(source.pose.bones[f"Biped_thigh_{s}"], "down")
                           - abs_angle(source.pose.bones[f"Biped_leg_{s}"], "down"), 1) for s in SIDES}
            an = ankles()
            log(f"   frame {f} (phase {f/F:.2f}): thigh {th} knee {kn} root dz {dz[f]:+.3f} dy {dy[f]:+.3f} "
                f"ankle y R {an['R'].y:+.2f} L {an['L'].y:+.2f}")
        if prop_objs:
            tip_log.append((f, _prop_extent(prop_objs)))
    if tip_log:
        lo = min(t[1][0] for t in tip_log)
        hi = max(t[1][1] for t in tip_log)
        log(f"   props: lowest point {lo:+.3f} (ground {ground_z:+.3f}), highest {hi:.3f} over the clip")
        for f, (zlo, zhi, ymin) in tip_log:
            if zlo < ground_z - 0.05:
                log(f"      frame {f}: a prop dips {ground_z - zlo:.2f} below the ground")

    # ---- write the action (linear keys on every frame; looping: key F repeats key 0 so the
    # loop closes; non-looping: H hold frames of the final pose so the bake's last sample is it)
    act = bpy.data.actions.new(name)
    if hasattr(act, "slots"):
        slot = act.slots.new(id_type="OBJECT", name="Biped")
        layer = act.layers.new("Layer")
        strip = layer.strips.new(type="KEYFRAME")
        curves = strip.channelbag(slot, ensure=True).fcurves
    else:
        curves = act.fcurves
    N = F + 1 if loop else F + H
    frames_x = np.arange(N, dtype=np.float64)
    nk = 0
    for b in bones:
        vals = rec[b] + ([rec[b][0]] if loop else [rec[b][-1]] * H)
        for path, width, idx in (("location", 3, 0), ("rotation_quaternion", 4, 1)):
            for c in range(width):
                fc = curves.new(f'pose.bones["{b}"].{path}', index=c)
                fc.keyframe_points.add(N)
                co = np.empty(2 * N)
                co[0::2] = frames_x
                co[1::2] = [v[idx][c] for v in vals]
                fc.keyframe_points.foreach_set("co", co)
                for kp in fc.keyframe_points:
                    kp.interpolation = "LINEAR"
                fc.update()
                nk += 1
    act.use_fake_user = True
    act["loop"] = bool(loop)
    act["cycle_frames"] = F
    if clip.get("impact_phase") is not None:
        act["impact_phase"] = float(clip["impact_phase"])
    source.animation_data.action = act
    if hasattr(source.animation_data, "action_slot"):
        slots = list(getattr(act, "slots", []))
        if slots:
            source.animation_data.action_slot = slots[0]
    log(f"== action {name}: frames 0..{N-1}, {nk} curves, {len(bones)} bones keyed, loop={loop}")
    return act


def _prop_extent(objs):
    """(lowest z, highest z, min y) over the evaluated prop meshes (sword tip checks)."""
    import bpy
    dg = bpy.context.evaluated_depsgraph_get()
    zlo, zhi, ymin = 1e9, -1e9, 1e9
    for o in objs:
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        n = len(me.vertices)
        arr = np.empty(n * 3)
        me.vertices.foreach_get("co", arr)
        arr = arr.reshape(n, 3)
        m = np.array(ev.matrix_world)
        w = arr @ m[:3, :3].T + m[:3, 3]
        ev.to_mesh_clear()
        zlo, zhi, ymin = min(zlo, w[:, 2].min()), max(zhi, w[:, 2].max()), min(ymin, w[:, 1].min())
    return float(zlo), float(zhi), float(ymin)


def _lowest_z(objs):
    import bpy
    dg = bpy.context.evaluated_depsgraph_get()
    low = None
    for o in objs:
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        n = len(me.vertices)
        arr = np.empty(n * 3)
        me.vertices.foreach_get("co", arr)
        arr = arr.reshape(n, 3)
        m = np.array(ev.matrix_world)
        z = (arr @ m[:3, :3].T + m[:3, 3])[:, 2].min()
        ev.to_mesh_clear()
        low = z if low is None else min(low, z)
    return float(low)


# ----------------------------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract", help="video -> clip JSON (+ diagnostics)")
    e.add_argument("--video", required=True)
    e.add_argument("--model", required=True, help="pose_landmarker_heavy.task")
    e.add_argument("--start", type=float, default=0.0, help="seconds; skip Veo's morph-in")
    e.add_argument("--end", type=float, default=1e9)
    e.add_argument("--facing", choices=("right", "left"), default="right",
                   help="which way the figure faces on screen; the near side follows from it")
    e.add_argument("--far", choices=("mirror", "track"), default="mirror",
                   help="far-side limbs: near side shifted half a cycle (default) or as tracked")
    e.add_argument("--fit", choices=("all", "cycle"), default="all",
                   help="Fourier fit over the whole trim (averages cycles) or the one chosen cycle")
    e.add_argument("--max-drift", type=float, default=0.10,
                   help="if heel-strike intervals vary more than this fraction, fit one cycle only")
    e.add_argument("--harmonics", type=int, default=4)
    e.add_argument("--samples", type=int, default=48)
    e.add_argument("--min-conf", type=float, default=0.3)
    e.add_argument("--gain", default="hip=1.2,knee=1.2,arm=1.2,foot=1.0,bob=1.0,torso=1.0")
    e.add_argument("--shield-arm", choices=("L", "R", "none"), default="L")
    e.add_argument("--shield-arm-gain", type=float, default=0.3)
    e.add_argument("--elbow-gain", type=float, default=0.5, help="sword-arm elbow swing gain")
    e.add_argument("--pelvis-yaw", type=float, default=4.0, help="degrees, synthetic (not measurable from the side)")
    e.add_argument("--chest-yaw", type=float, default=-6.0, help="degrees relative to the pelvis")
    e.add_argument("--out", required=True)
    e.add_argument("--previews")

    o = sub.add_parser("oneshot", help="video segment -> one-shot clip JSON (attack, death)")
    o.add_argument("--video", required=True)
    o.add_argument("--model", required=True)
    o.add_argument("--start", type=float, required=True, help="trim in (s)")
    o.add_argument("--end", type=float, required=True, help="trim out (s)")
    o.add_argument("--facing", choices=("right", "left"), default="right")
    o.add_argument("--min-conf", type=float, default=0.3)
    o.add_argument("--smooth-s", type=float, default=0.17, help="Savitzky-Golay window (s)")
    o.add_argument("--keys", required=True, help="time warp: src_seconds=phase,... (phase 0 first)")
    o.add_argument("--synth", action="append", help="phase:curve=value,...  ('*=start' copies the phase-0 pose)")
    o.add_argument("--phase-curve", action="append",
                   help="synthesized curve: name=phase:value,phase:value,... (wrist_R, arm_yaw_R, chest_yaw, "
                        "pelvis_yaw, upperarm_L, elbow_L, root_fwd)")
    o.add_argument("--cycle", type=float, required=True, help="clip length (s)")
    o.add_argument("--hold-s", type=float, default=0.2, help="non-looping: hold of the final pose appended")
    o.add_argument("--loop", action="store_true", help="cycle back to the phase-0 pose (attack)")
    o.add_argument("--impact-phase", type=float, default=None)
    o.add_argument("--samples", type=int, default=40)
    o.add_argument("--gain", default="arm=1.0,crouch=1.0,foot=0.7,torso=1.0",
                   help="about the phase-0 pose: sword arm excursion, leg crouch, foot pitch, torso lean")
    o.add_argument("--torso-ref", default="auto", help="standing torso lean (deg) or 'auto' (video start)")
    o.add_argument("--torso-ref-window", type=float, default=0.5)
    o.add_argument("--arm-mode", choices=("relative", "absolute"), default="absolute")
    o.add_argument("--shield-mode", choices=("relative", "offset", "absolute"), default="offset")
    o.add_argument("--head-counter", type=float, default=0.6, help="fraction of the torso lean undone at the head")
    o.add_argument("--foot-lock", action="store_true")
    o.add_argument("--foot-lock-until", type=float, default=1.0, help="phase after which the lock holds")
    o.add_argument("--clamp-props", action="store_true", help="keep the props above the ground too (death)")
    o.add_argument("--out", required=True)
    o.add_argument("--previews")
    a = ap.parse_args()
    if a.cmd == "extract":
        extract(a)
    elif a.cmd == "oneshot":
        extract_oneshot(a)


if __name__ == "__main__":
    main()
