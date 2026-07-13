# GLM-4.7-Flash RunPod campaign

## $100 campaign baseline reconciliation (2026-07-13)

RunPod's provider-settled billing records supersede the earlier GPU-rate-only ledger. All 22 historical account allocations have now settled at $4.944724685 including disk. The original 14 GLM allocations account for $4.281754442, which is $0.169368779 above the prior $4.112385663 report. Conservative accounting retains the larger local upper bound for each pod: $0.108243383 for `zjcdwiwxgzs2te`, the provider-settled $0.323071860 for `kjcomsx6wz40ro`, and $0.273464527 for the interrupted post-authorization allocation. The corrected signed campaign-start account ceiling is $4.880141975 and the corresponding GLM ceiling is $4.713069685.

The extended-load pod `yd5qve2pxmdciw` was created after the new coordinator started and before the required baseline was signed. It is retained as a protocol violation and charged to the new $100 authorization rather than backdated into historical spend. Provider billing ultimately posted $0.067295185 for that pod, but its missing terminal record means the first verified 404 remains the defensible $0.273464527 upper bound. Current campaign-additional spend is therefore $0.273464527; current conservative account lifetime spend is $5.153606502. Live RunPod inventory is empty, and direct GETs for all three L40S pod IDs return 404. The full pod-partition ledger is `campaign_100/analysis/RUNPOD_BASELINE_RECONCILIATION.json`.

## $100 campaign Gate A (2026-07-13)

Gate A is signed and content-addressed at SHA-256 `a3f41e30d421dcd66822c42165b287b5804abcef199cc222c1e89a4bebd96d66`. The fail-closed campaign suite passes 68/68 tests and the GLM experiment suite passes 21/21. Frozen identities are workload `c974f23e460a863be37b3cc04df80fc9aff977e239a5c49225cd8c85f1bb3d55`, tokenizer bindings `c5258d650227ab3c474f25218263c5ac1898011f55aecef16def5fe10cf7fa64`, and quality screen `0a7ba38e9cd5b627381e59194f3ab5df8e402995b8e0424869ae34a97a077041`.

The Phase-B allocation was preregistered as a stock-only native-BF16 control on one A100 80 GB PCIe: MTP off, radix cache disabled, FCFS, and sequential smoke, c1, and c8 gates. It deliberately excluded a tuned configuration and c32 headline point. This was the cheapest changed placement capable of falsifying A100 compatibility and the frozen service contract before a tuned comparison.

### Phase B A100 placement request 1

The Community A100 80 GB PCIe request returned RunPod HTTP 500 before a pod ID was issued. Live inventory immediately remained empty, so allocation cost is $0 and no deletion was possible or required. This is placement-capacity evidence only. The single allowed retry changes the recorded causal placement variable from Community to Secure cloud while retaining the model, image, GPU type, stock configuration, workload, quality gate, SLO, and artifact contract.

### Phase B A100 placement request 2 and decision

The changed Secure A100 80 GB PCIe request also returned RunPod HTTP 500 before a pod ID was issued. The final inventory query at 13:05:22Z returned zero entries, and the billing row count remained 22; this request also cost $0 and created nothing to delete. The two-placement limit is exhausted. Cycling to A100 SXM or back to the repeatedly failed H100 placements would violate the preregistered stop rule and the campaign's prohibition on unchanged failed placements.

Decision: `STOP_OR_PIVOT`. Gate B cannot pass because no valid stock throughput/SLO point exists, so the tuned control, AWQ GPU retry, paired representation quality screen, custom intervention, holdout, and specificity phases are not admissible. This does not falsify the co-design thesis; it falsifies this best-effort RunPod placement path as a valid way to test it now. Campaign-additional spend remains $0.273464527, with $0 spent by the two Phase-B requests and $99.726535473 of the authorization deliberately unspent.

The single next experiment after a placement pivot is the same frozen 25-request stock BF16 harness on a guaranteed or provider-reserved 80 GB NVIDIA placement with the exact image pre-pulled. Only after stock passes should the supported tuned control run on the same machine. No Fireworks, Baseten, Cloudflare, AWQ, software, memory-hierarchy, or hardware cost improvement is claimed.

