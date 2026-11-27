# syntax=docker/dockerfile:1.7
# The grad-trainer worker as a host bundle, for hosts the gpu-fleet operator
# leases to grad. It repackages the published CUDA image unchanged: its Python,
# its virtual environment and grad_trainer. The host agent runs it with
# train_start, never as a pod (product/inference/gpu/host-agent.py).
#
# Not yet listed in tools/models/release.mjs, so nothing builds or publishes
# it. Pin it in runtimes.json as kind "grad-trainer", with source_image set to
# the FROM line below. 0.2.0-alpha.4 is the first release whose worker reads
# GRAD_WORKER_TOKEN (lease tokens); alpha.3 reads only TRAINER_API_KEY.
FROM docker.io/gradiated/grad-trainer:0.2.0-alpha.4-gpu@sha256:69851412594f79e5f37bfd4fc1a1bb72f470285fe212f4492a69abb90005a0cd AS source

FROM ubuntu:24.04@sha256:224a1869083a311ef3f13648a154ba79832fbef6364d31493642ca03082da254 AS package
RUN apt-get update && apt-get install -y --no-install-recommends pigz \
    && rm -rf /var/lib/apt/lists/*
COPY --from=source /usr/bin/python3.12 /bundle/python/bin/python3.12
COPY --from=source /usr/lib/python3.12 /bundle/python/lib/python3.12
COPY --from=source /opt/venv/lib/python3.12/site-packages /bundle/site-packages
COPY --chmod=755 inference/bundles/grad-trainer/entrypoint /bundle/entrypoint
COPY inference/images/gpu-base/base-id /bundle/base-id
COPY inference/bundles/package.sh /package.sh
RUN PYTHONHOME=/bundle/python PYTHONPATH=/bundle/site-packages \
    /bundle/python/bin/python3.12 -c 'import torch, grad_trainer.worker' \
    && bash /package.sh

FROM scratch AS artifact
COPY --from=package /runtime.tar.gz /runtime.tar.gz
