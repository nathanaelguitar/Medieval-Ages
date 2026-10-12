#!/usr/bin/env python3
"""Assemble a landscape (1920x1080, 30 fps) Medieval Ages trailer from an edit decision list.
Adapted from art/source/promo/assemble_v.py (the vertical promo assembler).

Usage: assemble.py EDL.json OUT.mp4

Each shot is rendered to a cached, normalized segment, the segments are joined with cuts or short
fades, caption PNGs are laid on top, and the audio is the music bed + game SFX at given times.

EDL keys:
  music: {path, start, db, fade_in, fade_out, tail}   (the fade-out ends `tail` s before the end)
  shots: [{src, in, dur, xf, z0, z1, ax, ay, grade, speed}]  gameplay clip (1920x1080); optional slow push z0->z1
         {card: {bg, text, dur, text_at, fade_in}}     key-art card: slow push on bg, text PNG fades up
         {phone: {src, in, dur, bezel, label, label_at}} 852x393 phone capture set into a device bezel
                                                         over a blurred copy of itself
         (xf: seconds of cross-fade into this shot, 0 = hard cut)
  overlays: [{png, at, dur, fade}]                     on the output timeline
  sfx: [{path, at, db}]
Paths are relative to the EDL's folder unless absolute.
"""
import hashlib, json, os, subprocess, sys

EDL = os.path.abspath(sys.argv[1]); OUT = os.path.abspath(sys.argv[2])
BASE = os.path.dirname(EDL)
cfg = json.load(open(EDL))
FPS, W, H = 30, 1920, 1080
CACHE = os.path.join(os.path.dirname(OUT), ".seg_cache"); os.makedirs(CACHE, exist_ok=True)
PHONE_SCREEN = (180, 170, 1560, 720)   # must match make_text.py

def P(p): return p if os.path.isabs(p) else os.path.normpath(os.path.join(BASE, p))

GRADES = {
    "none": "",
    # a touch of warmth and contrast so the captures sit with the key-art cards
    "game": "eq=saturation=1.05:contrast=1.03,colorbalance=rs=0.012:bs=-0.015",
}

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode: print(" ".join(cmd)); print(r.stderr[-3000:]); sys.exit(1)

def files_of(s):
    if "card" in s: return [s["card"]["bg"], s["card"]["text"]]
    if "phone" in s: return [s["phone"]["src"], s["phone"]["bezel"]] + ([s["phone"]["label"]] if s["phone"].get("label") else [])
    return [s["src"]]

def dur_of(s):
    return s["card"]["dur"] if "card" in s else s["phone"]["dur"] if "phone" in s else s["dur"]

SILENT = ["-f", "lavfi", "-t", "{d}", "-i", "anullsrc=r=48000:cl=stereo"]
ENC = ["-c:v", "libx264", "-preset", "medium", "-crf", "14", "-r", str(FPS), "-c:a", "pcm_s16le"]

def segment(s):
    """Render one shot to CACHE as 1920x1080 30 fps with a silent stereo 48 k track; returns its path."""
    stamp = "".join(f"{os.path.getsize(P(f))}:{os.path.getmtime(P(f))};" for f in files_of(s))
    key = hashlib.md5(json.dumps(s, sort_keys=True).encode() + stamp.encode()).hexdigest()[:12]
    out = os.path.join(CACHE, f"seg_{key}.mkv")
    if os.path.exists(out): return out
    d = dur_of(s); n = int(round(d * FPS)); sil = [x.replace("{d}", str(d)) for x in SILENT]
    if "card" in s:
        c = s["card"]
        fc = (f"[0:v]scale={W*2}:{H*2},zoompan=z='1.0+{c.get('push',0.04)}*on/{n}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s={W}x{H}:fps={FPS},"
              f"format=yuv420p,trim=duration={d}[bg];"
              f"[1:v]format=rgba,fade=t=in:st={c.get('text_at',0.3)}:d={c.get('fade_in',0.7)}:alpha=1[tx];"
              f"[bg][tx]overlay=shortest=1,setsar=1,format=yuv420p[v]")
        run(["nice", "ffmpeg", "-y", "-v", "error", "-loop", "1", "-framerate", str(FPS), "-t", str(d), "-i", P(c["bg"]),
             "-loop", "1", "-framerate", str(FPS), "-t", str(d), "-i", P(c["text"])] + sil +
            ["-filter_complex", fc, "-map", "[v]", "-map", "2:a"] + ENC + ["-t", str(d), out])
        return out
    if "phone" in s:
        ph = s["phone"]; x, y, w, h = PHONE_SCREEN
        ins = ["-i", P(ph["src"]), "-loop", "1", "-framerate", str(FPS), "-t", str(d), "-i", P(ph["bezel"])]
        fc = (f"[0:v]trim=start={ph['in']}:duration={d},setpts=PTS-STARTPTS,fps={FPS},split=2[a][b];"
              f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=28:2,eq=brightness=-0.20:saturation=0.75[bg];"
              f"[b]scale={w}:{h}:flags=lanczos[fg];[bg][fg]overlay={x}:{y}[c];[c][1:v]overlay=shortest=1[d]")
        last = "d"
        if ph.get("label"):
            ins += ["-loop", "1", "-framerate", str(FPS), "-t", str(d), "-i", P(ph["label"])]
            fc += f";[2:v]format=rgba,fade=t=in:st={ph.get('label_at',0.4)}:d=0.5:alpha=1[lb];[d][lb]overlay=shortest=1[e]"; last = "e"
        fc += f";[{last}]setsar=1,format=yuv420p[v]"
        na = 3 if ph.get("label") else 2
        run(["nice", "ffmpeg", "-y", "-v", "error"] + ins + sil + ["-filter_complex", fc, "-map", "[v]", "-map", f"{na}:a"] + ENC + ["-t", str(d), out])
        return out
    src = P(s["src"]); z0, z1 = s.get("z0", 1.0), s.get("z1", 1.0); ax, ay = s.get("ax", 0.5), s.get("ay", 0.5)
    g = GRADES[s.get("grade", "game")]
    sp = s.get("speed", 1.0)   # >1 plays the capture faster (a time-lapse sped up further in the edit)
    vf = f"trim=start={s['in']}:duration={d*sp},setpts=(PTS-STARTPTS)/{sp},fps={FPS},"
    if z0 != 1.0 or z1 != 1.0:   # push-in on a 2x canvas so the motion is sub-pixel smooth
        vf += (f"scale={W*2}:{H*2}:flags=lanczos,zoompan=z='{z0}+({z1}-{z0})*on/{max(1,n-1)}':x='(iw-iw/zoom)*{ax}':y='(ih-ih/zoom)*{ay}':d=1:s={W}x{H}:fps={FPS},")
    else:
        vf += f"scale={W}:{H}:flags=lanczos,"
    vf += (g + "," if g else "") + "setsar=1,format=yuv420p"
    run(["nice", "ffmpeg", "-y", "-v", "error", "-i", src] + sil +
        ["-filter_complex", f"[0:v]{vf},trim=duration={d}[v]", "-map", "[v]", "-map", "1:a"] + ENC + ["-t", str(d), out])
    return out

