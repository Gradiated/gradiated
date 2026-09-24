FROM ubuntu:24.04@sha256:224a1869083a311ef3f13648a154ba79832fbef6364d31493642ca03082da254 AS dependencies
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl pigz \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSLo /tmp/crane.tar.gz https://github.com/google/go-containerregistry/releases/download/v0.20.3/go-containerregistry_Linux_x86_64.tar.gz \
    && echo '36c67a932f489b3f2724b64af90b599a8ef2aa7b004872597373c0ad694dc059  /tmp/crane.tar.gz' | sha256sum -c - \
    && tar -xzf /tmp/crane.tar.gz -C /usr/local/bin crane && rm /tmp/crane.tar.gz
COPY bundles/deepseek-v4-1-flash/extract-dependencies.sh /extract-dependencies.sh
RUN bash /extract-dependencies.sh

FROM dependencies AS package
COPY bundles/deepseek-v4-1-flash/package.sh /package.sh
COPY images/deepseek-v4-1-flash/start.sh /bundle/start.sh
COPY --chmod=755 bundles/deepseek-v4-1-flash/entrypoint /bundle/entrypoint
COPY --chmod=755 bundles/deepseek-v4-1-flash/vllm /bundle/vllm
COPY images/nomad-base/base-id /bundle/base-id
RUN bash /package.sh

# The caller supplies the exact base digest as a named build context.
FROM runtime-base AS verify
COPY images/nomad-base/tests/test-serving.sh /tmp/test-serving.sh
RUN bash /tmp/test-serving.sh \
    && rm /tmp/test-serving.sh /etc/gradiated/runtime-access.token \
       /etc/gradiated/deployment-status.token /etc/gradiated/runtime-proxy.conf
ENV PYTHONHOME=/bundle/python PYTHONPATH=/bundle/python/lib/python3.12/site-packages
# Compile Triton's actual helper to check bundled headers without a GPU or driver.
RUN --mount=from=package,source=/runtime.tar.gz,target=/tmp/runtime.tar.gz \
    mkdir /bundle && tar -xzf /tmp/runtime.tar.gz -C /bundle \
    && /bundle/python/bin/python3 -c 'import bz2, ctypes, lzma, readline, sqlite3, ssl, uuid, xml.parsers.expat' \
    && /bundle/python/bin/python3 -c 'import torch, vllm; print(torch.__version__, vllm.__version__)' \
    && /bundle/python/bin/python3 -c 'import vllm.entrypoints.cli.main' \
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
