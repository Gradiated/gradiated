# Same SGLang, SMG and FlashInfer build as the GLM SGLang bundle; only the runtime layer differs.
FROM ubuntu:24.04@sha256:224a1869083a311ef3f13648a154ba79832fbef6364d31493642ca03082da254 AS dependencies
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl pigz patch \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.12.0@sha256:606e70c71c852d03f611b1e56a195d08648507018a7057fab82c4974c4eae105 /uv /usr/local/bin/uv
ENV UV_PYTHON_INSTALL_DIR=/opt/python UV_LINK_MODE=copy UV_NO_CACHE=1 \
    CUDA_VISIBLE_DEVICES="" NVIDIA_VISIBLE_DEVICES="" OMP_NUM_THREADS=4 \
    SGLANG_BUILD_RUST_EXTS=none SETUPTOOLS_SCM_PRETEND_VERSION_FOR_SGLANG=0.0.0.dev0+gf171859219b54
RUN uv python install 3.12.13 \
    && mkdir /bundle && mv "$(uv python dir)"/cpython-3.12.13-linux-x86_64-gnu /bundle/python
COPY bundles/glm-5-3-flash-sglang/requirements.txt /tmp/requirements.txt
RUN uv pip install --python /bundle/python/bin/python3 --break-system-packages \
       --no-deps --require-hashes -r /tmp/requirements.txt
ADD --checksum=sha256:659010efc001d8abfb64eb774e60c44338ebe15a8daec2a9c03ca73a323718a8 \
    https://codeload.github.com/sgl-project/sglang/tar.gz/f171859219b54e1dad45dda60028034490836974 /tmp/sglang.tar.gz
RUN mkdir /src && tar -xzf /tmp/sglang.tar.gz -C /src --strip-components=1 \
    && uv pip install --python /bundle/python/bin/python3 --break-system-packages \
       --no-deps --no-build-isolation /src/python \
    && rm -rf /src /tmp/sglang.tar.gz
COPY bundles/glm-5-3-flash-sglang/patches /tmp/sglang-patches/patches
COPY bundles/glm-5-3-flash-sglang/patches.json bundles/glm-5-3-flash-sglang/apply-patches.py /tmp/sglang-patches/
RUN /bundle/python/bin/python3 /tmp/sglang-patches/apply-patches.py /bundle/python/lib/python3.12/site-packages /tmp/sglang-patches \
    && cd /bundle/python/lib/python3.12/site-packages/nvidia/cu13 \
    && ln -sfn lib lib64 \
    && ln -sfn libcudart.so.13 lib/libcudart.so \
    && ln -sfn libnvrtc.so.13 lib/libnvrtc.so \
    && uv pip check --python /bundle/python/bin/python3

COPY bundles/glm-5-3-flash-sglang/artifacts.json bundles/glm-5-3-flash-sglang/fetch-artifacts.py /tmp/flashinfer-seed/
RUN /bundle/python/bin/python3 /tmp/flashinfer-seed/fetch-artifacts.py --output /bundle/flashinfer-artifacts \
    && cp /tmp/flashinfer-seed/artifacts.json /bundle/artifacts.json

FROM rust:1.98.0-bookworm@sha256:82150a52ec202c1b14d7817e14516c392bb7f5cfebd88f1ed531cb37ebd39922 AS smg-rust

