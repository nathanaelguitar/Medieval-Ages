# Stable Audio 3 (small-sfx) on the Spark, on top of NVIDIA's aarch64 CUDA-13 torch build.
# The stable-audio-3 package pins torch==2.7.1, so it is installed --no-deps and the pure-Python
# deps are listed by hand. PyPI torchaudio wheels do not dlopen against NVIDIA's torch 2.10.0a0,
# and the model only needs torchaudio.transforms.Resample, so a tiny pure-torch shim stands in.
#   docker build -t sa3-sfx art/pipeline/docker/sfx      (on the Spark: ~/sfx/docker)
FROM nvcr.io/nvidia/pytorch:25.11-py3
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
COPY torchaudio_shim /tmp/torchaudio_shim
RUN pip install --no-cache-dir --no-deps /tmp/torchaudio_shim \
 && pip install --no-cache-dir "transformers>=5.8.0" "huggingface-hub>=1.7.1" einops-exts soundfile tqdm packaging \
 && pip install --no-cache-dir --no-deps "git+https://github.com/Stability-AI/stable-audio-3@main" \
 && python -c "import torchaudio, transformers, stable_audio_3; print('ok', transformers.__version__)"
ENV HF_HUB_DISABLE_PROGRESS_BARS=1 PYTORCH_ALLOC_CONF=expandable_segments:True
WORKDIR /work
