ARG BASE_IMAGE
FROM vllm/vllm-openai@sha256:4f3c8bcf6328305b8cb6f61146dbfa125b0b04ae98eef3d091019ec30f564a9b AS package
COPY bundles/deepseek-v4-1-flash/package.sh /package.sh
RUN bash /package.sh
COPY images/deepseek-v4-1-flash/start.sh /bundle/start.sh
COPY bundles/deepseek-v4-1-flash/entrypoint /bundle/entrypoint
COPY images/nomad-base/base-id /bundle/base-id
COPY bundles/deepseek-v4-1-flash/vllm /bundle/vllm
RUN chmod 755 /bundle/entrypoint /bundle/vllm

FROM ${BASE_IMAGE} AS verify
COPY --from=package /bundle /bundle
# This checks imports on the actual base without a GPU or model weights.
RUN /bundle/python/bin/python3 -c 'import torch, vllm; print(torch.__version__, vllm.__version__)'
RUN CUDA_VISIBLE_DEVICES="" /bundle/python/bin/python3 -m vllm.entrypoints.cli.main --help >/dev/null
RUN tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner \
    -C /bundle -czf /runtime.tar.gz .

FROM scratch AS artifact
COPY --from=verify /runtime.tar.gz /runtime.tar.gz
