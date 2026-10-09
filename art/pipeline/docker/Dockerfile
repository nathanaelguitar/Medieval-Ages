FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends blender assimp-utils python3-pil python3-numpy libegl1 libgl1 && rm -rf /var/lib/apt/lists/*
ENV HOME=/tmp
WORKDIR /work
