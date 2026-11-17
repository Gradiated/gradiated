# A CPU build of SGLang with the test weights baked in, for the gateway's
# real-runtime fidelity tests.
#
# This is NOT a production image: production serves every model on GPU SGLang
# bundles (and Kev on its native runtime). This uses upstream's CPU release so CI
# can exercise the gateway against the same OpenAI-compatible server as production
# rather than our own mock, and a run never has to reach Hugging Face to do it.
#
# The base is pinned by digest and the weights by commit. A download pinned by
# commit records no refs/main, and the caller serves the weights by name, so the
# weights layer records it.
FROM docker.io/lmsysorg/sglang:v0.5.23-xeon@sha256:f22c18d175270ad1aa63ff6298a4d5a79954520863d5eab6862f94728c2d18df

ARG CPU_WEIGHTS=Qwen/Qwen2.5-0.5B-Instruct
ARG CPU_WEIGHTS_REVISION=7ae557604adf67be50417f59c2c2f167def9a775

ENV CPU_WEIGHTS=${CPU_WEIGHTS}

RUN python3 -c "\
from pathlib import Path; \
from huggingface_hub import snapshot_download; \
weights = Path(snapshot_download('${CPU_WEIGHTS}', revision='${CPU_WEIGHTS_REVISION}')); \
ref = weights.parents[1] / 'refs' / 'main'; \
ref.parent.mkdir(exist_ok=True); \
ref.write_text(weights.name)"

# Only after the weights are in the image: serving offline is deliberate, so an
# image that lost them fails loudly instead of quietly downloading them again.
ENV HF_HUB_OFFLINE=1

# The caller supplies the model and server flags as arguments.
ENTRYPOINT ["python3", "-m", "sglang.launch_server"]