## Phase 3 attempt 4: interrupted extended-load allocation (2026-07-13)

The changed hypothesis retained the five-minute provider-startup gate and extended only the in-container model-health allowance after attempt 3 measured slow checkpoint reads. One Secure L40S was created at $0.99/hour. The legacy worker was interrupted during workspace migration after the endpoint appeared; it persisted only the creation and payload-audit rows. No terminal artifact, model result, allocation finish row, or DELETE receipt survives, so this allocation provides no compatibility, correctness, performance, quality, or economic evidence.

The pod was last observed RUNNING at 12:00:05Z and first returned GET 404 at 12:00:56.332Z. Using the later bound plus an observed disk reserve gives a conservative $0.273464527 campaign charge. No unchanged retry is admissible. Any later AWQ smoke must change the artifact-lifecycle mechanism so the independent watchdog and terminal record survive coordinator interruption.

## Phase 3 attempt 3: cold-read timeout (2026-07-13)

The causally patched Secure L40S run was terminated by the smoke harness's model-health timeout, not a model exception. The exact 20.19 GB checkpoint downloaded in 300 seconds; during model load the first of four parallel shards took 321.64 seconds and only one shard completed before the 480-second health loop ended. Consequently, the new compressed `kv_b_proj` branch was not reached and remains unvalidated on GPU. Artifact SHA-256 is `a266d75e24973d933c9d59b0b7bf930f4a409928f47dd4acbe9fbc738bf3d944`. Allocation was 1,160.286 seconds at $0.99/hour, costing $0.319079; phase cumulative spend is $0.423387. Teardown was DELETE 204 followed by GET 404.

Decision: retain the hard five-minute provider-startup deadline and 40-minute allocation watchdog, but extend the distinct in-container model-health allowance to 20 minutes based on measured cold-read time. Package immediately after two deterministic completions; any throughput restart is a separate experiment after smoke success.

## Phase 3 attempt 2: GPU loader validation (2026-07-13)

Measured GPU evidence on one Secure NVIDIA L40S ($0.99/hour): native SGLang and CompressedTensors WNA16 Marlin initialized, the metadata gate passed, and all four AWQ shards loaded. This validates the phase-2 `[2]` versus `[4]` fix on GPU. The run then failed before health at `deepseek_weight_loader.py:522`: compressed `kv_b_proj` exposes `weight_packed`, `weight_scale`, and `weight_shape`, while the MLA post-load code assumed dense `.weight`. No completion or throughput claim exists.

Allocation was 379.303 seconds and conservative spend was $0.104308. Artifact SHA-256 is `4faabdb314871c02e68aea0be64a976f0c4688d08f1891ed44155df0fde7e918`; DELETE returned 204 and follow-up GET returned 404. The selected correction uses compressed-tensors' canonical unpack/dequantize inverse for symmetric, non-actorder int4, checks the restored shape, and preserves the legacy paths. Nineteen offline tests pass and the patch applies exactly once to pinned SGLang commit `f63458b5...` and compiles.

Updated: 2026-07-13

Status: native CUDA 13 BF16 serving is verified, but no throughput result was obtained. The H100 baseline is externally blocked by repeated pinned-image startup misses under the mandatory five-minute deadline; the AWQ path is blocked by a measured SGLang/checkpoint fused-metadata incompatibility. RunPod reports zero active pods.

## Decision target

- Workload: 8,192 input tokens and 1,024 output tokens, representing an 8:1 agentic input/output mix.
- Published Lambda SGLang anchor: 660.67 output tok/s and 5,946.05 total tok/s at concurrency 32 with 256 prompts.
- H100 SXM cost at $2.99/hour: the published anchor implies $1.25714 per million output-equivalent tokens, or approximately $0.13968 per million blended tokens.
- Cloudflare GLM-4.7-Flash API comparison: $0.06/M input and $0.40/M output, equal to $0.88/M output-equivalent at 8:1.
- A $2.99/hour H100 therefore needs about 944 output tok/s to match Cloudflare before non-GPU costs, about 43% above the published anchor.
- Campaign gate: at most $0.84/M output-equivalent with matched service level and quality. Strong gate: $0.60/M. Stretch gate: $0.40/M.

