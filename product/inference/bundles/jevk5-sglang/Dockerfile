# posthog/jevk5 on SGLang 0.5.21: linden-1's pinned SGLang environment, without its B300 attention kernels.
FROM ubuntu:24.04@sha256:224a1869083a311ef3f13648a154ba79832fbef6364d31493642ca03082da254 AS dependencies
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates pigz \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.12.0@sha256:606e70c71c852d03f611b1e56a195d08648507018a7057fab82c4974c4eae105 /uv /usr/local/bin/uv
ENV UV_PYTHON_INSTALL_DIR=/opt/python UV_LINK_MODE=copy UV_NO_CACHE=1 \
    CUDA_VISIBLE_DEVICES="" NVIDIA_VISIBLE_DEVICES=""
RUN uv python install 3.12.13 \
    && mkdir /bundle && mv "$(uv python dir)"/cpython-3.12.13-linux-x86_64-gnu /bundle/python
COPY bundles/linden-1-sglang/requirements.txt /tmp/requirements.txt
RUN uv pip install --python /bundle/python/bin/python3 --break-system-packages \
       --no-deps --require-hashes -r /tmp/requirements.txt \
    && cd /bundle/python/lib/python3.12/site-packages/nvidia/cu13 \
    && ln -sfn lib lib64 \
    && ln -sfn libcudart.so.13 lib/libcudart.so \
    && ln -sfn libnvrtc.so.13 lib/libnvrtc.so \
    && uv pip check --python /bundle/python/bin/python3
COPY bundles/linden-1-sglang/jit-cache-requirements.txt /tmp/jit-cache-requirements.txt
RUN uv pip install --python /bundle/python/bin/python3 --break-system-packages \
       --no-deps --require-hashes -r /tmp/jit-cache-requirements.txt

FROM dependencies AS package
COPY bundles/package.sh /package.sh
COPY runtimes/jevk5/service.py runtimes/jevk5/jevk5_prompt.py runtimes/jevk5/verify-build.py \
     runtimes/jevk5/LICENSE.jevk5 runtimes/jevk5/NOTICE.jevk5 /bundle/
COPY runtimes/posthog/posthog_common.py /bundle/posthog_common.py
COPY runtimes/kev/adapter.py /bundle/kev_http.py
COPY --chmod=755 bundles/jevk5-sglang/entrypoint /bundle/entrypoint
COPY images/gpu-base/base-id /bundle/base-id
RUN bash /package.sh

FROM runtime-base AS verify
RUN --mount=from=package,source=/runtime.tar.gz,target=/tmp/runtime.tar.gz \
    mkdir /bundle && tar -xzf /tmp/runtime.tar.gz -C /bundle \
    && cd /bundle && python/bin/python3 verify-build.py \
    && rm -rf /bundle && touch /verified

FROM scratch AS artifact
COPY --from=verify /verified /verified
COPY --from=package /runtime.tar.gz /runtime.tar.gz
