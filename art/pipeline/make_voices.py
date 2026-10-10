#!/usr/bin/env python3
"""Generate the unit voice lines (Middle English, c. 1350-1400) with Chatterbox on the Spark.

Also the tutorial narrator (voice ``narrator``, modern English so a new player follows it, one set
per tutorial step s00..s24 so the game can key each clip by step).  Kept apart from the unit bank:

    ssh spark 'cd ~/voice && nice -n 10 venv/bin/python make_voices.py all --voices narrator --out out_narr --good 2 --max-takes 8 --no-f0'
    rsync -a --delete --exclude candidates spark:~/voice/out_narr/ art/out/narr/
    python3 art/pipeline/pack_audio.py narr art/out/narr/game/voice_manifest.json   # -> audio/narr_bank.js

Models
    ResembleAI/chatterbox  (0.5B English TTS; model card: ``license: mit``, "Don't use this model
        to do bad things.")  Every clip carries Resemble's imperceptible Perth watermark; it is
        applied inside ``generate()`` and survives our trim/normalize.
    hexgrad/Kokoro-82M     (Apache-2.0) only makes the ~10 s *seed* clips that Chatterbox uses as
        its voice reference, so no real person is cloned: vill_m <- am_michael, vill_f <- af_bella,
        soldier <- am_onyx.  The soldier's attack lines use a second-stage reference: a few
        shouted lines rendered by Chatterbox from the am_onyx seed, concatenated (Chatterbox copies
        the reference's *delivery*, so a calm reference never shouts however high `exaggeration`).

Runs in the plain venv at ~/voice/venv on the Spark (python3 -m venv --system-site-packages,
torchaudio==2.11.0, chatterbox-tts==0.1.7 --no-deps + its pure-python deps, kokoro).  The exact
invocation, from the repo root on the Mac (`post` is CPU-only but also runs on the Spark: the Mac python has no numpy):

    scp art/pipeline/make_voices.py spark:~/voice/make_voices.py
    ssh spark 'cd ~/voice && nice -n 10 venv/bin/python make_voices.py all --out out'
    # more takes for the lines that still lack 4 clean ones (continues the numbering):
    ssh spark 'cd ~/voice && nice -n 10 venv/bin/python make_voices.py gen post --out out --max-takes 20'
    rsync -a --delete --exclude candidates spark:~/voice/out/ art/out/voice/
    rsync -a spark:~/voice/out/candidates/ art/out/voice/candidates/     # optional, ~300 takes

Stages (``all`` runs them in order; each can be rerun alone):
    seeds  GPU: Kokoro seed clip per voice -> out/refs/<voice>_seed.wav (+ .json: which Kokoro voice)
    gen    GPU: builds the soldier shout reference, then every line x (exaggeration, cfg) x seed ->
           out/candidates/<voice>/<voice>_<set>_<line>_t<take>.wav (24 kHz) + .json sidecar with the
           sampling params and a Whisper (small.en) transcript used to catch garbled takes.
           Takes per line stop early once `--good` takes pass the transcript/duration check.
    post   CPU: trim (onset within ~5 ms, -45 dB re peak), 2 ms / 15 ms fades, -3 dBFS peak, mono
           -> out/masters/*.wav (24 kHz) + metrics; ranked picks -> out/game/<voice>_<set>_<n>.wav
           (16-bit PCM mono 22.05 kHz), out/game/voice_manifest.json, out/preview.html.

Picks are heuristic (transcript match, duration band for the word count, loudness for the attack
set, no babble tail).  Audition in preview.html (it lists every candidate too) and override with
    post --pick soldier/attack/0=t3,t7 --pick vill_f/ack/2=t1
"""
import argparse
import difflib
import html
import json
import os
import re
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

SR_GEN = 24000
SR_GAME = 22050

