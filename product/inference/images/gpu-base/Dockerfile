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
    && useradd --uid 10005 --create-home --shell /usr/sbin/nologin tailscale \
    && install -d /etc/gradiated /opt/gradiated/bin /opt/gradiated/kubelet /opt/gradiated/tailscale /run/sshd \
    && install -d -m 700 -o tailscale -g tailscale /var/lib/gradiated-tailscale \
    && touch /etc/gradiated/platform-only \
    && install -d -m 700 -o downloader -g downloader /var/cache/gradiated/runtime-bundles \
    && install -d -o runtime -g runtime /home/runtime/.cache/huggingface
# Same pinned release as tailscale/install-tailscale.py.
RUN curl -fsSL -o /tmp/tailscale.tgz https://pkgs.tailscale.com/stable/tailscale_1.104.1_amd64.tgz \
    && echo '108d1d96ecf410d305571e173516f27038f870919a9b89c914a167c6d33a4528  /tmp/tailscale.tgz' | sha256sum -c - \
    && tar -xzf /tmp/tailscale.tgz -C /opt/gradiated/tailscale --strip-components=1 \
       tailscale_1.104.1_amd64/tailscale tailscale_1.104.1_amd64/tailscaled \
    && rm /tmp/tailscale.tgz
COPY images/gpu-base/base-id /etc/gradiated/base-id
COPY images/gpu-base/sshd_config /etc/ssh/sshd_config
COPY --chmod=755 tailscale/run-tailscale.sh /opt/gradiated/bin/run-tailscale
COPY --chmod=755 tailscale/start-tailscale.sh /opt/gradiated/bin/start-tailscale
COPY --chmod=755 images/gpu-base/start-host.sh /usr/local/bin/start-host
STOPSIGNAL SIGTERM
ENTRYPOINT ["/usr/local/bin/start-host"]
