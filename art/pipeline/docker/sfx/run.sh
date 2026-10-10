#!/bin/bash
# Run a command inside the sa3-sfx image on the Spark (copy to ~/sfx/run.sh).
#   ~/sfx/run.sh python /work/make_sfx.py --out /work/out ...
# Mounts ~/sfx -> /work and the HF cache; niced so the vLLM server on the same box keeps priority.
set -e
HF=$HOME/.cache/huggingface
exec docker run --rm --gpus all --ipc=host --ulimit memlock=-1 --ulimit stack=67108864 \
    -v "$HOME/sfx:/work" -v "$HF:/root/.cache/huggingface" \
    -e HF_TOKEN="$(cat $HF/token 2>/dev/null)" -e HF_HUB_OFFLINE=${HF_HUB_OFFLINE:-0} \
    -w /work ${IMG:-sa3-sfx} nice -n 10 "$@"