# tts spelling (what the model is given; "a|b" = alternates, take N uses spelling N % len) |
# display (period spelling) | gloss (modern English, also used to score the Whisper transcript,
# because Whisper modernises what it hears)
VILL_LINES = {
    "select": [
        ("Sire?", "Sire?", "sir?"),
        ("What wold ye?", "What wolde ye?", "what would you?"),
        ("My lord?", "My lord?", "my lord?"),
        ("Yay?|Yea?|Yeh?", "Yea?", "yes?"),
    ],
    "ack": [
        ("Yay, my lord.", "Yea, my lord.", "yes, my lord."),
        ("Anon, sire.|Anon, sire!", "Anon, sire.", "right away, sir."),
        ("As ye will.", "As ye wille.", "as you will."),
        ("Hit shal be doon.", "Hit shal be doon.", "it shall be done."),
        ("At your bidding.", "At youre biddinge.", "at your bidding."),
        ("I go.|I go!", "I go.", "I go."),
        ("Full gladly.", "Ful gladly.", "full gladly."),
        ("By your leeve.", "By youre leve.", "by your leave."),
    ],
    "work": [
        ("To the wode.|To the wood.", "To the wode.", "to the wood."),
        ("I shal hew.", "I shal hewe.", "I shall hew."),
        ("To the fields.", "To the fields.", "to the fields."),
    ],
}
SOLDIER_LINES = {
    "select": [
        ("My lord!", "My lord!", "my lord!"),
        ("Redy!", "Redy!", "ready!"),
        ("Commaund me!|Command me!", "Commaunde me!", "command me!"),
        ("Sire!", "Sire!", "sir!"),
    ],
    "attack": [
        ("Have at thee!", "Have at thee!", "have at thee!"),
        ("Out! Harrow!", "Out! Harrow!", "out! harrow!"),
        ("For the king!", "For the king!", "for the king!"),
        ("Werra!", "Werre!", "war!"),
        ("Slee them!", "Slee them!", "slay them!"),
        ("To arms!", "To armes!", "to arms!"),
        ("Avaunt!", "Avaunt!", "forward!"),
        ("Saint George!", "Saint George!", "saint george!"),
    ],
}

# (exaggeration, cfg_weight, temperature) grid per set kind
GRID_CALM = [(0.5, 0.5, 0.8), (0.7, 0.4, 0.8)]
GRID_ALERT = [(0.6, 0.4, 0.8), (0.8, 0.3, 0.8)]
GRID_SHOUT = [(0.9, 0.3, 0.8), (1.1, 0.25, 0.9), (0.75, 0.35, 0.8)]

