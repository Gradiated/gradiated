FROM ubuntu:24.04@sha256:224a1869083a311ef3f13648a154ba79832fbef6364d31493642ca03082da254 AS launcher
RUN apt-get update && apt-get install -y --no-install-recommends cmake g++ make ca-certificates curl unzip libcurl4-openssl-dev \
    && rm -rf /var/lib/apt/lists/*
COPY runtime-launcher/CMakeLists.txt runtime-launcher/main.cpp runtime-launcher/supervise.cpp runtime-launcher/supervise.h /src/
RUN cmake -S /src -B /build -DBUILD_TESTING=OFF -DCMAKE_BUILD_TYPE=Release \
    && cmake --build /build --parallel 2
COPY CMakeLists.txt /desmond-src/CMakeLists.txt
COPY desmond/ /desmond-src/desmond/
COPY engine/ /desmond-src/engine/
RUN cmake -S /desmond-src -B /desmond-build -DBUILD_TESTING=OFF -DCMAKE_BUILD_TYPE=Release \
    && cmake --build /desmond-build --target desmondd --parallel 2
RUN curl -fsSLo /tmp/s5cmd.tar.gz https://github.com/peak/s5cmd/releases/download/v2.3.0/s5cmd_2.3.0_Linux-64bit.tar.gz \
    && echo 'de0fdbfa3aceae55e069ba81a0fc17b2026567637603734a387b2fca06c299b4  /tmp/s5cmd.tar.gz' | sha256sum -c - \
    && mkdir /s5cmd && tar -xzf /tmp/s5cmd.tar.gz -C /s5cmd s5cmd

FROM nvidia/cuda:13.0.1-devel-ubuntu24.04@sha256:7d2f6a8c2071d911524f95061a0db363e24d27aa51ec831fcccf9e76eb72bc92
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl python3 openssl libcurl4t64 openssh-server nginx util-linux libarchive-tools libnuma1 libgomp1 libibverbs1 librdmacm1 \
    libopenmpi3t64 libssl3t64 libgfortran5 \
    libexpat1 libffi8 libbz2-1.0 liblzma5 libsqlite3-0 libreadline8t64 libuuid1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home --shell /usr/sbin/nologin runtime \
    && useradd --uid 10004 --create-home --shell /usr/sbin/nologin desmond \
    && useradd --uid 10003 --no-create-home --shell /usr/sbin/nologin downloader \
    && install -d /etc/gradiated /opt/gradiated/bin /opt/gradiated/kubelet /run/sshd \
    && install -d -m 700 -o downloader -g downloader /var/cache/gradiated/runtime-bundles \
    && install -d -o runtime -g runtime /home/runtime/.cache/huggingface
COPY --from=launcher /desmond-build/desmond/desmondd /opt/gradiated/bin/desmondd
COPY images/gpu-base/start-desmond.sh /opt/gradiated/bin/start-desmond
COPY --from=launcher /build/runtime-launch /opt/gradiated/bin/runtime-launch
COPY --from=launcher /s5cmd/s5cmd /usr/local/bin/s5cmd
COPY images/gpu-base/fetch-runtime.sh /opt/gradiated/bin/fetch-runtime
COPY images/gpu-base/download-runtime.py /opt/gradiated/bin/download-runtime
COPY images/gpu-base/base-id /etc/gradiated/base-id
COPY images/gpu-base/sshd_config /etc/ssh/sshd_config
STOPSIGNAL SIGTERM
COPY gpu/bootstrap.py gpu/host_state.py gpu/supervise.py /opt/gradiated/kubelet/
COPY images/gpu-base/recovery/ /opt/gradiated/kubelet/recovery/
COPY tailscale/ /opt/gradiated/tailscale-scripts/
COPY --from=launcher /desmond-build/desmond/desmondd /opt/gradiated/kubelet/recovery/desmondd
ENTRYPOINT ["python3", "/opt/gradiated/kubelet/bootstrap.py"]
