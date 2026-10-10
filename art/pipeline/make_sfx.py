#!/usr/bin/env python3
"""Generate the game's combat/work foley with Stable Audio 3 (small-sfx) on the Spark.

Engines (``--engine``), all self-hosted on the Spark:
  sa3        Stable Audio 3 via --model: small-sfx-base (default) or medium-base, both ungated,
             Stability AI Community License (free commercial use under US$1M/yr revenue, register
             at https://stability.ai/community-license, keep the Notice file + "Powered by
             Stability AI"). The post-trained small-sfx / medium repos are gated: once accepted
             on Hugging Face, --model small-sfx|medium (8 steps, cfg 1; cfg only matters on -base).
             Runs in fp32: fp16 gives NaN latents on the GB10 / torch 2.10 stack. Base defaults are
             50 steps, cfg 4, APG on: the model card's cfg 7 overdrives the decoder (clipped,
             hissy output) and a negative prompt makes it explode (latent std ~250 vs 1), so
             --negative is opt-in and cfg > 5 is not recommended.
  tangoflux  declare-lab/TangoFlux (non-commercial research weights; needs the sa3-sfx:tf image).
Candidates from every engine land in the same out/candidates tree (stem tag: none = small-sfx-base,
mb_ = medium-base, tf_ = TangoFlux) and are ranked together in the post stage.

Runs inside the sa3-sfx image (art/pipeline/docker/sfx/Dockerfile) — the exact invocation,
from the repo root on the Mac:

    scp art/pipeline/make_sfx.py spark:~/sfx/make_sfx.py
    ssh spark 'HF_HUB_OFFLINE=1 ~/sfx/run.sh python /work/make_sfx.py gen --out /work/out --seeds 8'
    ssh spark 'HF_HUB_OFFLINE=1 ~/sfx/run.sh python /work/make_sfx.py gen --out /work/out --seeds 8 --model medium-base'
    ssh spark 'HF_HUB_OFFLINE=1 IMG=sa3-sfx:tf ~/sfx/run.sh python /work/make_sfx.py gen --out /work/out --seeds 8 --engine tangoflux'
    ssh spark '~/sfx/run.sh python /work/make_sfx.py post --out /work/out'
    rsync -a --delete spark:~/sfx/out/ art/out/sfx/

Stages (``all`` runs them in order; each can be rerun alone):
    gen   GPU: every prompt x seed -> out/candidates/<sound>/<sound>_p<i>_s<seed>.wav (+ .json)
    post  CPU: mono, attack-tight trim (cut at the zero crossing just before the transient,
          1.5 ms fade-in), short fade-out, -3 dBFS peak -> out/masters/*.wav + metrics,
          heuristic ranking -> picks copied to out/game/<sound>_<n>.wav (16-bit PCM mono
          44.1 kHz; --rate22 <sounds> stores those at 22.05 kHz), out/game/sfx_manifest.json
          and out/preview.html.

Picks are heuristic (duration inside the target band, crest factor, short tail, plausible
spectral centroid, no clipping, tonal similarity to the top pick so a random +-2 semitone
shift in game keeps them a family) — audition in preview.html and override with
``post --pick sound=p1_s3,p0_s2,...``.
"""
import argparse
import html
import json
import os
import sys
import time
from pathlib import Path

NEGATIVE = ("reverb, echo, hall, room ambience, music, melody, speech, words, crowd, wind, "
            "distant, muffled, low quality, noise, hiss, hum, looping, repeated")