VOICES = {
    "vill_m": dict(kokoro="am_michael", lines=VILL_LINES, grids={"select": GRID_CALM, "ack": GRID_CALM, "work": GRID_CALM},
                   seed_text="The harvest is in and the barns are full. We will mend the fence by the north field "
                             "before the rains come, then bring the sheep down from the hill and see to the mill."),
    "vill_f": dict(kokoro="af_bella", lines=VILL_LINES, grids={"select": GRID_CALM, "ack": GRID_CALM, "work": GRID_CALM},
                   seed_text="The bread is baked and the water drawn. Take the pails down to the river, and mind the "
                             "geese by the gate, they will have your fingers if you let them."),
    "soldier": dict(kokoro="am_onyx", lines=SOLDIER_LINES, grids={"select": GRID_ALERT, "attack": GRID_SHOUT},
                    shout_ref=True,
                    seed_text="Hold the line and keep your shields up. The enemy will come at the gate before dawn, "
                              "and when they do we will meet them with steel. Nobody runs. Nobody yields.",
                    shout_texts=["Have at thee, dogs! To arms! For the king! Slay them all!",
                                 "Out! Out! Harrow! Saint George! Forward, and cut them down!"]),
}
# Tutorial narrator: clip sNN is keyed to a step by TUT[].v in ios/WebGame/index.html. s00-s24 follow
# the original step order; later clips are appended and named explicitly by the step that uses them.
NARR_LINES = [
    "Welcome, my lord. This short lesson will show you how to rule your village. Each step moves on by itself once you have done it, or tap Next whenever you are ready for the next one.",
    "Your three villagers are selected. Push the stick to walk them around.",
    "Now tap the red cross to clear the selection.",
    "With nothing selected, the stick moves your view instead. Push it to look around the land.",
    "The small map shows the whole realm. Tap it to jump anywhere, and pinch the screen to zoom.",
    "Back home. Drag a box around your villagers to select them, or tap just one.",
    "Now tap a wild boar to hunt it for food. Berry bushes and sheep give food too.",
    "Wood builds everything. Select a villager, then tap a tree.",
    "Gold pays for soldiers, and stone for walls and towers. Send a villager to either one.",
    "Your stores are shown at the top: wood, food, gold and stone, then your people.",
    "Each house gives room for five more people. Select a villager, tap House in the bar below, then tap open ground to place it.",
    "Tap open ground to set it down. Green means it fits. The red cross cancels.",
    "A wood yard, mill or mining camp near the work saves long walks. Its builders start gathering as soon as it stands.",
    "Farms never run dry. Tap Farm, then tap the ground. You get one farm for each selected villager.",
    "With villagers selected, the hammer sends them back to their last task, or to help finish a building.",
    "More hands, more harvest. Tap your Town Center, then tap Villager to train one.",
    "With the Town Center selected, tap a tree or a berry bush. New villagers will walk straight to work there.",
    "If raiders come, select your villagers and tap the Town Center. They shelter inside, and it shoots harder.",
    "The Idle button finds every villager with nothing to do.",
    "Now for an army. Select a villager and build a Barracks. It costs one hundred and twenty five wood.",
    "When the Barracks is built, tap it to train men at arms and archers.",
    "The sword button gathers your army. Press it again to charge the nearest enemy, or tap an enemy to strike it.",
    "Your soldiers hold their ground. They fight anything that comes near, but will not chase far unless you order it.",
    "The gear pauses the game. There you can set the sound and music, or replay this lesson.",
    # s24 ships a hand-assembled take (art/pipeline/narr_godspeed.py -> art/source/narration/): this
    # half plus a slow, grave "Godspeed... my liege." from the plain seed at exaggeration 0.8. A
    # `post` run overwrites game/narrator_s24_1.wav, so re-copy that file after one.
    "Your goal is to destroy the enemy's Town Center, far to the east. The enemy wakes now. Godspeed, my liege.",
    # s25 and on were added later; the game maps them to their steps by key (TUT[].v), not position
    "To bring them back out, tap the Town Center, then tap Unload. They walk out to its flag.",
    "With the Barracks selected, tap open ground to plant its flag. New soldiers will gather there.",
]
NARR_SETS = {f"s{i:02d}": [(t, t, t)] for i, t in enumerate(NARR_LINES)}
GRID_NARR = [(0.45, 0.5, 0.7), (0.55, 0.45, 0.8)]
VOICES["narrator"] = dict(
    kokoro="bm_george", lang="b", lines=NARR_SETS, grids={k: GRID_NARR for k in NARR_SETS},
    seed_text="Long ago, when the kingdom was young, a small village stood at the edge of the great forest. "
              "Its people were few, but their hearts were brave, and their lord was wise and patient.")

PICKS_PER_LINE = {"select": 1, "ack": 2, "work": 1, "attack": 2}
VOLUME = {"narrator": {k: 1.0 for k in NARR_SETS},
          "vill_m": {"select": 0.8, "ack": 0.8, "work": 0.8},
          "vill_f": {"select": 0.8, "ack": 0.8, "work": 0.8},
          "soldier": {"select": 0.9, "attack": 1.0}}


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def norm_text(s):
    return re.sub(r"[^a-z]", "", s.lower())


def match_score(asr, tts_text, gloss):
    a = norm_text(asr)
    if not a:
        return 0.0
    return max(difflib.SequenceMatcher(None, a, norm_text(t)).ratio() for t in (tts_text, gloss))


def dur_band(text):
    words = len(text.split())
    return 0.18 * words + 0.12, 0.7 * words + 0.5


# ----------------------------------------------------------------------------- seeds (Kokoro)
def stage_seeds(out, voices):
    from kokoro import KPipeline
    refs = out / "refs"
    refs.mkdir(parents=True, exist_ok=True)
    pipes = {}
    for v in voices:
        cfg = VOICES[v]
        lang = cfg.get("lang", "a")          # "b" = British English, needed by the bm_/bf_ voices
        if lang not in pipes:
            pipes[lang] = KPipeline(lang_code=lang, repo_id="hexgrad/Kokoro-82M")
        pipe = pipes[lang]
        wav = np.concatenate([np.asarray(a, dtype=np.float32) for _, _, a in pipe(cfg["seed_text"], voice=cfg["kokoro"])])
        path = refs / f"{v}_seed.wav"
        sf.write(path, wav, SR_GEN)
        (refs / f"{v}_seed.json").write_text(json.dumps(
            {"model": "hexgrad/Kokoro-82M (Apache-2.0)", "voice": cfg["kokoro"], "text": cfg["seed_text"],
             "seconds": len(wav) / SR_GEN}, indent=2))
        log("seed", v, cfg["kokoro"], f"{len(wav) / SR_GEN:.1f}s")


