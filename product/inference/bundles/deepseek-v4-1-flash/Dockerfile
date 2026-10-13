FROM ubuntu:24.04@sha256:224a1869083a311ef3f13648a154ba79832fbef6364d31493642ca03082da254 AS dependencies
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl pigz \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSLo /tmp/crane.tar.gz https://github.com/google/go-containerregistry/releases/download/v0.20.3/go-containerregistry_Linux_x86_64.tar.gz \
    && echo '36c67a932f489b3f2724b64af90b599a8ef2aa7b004872597373c0ad694dc059  /tmp/crane.tar.gz' | sha256sum -c - \
    && tar -xzf /tmp/crane.tar.gz -C /usr/local/bin crane && rm /tmp/crane.tar.gz
COPY bundles/deepseek-v4-1-flash/extract-dependencies.sh /extract-dependencies.sh
RUN bash /extract-dependencies.sh
COPY --from=ghcr.io/astral-sh/uv:0.12.0@sha256:606e70c71c852d03f611b1e56a195d08648507018a7057fab82c4974c4eae105 /uv /usr/local/bin/uv
COPY bundles/deepseek-v4-1-flash/cuda-requirements.txt /tmp/cuda-requirements.txt
# Keep the compiler and its headers together, independent of upstream Python packages.
RUN uv python install 3.12.13 \
    && uv pip install --python "$(uv python find 3.12.13)" --target /bundle/cuda \
       --require-hashes -r /tmp/cuda-requirements.txt \
    && cd /bundle/cuda/nvidia/cu13 && ln -sfn lib lib64 \
    && ln -sfn libcudart.so.13 lib/libcudart.so

FROM dependencies AS package
COPY bundles/package.sh /package.sh
COPY images/deepseek-v4-1-flash/start.sh /bundle/start.sh
COPY --chmod=755 bundles/deepseek-v4-1-flash/entrypoint /bundle/entrypoint
COPY --chmod=755 bundles/deepseek-v4-1-flash/vllm /bundle/vllm
COPY images/gpu-base/base-id /bundle/base-id
RUN bash /package.sh

# The caller supplies the exact base digest as a named build context.
FROM runtime-base AS verify
COPY bundles/deepseek-v4-1-flash/cuda-compile.cu /tmp/cuda-compile.cu
COPY bundles/deepseek-v4-1-flash/checkpoint-loader.py /tmp/checkpoint-loader.py
ENV PYTHONHOME=/bundle/python PYTHONPATH=/bundle/python/lib/python3.12/site-packages
# Compile Triton's actual helper to check bundled headers without a GPU or driver.
RUN --mount=from=package,source=/runtime.tar.gz,target=/tmp/runtime.tar.gz \
    mkdir /bundle && tar -xzf /tmp/runtime.tar.gz -C /bundle \
    && /bundle/python/bin/python3 -c 'import bz2, ctypes, lzma, readline, sqlite3, ssl, uuid, xml.parsers.expat' \
    && /bundle/python/bin/python3 -c 'import site; site.addsitedir("/bundle/python/lib/python3.12/site-packages"); import torch, vllm, cutlass.cute; print(torch.__version__, vllm.__version__)' \
    && /bundle/python/bin/python3 -c 'import vllm.entrypoints.cli.main' \
    && /bundle/python/bin/python3 /tmp/checkpoint-loader.py \
    && timeout 60 /bundle/cuda/nvidia/cu13/bin/nvcc -arch=sm_103 \
        -I/bundle/cuda/nvidia/cu13/include/cccl \
        --cubin /tmp/cuda-compile.cu -o /tmp/cuda-compile.cubin \
    && timeout 60 cc -O3 -fPIC -c \
        /bundle/python/lib/python3.12/site-packages/triton/backends/nvidia/driver.c \
        -I/bundle/python/include/python3.12 \
        -I/bundle/python/lib/python3.12/site-packages/triton/backends/nvidia/include \
        -o /tmp/cuda_utils.o \
    && rm /tmp/cuda_utils.o \
    && rm -rf /bundle && touch /verified

FROM scratch AS artifact
COPY --from=verify /verified /verified
COPY --from=package /runtime.tar.gz /runtime.tar.gz
