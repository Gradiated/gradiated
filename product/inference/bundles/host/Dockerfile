FROM ubuntu:24.04@sha256:224a1869083a311ef3f13648a154ba79832fbef6364d31493642ca03082da254 AS package
COPY --from=alpine:3.22@sha256:14358309a308569c32bdc37e2e0e9694be33a9d99e68afb0f5ff33cc1f695dce /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
RUN sed -i 's|http://|https://|g' /etc/apt/sources.list.d/ubuntu.sources && apt-get update && apt-get install -y --no-install-recommends python3 pigz cmake g++ make libcurl4-openssl-dev && rm -rf /var/lib/apt/lists/*
COPY product/inference/gpu/host-agent.py product/inference/gpu/host_state.py product/inference/gpu/host_bundle.py product/inference/gpu/bootstrap.py product/inference/gpu/supervise.py product/inference/gpu/install-seed.py /bundle/
COPY --chmod=755 product/inference/gpu/fetch-runtime.sh /bundle/fetch-runtime
COPY product/inference/gpu/download-runtime.py /bundle/download-runtime
COPY product/inference/tailscale/*.py product/inference/tailscale/*.sh /bundle/
COPY product/inference/runtime-launcher/CMakeLists.txt product/inference/runtime-launcher/main.cpp product/inference/runtime-launcher/supervise.cpp product/inference/runtime-launcher/supervise.h /runtime-launcher/
RUN cmake -S /runtime-launcher -B /runtime-build -DBUILD_TESTING=OFF -DCMAKE_BUILD_TYPE=Release \
    && cmake --build /runtime-build --parallel 2 \
    && cp /runtime-build/runtime-launch /bundle/runtime-launch
COPY product/inference/CMakeLists.txt /src/CMakeLists.txt
COPY product/inference/desmond/ /src/desmond/
COPY product/inference/engine/ /src/engine/
RUN cmake -S /src -B /build -DBUILD_TESTING=OFF -DCMAKE_BUILD_TYPE=Release \
    && cmake --build /build --target desmondd --parallel 2 \
    && cp /build/desmond/desmondd /bundle/desmondd
COPY product/inference/images/gpu-base/base-id /bundle/base-id
RUN python3 -c 'import hashlib,json,pathlib; p=pathlib.Path("/bundle"); (p/"files.json").write_text(json.dumps({f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(p.iterdir())},sort_keys=True))'
COPY product/inference/bundles/package.sh /package.sh
RUN bash /package.sh

FROM runtime-base AS verify
RUN apt-get update && apt-get install -y --no-install-recommends python3-yaml && rm -rf /var/lib/apt/lists/*
COPY tools/virtual-kubelet/host_agent_test.py tools/virtual-kubelet/host_state_test.py product/inference/gpu/install_seed_test.py product/inference/gpu/host_bundle_test.py /tests/tools/virtual-kubelet/
COPY infra/environments/prod/us-east-1/kubernetes/workloads/gateway.yaml /tests/infra/environments/prod/us-east-1/kubernetes/workloads/gateway.yaml
RUN --mount=from=package,source=/runtime.tar.gz,target=/tmp/runtime.tar.gz \
    tar -xzf /tmp/runtime.tar.gz -C /tests/tools/virtual-kubelet \
    && cd /tests/tools/virtual-kubelet && python3 host_agent_test.py && python3 host_state_test.py \
    && python3 install_seed_test.py && python3 host_bundle_test.py \
    && (./runtime-launch >/dev/null 2>&1; test "$?" = 1) \
    && (./desmondd --invalid >/dev/null 2>&1; test "$?" = 64) && touch /verified

FROM scratch AS artifact
COPY --from=verify /verified /verified
COPY --from=package /runtime.tar.gz /runtime.tar.gz
