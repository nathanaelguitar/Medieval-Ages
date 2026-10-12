#!/usr/bin/env python3
"""Batch-2 promo EDLs (ten daily posts) for assemble_v.py. Same scheme as make_edls.py: shots are
measured in beats of the promo's track so every cut lands on the grid; captions ride on shots.

Tracks and grids (measured with beats.py / onsets.py):
  MARCH  Medieval March (intro edit)  112.35 BPM, 0.5340 s   hits 18.10 / 20.24 / 21.30, run 38.41-61, peak 81.45
  NOBLE  March of the Noble           112.35 BPM, 0.53404 s  quiet->full at 43.96, strong 84.45-99 and 150.09-172
  DUSKA  Village at Dusk a            90.9 BPM, 0.6601 s     strong every 2nd beat from 105.567; 28.87 entry
  DUSKB  Village at Dusk b            89.1 BPM, 0.6734 s     gentle entries 17.23 and 38.10

Usage: make_edls_b2.py [names...]   -> edl_b2_<name>.json (all ten by default)
Render: render_b2.py (assemble, loudness-match to -14 LUFS, upload copy, contact sheet)
"""
import json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
GEN, GEN2 = "../../out/promo/fasth3/", "../../out/promo/fasth3_b2/"     # FastH3 takes, batch 1 / batch 2
GAME, GAME2 = "../../out/promo/game/", "../../out/promo/game_b2/"       # gameplay captures, batch 1 / batch 2
SFX = "../../out/sfx/game/"
TXT = "text/b2/"
TITLE = {"bg": "text/title_bg.jpg", "text": TXT + "title_text_b2.png", "soon": TXT + "title_soon_b2.png"}
TRACKS = {
    "MARCH": ("../intro/edit/music_march_decoded.m4a", 60 / 112.35),
    "NOBLE": ("../music/march_of_the_noble.m4a", 60 / 112.35),
    "DUSKA": ("../music/village_at_dusk_a.m4a", 0.6601),
    "DUSKB": ("../music/village_at_dusk_b.m4a", 0.6734),
}
# promos whose loudness pass found the music needed trimming (render_b2.py writes this)
DB_FILE = os.path.join(HERE, "b2_music_db.json")
MUSIC_DB = json.load(open(DB_FILE)) if os.path.exists(DB_FILE) else {}