# ----------------------------------------------------------------------------- gen (Chatterbox)
class Asr:
    def __init__(self):
        from transformers import pipeline
        self.pipe = pipeline("automatic-speech-recognition", model="openai/whisper-small.en", device="cuda")
        import librosa
        self.librosa = librosa

    def __call__(self, wav, sr):
        a16 = self.librosa.resample(wav.astype(np.float32), orig_sr=sr, target_sr=16000)
        return self.pipe({"raw": a16, "sampling_rate": 16000})["text"].strip()


def rms_db(w):
    return float(20 * np.log10(np.sqrt(np.mean(w ** 2)) + 1e-9))


def gen_take(model, text, exag, cfg, temp, seed):
    import torch
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    w = model.generate(text, exaggeration=exag, cfg_weight=cfg, temperature=temp)
    return w.squeeze().cpu().numpy().astype(np.float32)


def build_shout_ref(model, asr, out, v, cfg):
    """Stage-2 reference for the soldier: Chatterbox shouting from the Kokoro seed, loudest takes kept."""
    refs = out / "refs"
    path = refs / f"{v}_shout_ref.wav"
    if path.exists():
        log("shout ref exists", path)
        return path
    model.prepare_conditionals(str(refs / f"{v}_seed.wav"), exaggeration=1.0)
    takes = []
    for ti, text in enumerate(cfg["shout_texts"]):
        for seed in range(4):
            w = gen_take(model, text, 1.0, 0.3, 0.8, 1000 + ti * 10 + seed)
            tx = asr(w, SR_GEN) if asr else ""
            m = match_score(tx, text, text) if asr else 1.0
            takes.append(dict(text=text, seed=seed, rms=rms_db(w), match=m, asr=tx, wav=w))
            log(f"  shout-ref take {ti}/{seed} rms {rms_db(w):.1f} match {m:.2f} :: {tx}")
    ok = [t for t in takes if t["match"] >= 0.5] or takes
    ok.sort(key=lambda t: -t["rms"])
    chosen, total = [], 0
    for t in ok:
        if total > 9 * SR_GEN:
            break
        chosen.append(t)
        total += len(t["wav"]) + int(0.15 * SR_GEN)
    gap = np.zeros(int(0.15 * SR_GEN), np.float32)
    ref = np.concatenate(sum([[t["wav"], gap] for t in chosen], []))
    ref = ref / (np.abs(ref).max() + 1e-9) * 0.9
    sf.write(path, ref, SR_GEN)
    (refs / f"{v}_shout_ref.json").write_text(json.dumps(
        {"from": f"{v}_seed.wav (Kokoro {cfg['kokoro']}) rendered by Chatterbox at exaggeration 1.0, cfg 0.3",
         "takes": [{k: t[k] for k in ("text", "seed", "rms", "match", "asr")} for t in chosen]}, indent=2))
    log("shout ref", path, f"{len(ref) / SR_GEN:.1f}s from {len(chosen)} takes")
    return path


