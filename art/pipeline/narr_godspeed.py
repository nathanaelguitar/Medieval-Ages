"""Grave ending, pitched down; first half rephrased so "enemy's Town Center" runs together."""
import sys, numpy as np, soundfile as sf, librosa
from pathlib import Path
sys.path.insert(0, str(Path.home() / "voice"))
from make_voices import gen_take, trim_fade_norm, Asr, match_score, SR_GEN, log
from chatterbox.tts import ChatterboxTTS
out = Path("/tmp/gs3"); out.mkdir(exist_ok=True)
refs = Path.home() / "voice/out_narr/refs"
model = ChatterboxTTS.from_pretrained(device="cuda"); asr = Asr()
model.prepare_conditionals(str(refs / "narrator_seed.wav"), exaggeration=0.5)
t = "Your goal is to destroy the enemy's Town Center, far to the east. The enemy wakes now."
calm = []
for s in range(8):
    w = gen_take(model, t, 0.5, 0.5, 0.7, 400 + s); tx = asr(w, SR_GEN); m = match_score(tx, t, t)
    wt, _ = trim_fade_norm(w, SR_GEN)
    # a break before "town" shows up as a comma in the transcript; also measure the silence there
    low = tx.lower(); smooth = "enemy's town" in low or "enemies town" in low
    calm.append((smooth, m, -len(wt), wt)); log("calm", s, smooth, f"{m:.2f}", f"{len(wt)/SR_GEN:.2f}s", tx)
calm.sort(key=lambda x: (not x[0], -x[1], -x[2]))
c = calm[0][3]
model.prepare_conditionals(str(refs / "narrator_seed.wav"), exaggeration=0.8)
g = "Godspeed... my liege."
B = None
for s in range(6):
    w = gen_take(model, g, 0.8, 0.25, 0.75, 700 + s); tx = asr(w, SR_GEN); m = match_score(tx, g, g)
    wt, _ = trim_fade_norm(w, SR_GEN); log("grave", s, f"{m:.2f}", f"{len(wt)/SR_GEN:.2f}s", tx)
    if m >= 0.95 and (B is None or len(wt) > len(B)): B = wt
pause = np.zeros(int(0.45 * SR_GEN), np.float32)
for st in (0,):
    e = B if st == 0 else librosa.effects.pitch_shift(B, sr=SR_GEN, n_steps=st)
    full = np.concatenate([c, pause, e]); full = full / np.abs(full).max() * 0.708
    sf.write(out / f"grave_{-st}st.wav", full.astype(np.float32), SR_GEN); log("wrote", st)
