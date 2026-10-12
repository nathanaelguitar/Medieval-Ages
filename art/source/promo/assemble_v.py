#!/usr/bin/env python3
"""Assemble a vertical (1080x1920, 30 fps) Medieval Ages promo from an edit decision list.

Usage: assemble_v.py EDL.json OUT.mp4

Every shot is first rendered to a normalized segment (scaled/cropped to 9:16, graded with the
intro's grades, optional slow push-in), then the segments are joined with hard cuts or short
fades, text overlays are laid on top, and the audio is the music bed + the FastH3 shots' own
ambience (ducked) + game SFX at given times.

EDL keys:
  music: {path, start, db, fade_in, fade_out, tail}  amb_db: level for FastH3 clip audio
         (the fade-out ends `tail` s (default 0.3) before the end, so every cut closes on true silence)
  shots: [{src, in, dur, grade, z0, z1, ax, ay, xf, amb}]   (xf: fade into this shot, 0 = cut)
         or {title: {bg, text, soon, dur}}                    (end card built from PNGs)
  overlays: [{png, at, dur, fade}]                            (times on the output timeline)
  sfx: [{path, at, db}]
Paths are relative to the EDL's folder unless absolute.
"""
import hashlib, json, os, subprocess, sys

EDL = os.path.abspath(sys.argv[1]); OUT = os.path.abspath(sys.argv[2])
BASE = os.path.dirname(EDL)
cfg = json.load(open(EDL))
FPS, W, H = 30, 1080, 1920
CACHE = os.path.join(os.path.dirname(OUT), ".seg_cache"); os.makedirs(CACHE, exist_ok=True)

def P(p): return p if os.path.isabs(p) else os.path.normpath(os.path.join(BASE, p))

# The intro's grades (art/source/intro/edit/assemble.py), plus a gentle one for gameplay captures.
GRADES = {
    "none": "",
    "default": "curves=all='0/0.035 0.2/0.235 0.5/0.52 0.8/0.81 1/1',eq=saturation=1.06:contrast=1.02",
    "warm": "curves=all='0/0.035 0.2/0.235 0.5/0.52 0.8/0.81 1/1',eq=saturation=1.08:contrast=1.02,colorbalance=rs=0.02:gs=0.0:bs=-0.03",
    # a touch warmer still, for the cooler-looking portrait takes, so they sit with the intro
    "golden": "curves=all='0/0.035 0.2/0.235 0.5/0.52 0.8/0.81 1/1',eq=saturation=1.08:contrast=1.03,colorbalance=rs=0.04:gs=0.01:bs=-0.05:rm=0.02:bm=-0.02",
    "game": "eq=saturation=1.06:contrast=1.03,colorbalance=rs=0.015:bs=-0.02",
}

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode: print(" ".join(cmd)); print(r.stderr[-3000:]); sys.exit(1)

