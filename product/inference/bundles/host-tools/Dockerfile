FROM runtime-base AS package
USER root
RUN mkdir -p /bundle/bin \
    && cp /opt/gradiated/bin/runtime-launch /opt/gradiated/bin/desmondd \
       /opt/gradiated/bin/fetch-runtime /opt/gradiated/bin/start-desmond \
       /usr/local/bin/s5cmd /usr/bin/bsdtar /bundle/bin/ \
    && cp /etc/gradiated/base-id /bundle/base-id
COPY bundles/host-tools/install.sh /bundle/install.sh
RUN tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -C /bundle -czf /runtime.tar.gz .

FROM runtime-base AS verify
USER root
COPY --from=package /bundle /bundle
RUN printf 'runpod-glm-existing-v1\n' >/etc/gradiated/base-id \
    && printf 'synthetic_runtime_token_0000000000000000\n' >/etc/gradiated/runtime-access.token \
    && printf 'AWS_ACCESS_KEY_ID=synthetic\nAWS_SECRET_ACCESS_KEY=synthetic\n' >/tmp/artifact.env \
    && bash /bundle/install.sh /tmp/artifact.env \
    && bash /bundle/install.sh /tmp/artifact.env \
    && test "$(cat /etc/gradiated/base-id)" = runpod-glm-existing-v1 \
    && test "$(stat -c %U:%a /etc/gradiated/artifact.env)" = downloader:600 \
    && /usr/local/bin/bsdtar --version \
    && /usr/local/bin/s5cmd version \
    && touch /verified

FROM scratch AS artifact
COPY --from=verify /verified /verified
COPY --from=package /runtime.tar.gz /runtime.tar.gz