# name -> (prompts, target seconds (lo, hi), generate seconds, centroid band Hz (lo, hi),
#          loudness target dBFS RMS used for the suggested relative volume, number of picks)
SOUNDS = {
    "bow_release": (
        ["Longbow string twang release then a fast arrow whoosh flying past, single shot, close mic, dry, no reverb, medieval foley",
         "Bowstring snap and a quick arrow whoosh, one archer shot, tight dry recording",
         "Arrow shot from a wooden bow: taut string thump followed by a short whoosh, single sound effect, dry"],
        (0.35, 0.75), 2.0, (1500, 7000), -19, 5),
    "arrow_hit": (
        ["Arrow thudding into a wooden target, single short impact, close mic, dry, no reverb",
         "Arrow hits flesh with a wet thud, one short impact, foley, dry",
         "Arrow strikes a wooden plank with a thunk and a brief shaft vibration, single hit, dry foley"],
        (0.18, 0.42), 1.5, (300, 4000), -17, 5),
    "sword_swing": (
        ["Fast sword swing whoosh through the air, single slash, dry, no reverb, foley",
         "Blade slash whoosh, one quick swing of a steel sword, close mic, dry",
         "Short sharp metallic sword swipe whoosh, one swing, dry recording"],
        (0.25, 0.55), 1.5, (1500, 8000), -20, 5),
    "sword_hit": (
        ["Sword striking a steel shield, sharp metallic clang with impact, single hit, short decay, dry, no reverb",
         "Steel blade hits plate armour, metallic clank and thud, one impact, close mic, dry",
         "Sword clash on metal, a single short ringing clang, dry foley"],
        (0.25, 0.65), 1.5, (1500, 8000), -17, 5),
    "death_grunt": (
        ["Short pained grunt of a man being hit, single ugh, no words, close mic, dry",
         "Male warrior death grunt, one short groan of pain, no speech, dry recording"],
        (0.25, 0.65), 1.5, (300, 3000), -19, 3),
    "axe_chop": (
        ["Axe chopping into a tree trunk, single wood chop impact, close mic, dry, no reverb",
         "Hatchet biting into a log, one solid chop, foley, dry",
         "Woodcutter's axe hits a tree, single sharp thock, dry recording"],
        (0.18, 0.5), 1.5, (300, 4000), -18, 3),
    "pick_hit": (
        ["Pickaxe striking rock, single metallic clink with a stone chip, close mic, dry",
         "Iron pick hits stone in a quarry, one sharp strike, short, dry foley",
         "Mining pick on rock, single clink and crumble, dry, no reverb"],
        (0.15, 0.5), 1.5, (1000, 7000), -18, 3),
    "hammer_hit": (
        ["Wooden mallet hitting a wooden peg, single knock, close mic, dry, no reverb",
         "Hammer strikes a wooden beam, one solid thock, carpentry foley, dry",
         "Carpenter's hammer on timber, single hit, short, dry"],
        (0.12, 0.45), 1.5, (300, 4000), -18, 3),
    "building_collapse": (
        ["Wooden building collapsing, timber cracking and stones tumbling, short rubble crash, dry, no reverb",
         "Stone wall crumbles and wooden beams snap, short collapse crash, foley",
         "Medieval house falls apart: splintering wood and falling masonry, one short crash, dry"],
        (0.9, 2.2), 3.0, (200, 3000), -15, 2),
}
FADE_OUT_MS = {"building_collapse": 80}
TAGS = {"small-sfx-base": "", "small-sfx": "ss_", "medium-base": "mb_", "medium": "md_", "tangoflux": "tf_"}
LICENSES = {
    "stabilityai/stable-audio-3-*": "Stability AI Community License: commercial use permitted under US$1M annual "
                                    "revenue; register at https://stability.ai/community-license; credit 'Powered by Stability AI'",
    "declare-lab/TangoFlux": "NON-COMMERCIAL research use only (Stable Audio Open + WavCaps terms)",
}