def probe_audio(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", p], capture_output=True, text=True)
    return bool(r.stdout.strip())

def segment(s, i):
    """Render one shot to CACHE as 1080x1920 30 fps with a stereo 48 k track; returns its path."""
    # key on the referenced files' size+mtime too, so a regenerated PNG/take is never served stale from cache
    files = [s["src"]] if "src" in s else [s["title"][k] for k in ("bg", "text", "soon")]
    stamp = "".join(f"{os.path.getsize(P(f))}:{os.path.getmtime(P(f))};" for f in files)
    key = hashlib.md5(json.dumps(s, sort_keys=True).encode() + str(cfg.get("amb_db", -10)).encode() + stamp.encode()).hexdigest()[:12]
    out = os.path.join(CACHE, f"seg_{key}.mkv")
    if os.path.exists(out): return out
    if "title" in s:
        t = s["title"]; d = t["dur"]; n = int(round(d * FPS))
        # slow push on the still, then the title text fades up, then the release line
        fc = (f"[0:v]scale={W*2}:{H*2},zoompan=z='1.0+0.05*on/{n}':x='iw/2-iw/zoom/2':y='ih*0.3-ih*0.3/zoom':d=1:s={W}x{H}:fps={FPS},"
              f"format=yuv420p,trim=duration={d}[bg];"
              f"[1:v]format=rgba,fade=t=in:st={t.get('text_at',0.25)}:d=0.6:alpha=1[tx];"
              f"[2:v]format=rgba,fade=t=in:st={t.get('soon_at',1.1)}:d=0.5:alpha=1[sn];"
              f"[bg][tx]overlay=shortest=1[b1];[b1][sn]overlay=shortest=1,setsar=1,format=yuv420p[v]")
        run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-framerate", str(FPS), "-t", str(d), "-i", P(t["bg"]),
             "-loop", "1", "-framerate", str(FPS), "-t", str(d), "-i", P(t["text"]),
             "-loop", "1", "-framerate", str(FPS), "-t", str(d), "-i", P(t["soon"]),
             "-f", "lavfi", "-t", str(d), "-i", "anullsrc=r=48000:cl=stereo",
             "-filter_complex", fc, "-map", "[v]", "-map", "3:a", "-c:v", "libx264", "-preset", "medium", "-crf", "14",
             "-r", str(FPS), "-c:a", "pcm_s16le", "-t", str(d), out])
        return out
    src = P(s["src"]); d = s["dur"]; n = int(round(d * FPS))
    z0, z1 = s.get("z0", 1.0), s.get("z1", 1.0); ax, ay = s.get("ax", 0.5), s.get("ay", 0.5)
    g = GRADES[s.get("grade", "default")]
    speed = s.get("speed", 1.0)
    vf = f"trim=start={s['in']}:duration={d*speed},setpts=(PTS-STARTPTS)/{speed},fps={FPS},"
    # cover-fit to 9:16 at 2x, then a zoompan push (sub-pixel smooth thanks to the 2x canvas)
    vf += f"scale={W*2}:{H*2}:force_original_aspect_ratio=increase:flags=lanczos,crop={W*2}:{H*2}:(iw-{W*2})*{s.get('cx',0.5)}:(ih-{H*2})*{s.get('cy',0.5)},"
    vf += (f"zoompan=z='{z0}+({z1}-{z0})*on/{max(1,n-1)}':x='(iw-iw/zoom)*{ax}':y='(ih-ih/zoom)*{ay}':d=1:s={W}x{H}:fps={FPS},"
           + (g + "," if g else "") + "setsar=1,format=yuv420p")
    amb = s.get("amb", cfg.get("amb_db", -10))
    has_a = probe_audio(src) and amb is not None and amb > -60
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", src]
    if has_a:
        af = f"[0:a]atrim=start={s['in']}:duration={d*speed},asetpts=PTS-STARTPTS,atempo={speed if speed>=0.5 else 0.5},aformat=sample_rates=48000:channel_layouts=stereo,volume={amb}dB,apad,atrim=duration={d}[a]"
    else:
        cmd += ["-f", "lavfi", "-t", str(d), "-i", "anullsrc=r=48000:cl=stereo"]
        af = f"[1:a]atrim=duration={d}[a]"
    cmd += ["-filter_complex", f"[0:v]{vf},trim=duration={d}[v];{af}", "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "14", "-r", str(FPS), "-c:a", "pcm_s16le", "-t", str(d), out]
    run(cmd); return out

shots = cfg["shots"]
segs = [segment(s, i) for i, s in enumerate(shots)]
durs = [s["title"]["dur"] if "title" in s else s["dur"] for s in shots]

inputs, fc = [], []
for i, p in enumerate(segs):
    inputs += ["-i", p]
    # one timebase for everything, or xfade refuses to join a concat output to a fresh input
    fc.append(f"[{i}:v]fps={FPS},settb=AVTB,setpts=PTS-STARTPTS[nv{i}]")
    fc.append(f"[{i}:a]asetpts=PTS-STARTPTS[na{i}]")
cur_v, cur_a, t = "nv0", "na0", durs[0]
starts = [0.0]
for i in range(1, len(segs)):
    xf = shots[i].get("xf", 0); kind = shots[i].get("xfk", "fade")
    if xf > 0:
        off = t - xf
        fc.append(f"[{cur_v}][nv{i}]xfade=transition={kind}:duration={xf}:offset={off:.4f},settb=AVTB[v{i}]")
        fc.append(f"[{cur_a}][na{i}]acrossfade=d={xf}:c1=tri:c2=tri[a{i}]")
        starts.append(off); t = off + durs[i]
    else:
        fc.append(f"[{cur_v}][{cur_a}][nv{i}][na{i}]concat=n=2:v=1:a=1[vc{i}][a{i}]")
        fc.append(f"[vc{i}]settb=AVTB[v{i}]")
        starts.append(t); t += durs[i]
    cur_v, cur_a = f"v{i}", f"a{i}"
total = t
print("timeline:", " ".join(f"{i}:{st:.2f}" for i, st in enumerate(starts)), f"total {total:.2f}s")

# text overlays
k = len(segs)
for o in cfg.get("overlays", []):
    inputs += ["-loop", "1", "-framerate", str(FPS), "-t", f"{total:.3f}", "-i", P(o["png"])]
    fd = o.get("fade", 0.2); a0, d = o["at"], o["dur"]
    fc.append(f"[{k}:v]format=rgba,fade=t=in:st={a0}:d={fd}:alpha=1,fade=t=out:st={a0+d-fd}:d={fd}:alpha=1[o{k}]")
    fc.append(f"[{cur_v}][o{k}]overlay=enable='between(t,{a0},{a0+d})':shortest=1[ov{k}]")
    cur_v = f"ov{k}"; k += 1

# music + sfx
m = cfg["music"]
inputs += ["-i", P(m["path"])]
fc.append(f"[{k}:a]atrim=start={m['start']}:duration={total:.3f},asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,"
          f"afade=t=in:d={m.get('fade_in',0.05)},afade=t=out:st={total-m.get('fade_out',2.0)-m.get('tail',0.3):.3f}:d={m.get('fade_out',2.0)}:curve=qsin,volume={m.get('db',0)}dB[mus]")
mix = ["[mus]", f"[{cur_a}]"]; k += 1
for j, x in enumerate(cfg.get("sfx", [])):
    inputs += ["-i", P(x["path"])]
    ms = int(x["at"] * 1000)
    # 12 ms fade at each end of every effect: a file that stops on a non-zero sample would otherwise click
    fc.append(f"[{k}:a]aformat=sample_rates=48000:channel_layouts=stereo,afade=t=in:d=0.004,areverse,afade=t=in:d=0.012,areverse,"
              f"volume={x.get('db',-6)}dB,adelay={ms}|{ms}[s{j}]")
    mix.append(f"[s{j}]"); k += 1
fc.append(f"{''.join(mix)}amix=inputs={len(mix)}:duration=first:normalize=0,alimiter=limit=0.93,atrim=duration={total:.3f}[aout]")
fc.append(f"[{cur_v}]setsar=1,format=yuv420p[vout]")

cmd = ["ffmpeg", "-y", "-v", "error", "-stats"] + inputs + ["-filter_complex", ";".join(fc), "-map", "[vout]", "-map", "[aout]",
       "-c:v", "libx264", "-preset", "slow", "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", str(FPS), "-g", "60",
       "-crf", str(cfg.get("crf", 18)), "-maxrate", "12M", "-bufsize", "24M",
       "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", "-t", f"{total:.3f}", OUT]
open(EDL + ".cmd", "w").write(" ".join(cmd))
r = subprocess.run(cmd)
if r.returncode: sys.exit(r.returncode)
print("wrote", OUT, f"{total:.2f}s")
