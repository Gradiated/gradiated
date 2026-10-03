FROM vllm/vllm-openai@sha256:0674a3ea3c971706cea310bca71daadff68ea1717c758d2f54affa5def001b86 AS upstream

FROM ubuntu:24.04@sha256:224a1869083a311ef3f13648a154ba79832fbef6364d31493642ca03082da254 AS dependencies
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl pigz patch \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.12.0@sha256:606e70c71c852d03f611b1e56a195d08648507018a7057fab82c4974c4eae105 /uv /usr/local/bin/uv
ENV UV_PYTHON_INSTALL_DIR=/opt/python UV_LINK_MODE=copy UV_NO_CACHE=1
RUN uv python install 3.12.13 \
    && mkdir /bundle && mv "$(uv python dir)"/cpython-3.12.13-linux-x86_64-gnu /bundle/python
COPY bundles/glm-5-3-flash/requirements.txt /tmp/requirements.txt
RUN uv pip install --python /bundle/python/bin/python3 --break-system-packages \
       --require-hashes -r /tmp/requirements.txt
COPY --from=upstream /usr/local/lib/python3.12/dist-packages/vllm /bundle/python/lib/python3.12/site-packages/vllm
COPY --from=upstream /usr/local/lib/python3.12/dist-packages/vllm-0.28.1rc1.dev580+g385dce36b.dist-info /bundle/python/lib/python3.12/site-packages/vllm-0.28.1rc1.dev580+g385dce36b.dist-info
COPY runtimes/glm/lora-projections.patch runtimes/glm/mla-lora.patch runtimes/glm/slot-mapping.patch /tmp/
RUN patch --fuzz=0 -p1 -d /bundle/python/lib/python3.12/site-packages/vllm < /tmp/lora-projections.patch \
    && patch --fuzz=0 -p1 -d /bundle/python/lib/python3.12/site-packages/vllm < /tmp/mla-lora.patch \
    && patch --fuzz=0 -p1 -d /bundle/python/lib/python3.12/site-packages/vllm < /tmp/slot-mapping.patch
RUN cd /bundle/python/lib/python3.12/site-packages/nvidia/cu13 \
    && ln -sfn lib lib64 \
    && ln -sfn libcudart.so.13 lib/libcudart.so \
    && ln -sfn libnvrtc.so.13 lib/libnvrtc.so \
    && uv pip check --python /bundle/python/bin/python3

FROM dependencies AS package
COPY --from=runtime-base /opt/gradiated/bin/runtime-launch /bundle/runtime-launch
COPY --from=runtime-base /opt/gradiated/bin/desmondd /bundle/desmondd
COPY bundles/package.sh /package.sh
COPY --chmod=755 bundles/glm-5-3-flash/entrypoint /bundle/entrypoint
COPY runtimes/glm/warmup-supervisor.py /bundle/warmup-supervisor.py
COPY runtimes/glm/test_mla_lora.py runtimes/glm/test_slot_mapping.py /bundle/glm-tests/
COPY lora/*.py /bundle/lora/
COPY lora/pyproject.toml lora/vllm_resolver.py /tmp/lora-plugin/
RUN uv pip install --python /bundle/python/bin/python3 --break-system-packages \
    --no-build-isolation --no-deps /tmp/lora-plugin && rm -rf /tmp/lora-plugin
COPY images/nomad-base/base-id /bundle/base-id
RUN bash /package.sh

FROM runtime-base AS verify
RUN --mount=from=package,source=/runtime.tar.gz,target=/tmp/runtime.tar.gz \
    mkdir /bundle && tar -xzf /tmp/runtime.tar.gz -C /bundle \
    && /bundle/python/bin/python3 -c 'import importlib.metadata as m; assert m.version("vllm") == "0.28.1rc1.dev580+g385dce36b"; from vllm.model_executor.models import ModelRegistry; assert "Glm5NextForConditionalGeneration" in ModelRegistry.get_supported_archs()' \
    && GRADIATED_REQUIRE_VLLM_RESOLVER=1 /bundle/python/bin/python3 -m unittest discover -s /bundle/lora -p 'test_*.py' \
    && GRADIATED_REQUIRE_GLM_LORA=1 /bundle/python/bin/python3 -m unittest discover -s /bundle/glm-tests -p 'test_*.py' \
    && rm -rf /bundle && touch /verified

FROM scratch AS artifact
COPY --from=verify /verified /verified
COPY --from=package /runtime.tar.gz /runtime.tar.gz