shots = cfg["shots"]
segs = [segment(s) for s in shots]
durs = [dur_of(s) for s in shots]

inputs, fc = [], []
for i, p in enumerate(segs):
    inputs += ["-i", p]
    fc.append(f"[{i}:v]fps={FPS},settb=AVTB,setpts=PTS-STARTPTS[nv{i}]")
    fc.append(f"[{i}:a]asetpts=PTS-STARTPTS[na{i}]")
cur_v, cur_a, t = "nv0", "na0", durs[0]
starts = [0.0]
for i in range(1, len(segs)):
    xf = shots[i].get("xf", 0)
    if xf > 0:
        off = t - xf
        fc.append(f"[{cur_v}][nv{i}]xfade=transition={shots[i].get('xfk','fade')}:duration={xf}:offset={off:.4f},settb=AVTB[v{i}]")
        fc.append(f"[{cur_a}][na{i}]acrossfade=d={xf}:c1=tri:c2=tri[a{i}]")
        starts.append(off); t = off + durs[i]
    else:
        fc.append(f"[{cur_v}][{cur_a}][nv{i}][na{i}]concat=n=2:v=1:a=1[vc{i}][a{i}]")
        fc.append(f"[vc{i}]settb=AVTB[v{i}]")
        starts.append(t); t += durs[i]
    cur_v, cur_a = f"v{i}", f"a{i}"
total = t
print("timeline:", " ".join(f"{i}:{st:.2f}" for i, st in enumerate(starts)), f"total {total:.2f}s")
json.dump({"starts": starts, "durs": durs, "total": total}, open(OUT + ".timeline.json", "w"))

k = len(segs)
for o in cfg.get("overlays", []):
    inputs += ["-loop", "1", "-framerate", str(FPS), "-t", f"{total:.3f}", "-i", P(o["png"])]
    fd = o.get("fade", 0.25); a0, d = o["at"], o["dur"]
    fc.append(f"[{k}:v]format=rgba,fade=t=in:st={a0}:d={fd}:alpha=1,fade=t=out:st={a0+d-fd}:d={fd}:alpha=1[o{k}]")
    fc.append(f"[{cur_v}][o{k}]overlay=enable='between(t,{a0},{a0+d})':shortest=1[ov{k}]")
    cur_v = f"ov{k}"; k += 1

m = cfg["music"]
inputs += ["-i", P(m["path"])]
fc.append(f"[{k}:a]atrim=start={m['start']}:duration={total:.3f},asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,"
          f"afade=t=in:d={m.get('fade_in',0.05)},afade=t=out:st={total-m.get('fade_out',2.0)-m.get('tail',0.3):.3f}:d={m.get('fade_out',2.0)}:curve=qsin,volume={m.get('db',0)}dB[mus]")
mix = ["[mus]", f"[{cur_a}]"]; k += 1
for j, x in enumerate(cfg.get("sfx", [])):
    inputs += ["-i", P(x["path"])]
    ms = int(x["at"] * 1000)
    # short fades at both ends of every effect: a file that stops on a non-zero sample would click
    fc.append(f"[{k}:a]aformat=sample_rates=48000:channel_layouts=stereo,afade=t=in:d=0.004,areverse,afade=t=in:d=0.012,areverse,"
              f"volume={x.get('db',-6)}dB,adelay={ms}|{ms}[s{j}]")
    mix.append(f"[s{j}]"); k += 1
fc.append(f"{''.join(mix)}amix=inputs={len(mix)}:duration=first:normalize=0,alimiter=limit=0.89,atrim=duration={total:.3f}[aout]")
fc.append(f"[{cur_v}]setsar=1,format=yuv420p[vout]")

cmd = ["nice", "ffmpeg", "-y", "-v", "error", "-stats"] + inputs + ["-filter_complex", ";".join(fc), "-map", "[vout]", "-map", "[aout]",
       "-c:v", "libx264", "-preset", "slow", "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", str(FPS), "-g", "60",
       "-crf", str(cfg.get("crf", 17)), "-maxrate", "16M", "-bufsize", "32M",
       "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", "-t", f"{total:.3f}", OUT]
r = subprocess.run(cmd)
if r.returncode: sys.exit(r.returncode)
print("wrote", OUT, f"{total:.2f}s")
