#!/usr/bin/env python3
"""Write the promo EDLs (edl_*.json) for assemble_v.py, with every cut on the beat of
"March of the Noble" (112.35 BPM, 0.534 s a beat; beat phases measured with onsets.py).

Each cut is a list of shots measured in beats. A shot that fades in (xf) is lengthened by xf so the
following cuts stay on the grid. Captions are tied to shots, so retiming a shot moves its caption.

Usage: make_edls.py            -> writes edl_hook.json, edl_cinematic.json, edl_howitplays.json
Render: assemble_v.py edl_hook.json ../../out/promo/medieval_ages_hook_9x16.mp4
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
B = 60 / 112.35
GEN = "../../out/promo/fasth3/"      # FastH3 portrait takes (untracked, large)
GAME = "../../out/promo/game/"       # gameplay captures (untracked, large)
SFX = "../../out/sfx/game/"
MUSIC = "../music/march_of_the_noble.m4a"
TXT = "text/"
TITLE = {"bg": TXT + "title_bg.jpg", "text": TXT + "title_text.png", "soon": TXT + "title_soon.png"}

def gen(name, i, beats, **kw):  return dict(src=GEN + name + ".mp4", **{"in": i}, beats=beats, grade=kw.pop("grade", "golden"), **kw)
def game(name, i, beats, **kw): return dict(src=GAME + name + ".mp4", **{"in": i}, beats=beats, grade="game", amb=-90, **kw)

def build(name, music_start, shots, title_beats, title_xf=0.5, fade_out=2.2):
    out, overlays, sfx, t, ends = [], [], [], 0.0, []
    for s in shots:
        s = dict(s); beats = s.pop("beats"); xf = s.get("xf", 0)
        caps = s.pop("cap", []); hits = s.pop("sfx", [])
        s["dur"] = round(beats * B + xf, 4)
        start = t - xf if out else 0.0
        for png, a, d in caps: overlays.append({"png": TXT + png, "at": round(t + a * B, 3), "dur": round(d * B, 3), "fade": 0.12, "_shot": len(out)})
        for f, a, db in hits: sfx.append({"path": SFX + f, "at": round(t + a * B, 3), "db": db})
        out.append(s); t = start + s["dur"]; ends.append(t)
    # a caption never runs into the next shot's crossfade (or the fade to the end card)
    xfs = [x.get("xf", 0) for x in out[1:]] + [title_xf]
    for o in overlays:
        i = o.pop("_shot"); j = i
        while j + 1 < len(ends) and o["at"] + o["dur"] > ends[j] + 0.01: j += 1   # caption spans later shots
        lim = ends[j] - xfs[j]
        if o["at"] + o["dur"] > lim: o["dur"] = round(lim - o["at"], 3)
    title = dict(TITLE, dur=round(title_beats * B + title_xf, 4))
    out.append({"title": title, "xf": title_xf, "xfk": "fadeblack"})
    cfg = {"amb_db": -11, "crf": 18,
           "music": {"path": MUSIC, "start": music_start, "db": 0, "fade_in": 0.05, "fade_out": fade_out},
           "shots": out, "overlays": overlays, "sfx": sfx}
    json.dump(cfg, open(os.path.join(HERE, f"edl_{name}.json"), "w"), indent=1)
    print(name, f"{t + title_beats * B:.2f}s")

# 1. HOOK, ~18.7 s. Music from 61.045 (full march). Cinematic charge + shield slam in the first 2.7 s,
#    then real gameplay on one-word beats, then the end card.
build("hook", 61.045, [
    gen("v_charge_b", 2.7, 2, z0=1.04, z1=1.1, ay=0.45, grade="warm"),
    gen("v_slam_b", 2.0, 3, z0=1.04, z1=1.0, sfx=[("sword_hit_2.wav", 0.35, -3), ("sword_hit_4.wav", 1.2, -8)]),
    game("village", 0.6, 4, cap=[("tag_gameplay.png", 0, 4), ("cap_w_build.png", 0.15, 3.85)]),
    game("mill", 1.0, 3, z0=1.12, z1=1.18, ay=0.35),
    game("gather", 1.0, 3, z0=1.22, z1=1.3, ax=0.45, ay=0.15, cap=[("cap_w_gather.png", 0.1, 2.9)], sfx=[("axe_chop_1.wav", 0.5, -10), ("pick_hit_2.wav", 1.5, -12), ("axe_chop_3.wav", 2.4, -10)]),
    game("march", 1.0, 4, cap=[("cap_w_march.png", 0.1, 3.9)]),
    game("battle", 2.0, 6, cap=[("cap_w_conquer.png", 0.1, 4.0)],
         sfx=[("bow_release_1.wav", 0.2, -10), ("sword_hit_1.wav", 0.9, -9), ("arrow_hit_2.wav", 1.6, -12), ("sword_hit_3.wav", 2.2, -9),
              ("sword_swing_2.wav", 3.0, -11), ("sword_hit_5.wav", 3.6, -9), ("death_grunt_1.wav", 4.4, -14), ("sword_hit_2.wav", 5.1, -10)]),
    game("tower", 0.5, 3, z0=1.0, z1=1.06, ay=0.3, sfx=[("bow_release_1.wav", 0.3, -9), ("arrow_hit_3.wav", 1.1, -11), ("arrow_flesh_1.wav", 2.0, -12)]),
], title_beats=7)

# 2. CINEMATIC, ~29.5 s. Music from 30.081: the quiet opening under the village, the build (40.7-44)
#    under the lookout, full march from 43.96 under muster, volley, charge and the slam on the 55.7 hit.
build("cinematic", 30.081, [
    gen("v_village", 0.4, 7, z0=1.0, z1=1.05),
    gen("v_woodcutter", 0.3, 5, xf=0.4, sfx=[("axe_chop_2.wav", 2.0, -8)]),
    game("village", 0.5, 5, xf=0.4, cap=[("tag_gameplay.png", 0, 5)]),
    gen("v_lookout", 2.2, 5, xf=0.3, z0=1.0, z1=1.14, ay=0.1),
    gen("v_muster", 0.5, 4),
    game("march", 1.0, 4, cap=[("tag_gameplay.png", 0, 4)]),
    gen("v_draw", 1.4, 3, sfx=[("bow_release_1.wav", 2.6, -8)]),
    gen("v_loose_side", 0.9, 3, z0=1.0, z1=1.05),
    game("battle", 2.5, 4, cap=[("tag_gameplay.png", 0, 4)], sfx=[("sword_hit_1.wav", 0.6, -10), ("sword_hit_3.wav", 1.9, -10), ("sword_hit_5.wav", 3.1, -10)]),
    gen("v_charge_b", 1.4, 4, z0=1.0, z1=1.08, ay=0.45, grade="warm"),
    gen("v_slam_b", 2.0, 5, z0=1.0, z1=1.06, sfx=[("sword_hit_2.wav", 0.5, -4), ("sword_hit_4.wav", 2.0, -9)]),
], title_beats=7, title_xf=0.4, fade_out=3.0)

# 3. HOW IT PLAYS, ~15 s. Music from 133.128 (the second surge, 136-146), captions per beat of the loop.
build("howitplays", 133.128, [
    game("village", 0.5, 4, cap=[("cap_village.png", 0.1, 3.8)]),
    game("mill", 0.8, 2, z0=1.12, z1=1.16, ay=0.35),
    game("march", 0.5, 5, cap=[("cap_army.png", 0.1, 4.8)]),
    game("command", 1.0, 6, cap=[("cap_thumb.png", 0.1, 5.8)]),
    game("battle", 2.0, 4, cap=[("cap_realm.png", 0.1, 6.0)], sfx=[("sword_hit_1.wav", 0.5, -10), ("sword_hit_3.wav", 1.6, -10), ("bow_release_1.wav", 2.6, -12)]),
    game("tower", 0.5, 3, z0=1.0, z1=1.06, ay=0.3, sfx=[("arrow_hit_3.wav", 0.8, -11)]),
], title_beats=5, fade_out=2.0)
