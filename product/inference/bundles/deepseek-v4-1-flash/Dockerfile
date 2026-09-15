FROM vllm/vllm-openai@sha256:4f3c8bcf6328305b8cb6f61146dbfa125b0b04ae98eef3d091019ec30f564a9b AS package
COPY bundles/deepseek-v4-1-flash/package.sh /package.sh
COPY images/deepseek-v4-1-flash/start.sh /bundle/start.sh
COPY --chmod=755 bundles/deepseek-v4-1-flash/entrypoint /bundle/entrypoint
COPY --chmod=755 bundles/deepseek-v4-1-flash/vllm /bundle/vllm
COPY images/nomad-base/base-id /bundle/base-id
RUN bash /package.sh

# The caller supplies the exact base digest as a named build context.
FROM runtime-base AS verify
RUN --mount=from=package,source=/runtime.tar.gz,target=/tmp/runtime.tar.gz \
    mkdir /bundle && tar -xzf /tmp/runtime.tar.gz -C /bundle \
    && /bundle/python/bin/python3 -c 'import torch, vllm; print(torch.__version__, vllm.__version__)' \
    && CUDA_VISIBLE_DEVICES="" /bundle/python/bin/python3 -m vllm.entrypoints.cli.main --help >/dev/null \
    && rm -rf /bundle && touch /verified

FROM scratch AS artifact
COPY --from=verify /verified /verified
COPY --from=package /runtime.tar.gz /runtime.tar.gz