def stage_gen(out, voices, sets, good, max_takes, use_asr=True):
    from chatterbox.tts import ChatterboxTTS
    model = ChatterboxTTS.from_pretrained(device="cuda")
    asr = Asr() if use_asr else None
    cand = out / "candidates"
    for v in voices:
        cfg = VOICES[v]
        ref = out / "refs" / f"{v}_seed.wav"
        if cfg.get("shout_ref"):
            ref = build_shout_ref(model, asr, out, v, cfg)
        vdir = cand / v
        vdir.mkdir(parents=True, exist_ok=True)
        # prepare_conditionals is per reference; generate() updates the exaggeration itself
        model.prepare_conditionals(str(ref), exaggeration=0.5)
        for s, lines in cfg["lines"].items():
            if sets and s not in sets:
                continue
            grid = cfg["grids"][s]
            for li, (spellings, display, gloss) in enumerate(lines):
                spellings = spellings.split("|")
                lo, hi = dur_band(spellings[0])
                n_good = 0
                for take in range(max_takes):
                    stem = f"{v}_{s}_{li}_t{take}"
                    jpath = vdir / f"{stem}.json"
                    if jpath.exists():
                        meta = json.loads(jpath.read_text())
                        n_good += meta.get("good", False)
                        if n_good >= good:
                            break
                        continue
                    exag, cw, temp = grid[take % len(grid)]
                    text = spellings[take % len(spellings)]
                    seed = 100 * li + take + (7 if s == "attack" else 0)
                    w = gen_take(model, text, exag, cw, temp, seed)
                    tx = asr(w, SR_GEN) if asr else ""
                    m = match_score(tx, text, gloss) if asr else 1.0
                    # rough trimmed duration for the early-stop check
                    env = np.abs(w)
                    thr = env.max() * 10 ** (-45 / 20)
                    idx = np.nonzero(env > thr)[0]
                    d = (idx[-1] - idx[0]) / SR_GEN if len(idx) else 0.0
                    is_good = m >= 0.6 and lo <= d <= hi
                    n_good += is_good
                    sf.write(vdir / f"{stem}.wav", w, SR_GEN)
                    meta = dict(voice=v, set=s, line=li, take=take, text=text, display=display, gloss=gloss,
                                seed=seed, exaggeration=exag, cfg_weight=cw, temperature=temp, ref=ref.name,
                                raw_seconds=len(w) / SR_GEN, voiced_seconds=d, rms_db=rms_db(w), asr=tx,
                                match=m, good=bool(is_good))
                    jpath.write_text(json.dumps(meta, indent=2))
                    log(f"{stem:26s} ex{exag:.2f} cfg{cw:.2f} {d:4.2f}s rms{rms_db(w):6.1f} m{m:.2f} {'ok ' if is_good else '-- '}:: {tx}")
                    if n_good >= good:
                        break