# ----------------------------------------------------------------------------- generation
def load_model(name, device="cuda", half=False):
    """StableAudioModel.from_pretrained, but with the text encoder pointed at the repo we can
    actually download (the -base config references the gated small-sfx repo for t5gemma) and
    with fp32 weights by default (fp16 -> NaN latents on the Spark)."""
    from stable_audio_3.model import StableAudioModel
    from stable_audio_3.model_configs import all_models
    from stable_audio_3.loading_utils import load_diffusion_cond
    cfg = all_models[name]
    local_config, local_ckpt = cfg.resolve()
    model_config = json.load(open(local_config))
    for c in model_config["model"].get("conditioning", {}).get("configs", []):
        if c.get("type") == "t5gemma" and c["config"].get("repo_id"):
            c["config"]["repo_id"] = cfg.repo_id
    model = load_diffusion_cond(model_config, local_ckpt, device=device, model_half=half)
    model.use_lora = False
    model.lora_names = []
    return StableAudioModel(model, model_config, device, half)


def make_engine(args):
    """Returns (model_id, tag, gen(prompt, seconds, seed) -> (samples (n, ch) float32, sr), params)."""
    import torch
    t0 = time.time()
    if args.engine == "tangoflux":
        from tangoflux import TangoFluxInference
        tf = TangoFluxInference(name="declare-lab/TangoFlux")
        steps, cfg = args.steps or 50, args.cfg if args.cfg is not None else 4.5

        def gen(prompt, seconds, seed):
            # TangoFluxInference.generate() reseeds inference_flow with seed=0 every call, so the
            # flow is driven directly to get distinct seeds (decode copied from generate()).
            dur = max(seconds, 3)
            with torch.no_grad():
                lat = tf.model.inference_flow(prompt, duration=dur, num_inference_steps=steps, guidance_scale=cfg, seed=seed)
                w = tf.vae.decode(lat.transpose(2, 1)).sample.cpu()[0]
            w = w[:, :int(dur * tf.vae.config.sampling_rate)]
            return w.float().numpy().T, tf.vae.config.sampling_rate
        print(f"TangoFlux loaded in {time.time() - t0:.0f}s, steps={steps}, cfg={cfg}", flush=True)
        return "declare-lab/TangoFlux", TAGS["tangoflux"], gen, {"steps": steps, "cfg": cfg, "negative": None}
    base = args.model.endswith("-base")
    steps = args.steps or (50 if base else 8)
    cfg = args.cfg if args.cfg is not None else (4.0 if base else 1.0)
    model = load_model(args.model, half=args.half)
    sr = model.model.sample_rate
    neg = NEGATIVE if (base and args.negative) else None

    def gen(prompt, seconds, seed):
        audio = model.generate(prompt=prompt, negative_prompt=neg, duration=seconds, steps=steps, cfg_scale=cfg, seed=seed)
        return audio[0].float().cpu().numpy().T, sr
    print(f"model {args.model} loaded in {time.time() - t0:.0f}s, sr={sr}, steps={steps}, cfg={cfg}", flush=True)
    return f"stabilityai/stable-audio-3-{args.model}", TAGS[args.model], gen, {"steps": steps, "cfg": cfg, "negative": neg}


def stage_gen(args):
    import soundfile as sf
    import torch
    model_id, tag, gen, params = make_engine(args)
    cand = Path(args.out) / "candidates"
    for name in args.sounds:
        prompts, _, gen_sec, _, _, _ = SOUNDS[name]
        d = cand / name
        d.mkdir(parents=True, exist_ok=True)
        for pi, prompt in enumerate(prompts):
            for seed in range(args.seed0, args.seed0 + args.seeds):
                stem = f"{name}_{tag}p{pi}_s{seed}"
                wav = d / f"{stem}.wav"
                if wav.exists() and not args.force:
                    continue
                t1 = time.time()
                a, sr = gen(prompt, gen_sec, seed)
                import numpy as np
                a = np.nan_to_num(a).clip(-1, 1)
                if not (abs(a).max() > 0):
                    print(f"  {stem}: silent/NaN output, skipped", flush=True)
                    continue
                sf.write(wav, a, sr, subtype="PCM_16")
                json.dump({"sound": name, "prompt": prompt, "seed": seed, "model": model_id, "engine": args.engine,
                           **params, "gen_seconds": gen_sec, "sample_rate": sr}, open(d / f"{stem}.json", "w"), indent=1)
                print(f"  {stem}  {time.time() - t1:.1f}s", flush=True)
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    print("gen done", flush=True)


