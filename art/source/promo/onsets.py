#!/usr/bin/env python3
"""Print onset strength per half-beat around a window, to pick cut points. Usage: onsets.py FILE start dur [bpm]"""
import sys, subprocess, numpy as np
f, st, du = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]); bpm = float(sys.argv[4]) if len(sys.argv) > 4 else 112.35
sr, hop, n = 22050, 256, 2048
x = np.frombuffer(subprocess.run(["ffmpeg","-v","error","-ss",str(st),"-t",str(du),"-i",f,"-ac","1","-ar",str(sr),"-f","f32le","-"],capture_output=True).stdout, np.float32)
fr = np.lib.stride_tricks.sliding_window_view(x, n)[::hop] * np.hanning(n)
S = np.log1p(np.abs(np.fft.rfft(fr, axis=1))); lowS = S[:, :60]
flux = np.r_[0, np.maximum(0, np.diff(S, axis=0)).sum(1)]; low = np.r_[0, np.maximum(0, np.diff(lowS, axis=0)).sum(1)]
flux /= flux.max(); low /= low.max(); fps = sr / hop; P = 60 / bpm * fps
best = max(range(int(P)), key=lambda o: sum(flux[int(o + k * P)] for k in range(int((len(flux) - o) / P))))
print(f"local phase {st + best / fps:.3f}s  beat {60/bpm:.4f}s")
k = 0
while best + k * P < len(flux) - 2:
    i = int(best + k * P); w = slice(max(0, i - 3), i + 4)
    print(f"{st + i / fps:7.3f}  beat {k:3d}  all {flux[w].max():.2f} {'#' * int(flux[w].max() * 30):30s} low {low[w].max():.2f}")
    k += 1
