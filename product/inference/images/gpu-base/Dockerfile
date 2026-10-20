FROM nvidia/cuda:13.0.3-devel-ubuntu24.04@sha256:b7ae301dea2c162444795462ce17a05f6a516e5a75944b57af5b88540a1a2266
# The temporary pin limits the upgrade to Ubuntu packages and keeps the base's CUDA versions.
ARG DEBIAN_FRONTEND=noninteractive
RUN sed -i 's|http://|https://|g' /etc/apt/sources.list.d/ubuntu.sources && apt-get update \
    && printf 'Package: *\nPin: origin developer.download.nvidia.com\nPin-Priority: 1\n' > /etc/apt/preferences.d/99-gpu-base-keep-cuda \
    && apt-get upgrade -y -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold \
    && rm /etc/apt/preferences.d/99-gpu-base-keep-cuda \
    && apt-get install -y --no-install-recommends \
    ca-certificates curl python3 openssl libcurl4t64 openssh-server nginx util-linux libarchive-tools libnuma1 libgomp1 libibverbs1 librdmacm1 \
    libopenmpi3t64 libssl3t64 libgfortran5 \
    libexpat1 libffi8 libbz2-1.0 liblzma5 libsqlite3-0 libreadline8t64 libuuid1 \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /etc/ssh/ssh_host_* \
    && useradd --uid 10001 --create-home --shell /usr/sbin/nologin runtime \
    && useradd --uid 10004 --create-home --shell /usr/sbin/nologin desmond \
    && useradd --uid 10003 --no-create-home --shell /usr/sbin/nologin downloader \
    && install -d /etc/gradiated /opt/gradiated/bin /opt/gradiated/kubelet /run/sshd \
    && touch /etc/gradiated/platform-only \
    && install -d -m 700 -o downloader -g downloader /var/cache/gradiated/runtime-bundles \
    && install -d -o runtime -g runtime /home/runtime/.cache/huggingface
COPY images/gpu-base/base-id /etc/gradiated/base-id
COPY images/gpu-base/sshd_config /etc/ssh/sshd_config
COPY --chmod=755 images/gpu-base/start-ssh.sh /usr/local/bin/start-ssh
STOPSIGNAL SIGTERM
ENTRYPOINT ["/usr/local/bin/start-ssh"]
