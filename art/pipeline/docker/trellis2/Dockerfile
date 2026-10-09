# TRELLIS.2 (MIT) inference image for the DGX Spark (aarch64, GB10 / sm_121, CUDA 13.0).
#
# Built on NVIDIA's PyTorch container because it already ships torch 2.10 + flash-attn 2.7.4 +
# triton 3.5 compiled for sm_121; building flash-attn from source on aarch64 takes hours. The
# TRELLIS.2 custom ops (o-voxel, CuMesh, FlexGEMM, nvdiffrast, nvdiffrec) are compiled here for
# compute capability 12.1 only.
#
# Build context is ~/trellis2 on the Spark, which holds the clones (see trellis_body.py docstring):
#   ~/trellis2/TRELLIS.2            git clone -b main --recursive https://github.com/microsoft/TRELLIS.2
#   ~/trellis2/ext/nvdiffrast       -b v0.4.0 https://github.com/NVlabs/nvdiffrast
#   ~/trellis2/ext/nvdiffrec        -b renderutils https://github.com/JeffreyXiang/nvdiffrec
#   ~/trellis2/ext/CuMesh           --recursive https://github.com/JeffreyXiang/CuMesh
#   ~/trellis2/ext/FlexGEMM         --recursive https://github.com/JeffreyXiang/FlexGEMM
#   ~/trellis2/ext/utils3d          https://github.com/EasternJournalist/utils3d @ 9a4eb15e
#
#   cp art/pipeline/docker/trellis2/Dockerfile ~/trellis2/Dockerfile
#   cd ~/trellis2 && DOCKER_BUILDKIT=1 docker build -t trellis2 .
#
# Run (weights cached in the host's ~/.cache/huggingface; the HF token there must have access to
# the gated DINOv3 encoder):
#   docker run --rm --gpus all --ipc=host -v ~/.cache/huggingface:/root/.cache/huggingface \
#       -v ~/trellis2:/trellis2 -v ~/hunyuan3d/inputs:/inputs -w /trellis2/TRELLIS.2 trellis2 \
#       nice -n 10 python /trellis2/trellis_body.py ...
FROM nvcr.io/nvidia/pytorch:25.11-py3
ENV DEBIAN_FRONTEND=noninteractive
ENV TORCH_CUDA_ARCH_LIST="12.1"
ENV MAX_JOBS=12
ENV ATTN_BACKEND=flash_attn
ENV SPARSE_CONV_BACKEND=flex_gemm
ENV PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

RUN apt-get update && apt-get install -y --no-install-recommends libjpeg-dev libgl1 libglib2.0-0 libegl1 \
    && rm -rf /var/lib/apt/lists/*

# basic python deps (setup.sh --basic, minus gradio/tensorboard which are demo/training only)
RUN pip install --no-cache-dir imageio imageio-ffmpeg tqdm easydict opencv-python-headless ninja trimesh \
    "transformers>=4.56" pandas lpips zstandard kornia timm safetensors huggingface_hub "rembg[cpu]" \
    xatlas pymeshlab onnxruntime

# utils3d pulls in moderngl/glcontext (GL rasteriser, unused here) whose build fails on aarch64:
# install it without deps and add the two it actually needs
COPY ext/utils3d /src/utils3d
RUN pip install --no-cache-dir --no-build-isolation --no-deps /src/utils3d && pip install --no-cache-dir plyfile scipy

# compiled extensions; each is its own layer so a failed one can be retried without redoing the rest.
# Licences: o-voxel, CuMesh, FlexGEMM, TRELLIS.2 are MIT. nvdiffrast and nvdiffrec are NVIDIA
# "non-commercial" source licences: they are installed only because trellis2's texturing pipeline
# and renderers import them; trellis_body.py's production path (generation pipeline + its own numpy
# UV rasteriser + CuMesh post-processing) never calls either.
COPY ext/nvdiffrast /src/nvdiffrast
RUN pip install --no-cache-dir --no-build-isolation /src/nvdiffrast
COPY ext/nvdiffrec /src/nvdiffrec
RUN pip install --no-cache-dir --no-build-isolation /src/nvdiffrec
COPY ext/FlexGEMM /src/FlexGEMM
RUN pip install --no-cache-dir --no-build-isolation /src/FlexGEMM
COPY ext/CuMesh /src/CuMesh
RUN pip install --no-cache-dir --no-build-isolation /src/CuMesh
COPY TRELLIS.2/o-voxel /src/o-voxel
RUN pip install --no-cache-dir --no-build-isolation /src/o-voxel

# TRELLIS.2's DINOv3 feature extractor walks the model's internals (`.layer`, `.rope_embeddings`),
# which transformers 5.x renamed; the NGC image ships 5.19, so pin the 4.57 series it was written for
RUN pip install --no-cache-dir "transformers>=4.56,<4.58"

WORKDIR /trellis2/TRELLIS.2
ENV PYTHONPATH=/trellis2/TRELLIS.2
