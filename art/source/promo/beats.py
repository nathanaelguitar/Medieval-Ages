#!/usr/bin/env python3
"""Rough beat map of a music file (numpy only): onset envelope, tempo by autocorrelation,
beat grid phase, and loudness per second. Usage: beats.py FILE [start_s] [dur_s]"""
import sys, subprocess, numpy as np
f = sys.argv[1]; st = float(sys.argv[2]) if len(sys.argv) > 2 else 0; du = float(sys.argv[3]) if len(sys.argv) > 3 else 90
sr = 22050
raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(st), "-t", str(du), "-i", f, "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                     capture_output=True).stdout
x = np.frombuffer(raw, np.float32)
hop, n = 512, 2048
frames = np.lib.stride_tricks.sliding_window_view(x, n)[::hop] * np.hanning(n)
S = np.log1p(np.abs(np.fft.rfft(frames, axis=1)))
flux = np.maximum(0, np.diff(S, axis=0)).sum(1); flux = np.r_[0, flux]
flux = (flux - flux.mean()) / (flux.std() + 1e-9)
fps = sr / hop
ac = np.correlate(flux, flux, "full")[len(flux) - 1:]
lo, hi = int(fps * 60 / 180), int(fps * 60 / 60)
lag = lo + np.argmax(ac[lo:hi]); bpm = 60 * fps / lag
# phase: best offset of a comb at this period
period = lag
scores = [flux[o::period][: int(len(flux) / period) - 1].sum() for o in range(period)]
ph = int(np.argmax(scores)) / fps
print(f"bpm {bpm:.2f} beat {60/bpm:.4f}s phase {ph+st:.3f}s")
rms = [float(np.sqrt(np.mean(x[i*sr:(i+1)*sr] ** 2))) for i in range(int(len(x) / sr))]
print("rms/s", " ".join(f"{int(st)+i}:{20*np.log10(r+1e-9):.0f}" for i, r in enumerate(rms)))
# strongest onsets
idx = np.argsort(flux)[::-1]; picks = []
for i in idx:
    if all(abs(i - j) > fps * 0.4 for j in picks): picks.append(i)
    if len(picks) >= 30: break
print("top onsets", " ".join(f"{st+i/fps:.2f}" for i in sorted(picks)))
