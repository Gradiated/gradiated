FROM ubuntu:24.04@sha256:224a1869083a311ef3f13648a154ba79832fbef6364d31493642ca03082da254 AS dependencies
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl git pigz \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.12.0@sha256:606e70c71c852d03f611b1e56a195d08648507018a7057fab82c4974c4eae105 /uv /usr/local/bin/uv
ENV UV_PYTHON_INSTALL_DIR=/opt/python UV_LINK_MODE=copy UV_NO_CACHE=1
RUN uv python install 3.12.13 \
    && mkdir /bundle && mv "$(uv python dir)"/cpython-3.12.13-linux-x86_64-gnu /bundle/python
ARG KEV_COMMIT=f0ae8fb9af5762254974dcdba8c82cbf48587b2e
RUN git clone --quiet --filter=blob:none https://github.com/jaredpalmer/kev /kev \
    && git -C /kev checkout --quiet --detach "$KEV_COMMIT"
# FLA and Triton sit outside upstream's lock; the cutoff pins what they resolve to.
RUN cd /kev \
    && uv export --frozen --extra serve --no-dev --no-emit-project -o /tmp/requirements.txt \
    && uv pip install --python /bundle/python/bin/python3 --break-system-packages \
       --require-hashes -r /tmp/requirements.txt \
    && uv pip install --python /bundle/python/bin/python3 --break-system-packages \
       --exclude-newer 2026-09-26T00:00:00Z flash-linear-attention==0.5.2 triton==3.8.0 \
    && uv pip install --python /bundle/python/bin/python3 --break-system-packages --no-deps "kev @ git+https://github.com/jaredpalmer/kev@$KEV_COMMIT" \
    && find /bundle/python -name __pycache__ -prune -exec rm -rf {} + \
    && rm -rf /kev /tmp/requirements.txt

FROM dependencies AS package
COPY --from=runtime-base /opt/gradiated/bin/runtime-launch /bundle/runtime-launch
COPY --from=runtime-base /opt/gradiated/bin/desmondd /bundle/desmondd
COPY bundles/package.sh /package.sh
COPY runtimes/kev/adapter.py /bundle/adapter.py
COPY --chmod=755 bundles/kev-9b/entrypoint /bundle/entrypoint
COPY images/gpu-base/base-id /bundle/base-id
RUN bash /package.sh

# The caller supplies the exact base digest as a named build context.
FROM runtime-base AS verify
# Compile Triton's actual helper to check bundled headers without a GPU or driver.
RUN --mount=from=package,source=/runtime.tar.gz,target=/tmp/runtime.tar.gz \
    mkdir /bundle && tar -xzf /tmp/runtime.tar.gz -C /bundle \
    && cd /bundle \
    && python/bin/python3 -c 'import adapter, fla, kev.checkpoint, kev.serve, torch, uvicorn; assert torch.version.cuda.startswith("12.8"), torch.version.cuda; assert adapter.installed_commit() == adapter.UPSTREAM_COMMIT' \
    && timeout 60 cc -O3 -fPIC -c \
        python/lib/python3.12/site-packages/triton/backends/nvidia/driver.c \
        -Ipython/include/python3.12 \
        -Ipython/lib/python3.12/site-packages/triton/backends/nvidia/include \
        -o /tmp/cuda_utils.o \
    && rm -rf /tmp/cuda_utils.o /bundle && touch /verified

FROM scratch AS artifact
COPY --from=verify /verified /verified
COPY --from=package /runtime.tar.gz /runtime.tar.gz
