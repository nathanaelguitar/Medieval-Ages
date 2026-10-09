#!/bin/bash
# Run a command inside the trellis2 image on the Spark (copy to ~/trellis2/run.sh).
#   ~/trellis2/run.sh python /trellis2/trellis_body.py shape ...
# Mounts: ~/trellis2 -> /trellis2 (scripts, work dir, model config), the HF cache at both its
# host path (the model dir's ckpts symlink points there) and /root/.cache/huggingface,
# ~/hunyuan3d/inputs -> /inputs. Runs niced so the vLLM server on the same box keeps priority.
set -e
HF=$HOME/.cache/huggingface
exec docker run --rm --gpus all --ipc=host --ulimit memlock=-1 --ulimit stack=67108864 \
    -v "$HOME/trellis2:/trellis2" -v "$HF:$HF" -v "$HF:/root/.cache/huggingface" \
    -v "$HOME/hunyuan3d/inputs:/inputs" -e HF_HUB_OFFLINE=${HF_HUB_OFFLINE:-0} \
    -e PYTORCH_ALLOC_CONF=expandable_segments:True -w /trellis2/TRELLIS.2 trellis2 nice -n 10 "$@"
