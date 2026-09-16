#!/usr/bin/env bash
set -euo pipefail
mkdir -p /bundle
# Stream only Python from the pinned image. Do not unpack CUDA or build caches.
source_image=vllm/vllm-openai@sha256:4f3c8bcf6328305b8cb6f61146dbfa125b0b04ae98eef3d091019ec30f564a9b
crane export --platform linux/amd64 "$source_image" - |
  tar -x -C /bundle --exclude=__pycache__ --exclude='*.pyc' \
    --transform='s|^usr/bin/python3.12$|python/bin/python3|' \
    --transform='s|^usr/lib/python3.12|python/lib/python3.12|' \
    --transform='s|^usr/include/python3.12|python/include/python3.12|' \
    --transform='s|^usr/include/x86_64-linux-gnu/python3.12/pyconfig.h$|python/include/python3.12/pyconfig-linux.h|' \
    --transform='s|^usr/local/lib/python3.12/dist-packages|python/lib/python3.12/site-packages|' \
    usr/bin/python3.12 usr/lib/python3.12 usr/local/lib/python3.12/dist-packages \
    usr/include/python3.12 usr/include/x86_64-linux-gnu/python3.12/pyconfig.h
# Replace Ubuntu's forwarding header with the bundled target architecture config.
mv /bundle/python/include/python3.12/{pyconfig-linux.h,pyconfig.h}
