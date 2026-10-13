FROM nvidia/cuda:13.0.1-devel-ubuntu24.04@sha256:7d2f6a8c2071d911524f95061a0db363e24d27aa51ec831fcccf9e76eb72bc92
RUN sed -i 's|http://|https://|g' /etc/apt/sources.list.d/ubuntu.sources && apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl python3 openssl libcurl4t64 openssh-server nginx util-linux libarchive-tools libnuma1 libgomp1 libibverbs1 librdmacm1 \
    libopenmpi3t64 libssl3t64 libgfortran5 \
    libexpat1 libffi8 libbz2-1.0 liblzma5 libsqlite3-0 libreadline8t64 libuuid1 \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /etc/ssh/ssh_host_* \
    && useradd --uid 10001 --create-home --shell /usr/sbin/nologin runtime \
    && useradd --uid 10004 --create-home --shell /usr/sbin/nologin desmond \
    && useradd --uid 10003 --no-create-home --shell /usr/sbin/nologin downloader \
    && install -d /etc/gradiated /opt/gradiated/bin /opt/gradiated/kubelet /run/sshd \
    && install -d -m 700 -o downloader -g downloader /var/cache/gradiated/runtime-bundles \
    && install -d -o runtime -g runtime /home/runtime/.cache/huggingface
COPY images/gpu-base/base-id /etc/gradiated/base-id
COPY images/gpu-base/sshd_config /etc/ssh/sshd_config
COPY --chmod=755 images/gpu-base/start-ssh.sh /usr/local/bin/start-ssh
STOPSIGNAL SIGTERM
ENTRYPOINT ["/usr/local/bin/start-ssh"]