def dur_of(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", os.path.join(HERE, p)], capture_output=True, text=True)
    return float(r.stdout.strip() or 0)

def gen(name, i, beats, **kw):   return dict(src=GEN + name + ".mp4", **{"in": i}, beats=beats, grade=kw.pop("grade", "golden"), **kw)
def gen2(name, i, beats, **kw):  return dict(src=GEN2 + name + ".mp4", **{"in": i}, beats=beats, grade=kw.pop("grade", "golden"), **kw)
def game(name, i, beats, **kw):  return dict(src=GAME + name + ".mp4", **{"in": i}, beats=beats, grade="game", amb=-90, **kw)
def game2(name, i, beats, **kw): return dict(src=GAME2 + name + ".mp4", **{"in": i}, beats=beats, grade="game", amb=-90, **kw)

def build(name, track, music_start, shots, title_beats, title_xf=0.5, fade_out=2.4):
    path, B = TRACKS[track]
    out, overlays, sfx, t, ends = [], [], [], 0.0, []
    for s in shots:
        s = dict(s); beats = s.pop("beats"); xf = s.get("xf", 0)
        caps = s.pop("cap", []); hits = s.pop("sfx", [])
        s["dur"] = round(beats * B + xf, 4)
        sp = s.get("speed", 1.0); have = dur_of(s["src"])
        assert s["in"] + s["dur"] * sp <= have - 0.05, (name, s["src"], s["in"], s["dur"], have)   # never run off the end of a take
        start = t - xf if out else 0.0
        for png, a, d in caps:
            overlays.append({"png": TXT + png, "at": round(t + a * B, 3), "dur": round(d * B, 3),
                             "fade": 0 if (not overlays and a == 0 and not out) else 0.12, "_shot": len(out)})   # the hook line is up on frame 0
        for f, a, db in hits: sfx.append({"path": SFX + f, "at": round(t + a * B, 3), "db": db})
        out.append(s); t = start + s["dur"]; ends.append(t)
    xfs = [x.get("xf", 0) for x in out[1:]] + [title_xf]
    for o in overlays:     # a caption never runs into the next shot's crossfade or the fade to the end card
        i = o.pop("_shot"); j = i
        while j + 1 < len(ends) and o["at"] + o["dur"] > ends[j] + 0.01: j += 1
        lim = ends[j] - xfs[j]
        if o["at"] + o["dur"] > lim: o["dur"] = round(lim - o["at"], 3)
    for x in sfx: assert x["at"] < ends[-1] - title_xf, ("sfx inside the end-card fade", name, x)
    out.append({"title": dict(TITLE, dur=round(title_beats * B + title_xf, 4)), "xf": title_xf, "xfk": "fadeblack"})
    cfg = {"amb_db": -14, "crf": 18,
           "music": {"path": path, "start": music_start, "db": MUSIC_DB.get(name, 0), "fade_in": 0.05, "fade_out": fade_out, "tail": 0.3},
           "shots": out, "overlays": overlays, "sfx": sfx}
    json.dump(cfg, open(os.path.join(HERE, f"edl_b2_{name}.json"), "w"), indent=1)
    print(f"{name:12s} {t + title_beats * B:5.2f}s  {track} from {music_start}")

SWORDS = [("sword_hit_1.wav", 0.5, -10), ("sword_hit_3.wav", 1.7, -10), ("sword_hit_5.wav", 2.9, -11)]
P = {}
# 01  QUESTION. "Could you hold the gate?"  The gates slam on the red army; real gameplay: walls, towers, the gate held.
P["01_gate"] = lambda: build("01_gate", "MARCH", 38.406, [
    gen2("b_gate", 0.2, 6, z0=1.0, z1=1.05, cap=[("cap_gate_q.png", 0, 6)]),
    gen2("b_gate_hold", 1.0, 3, z0=1.03, z1=1.0),
    gen2("b_wall_archers", 1.0, 3),   # clean to 3.4 s: a red-tabard archer drifts into the second rank after
    game2("gate", 2.0, 5, cap=[("tag_gameplay.png", 0, 5)], sfx=SWORDS),
    game2("wall", 0.4, 5, cap=[("cap_walls.png", 0.1, 4.8), ("tag_speed4.png", 0, 5)], sfx=[("hammer_hit_1.wav", 0.6, -14), ("hammer_hit_3.wav", 2.2, -15)]),
    game2("garrison", 1.9, 8, cap=[("cap_towers.png", 0.1, 7.8)], sfx=[("bow_release_1.wav", 5.0, -12)]),
    game2("gate", 5.0, 4, cap=[("cap_hold.png", 0.1, 3.8)], sfx=[("sword_hit_2.wav", 0.6, -10), ("death_grunt_1.wav", 1.8, -15)]),
], title_beats=8)
# 02  POV. "POV: your villagers just saw the red army"  Quiet dread, the bell, then the full march under the muster.
P["02_pov"] = lambda: build("02_pov", "NOBLE", 36.489, [
    gen2("b_red_horizon", 0.3, 8, z0=1.0, z1=1.06, cap=[("cap_pov.png", 0, 8)]),
    gen2("b_bell", 0.5, 4, cap=[("cap_bell.png", 0.1, 3.8)]),
    gen2("b_gate", 2.2, 4),   # (batch-1 v_muster and v_banner mix red tabards/banners into the lion army: not used)
    game2("banners", 0.6, 5, cap=[("cap_banners.png", 0.1, 4.8), ("tag_gameplay.png", 0, 5)]),
    game2("garrison", 3.6, 6, sfx=[("bow_release_1.wav", 2.5, -12)]),
    game("battle", 2.0, 5, sfx=SWORDS),
    gen2("b_victory", 3.2, 4, z0=1.2, z1=1.26, ay=0.25, cap=[("cap_realm.png", 0.1, 3.8)]),
], title_beats=8)
# (b_victory: red shields in the back rank until 2.9 s and one at the bottom right throughout: cut from 3.2 s, pushed in 1.2x high)
# 03  SATISFYING BUILD. "Building a medieval village in 15 seconds"  One continuous 6x time-lapse.
P["03_village15"] = lambda: build("03_village15", "DUSKA", 105.567, [
    game2("timelapse", 0.0, 18, cap=[("cap_v15.png", 0, 6), ("tag_timelapse.png", 0, 18)],
          sfx=[("hammer_hit_1.wav", 2.0, -16), ("hammer_hit_2.wav", 6.0, -16), ("hammer_hit_3.wav", 10.0, -16)]),
    game2("gate", 3.0, 4, cap=[("cap_defend.png", 0.1, 3.8)], sfx=[("sword_hit_1.wav", 1.0, -12)]),
], title_beats=6, fade_out=2.8)
# 04  EPIC COLD OPEN. Night watch over the enemy's campfires, then the hit at 18.1 s: fire, charge, rain, snow.
P["04_coldopen"] = lambda: build("04_coldopen", "MARCH", 13.828, [
    gen2("b_night_watch_b", 0.4, 8, z0=1.0, z1=1.07, grade="default", cap=[("cap_coming.png", 0, 7.8)]),
    gen2("b_siege_tower", 0.5, 3, grade="default"),
    gen("v_charge_b", 2.7, 2, z0=1.04, z1=1.1, ay=0.45, grade="warm"),
    gen2("b_rain_clash", 1.0, 3, grade="default", sfx=[("sword_hit_2.wav", 0.6, -6)]),
    gen("v_slam_b", 2.0, 3, sfx=[("sword_hit_4.wav", 0.4, -5)]),
    gen2("b_winter_march_b", 2.5, 3, z0=1.7, z1=1.8, ax=0.4, ay=0.0, grade="default"),   # banners only: red-quartered shields sit low in frame
    gen2("b_volley_hill", 0.9, 3),   # loose + rise only: past ~2.6 s the arrows hang in the sky
    game("battle", 2.0, 4, cap=[("tag_real.png", 0, 4)], sfx=SWORDS[:2]),
    gen2("b_victory", 3.2, 4, z0=1.2, z1=1.26, ay=0.25, cap=[("cap_realm.png", 0.1, 3.8)]),
], title_beats=8)
# 05  REVEAL. "This is a mobile game?"  Gameplay only, with the touch controls on screen.
P["05_reveal"] = lambda: build("05_reveal", "NOBLE", 84.453, [
    game("battle", 2.5, 6, z0=1.12, z1=1.22, ay=0.45, cap=[("cap_mobile_q.png", 0, 6), ("tag_real.png", 0, 6)], sfx=SWORDS),
    game2("banners", 1.0, 4),
    game2("garrison", 3.8, 4, sfx=[("bow_release_1.wav", 0.6, -10), ("arrow_hit_3.wav", 1.6, -12)]),   # (batch-1 tower flashes white from 2.0 s)
    game("command", 1.0, 6, cap=[("cap_thumb.png", 0.1, 5.8)]),
    game2("dbltap", 0.6, 8, cap=[("cap_dbl.png", 1.2, 6.6)]),
    game("village", 0.5, 4, cap=[("cap_phone.png", 0.1, 3.8)]),
], title_beats=8)
# 06  DEVLOG. "I'm making a medieval RTS for mobile"  The controls, one feature a shot.
P["06_devlog"] = lambda: build("06_devlog", "DUSKB", 38.104, [
    game("village", 0.4, 4, cap=[("cap_dev.png", 0, 4)]),
    game2("selbox", 0.6, 7, cap=[("cap_selbox.png", 0.1, 6.8)]),
    game2("dbltap", 0.5, 5, cap=[("cap_dbl_dev.png", 0.1, 4.8)]),
    game2("wall", 0.3, 4, cap=[("cap_wall_dev.png", 0.1, 3.8), ("tag_speed4.png", 0, 4)]),
    game2("garrison", 1.9, 7, cap=[("cap_garr.png", 0.1, 6.8)]),
    game2("sheep", 3.0, 3, cap=[("cap_follow.png", 0.1, 2.8)], sfx=[("sheep_bleat_1.wav", 0.8, -16)]),
], title_beats=6, fade_out=2.8)
# 07  HISTORY. "How medieval mills worked"  -> the game's windmill and the farms that feed it.
P["07_mills"] = lambda: build("07_mills", "DUSKA", 28.867, [
    gen2("b_mill", 0.3, 6, z0=1.0, z1=1.06, cap=[("cap_mill_q.png", 0, 3), ("cap_sails.png", 3.1, 2.8)]),
    gen2("b_millstone", 0.5, 6, z0=1.0, z1=1.08, cap=[("cap_stones.png", 0.1, 5.8)]),
    gen2("b_farm_b", 0.5, 4, cap=[("cap_fields.png", 0.1, 3.8)]),
    game2("millwide", 0.3, 6, cap=[("cap_mill_game.png", 0.1, 5.8), ("tag_gameplay.png", 0, 6)]),
    game("mill", 1.0, 4, z0=1.12, z1=1.18, ay=0.35),
], title_beats=6, fade_out=2.8)
# 08  HISTORY. "Longbows won medieval battles"  Crecy and Agincourt -> the archers and garrisoned towers in the game.
P["08_longbow"] = lambda: build("08_longbow", "NOBLE", 150.093, [
    gen2("b_volley_hill", 0.4, 4, cap=[("cap_longbow.png", 0, 4)], sfx=[("bow_release_1.wav", 2.0, -8)]),   # draw, loose, rise (0.4-2.5 s)
    gen2("b_wall_archers", 0.5, 4, cap=[("cap_crecy.png", 0.1, 3.8)]),
    # (batch-1 v_draw has red-tabard archers in the lion line, v_loose_side red banners over our palisade: not used)
    gen2("b_volley_hill_b", 1.0, 5, cap=[("cap_volley.png", 0.1, 4.8)], sfx=[("bow_release_1.wav", 0.4, -9)]),
    game("tower", 0.3, 3, z0=1.0, z1=1.06, ay=0.3, cap=[("cap_my_archers.png", 0.1, 2.8), ("tag_gameplay.png", 0, 3)],   # tower clip is clean only to 2.0 s
         sfx=[("bow_release_1.wav", 0.3, -10), ("arrow_hit_3.wav", 1.2, -12)]),
    game2("garrison", 1.9, 9, cap=[("cap_garr.png", 0.1, 8.8)], sfx=[("bow_release_1.wav", 5.0, -12)]),
    game("battle", 3.0, 4, sfx=SWORDS[:2]),
], title_beats=8)
# 09  HISTORY. "What did a medieval village eat?"  Bread, mutton, and boar (mostly for lords) -> hunting and herding in the game.
P["09_food"] = lambda: build("09_food", "DUSKB", 17.229, [
    gen2("b_market", 0.3, 5, z0=1.0, z1=1.05, cap=[("cap_eat_q.png", 0, 5)]),
    gen2("b_farm_b", 2.0, 3, cap=[("cap_bread.png", 0.1, 2.8)]),
    gen2("b_sheep", 0.5, 3, cap=[("cap_mutton.png", 0.1, 2.8)]),
    gen2("b_boar", 1.0, 3, cap=[("cap_lords.png", 0.1, 2.8)]),
    game2("boar", 0.3, 5, cap=[("cap_hunt_game.png", 0.1, 4.8), ("tag_gameplay.png", 0, 5)], sfx=[("boar_squeal_1.wav", 1.2, -14)]),
    game2("sheep", 3.0, 5, cap=[("cap_herd.png", 0.1, 4.8)], sfx=[("sheep_bleat_2.wav", 1.0, -15)]),
], title_beats=6, fade_out=2.8)
# 10  KING. "Every king needs a plan"  War table -> muster -> the army under its lion standards -> march -> conquer.
P["10_king"] = lambda: build("10_king", "MARCH", 77.173, [
    gen2("b_king_table", 0.3, 8, z0=1.0, z1=1.06, grade="default", cap=[("cap_king.png", 0, 8)]),
    game2("banners", 0.6, 6, cap=[("cap_banners.png", 0.1, 5.8), ("tag_gameplay.png", 0, 6)]),
    game2("dbltap", 0.6, 6, cap=[("cap_dbl.png", 1.2, 4.6)]),
    game("march", 1.0, 6, cap=[("cap_march.png", 0.1, 5.8)]),
    game("battle", 2.0, 5, cap=[("cap_conquer.png", 0.1, 4.8)], sfx=SWORDS),
    gen2("b_victory", 3.2, 4, z0=1.2, z1=1.26, ay=0.25),
], title_beats=8)

if __name__ == "__main__":
    for n in (sys.argv[1:] or list(P)):
        P[n]()
