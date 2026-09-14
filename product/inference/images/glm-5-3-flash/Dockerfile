# Required: a digest-pinned image containing the qualified GLM runtime.
# The current manually installed runtime has no recorded image digest yet.
ARG RUNTIME_IMAGE
FROM ${RUNTIME_IMAGE}
RUN python3 -c 'import vllm; assert vllm.__version__ == "0.1.dev19910+g933876c38.d20260826", vllm.__version__'
COPY start.sh /opt/gradiated/start.sh
STOPSIGNAL SIGTERM
ENTRYPOINT ["/bin/bash", "/opt/gradiated/start.sh"]
