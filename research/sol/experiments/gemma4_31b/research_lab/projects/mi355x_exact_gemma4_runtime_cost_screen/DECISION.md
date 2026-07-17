# Decision — typed none (2026-07-17)

No content-bound later MI355X endpoint packet is admissible this cycle.

The current official vLLM Gemma 4 recipe is useful support evidence: it lists the exact 31B model on one MI355X and documents an AMD ROCm deployment path. The shared inventory independently records MI355X as 288 GB HBM3e and the planning rate as $2.60/GPU-hour ($2.40–$2.75 production range; $2.95 current listing). This establishes capacity plausibility and an economic input, not loadability, throughput, or cost.

The required content and access gates do not pass. The pinned content-addressed runtime in the campaign is the NVIDIA `vllm-openai:gemma4` image; the AMD `vllm-openai-rocm` route is published as a mutable tag, and the bounded registry metadata probe did not resolve its digest without an authenticated registry exchange. The only current MI355X venue found, TensorWave, presents a request/contact flow rather than executable self-service allocation evidence. Existing SGLang evidence binds an exact image and model route for H100, not MI355X.

This is a typed runtime/venue blocker, not an AMD hardware or economic result. Reopen only when an immutable AMD runtime image/source identity and executable MI355X access are available; then compare exact BF16 vLLM/SGLang against a same-MI355X control on 4,214/358 plus 10K single-stream arms, preserving raw outputs, telemetry, and the approximately $0.000614–$0.000621 campaign-mix retail hurdle.

See [MI355X_SCREEN.json](MI355X_SCREEN.json) and [metadata probe](artifacts/amd-route-metadata.json).
