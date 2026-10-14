FROM ubuntu:24.04@sha256:224a1869083a311ef3f13648a154ba79832fbef6364d31493642ca03082da254 AS dependencies
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl pigz \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.12.0@sha256:606e70c71c852d03f611b1e56a195d08648507018a7057fab82c4974c4eae105 /uv /usr/local/bin/uv
ENV UV_PYTHON_INSTALL_DIR=/opt/python UV_LINK_MODE=copy UV_NO_CACHE=1
RUN uv python install 3.12.13 \
    && mkdir /bundle && mv "$(uv python dir)"/cpython-3.12.13-linux-x86_64-gnu /bundle/python
COPY inference/training/requirements.txt /tmp/requirements.txt
RUN uv pip install --python /bundle/python/bin/python3 --break-system-packages \
    --require-hashes -r /tmp/requirements.txt

FROM dependencies AS package
COPY packages/autotrain/pyproject.toml /tmp/autotrain/pyproject.toml
COPY packages/autotrain/src /tmp/autotrain/src
COPY packages/autotrain/tests /tmp/autotrain/tests
RUN uv pip install --python /bundle/python/bin/python3 --break-system-packages \
    --no-deps --no-build-isolation /tmp/autotrain \
    && /bundle/python/bin/python3 -m unittest discover -s /tmp/autotrain/tests \
    && rm -rf /tmp/autotrain
COPY inference/training/*.py /bundle/
COPY packages/contracts/src/training-recipe.json /bundle/recipe.json
COPY --chmod=755 inference/training/entrypoint /bundle/entrypoint
COPY inference/images/gpu-base/base-id /bundle/base-id
COPY inference/bundles/package.sh /package.sh
RUN /bundle/python/bin/python3 -m unittest discover -s /bundle -p 'test_*.py' \
    && bash /package.sh

FROM runtime-base AS verify
RUN --mount=from=package,source=/runtime.tar.gz,target=/tmp/runtime.tar.gz \
    mkdir /bundle && tar -xzf /tmp/runtime.tar.gz -C /bundle \
    && /bundle/python/bin/python3 -c 'import torch, transformers, peft; from transformers import Qwen3ForCausalLM, Glm5NextForConditionalGeneration' \
    && /bundle/python/bin/python3 -m unittest discover -s /bundle -p 'test_*.py' \
    && rm -rf /bundle && touch /verified

FROM scratch AS artifact
COPY --from=verify /verified /verified
COPY --from=package /runtime.tar.gz /runtime.tar.gz