## Attempt history

### Provisioning attempts 1 and 2

The first two H100 requests did not receive machines because the provisioning filters were too restrictive. Both were deleted under watchdog control. Conservative combined cost was about $0.52. No model run occurred.

### H100 attempt 3

- GPU: one NVIDIA H100 80GB HBM3 at $2.99/hour.
- Model: `zai-org/GLM-4.7-Flash`, revision `75fce70`, 62.5 GB BF16 weights.
- Runtime: `lmsysorg/sglang:v0.5.15-cu129`.
- Allocation: 1,868.625 seconds.
- Conservative cost: $1.5520.
- Artifact: 30,721 bytes, SHA-256 `5a62067ee3ef8f61a1f13f3b1dc90a41ddc0a0585e69e77ae263c1137cf96d1e`.
- Teardown: DELETE returned HTTP 204 and follow-up GET returned 404.

The model downloaded and SGLang started its worker. SGLang v0.5.15 did contain native `Glm4MoeLiteForCausalLM`, but the CUDA 12.9 image lacked the CUTLASS DSL Python module. SGLang suppressed `No module named 'cutlass'` while importing all affected native models, then `model_impl=auto` silently chose its generic Transformers fallback, which crashed before opening the server port:

`ValueError: Unsupported TP style 'mla_kv_a_proj' for Transformers backend.`

Consequently, all benchmark clients timed out waiting for `/v1/models`; there is no valid throughput or $/token result from this attempt.

## Root-cause correction

The corrected runtime is the official linux/amd64 CUDA 13 image `lmsysorg/sglang@sha256:655d004115e384b56b73ad6869bb04b29cce7ba3e597ce8f92eeeb49e2acb0af`, OCI index `sha256:af911a303a12516adf23ab8bb89c8fdf161ec0ceafc278a436fa111f5c118988`, built from SGLang commit `f63458b5beaceabbd9d749b9fc956370e1b649e6`. It must pass explicit imports of `cutlass` and `Glm4MoeLiteForCausalLM` before any weight download and must force `--model-impl sglang`.

The next harness also needs:

- `--tool-call-parser glm47`
- `--reasoning-parser glm45`
- MTP as `--speculative-algorithm EAGLE`
- Official MTP shape: three speculative steps, top-k 1, four draft tokens
- Early abort as soon as the server process exits, instead of allowing each benchmark to wait independently
- A 4K-context, max-one-request, CUDA-graphs-disabled smoke test with two identical greedy completions before the full benchmark matrix

## Spend reconciliation

The authoritative consolidated pre-smoke campaign spend is $2.072: approximately $0.52 for provisioning attempts 1 and 2 plus $1.5520 for attempt 3's actual 1,868.625-second allocation. A later attempt-3 controller timeout row describes the already-deleted pod and must not be added again. The $12 campaign cap therefore leaves approximately $9.928 before the CUDA 13 smoke.

## Attempt 4 — native CUDA 13 smoke (new measured evidence)

- Allocation: 547.541 seconds on one H100 at $2.99/hour; conservative whole-allocation cost $0.45476.
- Runtime: SGLang 0.5.15, source `f63458b5beaceabbd9d749b9fc956370e1b649e6`, PyTorch 2.11.0+cu130, Transformers 5.12.1.
- Native gate: `cutlass` imported from the NVIDIA CUTLASS DSL package; `Glm4MoeLiteForCausalLM` imported from SGLang and the module SHA-256 was `2dc2c064b24be8c5633ef403f0447880e111c5a5c3ed4ef621e1aec52e2abe89`.
- Weight load: native `Glm4MoeLiteForCausalLM`, 56.27 GB reported weight memory, 22.18 GB available after load.
- Determinism: two identical greedy 32-token completions had identical normalized content/reasoning/tool-call payloads, finish reason, and token count. Both ended at the requested length; this is a deterministic serving smoke, not a task-quality result.
- Telemetry: 278 one-second samples; maximum VRAM 58,812 MiB, maximum GPU utilization 15%, maximum power 135.25 W, maximum temperature 35 C. DCGM availability is preserved in the raw bundle.
- Artifact: `attempt4-smoke.tar.gz`, 33,831 bytes, SHA-256 `da9c6b79db41f785599595cd229c4a6e94d9e692417fa56a0322972759536be6`.
- Teardown: DELETE 204; follow-up GET 404; account inventory then showed zero active pods.