# ----------------------------------------------------------------------------- post
def db(x):
    import numpy as np
    return 20 * np.log10(max(float(x), 1e-9))


def envelope(x, sr, win_ms=8, hop_ms=2):
    import numpy as np
    w, h = int(sr * win_ms / 1000), int(sr * hop_ms / 1000)
    n = max(1, (len(x) - w) // h + 1)
    idx = np.arange(w)[None, :] + h * np.arange(n)[:, None]
    env = np.sqrt((x[idx] ** 2).mean(axis=1) + 1e-12)
    return env, h


def trim(x, sr, lo, hi, fade_out_ms):
    """Attack-tight trim: the first sample above -30 dB re peak is the transient; cut at the last
    zero crossing before it (at most 2 ms earlier) and fade in over 1.5 ms, so the hit lands
    within ~2 ms of t=0. End where the 8 ms RMS envelope stays under -45 dB re peak for 50 ms;
    cap at hi seconds, fade out, peak-normalise to -3 dBFS. The end threshold is lifted to 6 dB
    above the clip's own noise floor when that floor sits above -45 dB."""
    import numpy as np
    # onset = walk back from the envelope peak until it drops 24 dB (so a creak or pre-echo before
    # the main hit does not anchor the cut), then the first sample above -30 dB re peak from there
    env0, hop0 = envelope(x, sr)
    pk0 = int(np.argmax(env0))
    i = pk0
    while i > 0 and env0[i] > env0[pk0] * 10 ** (-24 / 20):
        i -= 1
    region = max(0, i * hop0 - int(0.01 * sr))
    peak = np.abs(x).max() + 1e-9
    on = region + int(np.argmax(np.abs(x[region:]) > peak * 10 ** (-30 / 20)))
    start = max(0, on - int(0.002 * sr))
    sign = np.sign(x[start:on + 1])
    zc = np.nonzero(sign[:-1] * sign[1:] <= 0)[0]
    if len(zc):
        start = start + int(zc[-1]) + 1
    x = x[start:]
    env, hop = envelope(x, sr)
    # end threshold: -45 dB re peak, or 6 dB above the clip's own noise floor (median envelope of
    # its last 20 %) when the model leaves a hiss bed that never reaches -45 dB (TangoFlux does)
    floor = float(np.median(env[int(len(env) * 0.8):])) if len(env) > 10 else 0.0
    thr = max(env.max() * 10 ** (-45 / 20), floor * 10 ** (6 / 20))
    below = env < thr
    run = int(0.05 * sr / hop)
    end = len(x)
    pk = int(np.argmax(env))
    for i in range(pk, len(below) - run):
        if below[i:i + run].all():
            end = i * hop
            break
    end = min(end, int(hi * sr), len(x))
    end = max(end, min(len(x), int(lo * 0.6 * sr)))
    x = x[:end].copy()
    fi, fo = int(0.0015 * sr), min(int(fade_out_ms / 1000 * sr), len(x) // 2)
    x[:fi] *= np.linspace(0, 1, fi)
    if fo > 0:
        x[-fo:] *= np.linspace(1, 0, fo) ** 2
    x *= 10 ** (-3 / 20) / (np.abs(x).max() + 1e-9)
    return x, start


def metrics(x, sr, raw):
    import numpy as np
    peak = np.abs(x).max() + 1e-9
    rms = np.sqrt((x ** 2).mean() + 1e-12)
    env, hop = envelope(x, sr)
    pk = int(np.argmax(env))
    thr = env[pk] * 10 ** (-30 / 20)
    dec = next((i for i in range(pk, len(env)) if env[i] < thr), len(env)) - pk
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    freqs = np.fft.rfftfreq(len(x), 1 / sr)
    centroid = float((spec * freqs).sum() / (spec.sum() + 1e-9))
    # distinct onsets: envelope peaks above -12 dB re max, at least 80 ms apart
    gate = env > env.max() * 10 ** (-12 / 20)
    onsets, last = 0, -10 ** 9
    for i in range(1, len(env) - 1):
        if gate[i] and env[i] >= env[i - 1] and env[i] > env[i + 1] and (i - last) * hop > 0.08 * sr:
            onsets += 1
            last = i
    # first sample above -30 dB re peak, in ms, after the trim (attack tightness)
    attack_ms = round(float(np.argmax(np.abs(x) > peak * 10 ** (-30 / 20))) / sr * 1000, 2)
    clip = float((np.abs(raw) >= 0.999).mean())
    return {"duration": round(len(x) / sr, 3), "peak_db": round(db(peak), 1), "rms_db": round(db(rms), 1),
            "crest_db": round(db(peak / rms), 1), "decay30_ms": int(dec * hop / sr * 1000),
            "centroid_hz": int(centroid), "onsets": onsets, "attack_ms": attack_ms,
            "clip_pct": round(clip * 100, 2)}


def score(m, name):
    (_, (lo, hi), _, (clo, chi), _, _) = SOUNDS[name]
    s = 0.0
    d = m["duration"]
    if d < lo:
        s -= (lo - d) / lo * 6
    elif d > hi:
        s -= (d - hi) / hi * 6
    s += min(m["crest_db"], 24) / 4                       # punchy
    s -= max(0, m["decay30_ms"] - 150) / 100              # dry
    c = m["centroid_hz"]
    if c < clo:
        s -= (clo - c) / clo * 3
    elif c > chi:
        s -= (c - chi) / chi * 3
    want = 2 if name in ("bow_release", "building_collapse") else 1
    s -= abs(m["onsets"] - want) * 1.5
    s -= min(m["clip_pct"], 5) * 1.0                      # decoder clipping = distortion
    s -= max(0, m["attack_ms"] - 3) * 0.5                 # hit must land within a few ms of t=0
    if m["rms_db"] < -30:
        s -= 3                                             # mostly silence / thin
    return round(s, 2)


def pick_family(rows, n, floor=-6.0):
    """One model per sound: rank models by the mean score of their best n candidates, take the
    winner's top n (re-ranked with a centroid-similarity term against its best so the set stays
    one timbral family under the game's random pitch shift); backfill from the runner-up only if
    the winner has fewer than n candidates above the score floor."""
    import math
    by = {}
    for r in rows:
        by.setdefault(r["model"], []).append(r)
    if not by:
        return []
    order = sorted(by, key=lambda m: -sum(r["score"] for r in by[m][:n]) / min(n, len(by[m])))
    picked = []
    for m in order:
        cands = [r for r in by[m] if r["score"] >= floor] or (by[m][:1] if not picked else [])
        if not cands:
            continue
        top = cands[0]
        rest = sorted(cands[1:], key=lambda r: -(r["score"] - 1.5 * abs(math.log2((r["centroid_hz"] + 1) / (top["centroid_hz"] + 1)))))
        picked += [top] + rest
        if len(picked) >= n:
            break
    return picked[:n]


def stage_post(args):
    import numpy as np
    import soundfile as sf
    out = Path(args.out)
    cand, masters, game = out / "candidates", out / "masters", out / "game"
    masters.mkdir(parents=True, exist_ok=True)
    game.mkdir(parents=True, exist_ok=True)
    for old in game.glob("*.wav"):
        old.unlink()
    overrides = {}
    for p in args.pick or []:
        k, v = p.split("=")
        overrides[k] = v.split(",")
    manifest = {"generated": time.strftime("%Y-%m-%d"), "models": {}, "licenses": LICENSES,
                "format": "16-bit PCM WAV, mono, 44.1 kHz (22.05 kHz where noted); attack within ~2 ms of t=0; peak -3 dBFS",
                "sounds": {}}
    total = 0
    for name in args.sounds:
        prompts, (lo, hi), _, _, target_rms, npick = SOUNDS[name]
        rows = []
        for wav in sorted((cand / name).glob("*.wav")):
            meta = json.load(open(wav.with_suffix(".json")))
            x, sr = sf.read(wav, dtype="float32", always_2d=True)
            if sr != 44100:
                sys.exit(f"{wav}: sample rate {sr}")
            model_id = meta.get("model", "small-sfx-base")
            if "/" not in model_id:
                model_id = f"stabilityai/stable-audio-3-{model_id}"
            manifest["models"][model_id] = next((v for k, v in LICENSES.items() if k.rstrip("*") in model_id), "unknown")
            x = x.mean(axis=1)
            y, start = trim(x, sr, lo, hi, FADE_OUT_MS.get(name, 25))
            mwav = masters / f"{wav.stem}.wav"
            sf.write(mwav, y, sr, subtype="PCM_16")
            m = metrics(y, sr, x)
            m["score"] = score(m, name)
            rows.append({"id": wav.stem.replace(name + "_", ""), "master": f"masters/{mwav.name}", "model": model_id,
                         "prompt": meta["prompt"], "seed": meta["seed"], "cut_ms": round(start / sr * 1000, 1), **m})
        rows.sort(key=lambda r: -r["score"])
        want = overrides.get(name)
        picked = [r for r in rows if r["id"] in want] if want else pick_family(rows, args.npick or npick)
        rate = 22050 if name in (args.rate22 or []) else 44100
        files = []
        for n, r in enumerate(picked, 1):
            y, sr = sf.read(masters / Path(r["master"]).name, dtype="float32")
            if rate != sr:
                import torch
                import torchaudio
                y = torchaudio.transforms.Resample(sr, rate)(torch.from_numpy(y)).numpy()
                y *= 10 ** (-3 / 20) / (np.abs(y).max() + 1e-9)
            gw = game / f"{name}_{n}.wav"
            sf.write(gw, y, rate, subtype="PCM_16")
            r["picked"] = n
            total += gw.stat().st_size
            files.append({"file": f"game/{gw.name}", "candidate": r["id"], "model": r["model"], "seed": r["seed"], "prompt": r["prompt"],
                          "duration": r["duration"], "rate": rate, "bytes": gw.stat().st_size})
        rms = np.mean([r["rms_db"] for r in picked]) if picked else -20
        vol = float(10 ** ((target_rms - rms) / 20))        # gain that brings the set to its loudness target
        manifest["sounds"][name] = {"volume": vol, "model": picked[0]["model"] if picked else None,
                                    "files": files, "candidates": rows}
        print(f"{name}: {len(rows)} candidates, picked {[r['id'] for r in picked]}, volume {vol:.2f}", flush=True)
    # relative volumes: the loudest-needed sound gets 1.0, the rest sit below it at their targets
    vmax = max((s["volume"] for s in manifest["sounds"].values()), default=1.0)
    for s in manifest["sounds"].values():
        s["volume"] = round(max(0.1, s["volume"] / vmax), 2)
    manifest["total_game_bytes"] = total
    json.dump(manifest, open(game / "sfx_manifest.json", "w"), indent=1)
    write_preview(out, manifest)
    print(f"post done, game files total {total / 1024:.0f} KB", flush=True)


def write_preview(out, manifest):
    parts = ["<!doctype html><meta charset=utf-8><title>SFX preview</title>",
             "<style>body{font:14px/1.4 system-ui;margin:20px;background:#1b1a17;color:#eee}h2{margin:22px 0 6px}"
             "table{border-collapse:collapse}td,th{padding:3px 8px;border-bottom:1px solid #333;text-align:left;font-size:13px}"
             ".pick{background:#2d3a22}button{font-size:15px;padding:2px 10px}small{color:#999}.prompt{color:#bbb;max-width:520px}</style>",
             "<h1>Medieval Ages SFX</h1><ul>",
             *[f"<li><b>{html.escape(k)}</b> — {html.escape(v)}</li>" for k, v in manifest["models"].items()],
             "</ul><p>Green rows are the heuristic picks (copied to game/*.wav, %d KB total). Other rows play the trimmed WAV master."
             % (manifest["total_game_bytes"] // 1024),
             "<p>Preview volume <input id=v type=range min=0 max=1 step=0.05 value=1> &nbsp; "
             "<label><input id=rr type=checkbox checked> round-robin the picks when clicking the sound name</label></p>",
             "<script>function p(u){var a=document.getElementById('a');a.src=u;a.volume=parseFloat(document.getElementById('v').value)||1;a.play()}"
             "var rr={};function rot(name,files){rr[name]=((rr[name]||0)+1)%files.length;p(files[rr[name]])}</script>",
             "<audio id=a></audio>"]
    for name, s in manifest["sounds"].items():
        files = json.dumps([f["file"] for f in s["files"]])
        parts.append(f"<h2><a href=# onclick=\"rot('{name}',{html.escape(files)});return false\">{name}</a> "
                     f"<small>suggested volume {s['volume']} · {html.escape((s.get('model') or '').split('/')[-1])}</small></h2>")
        for f in s["files"]:
            parts.append(f"<button onclick=\"p('{f['file']}')\">&#9654; {Path(f['file']).name}</button> "
                         f"<small>{f['duration']}s · {f['bytes'] // 1024 + 1} KB · {f['rate']} Hz · {html.escape(f['model'].split('/')[-1])}</small> &nbsp;")
        parts.append("<table><tr><th></th><th>id</th><th>model</th><th>dur</th><th>attack</th><th>crest</th><th>decay</th><th>centroid</th>"
                     "<th>onsets</th><th>clip</th><th>score</th><th>prompt</th></tr>")
        for r in s["candidates"]:
            cls = " class=pick" if r.get("picked") else ""
            parts.append(f"<tr{cls}><td><button onclick=\"p('{r['master']}')\">&#9654;</button></td><td>{r['id']}</td>"
                         f"<td>{html.escape(r['model'].split('/')[-1])}</td><td>{r['duration']}s</td><td>{r['attack_ms']} ms</td><td>{r['crest_db']} dB</td><td>{r['decay30_ms']} ms</td>"
                         f"<td>{r['centroid_hz']} Hz</td><td>{r['onsets']}</td><td>{r['clip_pct']}%</td><td>{r['score']}</td>"
                         f"<td class=prompt>{html.escape(r['prompt'])}</td></tr>")
        parts.append("</table>")
    (out / "preview.html").write_text("\n".join(parts))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=["gen", "post", "all"])
    ap.add_argument("--out", default="out")
    ap.add_argument("--engine", choices=["sa3", "tangoflux"], default="sa3")
    ap.add_argument("--model", default="small-sfx-base", choices=list(TAGS), help="sa3 checkpoint")
    ap.add_argument("--sounds", nargs="*", default=list(SOUNDS))
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--seed0", type=int, default=1)
    ap.add_argument("--steps", type=int)
    ap.add_argument("--cfg", type=float)
    ap.add_argument("--half", action="store_true", help="fp16 weights (NaN on the Spark; off by default)")
    ap.add_argument("--negative", action="store_true", help="use the NEGATIVE prompt on -base models (blows up guidance; off)")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--npick", type=int, help="override the per-sound pick count")
    ap.add_argument("--rate22", nargs="*", help="sounds to store at 22.05 kHz (low-frequency thuds)")
    ap.add_argument("--pick", nargs="*", help="override picks: sound=p0_s3,p1_s2")
    args = ap.parse_args()
    for s in args.sounds:
        if s not in SOUNDS:
            sys.exit(f"unknown sound {s}; have {list(SOUNDS)}")
    if args.stage in ("gen", "all"):
        stage_gen(args)
    if args.stage in ("post", "all"):
        stage_post(args)


if __name__ == "__main__":
    main()