FROM dependencies AS smg-compiler
RUN apt-get update && apt-get install -y --no-install-recommends build-essential pkg-config libssl-dev protobuf-compiler libprotobuf-dev \
    && rm -rf /var/lib/apt/lists/*
COPY --from=smg-rust /usr/local/cargo /usr/local/cargo
COPY --from=smg-rust /usr/local/rustup /usr/local/rustup
ENV CARGO_HOME=/usr/local/cargo RUSTUP_HOME=/usr/local/rustup RUSTUP_TOOLCHAIN=1.98.0 \
    PATH=/usr/local/cargo/bin:$PATH CARGO_BUILD_JOBS=2
ADD --checksum=sha256:884b9e21d0efaa403fd307c413c7dd82306b1f5d72536314e2d115b805fe8c58 \
    https://codeload.github.com/smg-project/smg/tar.gz/91b3e0c440f9ab7971aa3ba48b049d951bd963de /tmp/smg.tar.gz
COPY bundles/glm-5-3-flash-sglang/smg-build-requirements.txt /tmp/smg-build-requirements.txt
COPY bundles/glm-5-3-flash-sglang/smg-patches.json /tmp/sglang-patches/
COPY bundles/glm-5-3-flash-sglang/smg-lora /tmp/smg-lora
RUN uv pip install --python /bundle/python/bin/python3 --break-system-packages \
      --no-deps --require-hashes -r /tmp/smg-build-requirements.txt \
    && mkdir /src-smg && tar -xzf /tmp/smg.tar.gz -C /src-smg --strip-components=1 \
    && /bundle/python/bin/python3 /tmp/sglang-patches/apply-patches.py /src-smg /tmp/sglang-patches --manifest smg-patches.json \
    && /bundle/python/bin/python3 /tmp/sglang-patches/apply-patches.py /src-smg /tmp/smg-lora --manifest smg-patches.json
RUN --mount=type=cache,target=/usr/local/cargo/registry \
    --mount=type=cache,target=/usr/local/cargo/git \
    --mount=type=cache,target=/src-smg/target \
    cd /src-smg && cargo test --locked --release -p smg --lib middleware::concurrency::tests \
    && cargo test --locked --release -p smg --lib worker::registry::tests::unknown_models \
    && cd bindings/python \
    && /bundle/python/bin/maturin build --locked --release --interpreter /bundle/python/bin/python3 --compatibility linux --out /smg-wheels \
    && uv pip install --python /bundle/python/bin/python3 --break-system-packages --reinstall --no-deps /smg-wheels/smg-*.whl \
    && uv pip uninstall --python /bundle/python/bin/python3 --break-system-packages maturin \
    && uv pip check --python /bundle/python/bin/python3 \
    && cp /tmp/sglang-patches/smg-patches.json /bundle/smg-patches.json \
    && cp /tmp/smg-lora/smg-patches.json /bundle/smg-lora-patches.json

FROM smg-compiler AS package
COPY bundles/glm-5-3-flash-sglang/jit-cache-requirements.txt /tmp/jit-cache-requirements.txt
# The shim declares a provider for every CUDA architecture; only B300's is installed, so
# `uv pip check` (already run on the full environment above) is not repeated here.
RUN uv pip install --python /bundle/python/bin/python3 --break-system-packages \
      --no-deps --require-hashes -r /tmp/jit-cache-requirements.txt
COPY bundles/package.sh /package.sh
COPY --chmod=755 bundles/deepseek-v4-1-flash-sglang/entrypoint /bundle/entrypoint
COPY bundles/glm-5-3-flash-sglang/patches.json /bundle/
COPY runtimes/glm/warmup-supervisor.py /bundle/warmup-base.py
# The DeepSeek runtime reuses the GLM SGLang supervisor, service and FlashInfer seeding with its own config.
COPY runtimes/glm-sglang/launch.py runtimes/glm-sglang/service.py runtimes/glm-sglang/artifact-cache.py runtimes/glm-sglang/autotune-seed.py /bundle/deepseek-sglang/
COPY runtimes/deepseek-sglang/*.py /bundle/deepseek-sglang/
COPY runtimes/deepseek-sglang/autotune /bundle/deepseek-sglang/autotune
COPY lora/*.py /bundle/lora/
COPY images/gpu-base/base-id /bundle/base-id
RUN bash /package.sh

FROM runtime-base AS verify
ENV CUDA_VISIBLE_DEVICES="" NVIDIA_VISIBLE_DEVICES="" OMP_NUM_THREADS=4
RUN --mount=from=package,source=/runtime.tar.gz,target=/tmp/runtime.tar.gz \
    mkdir /bundle && tar -xzf /tmp/runtime.tar.gz -C /bundle \
    && CUDA_VISIBLE_DEVICES="" NVIDIA_VISIBLE_DEVICES="" \
       /bundle/python/bin/python3 /bundle/deepseek-sglang/verify-build.py /bundle \
    && GRADIATED_REQUIRE_SGLANG=1 /bundle/python/bin/python3 -m unittest discover -s /bundle/deepseek-sglang -p 'test_*.py' \
    && /bundle/python/bin/python3 -m unittest discover -s /bundle/lora -p 'test_*.py' \
    && rm -rf /bundle && touch /verified

FROM scratch AS artifact
COPY --from=verify /verified /verified
COPY --from=package /runtime.tar.gz /runtime.tar.gz
