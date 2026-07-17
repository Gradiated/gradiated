# Research log

## 2026-07-16 — Director opening handoff

Replace the invalid custom selective-W4 implementation with a materially new official group-128 representation gate. Existing scale coarsening saves `1,314.715 MiB`; combined with the analytically valid head/shared scope it nominally reaches `44,531.019 MiB`, but that one-MiB crossing is not robust evidence. Require official `uint4b8`, native Linear/ParallelLMHead/fused-MoE dispatch and load, real-tensor error/saturation, and at least 64 MiB exact robust margin before any materialization or endpoint nomination.

## 2026-07-16 — official group-128 combined gate closes at $0

Question/action: ran the pinned `glm-vllm:0.15.0-transformers-1618d44` image against the immutable `ab31d120` checkpoint using only `compressed_tensors.pack_to_int32` / `unpack_from_int32` (the official signed `uint4b8` representation). The gate header-scanned exact safetensors payloads, sampled 128 real rows each from routed gate/up/down, ordinary attention/linear, head, and shared-expert tensors, and asked the native `CompressedTensorsConfig` to bind a group-128 scheme to Linear, ParallelLMHead, and FusedMoE. No checkpoint was materialized and no GPU, provider, controller, or model mutation was used.

Evidence: [`GROUP128_OFFICIAL_GATE.json`](artifacts/official_gate/GROUP128_OFFICIAL_GATE.json) records exact official pack/depack agreement for every sample and zero clamp saturation. Native dispatch succeeds for ordinary `Linear` (`CompressedTensorsLinearMethod`) and fused routed MoE (`CompressedTensorsWNA16MarlinMoEMethod`), but pinned `get_quant_method` tests only `LinearBase`, so `ParallelLMHead` is null. This is an in-scope native-runtime close: binding the head requires a runtime source change, forbidden by this native-path gate. Independent guards also fail: group-128 sample relative-L2 is `0.10331–0.11935`, exceeding `0.10` for all samples; exact combined payload saving is `2,493,794,128 B` (`2,378.267 MiB`), projecting c32 to `44,497.433 MiB`, only `34.567 MiB` below the `44,532 MiB` robust limit rather than the required `64 MiB`.

Interpretation/next move: return `RUNTIME_CLOSE_GROUP128_COMBINED`, additionally supported by numerical and memory closes. This candidate does not nominate materialization or a c16/c32 endpoint. Reopen only with a separately admitted native ParallelLMHead runtime implementation plus a representation with bounded error and at least another `29.433 MiB` of exact robust margin.

## 2026-07-16 — Director evidence correction

The terminal close stands, but the artifact's memory and numerical labels are not exact. Its existing-scale scan includes 197 non-serving layer-47 MTP scales; excluding their `29,331,456-B` credited saving leaves `2,464,462,672 B` (`2,350.295 MiB`) of serving saving, a projected `44,525.405 MiB` c32 peak, and only `6.595 MiB` below the robust convention. The sampled quantizer also used manual absmax/7 rather than the checkpoint's MSE observer, so its relative-L2 and zero-saturation rows are provisional, not authoritative calibration evidence. Missing `ParallelLMHead` binding and the corrected memory gate independently close group128; do not reopen or materialize it.
