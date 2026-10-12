#!/usr/bin/env python3
"""Render the batch-2 promos end to end.

For each promo: write its EDL (make_edls_b2.py), assemble it (assemble_v.py), measure integrated
loudness and, if it is more than 0.4 LU off -14 LUFS, shift the music level by the difference
(stored in b2_music_db.json) and re-mix (segments are cached, so only the final pass re-runs).
Then a size-targeted 2-pass upload copy (<= 9.3 MB, H.264 High, AAC 128k), a 1 fps contact sheet,
and a report of the last 3 s: peak sample jump (clicks) and the final 300 ms level.

Usage: render_b2.py [names...]     (default: all ten)
Outputs: art/out/promo/batch2/medieval_ages_<name>.mp4, upload/<same>.mp4, sheets/<name>_1fps.jpg
"""
import json, os, re, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
OUTD = os.path.normpath(os.path.join(HERE, "../../out/promo/batch2"))
for d in ("", "upload", "sheets"): os.makedirs(os.path.join(OUTD, d), exist_ok=True)
PY = sys.executable
DB_FILE = os.path.join(HERE, "b2_music_db.json")
sys.path.insert(0, HERE)

def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode: print(" ".join(cmd)); print(r.stdout[-2000:], r.stderr[-3000:]); sys.exit(1)
    return r

def lufs(p):
    r = subprocess.run(["ffmpeg", "-nostats", "-i", p, "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True)
    s = r.stderr[r.stderr.rfind("Summary"):]
    return float(re.search(r"I:\s+(-?[\d.]+) LUFS", s).group(1)), float(re.search(r"Peak:\s+(-?[\d.]+) dBFS", s).group(1))

def dur(p): return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p]).stdout)

def tail_report(p):
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-sseof", "-3", "-i", p, "-ac", "1", "-ar", "48000", "-f", "f32le", "-"], capture_output=True).stdout
    x = np.frombuffer(raw, np.float32)
    jump = float(np.abs(np.diff(x)).max()); end = float(np.abs(x[-14400:]).max())
    return f"tail jump {jump:.3f}  last300ms peak {20*np.log10(end+1e-9):.0f} dBFS"

def upload(src, dst):
    d = dur(src); vb = int(min(8000, (9.3e6 * 8 / d - 128000) / 1000))
    log = os.path.join(OUTD, "upload", ".2pass_" + os.path.basename(dst))
    base = ["ffmpeg", "-y", "-v", "error", "-i", src, "-c:v", "libx264", "-preset", "veryslow", "-profile:v", "high", "-pix_fmt", "yuv420p",
            "-b:v", f"{vb}k", "-maxrate", f"{int(vb*1.5)}k", "-bufsize", f"{vb*2}k", "-passlogfile", log]
    run(["nice"] + base + ["-pass", "1", "-an", "-f", "mp4", "/dev/null"])
    run(["nice"] + base + ["-pass", "2", "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-movflags", "+faststart", dst])
    for f in os.listdir(os.path.join(OUTD, "upload")):
        if f.startswith(".2pass_"): os.remove(os.path.join(OUTD, "upload", f))
    return os.path.getsize(dst), vb

import make_edls_b2 as M
names = sys.argv[1:] or list(M.P)
for n in names:
    db = json.load(open(DB_FILE)) if os.path.exists(DB_FILE) else {}
    out = os.path.join(OUTD, f"medieval_ages_{n}.mp4")
    for attempt in range(3):
        M.MUSIC_DB = db; M.P[n]()
        run([PY, os.path.join(HERE, "assemble_v.py"), os.path.join(HERE, f"edl_b2_{n}.json"), out])
        I, pk = lufs(out)
        if abs(I + 14) <= 0.4: break
        db[n] = round(db.get(n, 0) + (-14 - I), 1); json.dump(db, open(DB_FILE, "w"), indent=1, sort_keys=True)
        print(f"  {n}: {I} LUFS -> music {db[n]:+.1f} dB, re-mixing")
    size, vb = upload(out, os.path.join(OUTD, "upload", os.path.basename(out)))
    run([PY, os.path.join(HERE, "sheets.py"), out, os.path.join(OUTD, "sheets", f"{n}_1fps.jpg")])
    print(f"{n}: {dur(out):.2f}s  {I:.1f} LUFS  peak {pk:.1f} dBFS  upload {size/1e6:.2f} MB @ {vb}k  {tail_report(out)}", flush=True)
