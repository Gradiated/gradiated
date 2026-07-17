# Research log

## 2026-07-17 — director delegation

Activated as a materially different `$0` lane while the matched W4/FP8 component experiment owns provider mutation. Determine whether a passing synthetic W4 mechanism has any exact-revision producer/checkpoint and a falsifiable quality route. No full weights, provider, CUDA, compilation, or quality execution. Budgets are 60 wall minutes, 2 local CPU-hours, 2 GiB project storage, 256 MiB bounded probes, and `$0`.

## 2026-07-17 — exact W4 route closed as typed none

Question: does a content-addressed W4 route exist for `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`, and what is the cheapest later quality falsifier?

Action: checked the named W4 packet and paid brief, inspected the pinned vLLM compressed-tensors WNA16/Marlin source and AutoAWQ/AutoGPTQ loader paths, then performed bounded Hugging Face API/tree and metadata probes for current Gemma-4 31B W4 candidates. The shared lifecycle tools were checked once; no provider or CUDA action was in scope.

Evidence: `ebircak/gemma-4-31B-it-4bit-W4A16-AWQ@a3b96c7a8d07cc84cae0f0261ac2574310b12d37` has a measured 19,188,422,752-byte single safetensors file, compressed-tensors pack-quantized W4A16 asymmetric group-128 INT4 with int8 zero-points, and an AWQ recipe that leaves the tied head, vision tower, and projector in higher precision. Pinned vLLM source inspection finds `CompressedTensorsWNA16` selecting `MarlinLinearKernel` for supported devices. The card binds only the base model name; producer version is non-immutable and calibration inputs are not revision/hash/seed bound.

Interpretation: representation and loader compatibility are plausible, but provenance is not content-addressed to the exact target revision. Model-name similarity and a community quality disclaimer cannot close this gap. The terminal result is typed `none`; the cheapest missing fact is an immutable derivation manifest with exact base revision, producer/runtime versions, calibration identities/seed, recipe hash, and output hashes.

Next move: do not create another preparation project. If a later owner obtains that manifest, run the specified fresh-process raw-output/logit-feature falsifier in `ROUTE_DECISION.json`; otherwise retain this negative result and do not promote W4 to an endpoint or quality claim. See [ROUTE_DECISION.json](ROUTE_DECISION.json).