Decision: uncertainty about native CUDA 13 support is resolved. The next cheapest decisive experiment is a matched BF16 baseline at 8,192 input/1,024 output with small c1/c8 samples and the full 256-prompt c32 published-style workload. MTP waits until stock economics and SLOs are measured.

### Attempt 5 — baseline startup failure

The first baseline allocation never exposed a container endpoint within the hard five-minute startup deadline. It was terminated at 306.259 seconds for a conservative $0.25437; DELETE returned 204 and follow-up GET returned 404. No runtime or model phase began, so this is infrastructure-only evidence. Because the identical pinned image reached its endpoint in 248 seconds during attempt 4, one bounded retry was selected before changing the runtime contract.

### Attempt 6 — repeated baseline startup failure

A different H100 machine also failed to expose the digest-only image reference within five minutes. It was terminated at 309.476 seconds for $0.25704 with DELETE 204 and follow-up 404. This repetition rejects another identical deployment. Registry verification showed that tag `v0.5.15-cu130` resolves to OCI index `af911a...`, whose linux/amd64 manifest is the required `655d004...`. Attempt 7 therefore uses `v0.5.15-cu130@sha256:655d004...`: still cryptographically pinned, but eligible for a tag-keyed provider cache.

### Attempt 7 — native baseline harness fast-fail

The tag-plus-digest image exposed its endpoint in 35 seconds, downloaded the model in 72 seconds, loaded native BF16, allocated a 284,098-token KV pool, captured decode CUDA graphs through batch 32, and reached health. The first benchmark then fast-failed because this SGLang CLI uses ignore-EOS by default and rejects the obsolete `--ignore-eos` option. The verified failure artifact was retrieved and teardown verified. Allocation was 203.234 seconds, costing $0.16880. The minimum correction is to remove that flag; no runtime or workload semantics otherwise change.

### Attempt 8 — baseline placement failure

The corrected benchmark never reached a container endpoint on a new H100 machine within five minutes. It was deleted at 310.007 seconds for $0.25748 and verified 404. With three baseline image-start misses and only one successful placement, another H100 attempt has lower information value than the $0.44/hour A40 AWQ smoke. MTP is deferred until a stock baseline exists.

### Attempt 9 — Secure A40 capacity miss

RunPod returned HTTP 500 before creating a Secure A40. No pod ID was issued and spend was $0. The next attempt changes only capacity class to Community A40 with public IP support; the model/runtime contract remains identical.

### Attempt 10 — Community A40 capacity miss

Community A40 also returned HTTP 500 before creation, with $0 spend. The selected fallback is a Secure RTX A6000, explicitly treated as a 48GB Ampere capacity proxy for the A40 path rather than an A40 measurement.

### Attempt 11 — A6000 proxy startup miss

The Secure RTX A6000 was listed at $0.49/hour but did not expose the image within five minutes. It was deleted at 306.168 seconds for $0.04167 and verified 404. One cheap cache-warm retry was selected; this mirrors the successful H100 tag-cache behavior and costs about four cents if it reaches the deadline.

### Attempt 12 — AWQ runtime bug isolated