# ----------------------------------------------------------------------------- post (CPU)
def resample(w, sr_in, sr_out):
    if sr_in == sr_out:
        return w
    try:
        import soxr
        return soxr.resample(w, sr_in, sr_out, quality="VHQ").astype(np.float32)
    except ImportError:
        from math import gcd
        from scipy.signal import resample_poly
        g = gcd(sr_in, sr_out)
        return resample_poly(w, sr_out // g, sr_in // g).astype(np.float32)


def trim_fade_norm(w, sr, thr_db=-45.0, pre_ms=5.0, post_ms=30.0, fade_in_ms=2.0, fade_out_ms=15.0, peak_db=-3.0):
    if w.ndim > 1:
        w = w.mean(axis=1)
    w = w.astype(np.float32)
    win = max(1, int(sr * 0.005))
    env = np.sqrt(np.convolve(w ** 2, np.ones(win) / win, mode="same"))
    thr = env.max() * 10 ** (thr_db / 20)
    idx = np.nonzero(env > thr)[0]
    if len(idx) == 0:
        return w, {"trim_start": 0, "trim_end": len(w)}
    a = max(0, idx[0] - int(sr * pre_ms / 1000))
    b = min(len(w), idx[-1] + int(sr * post_ms / 1000))
    w = w[a:b].copy()
    fi, fo = int(sr * fade_in_ms / 1000), int(sr * fade_out_ms / 1000)
    if fi and len(w) > fi:
        w[:fi] *= np.linspace(0, 1, fi, dtype=np.float32)
    if fo and len(w) > fo:
        w[-fo:] *= np.linspace(1, 0, fo, dtype=np.float32)
    peak = np.abs(w).max() + 1e-9
    w = w * (10 ** (peak_db / 20) / peak)
    return w, {"trim_start": int(a), "trim_end": int(b)}


def median_f0(w, sr):
    try:
        import librosa
        f0, _, _ = librosa.pyin(w, fmin=60, fmax=400, sr=sr)
        f0 = f0[~np.isnan(f0)]
        return float(np.median(f0)) if len(f0) else None
    except Exception:
        return None


def score(meta, dur, rms):
    lo, hi = dur_band(meta["text"])
    s = 3.0 * meta.get("match", 1.0)
    extra = len(re.findall(r"[a-z']+", meta.get("asr", "").lower())) - len(meta["text"].split())
    if extra > 0:
        s -= 0.8 * extra            # "Oh, full gladly", "to the world, to the world"
    if dur < lo:
        s -= 2.0 * (lo - dur) / lo
    elif dur > hi:
        s -= 2.0 * (dur - hi) / hi - 1.0          # babble / trailing syllables
    if meta["set"] == "attack":
        s += np.clip((rms + 18.0) / 6.0, -1.0, 1.0)  # shouted takes are dense: high RMS at -3 dB peak
    elif meta["set"] == "select":
        s += 0.3 * np.clip((rms + 20.0) / 6.0, -1.0, 1.0)
    return float(s)


def stage_post(out, voices, sets, overrides, want_f0=True):
    cand, masters, game = out / "candidates", out / "masters", out / "game"
    masters.mkdir(parents=True, exist_ok=True)
    game.mkdir(parents=True, exist_ok=True)
    manifest = {"sample_rate": SR_GAME, "format": "wav pcm16 mono", "voices": {}, "lines": {},
                "models": {"tts": "ResembleAI/chatterbox (MIT; Perth-watermarked output)",
                           "seed_voices": "hexgrad/Kokoro-82M (Apache-2.0): " +
                                          ", ".join(f"{v}={VOICES[v]['kokoro']}" for v in VOICES)}}
    rows = []       # for preview
    per_voice_f0 = {}
    for v in voices:
        cfg = VOICES[v]
        manifest["voices"][v] = {}
        f0s = []
        for s, lines in cfg["lines"].items():
            if sets and s not in sets:
                continue
            picked_files = []
            n = 0
            for li, (spellings, display, gloss) in enumerate(lines):
                text = spellings.split("|")[0]
                metas = []
                for jpath in sorted((cand / v).glob(f"{v}_{s}_{li}_t*.json")):
                    meta = json.loads(jpath.read_text())
                    w, sr = sf.read(jpath.with_suffix(".wav"), dtype="float32")
                    wt, tr = trim_fade_norm(w, sr)
                    dur = len(wt) / sr
                    r = rms_db(wt)
                    meta.update(dur=dur, rms_norm_db=r, score=score(meta, dur, r), master=f"{jpath.stem}.wav")
                    sf.write(masters / f"{jpath.stem}.wav", wt, sr, subtype="PCM_16")
                    meta["_wav"] = wt
                    metas.append(meta)
                if not metas:
                    log("no candidates for", v, s, li)
                    continue
                key = f"{v}/{s}/{li}"
                if key in overrides:
                    chosen = [m for t in overrides[key] for m in metas if f"t{m['take']}" == t]
                else:
                    ranked = sorted(metas, key=lambda m: -m["score"])
                    chosen = [ranked[0]]
                    for m in ranked[1:]:
                        if len(chosen) >= PICKS_PER_LINE.get(s, 1):
                            break
                        if m["match"] >= 0.5 and m["score"] >= ranked[0]["score"] - 1.0:
                            chosen.append(m)
                for m in chosen:
                    n += 1
                    fname = f"{v}_{s}_{n}.wav"
                    wg = resample(m["_wav"], SR_GEN, SR_GAME)
                    wg = np.clip(wg, -1, 1)
                    sf.write(game / fname, wg, SR_GAME, subtype="PCM_16")
                    picked_files.append(fname)
                    manifest["lines"][fname] = {"text": display, "tts_text": text, "gloss": gloss,
                                                "take": m["master"], "seconds": round(m["dur"], 3)}
                    if want_f0:
                        f0 = median_f0(m["_wav"], SR_GEN)
                        if f0:
                            f0s.append(f0)
                rows.append(dict(voice=v, set=s, line=li, text=text, display=display, gloss=gloss,
                                 picks=[(f"{v}_{s}_{n - len(chosen) + 1 + i}.wav", m) for i, m in enumerate(chosen)],
                                 cands=sorted(metas, key=lambda m: m["take"])))
            manifest["voices"][v][s] = {"files": picked_files, "volume": VOLUME[v][s]}
        if f0s:
            per_voice_f0[v] = float(np.median(f0s))
            manifest["voices"][v]["median_f0_hz"] = round(per_voice_f0[v], 1)
    (game / "voice_manifest.json").write_text(json.dumps(manifest, indent=2))
    write_preview(out / "preview.html", rows, per_voice_f0)
    for v, f in per_voice_f0.items():
        log(f"median f0 {v}: {f:.0f} Hz")
    sizes = sorted((p.name, p.stat().st_size) for p in game.glob("*.wav"))
    log(f"{len(sizes)} game files, {sum(s for _, s in sizes) / 1024:.0f} KiB total")


def write_preview(path, rows, f0s):
    def a(src):
        return f'<audio controls preload="none" src="{html.escape(src)}"></audio>'
    parts = ["<!doctype html><meta charset=utf-8><title>Voice lines</title><style>"
             "body{font:14px system-ui;margin:20px;max-width:1100px}h2{margin-top:32px}table{border-collapse:collapse;width:100%}"
             "td,th{border-bottom:1px solid #ddd;padding:4px 8px;text-align:left;vertical-align:top}audio{height:28px;width:220px}"
             "details{margin:2px 0 10px}summary{cursor:pointer;color:#555}.me{font-weight:600}.g{color:#777}"
             ".ok{color:#2a7}.bad{color:#c33}small{color:#888}</style>",
             "<h1>Medieval Ages voice lines</h1><p>Chatterbox (MIT) from Kokoro seed voices. Picks are in <code>game/</code>; "
             "open the candidates under each line to re-pick with <code>post --pick voice/set/line=tN</code>.</p>",
             "<p>" + " · ".join(f"{v}: median f0 {f:.0f} Hz" for v, f in f0s.items()) + "</p>"]
    cur = None
    for r in rows:
        if (r["voice"], r["set"]) != cur:
            if cur:
                parts.append("</table>")
            cur = (r["voice"], r["set"])
            parts.append(f"<h2>{cur[0]} / {cur[1]}</h2><table><tr><th>line</th><th>picks</th></tr>")
        picks = "".join(
            f"<div>{a('game/' + fn)} <small>{fn} · {m['dur']:.2f}s · ex{m['exaggeration']:.2f}/cfg{m['cfg_weight']:.2f} · "
            f"heard: <i>{html.escape(m['asr'])}</i></small></div>" for fn, m in r["picks"])
        cands = "".join(
            f"<div>{a('masters/' + m['master'])} <small>t{m['take']} · {m['dur']:.2f}s · ex{m['exaggeration']:.2f}/cfg{m['cfg_weight']:.2f} · "
            f"rms {m['rms_norm_db']:.0f} dB · score {m['score']:.2f} · <span class={'ok' if m['match'] >= 0.6 else 'bad'}>"
            f"heard: <i>{html.escape(m['asr'])}</i></span></small></div>" for m in r["cands"])
        parts.append(f"<tr><td><span class=me>{html.escape(r['display'])}</span><br><span class=g>{html.escape(r['gloss'])}</span>"
                     f"<br><small>tts: {html.escape(r['text'])}</small></td><td>{picks}"
                     f"<details><summary>{len(r['cands'])} candidates</summary>{cands}</details></td></tr>")
    parts.append("</table>")
    path.write_text("\n".join(parts))
    log("preview", path)


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", nargs="+", choices=["seeds", "gen", "post", "all"])
    ap.add_argument("--out", default="out")
    ap.add_argument("--voices", default="", help="comma list, default all")
    ap.add_argument("--sets", default="", help="comma list of sets, default all")
    ap.add_argument("--good", type=int, default=4, help="stop a line after this many takes pass the checks")
    ap.add_argument("--max-takes", type=int, default=10)
    ap.add_argument("--no-asr", action="store_true")
    ap.add_argument("--no-f0", action="store_true")
    ap.add_argument("--pick", action="append", default=[], help="voice/set/line=t1,t4 (overrides the ranking)")
    args = ap.parse_args()
    out = Path(args.out)
    voices = args.voices.split(",") if args.voices else list(VOICES)
    sets = set(args.sets.split(",")) if args.sets else None
    overrides = {}
    for p in args.pick:
        k, v = p.split("=")
        overrides[k] = v.split(",")
    stages = set(args.stage)
    if stages & {"seeds", "all"}:
        stage_seeds(out, voices)
    if stages & {"gen", "all"}:
        stage_gen(out, voices, sets, args.good, args.max_takes, use_asr=not args.no_asr)
    if stages & {"post", "all"}:
        stage_post(out, voices, sets, overrides, want_f0=not args.no_f0)


if __name__ == "__main__":
    main()
