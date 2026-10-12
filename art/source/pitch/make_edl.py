#!/usr/bin/env python3
"""Edit decision lists for the Poki trailer (~85 s) and its 30 s cut. Writes edl_trailer.json and
edl_30s.json next to the clips (run inside ~/ma_pitch/edit on the Spark).

Music: "March of the Noble" from 15.0 s, so the track's first full-orchestra hit (18.02 s) lands on
the cut from the title card into gameplay at 3.02 s. Shot lengths are whole beats (112.35 bpm,
0.5341 s), so every later cut also falls on the beat.
Each shot: (clip, in, beats, {cap: caption png, cap_at, sfx: [(file, at, dB)], speed, xf}).
Usage: make_edl.py [music_db_trailer] [music_db_30]
"""
import json, sys

B = 0.5341
CARD = 3.02                       # title card, cut on the hit
MUSIC_START = 15.0

def build(name, shots, end_card, music_db, fade_out):
    out, overlays, sfx, t = [], [], [], 0.0
    out.append({"card": {"bg": "text/title_bg.png", "text": "text/title_text.png", "dur": CARD, "text_at": 0.35, "fade_in": 0.8, "push": 0.035}})
    t = CARD
    for clip, tin, beats, o in shots:
        d = round(beats * B, 4)
        xf = o.get("xf", 0)
        start = t - xf
        if clip.startswith("phone_"):
            sh = {"phone": {"src": f"../clips/{clip}.mp4", "in": tin, "dur": d, "bezel": "text/phone_bezel.png",
                            "label": o.get("label"), "label_at": o.get("label_at", 0.4)}}
            if not sh["phone"]["label"]: del sh["phone"]["label"]
        else:
            sh = {"src": f"../clips/{clip}.mp4", "in": tin, "dur": d}
            if o.get("speed"): sh["speed"] = o["speed"]
        if xf: sh["xf"] = xf
        out.append(sh)
        if o.get("cap"):
            ca = o.get("cap_at", 0.3); cd = o.get("cap_dur", min(d - ca - 0.2, 3.2))
            overlays.append({"png": f"text/cap_{o['cap']}.png", "at": round(start + ca, 3), "dur": round(cd, 3), "fade": 0.3})
        for f, a, db in o.get("sfx", []):
            if a < d: sfx.append({"path": f"sfx/{f}", "at": round(start + a, 3), "db": db})
        t = start + d
    ec, exf = end_card
    out.append({"card": {"bg": "text/title_bg.png", "text": "text/end_text.png", "dur": ec, "text_at": 0.5, "fade_in": 0.8, "push": 0.03}, "xf": exf})
    total = t - exf + ec
    for x in sfx: assert x["at"] < total - fade_out - 0.5, ("sfx inside the closing fade", x)
    edl = {"music": {"path": "march_of_the_noble.m4a", "start": MUSIC_START, "db": music_db, "fade_in": 0.05,
                     "fade_out": fade_out, "tail": 0.25},
           "shots": out, "overlays": overlays, "sfx": sfx}
    json.dump(edl, open(f"edl_{name}.json", "w"), indent=1)
    print(name, f"{total:.2f}s", len(out), "shots")

SW = [("sword_hit_1.wav", 0.9, -17), ("sword_hit_3.wav", 1.6, -18), ("sword_hit_2.wav", 2.5, -17), ("death_grunt_1.wav", 3.1, -22),
      ("sword_hit_4.wav", 3.9, -18), ("sword_hit_1.wav", 4.9, -19)]

TRAILER = [
    ("village",     0.4, 12, {}),
    ("gather",      0.4,  8, {"cap": "gather", "sfx": [("pick_hit_1.wav", 0.7, -21), ("pick_hit_2.wav", 1.9, -22), ("pick_hit_1.wav", 3.2, -22)]}),
    ("wood",        0.6,  6, {"sfx": [("axe_chop_1.wav", 0.5, -21), ("axe_chop_2.wav", 1.6, -22)]}),
    ("timelapse",   0.3, 12, {"cap": "build", "speed": 1.5, "sfx": [("hammer_hit_1.wav", 0.8, -22), ("hammer_hit_2.wav", 2.6, -22), ("hammer_hit_3.wav", 4.6, -23)]}),
    ("mill",        0.3,  8, {}),
    ("wall",        0.4, 12, {"cap": "defend", "cap_at": 3.0, "sfx": [("hammer_hit_1.wav", 3.2, -21), ("hammer_hit_3.wav", 4.6, -22)]}),
    ("garrison",    2.4, 10, {"sfx": [("bow_release_1.wav", 3.2, -17), ("arrow_hit_1.wav", 3.9, -21)]}),
    ("train",       0.4, 10, {}),
    ("banners",     0.5, 10, {"cap": "army"}),
    ("battle",      0.6, 12, {"cap": "conquer", "sfx": SW}),
    ("boar",        0.4,  9, {"cap": "hunt", "sfx": [("boar_squeal_1.wav", 1.2, -19), ("boar_death_1.wav", 3.6, -20)]}),
    ("sheep",       0.5,  7, {"sfx": [("sheep_bleat_1.wav", 0.8, -22), ("sheep_bleat_2.wav", 2.6, -23)]}),
    ("phone_build", 0.4, 13, {"label": "text/phone_label.png", "xf": 0.4}),
    ("phone_army",  0.6,  8, {"label": "text/phone_label.png", "label_at": 0.0}),
    ("victory",     0.9, 15, {"xf": 0.4, "sfx": [("building_collapse_1.wav", 3.65, -13)]}),
]

SHORT = [
    ("village",     0.4,  6, {}),
    ("gather",      0.8,  4, {"cap": "gather", "cap_at": 0.2}),
    ("timelapse",   1.5,  5, {"cap": "build", "cap_at": 0.2, "speed": 1.6}),
    ("wall",        2.6,  5, {"cap": "defend", "cap_at": 0.2}),
    ("banners",     0.5,  5, {"cap": "army", "cap_at": 0.2}),
    ("battle",      1.2,  6, {"cap": "conquer", "cap_at": 0.2, "sfx": SW[:3]}),
    ("phone_build", 3.6,  7, {"label": "text/phone_label.png", "label_at": 0.0}),
    ("victory",     3.4,  8, {"sfx": [("building_collapse_1.wav", 1.15, -13)]}),
]

if __name__ == "__main__":
    dbt = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0
    db3 = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
    build("trailer", TRAILER, (4.0, 0.8), dbt, 3.0)
    build("30s", SHORT, (3.0, 0.6), db3, 2.2)
