FROM lmsysorg/sglang@sha256:4a098ad7414702a2271296ac148854448d10710ec3554ac93b57ef194999305a AS dependencies
RUN /opt/sglang/bin/python3 /opt/k31-image/verify_image.py
RUN apt-get update && apt-get install -y --no-install-recommends pigz patch \
    && rm -rf /var/lib/apt/lists/*

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
COPY bundles/glm-5-3-flash-sglang/patches/smg_refused_upload.patch bundles/glm-5-3-flash-sglang/patches/smg_build_marker.patch /tmp/smg-patches/patches/
COPY bundles/glm-5-3-flash-sglang/smg-patches.json bundles/glm-5-3-flash-sglang/apply-patches.py /tmp/smg-patches/
RUN uv pip install --python /opt/sglang/bin/python3 --no-deps --require-hashes -r /tmp/smg-build-requirements.txt \
    && mkdir /src-smg && tar -xzf /tmp/smg.tar.gz -C /src-smg --strip-components=1 \
    && /opt/sglang/bin/python3 /tmp/smg-patches/apply-patches.py /src-smg /tmp/smg-patches --manifest smg-patches.json
RUN --mount=type=cache,id=kimi-k31-cargo-registry-v1,target=/usr/local/cargo/registry,sharing=locked \
    --mount=type=cache,id=kimi-k31-cargo-git-v1,target=/usr/local/cargo/git,sharing=locked \
    --mount=type=cache,id=kimi-k31-smg-target-v1,target=/src-smg/target,sharing=locked \
    cd /src-smg && cargo test --locked --release -p smg --lib middleware::concurrency::tests \
    && cd bindings/python \
    && /opt/sglang/bin/maturin build --locked --release --interpreter /opt/sglang/bin/python3 --compatibility linux --out /smg-wheels \
    && uv pip install --python /opt/sglang/bin/python3 --reinstall --no-deps /smg-wheels/smg-*.whl \
    && uv pip uninstall --python /opt/sglang/bin/python3 maturin

FROM smg-compiler AS package
COPY bundles/kimi-k31-pro/portable.py /portable.py
COPY bundles/kimi-k31-pro/draft-manifest.json /draft-manifest.json
COPY runtimes/kimi-k31/draft.py /draft.py
COPY runtimes/kimi-k31/overlay_patches.py /overlay_patches.py
COPY bundles/kimi-k31-pro/patches /k31-patches
COPY bundles/kimi-k31-pro/manifest-pins.json /manifest-pins.json
RUN /opt/sglang/bin/python3 /portable.py
COPY --chmod=755 bundles/kimi-k31-pro/entrypoint /bundle/entrypoint
COPY runtimes/glm/warmup-supervisor.py /bundle/warmup-base.py
COPY runtimes/kimi-k31/*.py /bundle/kimi-k31/
COPY images/gpu-base/base-id /bundle/base-id
COPY bundles/package.sh /package.sh
RUN bash /package.sh

FROM runtime-base AS verify
ENV CUDA_VISIBLE_DEVICES="" NVIDIA_VISIBLE_DEVICES="" OMP_NUM_THREADS=4 \
    KIMI_INSTALLED_SOURCE=/bundle/python/lib/python3.12/site-packages \
    KIMI_ORIGINAL_SOURCE=/k31-original KIMI_PATCH_DIRECTORY=/k31-patches
COPY --from=dependencies /sgl-workspace/sglang/python /k31-original
COPY bundles/kimi-k31-pro/tests /k31-test
COPY bundles/kimi-k31-pro/Dockerfile /k31-test/Dockerfile
COPY bundles/kimi-k31-pro/patches /k31-patches
COPY bundles/kimi-k31-pro/manifest-pins.json /k31-test/manifest-pins.json
COPY runtimes/kimi-k31/overlay_patches.py /k31-test/apply-kimi-patches.py
COPY --from=dependencies /usr/bin/patch /usr/bin/patch
RUN --mount=from=package,source=/runtime.tar.gz,target=/tmp/runtime.tar.gz \
    mkdir /bundle && tar -xzf /tmp/runtime.tar.gz -C /bundle \
    && export LD_LIBRARY_PATH=/bundle/python/lib:/bundle/cuda/lib64:/bundle/python/lib/python3.12/site-packages/torch/lib \
       CUDA_HOME=/bundle/cuda \
    && /bundle/python/bin/python3 /bundle/kimi-k31/verify-build.py /bundle \
    && /bundle/python/bin/python3 -m unittest discover -s /bundle/kimi-k31 -p 'test_*.py' \
    && /bundle/python/bin/python3 -m unittest discover -s /k31-test -p 'test_*.py' \
    && rm -rf /bundle && touch /verified

FROM scratch AS artifact
COPY --from=verify /verified /verified
COPY --from=package /runtime.tar.gz /runtime.tar.gz
