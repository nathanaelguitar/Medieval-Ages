#!/usr/bin/env python3
"""Pack picked game sounds into a JS bank the web game can decode into Web Audio.

    python3 art/pipeline/pack_audio.py sfx   art/out/sfx/game/sfx_manifest.json
    python3 art/pipeline/pack_audio.py voice art/out/voice/game/voice_manifest.json

The app's WKWebView blocks fetch() under file://, so sounds ship like the music: base64 inside a
script (ios/WebGame/audio/<bank>_bank.js) that sets window.PE_AUDIO[<bank>]. The game decodes
every clip once with AudioContext.decodeAudioData and plays buffers directly, so there is no
per-play latency. WAV is used rather than AAC because AAC's encoder priming would offset the hit
from the impact frame.

Manifest shapes accepted (as written by make_sfx.py / make_voices.py):
  sfx:   {"<sound>": {"files": ["a.wav", ...], "volume": 0.8}, ...}
         or {"<sound>": ["a.wav", ...]}
  voice: {"<voice>": {"<set>": {"files": [...], "volume": 0.9}} or {"<set>": [...]}, "lines": ...}
The bank is flattened to {"<sound>": {"vol": v, "clips": [b64, ...]}} with voice sounds named
"<voice>_<set>" (e.g. "soldier_attack").
"""
import base64
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEST = os.path.join(ROOT, "ios", "WebGame", "audio")


def fname(f):
    """A file entry is a path string or a {"file": path, ...} record."""
    return f["file"] if isinstance(f, dict) else f


def entries(node):
    """(files, volume) from either a list or a {files, volume} dict."""
    if isinstance(node, list):
        return [fname(f) for f in node], 1.0
    if isinstance(node, dict) and "files" in node:
        return [fname(f) for f in node["files"]], float(node.get("volume", 1.0))
    return None, None


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ("sfx", "voice"):
        sys.exit(__doc__)
    bank, man_path = sys.argv[1], os.path.abspath(sys.argv[2])
    base = os.path.dirname(man_path)
    man = json.load(open(man_path))
    for nest in ("sounds", "voices"):          # make_sfx.py / make_voices.py nest their sets
        if isinstance(man.get(nest), dict):
            man = man[nest]
            break
    flat = {}
    for name, node in man.items():
        if name in ("lines", "_meta", "meta"):
            continue
        files, vol = entries(node)
        if files is not None:
            flat[name] = (files, vol)
        elif isinstance(node, dict):           # voice: voice -> set -> files
            for set_name, sub in node.items():
                f2, v2 = entries(sub)
                if f2 is not None:
                    flat[f"{name}_{set_name}"] = (f2, v2)
    out, total = {}, 0
    for name, (files, vol) in sorted(flat.items()):
        clips = []
        for f in files:
            p = f if os.path.isabs(f) else os.path.join(base, os.path.basename(f))
            data = open(p, "rb").read()
            total += len(data)
            clips.append(base64.b64encode(data).decode())
        out[name] = {"vol": round(vol, 3), "clips": clips}
    os.makedirs(DEST, exist_ok=True)
    path = os.path.join(DEST, f"{bank}_bank.js")
    with open(path, "w") as fh:
        fh.write(f"/* {bank} sounds packed by art/pipeline/pack_audio.py from {os.path.relpath(man_path, ROOT)} */\n")
        fh.write("window.PE_AUDIO=window.PE_AUDIO||{};\n")
        fh.write(f"window.PE_AUDIO[{json.dumps(bank)}]={json.dumps(out)};\n")
    print(f"{path}: {len(out)} sounds, {sum(len(v['clips']) for v in out.values())} clips, "
          f"{total / 1024:.0f} KB of audio")


if __name__ == "__main__":
    main()
