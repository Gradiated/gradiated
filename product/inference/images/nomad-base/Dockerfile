FROM ubuntu:24.04@sha256:224a1869083a311ef3f13648a154ba79832fbef6364d31493642ca03082da254 AS launcher
RUN apt-get update && apt-get install -y --no-install-recommends cmake g++ make ca-certificates curl unzip \
    && rm -rf /var/lib/apt/lists/*
COPY runtime-launcher/CMakeLists.txt runtime-launcher/main.cpp runtime-launcher/supervise.cpp runtime-launcher/supervise.h /src/
RUN cmake -S /src -B /build -DBUILD_TESTING=OFF -DCMAKE_BUILD_TYPE=Release \
    && cmake --build /build --parallel 2
RUN curl -fsSLo /tmp/nvidia.zip https://releases.hashicorp.com/nomad-device-nvidia/1.1.0/nomad-device-nvidia_1.1.0_linux_amd64.zip \
    && echo '4c2ab571192ae465f1fbe09c47e5e6d1fcc8c1c7a6458b1ef563a9aec618d83d  /tmp/nvidia.zip' | sha256sum -c - \
    && unzip /tmp/nvidia.zip -d /plugin

FROM nvidia/cuda:13.0.1-devel-ubuntu24.04@sha256:7d2f6a8c2071d911524f95061a0db363e24d27aa51ec831fcccf9e76eb72bc92
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates openssh-server libnuma1 libgomp1 libibverbs1 librdmacm1 \
    libopenmpi3t64 libssl3t64 libgfortran5 \
    libexpat1 libffi8 libbz2-1.0 liblzma5 libsqlite3-0 libreadline8t64 libuuid1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home --shell /usr/sbin/nologin runtime \
    && install -d -m 700 /etc/nomad/tls \
    && install -d /etc/gradiated /opt/gradiated/bin /opt/nomad/plugins /run/sshd \
    && install -d -o runtime -g runtime /workspace/gradiated/model-cache
COPY --from=hashicorp/nomad@sha256:b964829b94c5493f3b543bb409b60c335a9ca03f21d9fac8b4cdd2af18b331c9 /bin/nomad /usr/local/bin/nomad
COPY --from=launcher /build/runtime-launch /opt/gradiated/bin/runtime-launch
COPY --from=launcher /plugin/nomad-device-nvidia /opt/nomad/plugins/nomad-device-nvidia
COPY images/nomad-base/base-id /etc/gradiated/base-id
COPY images/nomad-base/start.sh /opt/gradiated/bin/start-node
COPY images/nomad-base/sshd_config /etc/ssh/sshd_config
STOPSIGNAL SIGTERM
ENTRYPOINT ["/bin/bash", "/opt/gradiated/bin/start-node"]
