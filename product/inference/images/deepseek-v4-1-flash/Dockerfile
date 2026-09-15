FROM vllm/vllm-openai@sha256:4f3c8bcf6328305b8cb6f61146dbfa125b0b04ae98eef3d091019ec30f564a9b
COPY start.sh /opt/gradiated/start.sh
STOPSIGNAL SIGTERM
ENTRYPOINT ["/bin/bash", "/opt/gradiated/start.sh"]