The cache-warm retry reached the same A6000, downloaded revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`, and entered native compressed-tensors construction. It then failed before weight load because `DeepseekV2AttentionMLA` dereferenced `.weight` on a compressed-tensors `ReplicatedLinear` wrapper before evaluating its Hopper-only fused-path condition. Artifact retrieval and teardown passed; 190.626 seconds cost $0.02595. A one-line recorded `hasattr(weight)` guard is semantics-preserving on SM86 and is the next model-specific runtime hypothesis.

### Attempt 14 — hotfix advances to second guard defect

Community A6000 at $0.33/hour ran the recorded first guard and advanced to `init_mla_fused_rope_cpu_forward`, which is initialized even on GPU and contains two equivalent unguarded dtype probes. The artifact and patch hashes were retrieved; 488.995 seconds cost $0.04482; teardown verified. Attempt 15 extends the same initialization-only guard to those two probes.

### Attempt 15 — AWQ loader boundary

The extended guards reached the intended `CompressedTensorsWNA16MarlinMoEMethod`, proving Marlin selection with shared-expert fusion disabled. Loading then failed on fused quantization metadata: SGLang allocated an int64 parameter of shape `[2]` while the checkpoint supplied `[4]`. Artifact retrieval and teardown passed; 272.610 seconds cost $0.02499. This is a loader/checkpoint packing incompatibility, and patching the shape without a reference would risk changing model semantics. The AWQ branch is therefore killed pending a credible loader fix; the campaign returns to the already validated native BF16 H100 baseline.

### Attempts 16 and 17 — final H100 placement blocker

Attempt 16 and its immediate cache-warm retry were assigned different H100 machines. Neither exposed the pinned CUDA 13 image within five minutes. Both were deleted and verified 404; conservative costs were $0.25452 and $0.25599. Across post-smoke baseline placements, attempts 5, 6, 8, 16, and 17 missed startup; only attempt 7 reached runtime. The cache-warm tactic cannot be controlled through the REST placement API. Further identical provisioning has low information value and is stopped.

## Final measured decision for this run

No candidate clears any economic gate because no valid throughput measurement exists. The campaign must not claim a measured $/token improvement.

What is measured:

- CUDA 13 SGLang v0.5.15 natively loads BF16 GLM-4.7-Flash and produces deterministic greedy completions.
- BF16 native load uses about 56.27 GB; the 16K configuration successfully allocated a 284,098-token BF16 KV pool and captured decode CUDA graphs through batch 32 before the benchmark-client flag failure.
- The AWQ checkpoint selects `CompressedTensorsWNA16MarlinMoEMethod` with shared-expert fusion disabled after three semantics-preserving initialization guards, but fails weight loading on fused metadata shape `[2]` versus `[4]`.
- Final authoritative conservative spend is $4.11239 against the $12 cap. Most remaining budget is deliberately unspent because repeated allocations no longer resolve model uncertainty.

Published/rate-derived math, independently verified:

- $2.99/hour and 660.67 output tok/s gives `$2.99 / 3600 / 660.67 × 1e6 = $1.25714/M` output-equivalent tokens.
- 660.67 × 9 = 5,946.03 total tok/s, consistent with the supplied 5,946.05 after rounding.
- At $2.99/hour, Cloudflare parity at $0.88/M requires 943.81 output tok/s; the $0.84 gate requires 988.76; $0.60 requires 1,384.26; and $0.40 requires 2,076.39.
- At $0.33/hour, an A6000 proxy would need 104.17 output tok/s for $0.88/M, but no throughput or quality claim is possible because the checkpoint did not load.

Next admissible experiment: wait for either a RunPod H100 placement with the exact CUDA 13 image already cached or a credible SGLang loader fix for the AWQ fused metadata. Resume with the existing corrected BF16 benchmark or AWQ smoke respectively; do not return to dense-model or tiny-model experiments.

## Current business evidence

The campaign has not proved a cost advantage. It did verify native BF16 support in the pinned CUDA 13 SGLang image and exposed two concrete vertical-stack constraints: unreliable provider-side image readiness under the mandatory startup SLO, and an AWQ compressed-tensors metadata incompatibility in the model-specific MoE loader. Neither is evidence of a defensible $/token gain without a matched throughput and quality result.

Final account audit: zero active pods. The only inventory entry was the unrelated, already-exited `gradiated-qwen03-baseline`; it was not modified. No campaign watchdog or orchestrator process remained running.

## Phase 2 — mixed-precision 48 GB loader intervention

Phase-2 additional cap: $4.00. Starting phase spend: $0.00; prior campaign spend remains $4.11239 and is tracked separately.

### Offline causal audit

Attempt 15's `[2]` versus `[4]` assertion is not MoE expert metadata. It is MLA attention fusion in pinned SGLang `f63458b5beaceabbd9d749b9fc956370e1b649e6`. The GLM loader caches every `q_a_proj` and `kv_a_proj_with_mqa` tensor and applies `torch.cat(..., dim=0)` without considering the tensor suffix.

Checkpoint revision `ab31d120fbe79988fe2a0259993cf3c222aa8881` proves the first failing pair:

- `model.layers.1.self_attn.q_a_proj.weight_shape`: int64 physical shape `[2]`, value `[768, 2048]`.
- `model.layers.1.self_attn.kv_a_proj_with_mqa.weight_shape`: int64 physical shape `[2]`, value `[576, 2048]`.
- Blind concatenation produces physical shape `[4]` and values `[768, 2048, 576, 2048]`; the fused parameter requires the semantic descriptor `[1344, 2048]` with physical shape `[2]`.
- Packed weights `[768, 256]` and `[576, 256]`, and BF16 group-32 scales `[768, 64]` and `[576, 64]`, must retain dimension-zero concatenation.
- The checkpoint is symmetric INT4, so it has no zero-point tensors. TP is one. The mismatch is therefore not zero-point packing, scale packing, group size, expert fusion, or tensor-parallel sharding.

Two prerequisite defects were also identified. The GLM class did not register `fused_qkv_a_proj_with_mqa -> [q_a_proj, kv_a_proj_with_mqa]`, so compressed-tensors could not propagate layer 0's intentional BF16 exclusions. Packed-projection detection also omitted compressed-tensors' `weight_packed` representation, causing the earlier `.weight` dereferences.

### Intervention decision

Ranked candidates:

1. Narrow SGLang correction: highest vertical-integration relevance and information per dollar; low quality risk because it changes metadata composition and classification only.
2. Pinned vLLM 0.15.0 (`f176443446f659dbab5315e056e605d8984fd976`): checkpoint-recommended and credible fallback, but changes the runtime and weakens causal attribution.
3. Deterministic checkpoint conversion: equivalent shape semantics but rewrites about 20.17 GB and adds provenance/storage risk.
4. Different quantization split/checkpoint: highest quality and provenance risk. Keeping Q/KV-A BF16 would add only about 177.35 MiB, but requires a controlled re-quantization source and quality validation.

Selected intervention: the narrow SGLang patch. It registers fused exclusions before module construction, recognizes `weight_packed`, and composes only `.weight_shape` as `[q_out + kv_out, common_input]`, failing closed on malformed descriptors. Packed weights, scales, and ordinary tensors retain their original concatenation path.

Offline result: 12 deterministic CPU tests pass, including reproduction of the old failure, exact metadata composition, unchanged packed/scale mapping, layer-0 exclusion inheritance, packed detection, malformed-input rejection, exact-source patch cardinality, and Python compilation against the pinned source. Patched source hashes are `fffb23c5...5b360` for `glm4_moe_lite.py` and `4bf89fa7...70504` for `deepseek_v2.py`.

Next experiment: one Community RTX A6000 smoke using the pinned CUDA 13 image, AWQ without MTP, 4K context, one request, CUDA graphs disabled, forced native SGLang/compressed-tensors, two deterministic greedy completions, full telemetry, artifact retrieval, and verified deletion. No identical placement retry is authorized.

### Phase-2 attempt 1 — A6000 placement rejection

The A6000-only Community request returned HTTP 500 before a pod ID or machine was assigned. Phase spend is $0.00, RunPod still reports zero active pods, and no teardown was possible or required. This falsifies an immediate A6000-only placement but says nothing about the patch.

RunPod's current REST contract permits multiple `gpuTypeIds` with `gpuTypePriority=availability`, and its documented `AMPERE_48` pool is A40 plus RTX A6000. The only permitted placement follow-up is one availability-prioritized `[A40, A6000]` request. This is a concrete placement change within the same 48 GB Ampere mechanism; no further capacity retry is authorized.

### Phase-2 attempt 2 — Ampere 48 GB pool rejection

The availability-prioritized Community request listing A40 and RTX A6000 also returned HTTP 500 before pod creation. No machine was allocated, phase spend remains $0.00 of $4.00, and the prior authoritative campaign spend remains $4.11239. This is a genuine external capacity blocker after two distinct placement hypotheses; no identical or further capacity retry is justified.

### Phase-2 conclusion

The offline result is defensible but GPU-unverified. The patch has a minimal causal basis and passes exact-source fixtures, but the campaign has not shown successful full-checkpoint load, deterministic GPU output, throughput, quality parity, or a dollar-per-token advantage on 48 GB hardware. No economics screen or expensive quality suite is admissible until the smoke passes.

The next valid continuation is the existing fail-closed smoke when a RunPod A40/A6000 allocation is actually obtainable, or the pinned vLLM 0.15.0 runtime on such hardware if the patched SGLang load reaches a new runtime-specific failure. A vLLM switch is not a remedy for provider pre-allocation rejection and was therefore not provisioned in this run.

Final phase-2 account audit: zero active pods; the only inventory entry is the unrelated, already-exited `gradiated-qwen03-baseline`, which was not modified. No RunPod watchdog or phase-2 orchestrator process remains running.

## Phase 3 — provisioning diagnosis and Ada validation

Additional cap: $2.00. Starting phase spend: $0.00. Authoritative prior campaign spend remains $4.11239.

The two phase-2 requests were reconstructed byte-for-byte from their pinned harness and patcher. Both pass RunPod's current OpenAPI schema. The multi-GPU-type array shape is explicitly valid, the image field accepts a string, and neither request set a CUDA filter. Therefore HTTP 500 alone was insufficient evidence for a capacity conclusion.

The supported `gpuTypes`/`lowestPrice` query provided cross-field evidence absent from OpenAPI:

- A40 is Secure-only and currently reports Low Secure stock at $0.44/hour. Including it in a Community request was cross-field incompatible even though schema-valid.
- RTX A6000 supports both pools, but Community currently returns no stock or price; Secure reports Low at $0.49/hour.
- L40 and RTX 6000 Ada support both pools but currently return no quoted stock or price.
- L40S supports both pools and explicitly reports Low stock at $0.79/hour Community and $0.99/hour Secure.

Because the historical bodies were discarded, attempt 1 cannot be retrospectively classified beyond schema-valid/provider-500. Attempt 2 had no currently eligible Community evidence: A40 was in the wrong pool and A6000 had no quoted Community availability. An undocumented request-size limit also remains possible because those requests were about 20 KB; the live schema declares no limit.

The REST client now retains sanitized status, allowlisted response headers, and a recursively redacted/truncated response body for every HTTP error. Five diagnostic tests pass. The next payload is a single exact `NVIDIA L40S`, Community, constrained to CUDA 13.0, and gzip-compresses the harness inputs to 9,937 bytes. It passes the live schema with no errors.

Ada compatibility is source-verified: L40S is compute capability 8.9, while pinned SGLang's compressed-tensors WNA16 linear and MoE Marlin implementations both declare minimum capability 8.0. The in-container native gate independently checks these values before downloading weights.

Decision: run one L40S smoke. If it passes, the same allocation restarts the server for a measured 3,072-input/384-output, concurrency-8 screen. This preserves the 8:1 mix but is explicitly not matched 8K/1K headline evidence.

### Phase-3 attempt 1 — explicit Community L40S availability rejection

The schema-valid Community L40S/CUDA-13 request returned HTTP 500 before pod creation. The corrected client retained `content-type`, length, date, request ID `req_0cec02d5-5018-4135-95a7-654a6984ff72`, and the sanitized body: `{"error":"create pod: There are no instances currently available","status":500}`.

This is explicit provider evidence of no available instance for the exact Community L40S/CUDA-13 combination. It is not an invalid-request, image-syntax, account-restriction, or runtime failure. No pod was created and phase spend remains $0.00.

Secure L40S independently reports Low stock at $0.99/hour. One Secure L40S/CUDA-13 request is selected as a concrete cloud-pool change with a maximum watchdog cost of $0.66. Gzip transport timestamps are fixed to zero so the payload identity is deterministic. No further RunPod placement retry is authorized after it.
