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

## Campaign-100 RunPod placement pivot — resumed after explicit user authorization

The earlier `STOP_OR_PIVOT` checkpoint remains historically valid: both A100 PCIe cloud-class requests were rejected before allocation, so no stock baseline existed at that boundary. The user subsequently authorized a new RunPod placement pivot and autonomous continuation. This opens a new prospective lineage; it does not relabel either prior rejection.

Direct authenticated checks at 13:19 UTC found zero Pods, 22 settled billing rows totaling `$4.944724685296023`, no account templates, and no account capacity reservations. RunPod's exact Secure availability query for one A100 SXM, CUDA 13, public IP, and 140 GB total disk identified `US-KS-2` and `US-MD-1` at `Low` stock and `$1.49/hour`. `US-KS-2` was selected as the single exact placement; the other observation is not an automatic retry authorization.

The selected experiment is `phase-b-stock-a100-sxm-secure-v3`. It changes the provider SKU and scheduler pool from A100 PCIe to A100 SXM while keeping the exact model revision, native-BF16 representation, SGLang image/source, stock configuration, workload, quality screen, SLO, and artifact contract fixed. The request is explicitly non-interruptible after allocation, but this is not a claim of initial reserved capacity or image pre-pull; RunPod exposes neither a public Pod machine/cache selector nor a self-service reservation API for this account.

Before allocation, the driver gained fail-closed binding for CUDA, datacenter, public-IP, and non-interruptible controls, plus immediate teardown when the provider-returned hourly rate exceeds the preregistered ceiling. Campaign tests pass `70/70`; GLM experiment tests pass `21/21`. The allocation cap is `$2.255`, the absolute deadline is 14:50 UTC, and the frozen contract requires telemetry, TTFT, token-level ITL/TPOT, throughput, queueing, failures, quality evidence, verified artifact hashing, DELETE, and GET 404.

The exact `US-KS-2` POST returned HTTP 500 in 1.459 seconds before a pod ID, machine, or hourly rate was assigned. Cost is therefore `$0`; deletion is not applicable because no resource existed. A direct post-request audit found zero Pods, the same 22 billing rows, and the same `$4.944724685296023` settled account total. The driver version retained the status but not the sanitized error body, so the classification is placement rejection rather than a more specific provider cause.

An immediate exact-query recheck still labeled `US-KS-2` Low but now labeled the independently observed `US-MD-1` pool Medium at `$1.49/hour`. This demonstrates that the GraphQL stock label is not an allocation guarantee. Under the two-placement campaign rule, `US-KS-2` is exhausted; one new `US-MD-1` preregistration is admissible only after adding sanitized HTTP-error capture. It is a changed datacenter/scheduler pool, not an unchanged retry.

The separately preregistered `US-MD-1` request also returned HTTP 500 before pod creation, in 1.419 seconds. The hardened driver hashed the 172-byte response as `887f9a284d2cff925262b0628b07915dabc7bcaf72a3847cbef13223dfab6a46` and retained only safe provider fields. The body reports an internal RunPod deployment-response parsing failure (`invalid character 'I' looking for beginning of value`), not model/runtime, quality, or SLO evidence. No pod existed, cost was `$0`, and teardown is not applicable.

Final direct checks at 13:30 UTC found zero Pods and the unchanged 22 billing rows totaling `$4.944724685296023`. All four campaign Phase-B POSTs added `$0`; campaign-additional spend remains the conservative `$0.273464527` legacy L40S charge, leaving `$99.726535473` unspent.

### Resumed campaign decision: STOP_OR_PIVOT

Gate B remains empty. Both exact A100-SXM datacenter pools are exhausted; the account has no reservation, API-visible deploy queue, template, or cached-image host selector; and another cold H100 or best-effort A100 request would repeat an already measured provisioning failure mode. The campaign therefore stops without a throughput, quality, SLO-goodput, cost-per-token, tuned, AWQ, provider, memory-hierarchy, or hardware claim.

The only admissible next experiment requires an external state change: a documented reservation or API-visible deployment queue on an 80 GB NVIDIA host with the exact image confirmed ready. Then run the same frozen stock harness once and, only after a pass, the matched tuned control on the same machine. The machine-readable resumed decision is `campaign_100/DECISION_RESUMED_2026-07-13.json`.

### Read-only RunPod capacity diagnosis

A live authenticated inventory audit at 13:49–13:50 UTC allocated no resources and cost `$0`. It falsified platform-wide GPU exhaustion: Secure H100 SXM was labeled `High` in `AP-IN-1`, while aggregate Secure A100 SXM was `Medium` and several other 80+ GB SKUs were `Low`. The account remained at zero active Pods, and RunPod's public status page reported GPU Cloud operational.

This does not make the prior A100 placements false negatives. Their exact pools were only `Low`/`Medium`, RunPod exposed no allocatable-machine counts, and both POSTs failed before a Pod existed. The retained `US-MD-1` body additionally proves an internal provider deployment-response parsing failure, so capacity is a contributor but not a complete explanation. The audit leaves `STOP_OR_PIVOT` unchanged: the apparently least-constrained H100 pool changes hardware and repeats the already measured cold-image/SLO failure mode. Full evidence and source classification are in `campaign_100/analysis/RUNPOD_CAPACITY_DIAGNOSIS_2026-07-13.md`.

### Autonomous continuation — High-stock H100 REST falsification

After the user strengthened the campaign's autonomy instruction, the High-stock H100 pool became a new hardware-and-placement lineage rather than a user checkpoint. Before allocation, the stock harness was corrected to treat an intentional fixed-workload max-token finish separately from silent truncation, invoke its pinned artifact builder on the remote path, use the historically validated 16K context regime, and propagate workload or quality failure as a nonzero remote result after packaging. The campaign suite passes `77/77` tests.

The preregistered Secure `AP-IN-1` H100 SXM REST request returned HTTP 500 before pod creation in 1.440 seconds and cost `$0`. Its 172-byte response has the exact same SHA-256, `887f9a28...ab6a46`, as the earlier A100 `US-MD-1` failure and reports the same internal deployment-response parsing error. This materially falsifies a capacity-only explanation: the failure reproduced on a different GPU and High-stock datacenter while the account remained at zero Pods. The next lineage changes the public create API itself to RunPod's documented GraphQL `podFindAndDeployOnDemand` mutation; REST inventory/get/delete and verified cleanup remain the control.

The separately preregistered GraphQL v6 request also returned HTTP 500 before creating a Pod, in 1.078 seconds and at `$0` cost. Its retained 21-byte response hash exactly matches the literal `Internal Server Error`. This demonstrates that changing the public create surface alone does not bypass the failure, but it does not yet distinguish a shared RunPod deployment-backend fault from rejection of the pinned image plus large bootstrap environment. The next experiment is therefore a minimal placement-only GraphQL control on the same H100/datacenter using RunPod's standard PyTorch image and immediate delete/404 verification.

The minimal v7 control removed the pinned SGLang image, bootstrap environment, Docker arguments, ports, and unusual storage sizes. It used `runpod/pytorch`, 20 GB container disk, and 20 GB volume on the same Secure H100/AP-IN-1/CUDA-13 placement. RunPod returned one typed GraphQL error at HTTP 200 in 0.312 seconds, before a Pod ID; cost was `$0`, no watchdog was needed, and direct inventory remained empty. This falsifies those payload elements as necessary causes. Across REST full payload, GraphQL full payload, and GraphQL minimal standard-image control, direct Pod creation is unusable for this account/placement despite the persistent `High` stock label.

The autonomous next lineage is a managed provider control rather than another Pod create. RunPod Public Endpoints do not list GLM-4.7-Flash. Fireworks lists the exact model for on-demand deployment, and Baseten lists a 2xH100 OpenAI-compatible configuration, but neither provider credential is present in the campaign environment. Those are vendor availability claims, not measured service evidence; no provider comparison or cost claim is admitted from them.

### Nebius provider pivot — H100 placement smoke v1

The user authorized a Nebius provider pivot under the campaign's remaining cross-provider budget. Authenticated read-only inventory found zero instances and disks in the target project, and Nebius capacity advice reported regular one-GPU H100 availability in several `eu-north1` fabrics. The preregistered control selected regular on-demand `gpu-h100-sxm` / `1gpu-16vcpu-200gb`, Ubuntu 24.04 CUDA 13, a 100 GiB managed SSD, a 600-second readiness SLO, a 900-second absolute deadline, and a `$0.80` cap at the vendor's `$2.95/hour` list rate.

Nebius created instance `computeinstance-e00c5byf609vnkn53c`; a fresh API read measured it in `RUNNING` state with private and public IPv4 allocations. This falsifies provider-wide unavailability and demonstrates that the service account, project authorization, subnet, GPU SKU, image family, and regular placement path work. The experiment did not reach SSH or hardware telemetry because the new observer failed to normalize Nebius's `/32` suffix before parsing the public address. This is a local harness defect, not a provider placement failure or a model result.

The instance and its managed disk were deleted. Fresh API inventories measured zero instances and zero disks. The conservative cost upper bound is `$0.171193495`, derived from 208.914096 seconds between the pre-request stock-control event and final empty-inventory verification; the provider invoice is pending. No quality, inference, throughput, TTFT, TPOT, SLO-goodput, or cost-per-token claim is admitted from v1. The corrected v2 changes the observer and interruption-finalization logic and is the cheapest experiment capable of completing the frozen hardware/SSH gate.

### Nebius H100 placement smoke v2 — PASS

The corrected control changed only CIDR normalization and interrupt-safe outcome initialization. Nebius again placed a regular one-GPU H100. Public IP was available at 40.192 seconds and cloud-init SSH at 87.155 seconds, both within the preregistered 600-second SLO. The retrieved and hash-matched archive (`9365bf33...e3ffb`) measured one `NVIDIA H100 80GB HBM3`, 81,559 MiB VRAM, MIG disabled, driver 580.159.04, 0% idle utilization, 0 MiB used VRAM, and 69.23 W idle power.

Deletion began after 88.753 seconds of allocation exposure. Instance GET became not-found and fresh final inventories measured zero instances and zero disks after 48.489 seconds of cleanup. The derived compute cost is `$0.072728172` at the vendor's `$2.95/hour` list rate; invoice evidence remains pending. Together, v1 and v2 have a conservative Nebius cost of `$0.243921667`, leaving `$24.756078333` of the explicitly authorized `$25` Nebius cap.

This passes the placement, identity, CUDA-host, evidence-retrieval, and teardown gate. It does not measure model load, quality, TTFT, TPOT, throughput, queueing, or inference cost. The next admissible allocation is a frozen native-BF16 GLM-4.7-Flash stock baseline, followed on the same host by a single high-leverage model-specific intervention only if stock passes exact-load, quality, and SLO gates.

### Nebius stock/MTP allocation v1 — frozen-bundle identity rejection

The first proper 250 GiB H100 allocation passed VM, SSH, Docker, NVIDIA Container Toolkit, pinned-image pull, and GPU-in-container gates. It reached SSH in 84.246 seconds and completed the cold 12.5 GiB compressed image bootstrap by 400.560 seconds. Before model download, the frozen workload validator rejected `replay_api.py`: its current SHA-256 was `a29f0176...361d`, while `FROZEN_MANIFEST.json` still bound the pre-fix `66b4de79...22a`.

This mismatch came from the already-tested correction that distinguishes an intentional fixed-workload max-token finish from silent truncation; the correction had not been rebound into the bundle manifest. The remote run failed closed before downloading weights or launching GLM. It still packaged an internally valid three-file failure artifact; its remote and local SHA-256 agree at `1f65bc86...1e82`. No MTP arm was admitted and no model, quality, latency, throughput, or economic hypothesis was tested.

The instance and 250 GiB managed disk are absent in fresh final inventories. Measured allocation exposure was 405.887 seconds, for a derived `$0.332601873` at `$2.95/hour`, pending invoice. The workload builder was then rerun deterministically: all 103 campaign tests pass and the corrected bundle identity is `d4353074...293c`. A v2 retry is admissible because it changes the causal contract variable that rejected v1; it is not an unchanged placement retry.

### Nebius stock/MTP allocation v2 — tokenizer implementation mismatch

V2 locally and remotely validated corrected workload `d4353074...293c`, passed native SGLang import, downloaded the exact model revision, and matched the pinned config, index, tokenizer, and chat-template hashes. The model directory reached approximately 54 GiB. Before server launch, plan materialization rejected the append fixture because Python Transformers 5.12.1 produced a different token sequence from the frozen binding.

The cause is contract-level and specific: `TOKENIZER_BINDINGS.json` declares `@huggingface/transformers` 4.2.0, while the exact pinned serving image contains Python `transformers` 5.12.1 and the plan materializer used its `AutoTokenizer`. The three tokenizer source files match exactly, but the two template implementations are not interchangeable evidence. Since the server would also use the Python runtime, bypassing the check or keeping JavaScript-derived counts would make request geometry false. No server, request, MTP, throughput, quality, or economics result is admitted.

The retrieved failure archive is hash-matched at `cb029f5f...d8b0` and includes exact model/source identities, download timing, telemetry, and teardown phases. Final Nebius inventories again measured zero instances and zero disks. Allocation exposure was 902.414 seconds and derived compute cost was `$0.739477971`, pending invoice. The next admissible lineage must regenerate the tokenizer bindings with the pinned serving runtime, bind that implementation and new workload identity, and validate them locally before provider access.

Post-allocation causal audit refined that next action. Python Transformers 5.12.1 returned a mapping-like `BatchEncoding`, while the materializer treated it as the token list; `len(result)` was therefore one and failed before hashing. An isolated exact-runtime audit extracted `input_ids` and matched all frozen JavaScript-derived counts, token hashes, and common-prefix identities exactly. The frozen binding remains valid and is not regenerated. V3 changes only return-shape normalization, with the full comparison in `campaign_100/analysis/TOKENIZER_RUNTIME_COMPATIBILITY_2026-07-13.json`.

### Nebius stock/MTP allocation v3 — arm-output path defect

V3 passed the corrected workload, exact model download, tokenizer source hashes, and all frozen tokenizer counts and token-ID hashes, confirming the return-shape diagnosis. Plan materialization then attempted to write `development_smoke.json` beneath the legacy hard-coded `/workspace/campaign-100-phase-b` path rather than the arm-specific `/workspace/campaign-100-phase-b-stock` output. The directory did not exist, so execution failed before server launch.

The failure artifact is remotely and locally hash-matched at `c4cf483d...97d8`. No model load, request, MTP, quality, latency, throughput, or economic result exists. The VM and managed disk are absent in fresh inventories. Allocation exposure was 904.024 seconds and derived compute cost was `$0.740797691`, pending invoice. V4 is admissible only after every inline Python path uses the exported arm paths and a regression test proves no non-default hard-coded workspace remains.

### Nebius stock/MTP allocation v4 — server pass, invalid append tool request

V4 passed the frozen bundle, exact native-BF16 model revision, tokenizer binding, plan materialization, pinned SGLang import, model load, and health gates. The stock server became healthy about 79.4 seconds after launch and occupied approximately 73.486 GiB of H100 VRAM. Its first development warmup completed the fixed 8,192-input/1,024-output request: SGLang logged 0.19 ms queue duration and 14,811.64 ms forward duration, while the client observation was approximately 128.5 output token/s. This single warmup is measured diagnostic evidence only—not an admissible throughput, TTFT, TPOT, quality, SLO-goodput, or cost-per-token baseline.

The following append/tool warmup returned HTTP 400 before inference. The strongest current diagnosis is a transport-schema mismatch: the frozen chat-template fixture intentionally stores the GLM-native flat function schema, while the OpenAI-compatible HTTP request sent that same flat object as `tools`; the OpenAI transport convention wraps it as `{"type":"function","function":...}`. The 400 and absence of a second request-time record are measured; the schema attribution remains an inference until the changed v5 request passes. Development smoke therefore failed closed, the measured profiles and quality gate did not run, and MTP was not admitted.

The failure archive was retrieved before teardown and its remote/local SHA-256 agrees at `7f30a355...9bb87`. The driver marks the typed artifact contract incomplete because failure occurred before `allocation-result.json`, but the retrieved archive itself is hash-matched and contains the server, runner, telemetry, phase, identity, and plan evidence used here. Allocation exposure was 998.404 seconds, for a derived `$0.818136755` at `$2.95/hour`, pending invoice. Fresh final inventories measured zero instances and zero disks. Conservative Nebius spend is `$2.874935957` of the authorized `$25`, leaving `$22.125064043`.

### Nebius stock/MTP allocation v5 — transport passed; stream and token-geometry contract rejected

V5 falsified the narrow v4 diagnosis as a complete fix. The OpenAI function envelope removed the HTTP 400: both the fixed warmup and append/tool warmup reached inference. SGLang measured the fixed request at 8,192 input and 1,024 output tokens with 0.16 ms queue and 14,593.10 ms forward duration. It measured the append request at 252 input and 69 output tokens with 0.18 ms queue and 971.84 ms forward duration. These are diagnostic request-time records, not an admitted stock baseline.

The newly persisted typed warmup evidence exposed two independent contract mismatches. First, the server emits a final usage-only SSE event with no choice, which the runner incorrectly rejected even though this is not a request failure. Second, tool/reasoning stream events can advance cumulative completion tokens without a text `content` delta; the runner only advanced its ITL clock for text, making the observed token sequence appear to jump. More importantly, the server tokenized the OpenAI-wrapped append request as 252 input tokens while the frozen flat-tool binding expected 233. Even after correcting SSE parsing, that 19-token mismatch must fail the exact geometry gate. V5 therefore admits no development profile, quality, SLO-goodput, economics, or MTP result.

The retrieved archive's remote/local SHA-256 agrees at `d45c0afb...7454`. Allocation exposure was 990.353 seconds and derived compute cost was `$0.811539496`, pending invoice. Teardown again passed with instance GET not-found and fresh zero instance/disk inventories. Conservative Nebius spend is `$3.686475453` of `$25`, leaving `$21.313524547`. A further retry is admissible only if it freezes the actual OpenAI transport representation into tokenizer geometry and makes token-count timing semantic-agnostic while retaining the one-token observability requirement.

The post-v5 offline audit met that condition without GPU spend. Running the exact pinned serving image and SGLang source on the local CPU host reproduced SGLang's OpenAI request normalization and exact tokenizer path. The development append fixture renders to 253 token IDs (`28e96d45...619f`), while v5 measured 252 scheduler-reported prompt tokens; these are now separate bound quantities rather than conflated geometry. The exact transport-expanded development-prefix inputs are 184 tokens each with a 180-token exact common prefix. The runner now times every one-token cumulative-usage advance independent of whether the delta is text, reasoning, or tool-call data, accepts only typed usage-only terminal events, and still rejects any unobservable multi-token jump. All 106 campaign tests and repository DevEx checks pass. Full measured/inferred labeling is in `campaign_100/analysis/OPENAI_TRANSPORT_TOKENIZER_AUDIT_2026-07-14.json`.

### Nebius stock/MTP allocation v6 — fixed stream measured; tool-parser ITL is structurally unobservable

V6 passed exact transport token-ID materialization and reproduced v5's measured 252-token scheduler accounting for the append request. The fixed 8K/1K warmup completed with 6,732.60 ms TTFT, 14,649.57 ms end-to-end latency, 1,023 directly timed inter-token intervals, and no truncation error at its intentional length cap. Its token-level ITL values were predominantly about 7.7 ms; this is a valid diagnostic request but not a quality- and workload-gated stock baseline because the following append warmup failed.

The append request itself completed successfully in SGLang at 252 input and 69 output tokens, 0.16 ms queue, and 971.07 ms forward duration. However, the GLM tool-call parser buffers generated tokens before emitting structured OpenAI tool-call deltas, so cumulative usage jumps by more than one between observable SSE events. The runner correctly rejected that stream: per-token ITL cannot be reconstructed from the public response timing, even after making delta semantics irrelevant. This falsifies the current combined agent-development gate as an observable token-level SLO workload on the pinned stock OpenAI/tool-parser path. It is not a model failure, HTTP failure, or evidence of slow tool inference.

No measured profile, quality gate, stock economics, or MTP arm was admitted. The archive's remote/local SHA-256 agrees at `b7297277...f319`. Allocation exposure was 1,237.052 seconds—extended by a recycled-IP host-key correction—and derived compute cost was `$1.013695247`, pending invoice. Teardown passed with instance GET not-found and zero final instance/disk inventories. Conservative Nebius spend is `$4.700170700` of `$25`, leaving `$20.299829300`.

The next experiment must not repeat this structurally unobservable combined gate. The narrow admissible pivot is to measure token-level SLO and throughput on the frozen fixed 8K/1K completion workload, where v6 proves every token is observable, and run semantic quality separately through the stock chat endpoint. Such a result may support only fixed-workload economics plus separate quality evidence; it cannot claim agent/tool-call TPOT or general agent-serving SLO.

### Nebius fixed-workload/quality/MTP allocation v7 — fixed SLO pass; quality truncated

V7 produced the campaign's first admissible fixed-geometry stock measurement. On one Nebius H100, all four concurrency-1 requests and all sixteen concurrency-8 requests completed at exactly 8,192 input and 1,024 output tokens with no errors or detected truncations. The c1 profile measured 86.887 output tok/s over the conservative runner wall time, TTFT p50/p95 179.264/182.630 ms, and token-level ITL p50/p95/p99 7.738/7.810/8.024 ms. The c8 profile measured 303.857 output tok/s, TTFT p50/p95/p99 734.642/1,320.948/1,320.948 ms, and ITL p50/p95/p99 9.182/9.435/9.665 ms. Both preregistered fixed-workload SLO gates passed.

At the vendor's `$2.95/hour` list rate, the measured conservative c8 throughput analytically implies `$2.697/M` output tokens (`2.95 / 3600 / 303.85685 × 1e6`). This is a compute-only steady-state estimate derived from a measured fixed synthetic workload. It excludes allocation/setup time and ancillary charges, has no matched provider workload, and is not a quality-adjusted cost or a competitiveness claim. Reaching the historical analytical `$0.88/M` anchor at the same rate would require 931.19 output tok/s, a 3.065× throughput increase or 67.4% cost reduction.

The separate development quality capture did not pass. Its first stock response reached the frozen 256-token maximum and returned `finish_reason=length`; the fail-closed runner rejected it as truncated before responses or scores could be admitted. Server evidence records 24 input and 256 output tokens. The most likely cause is default GLM reasoning consuming the small response budget, but that attribution remains a hypothesis until an explicit request policy changes the result. Because quality failed, the MTP arm was correctly not admitted.

The final allocation-result writer then hit an independent observer defect: it referenced `os.environ` without importing `os`, leaving an empty typed result file after the substantive gates had already completed. The retrieved archive remains complete enough for the scoped fixed-profile and quality-failure findings and is hash-matched remotely and locally at `efbc68a2...ae88b`. Allocation exposure was 1,134.662 seconds, for a derived `$0.929792499`, pending invoice. Teardown passed: instance lookup returned not found and final inventories contained zero instances and zero disks. Conservative Nebius spend is `$5.629963199` of `$25`, leaving `$19.370036801`.

The cheapest changed follow-up is an explicit GLM request policy with `chat_template_kwargs.enable_thinking=false` for the simple semantic quality suite. This is labeled a tuned representation/runtime policy rather than a stock-default quality result. It retains the fixed c1/c8 control, raises no quality limit, and admits MTP only if the reasoning-off quality capture and self-score pass. No agent/tool-call TPOT claim is permitted.

### Nebius reasoning-off quality/MTP allocation v8 — policy works; 16K server geometry rejects frozen 32K case

V8 reproduced the fixed control with negligible drift. C1 measured 87.022 output tok/s, TTFT p50/p95 179.236/181.543 ms, and ITL p50/p95/p99 7.732/7.817/8.118 ms. C8 measured 303.955 output tok/s, TTFT p50/p95/p99 733.241/1,319.250/1,319.250 ms, and ITL p50/p95/p99 9.174/9.458/9.838 ms. All 20 requests succeeded at exact 8,192/1,024 geometry and both SLOs passed. C1 and c8 throughput differ from v7 by only +0.16% and +0.03% respectively.

The explicit `enable_thinking=false` policy changed the prior failure as predicted for the first two quality cases: the 24-token tool prompt stopped after 32 output tokens and the 19-token code prompt stopped after 40, rather than reaching the 256-token cap. The third, long-context retrieval request returned HTTP 400 before inference, so the quality capture still failed and MTP was not admitted.

An exact-runtime offline tokenizer audit measured the five development chat inputs at 24, 19, 32,379, 36, and 17 tokens. The frozen retrieval case plus its unchanged 256-token output budget requires 32,635 tokens, exceeding the v8 server's 16,384 context. This makes the HTTP rejection a server-geometry defect in the campaign setup, not evidence of model quality. The changed follow-up raises only server context to 32,768 while retaining chunked prefill, fixed workload, quality policy/cap, and conditional MTP gate. Full labeled evidence is in `campaign_100/analysis/QUALITY_CONTEXT_GEOMETRY_AUDIT_2026-07-14.json`.

The v8 archive is internally valid and its remote/local SHA-256 agrees at `ad5b0d8a...0bb4`. Allocation exposure was 1,125.828 seconds, for a derived `$0.922553439` at the vendor list rate, pending invoice. Teardown passed with instance not found and zero final instance/disk inventories. Conservative Nebius spend is `$6.552516638` of `$25`, leaving `$18.447483362`. The repeated c8 rate analytically implies `$2.696/M` output tokens compute-only; it remains neither quality-adjusted nor provider-matched.

### Nebius 32K quality/MTP allocation v9 — geometry passes; absolute quality fails

V9 validated the server/memory-hierarchy change. The 32,768-context stock server loaded successfully, c1 measured 87.058 output tok/s, and c8 measured 304.134 output tok/s. Both fixed profiles again passed with 100% request success and no truncation. C8 TTFT p50/p95/p99 was 734.188/1,326.074/1,326.074 ms and ITL p50/p95/p99 was 9.166/9.575/9.919 ms. The +0.06% c8 change from v8 is negligible; increasing the per-request context ceiling did not measurably degrade this fixed workload.

All quality requests completed, including the exact 32,379-input-token retrieval case. It returned the correct key/value content, proving the v8 HTTP 400 was geometry rather than model failure. The absolute frozen screen nevertheless failed. The tool case used `file_path` instead of required `path`; code was fenced; retrieval included `K-4702:` rather than value-only; continuation returned `[development]`; serving JSON used `{"readiness":true}` instead of the bound object; and runtime teacher-forced NLL was 7.708 against the frozen 2.0 ceiling. The self-comparison had zero regression, but its absolute category scores were zero and `catastrophic_category_failure` correctly rejected it.

This is measured stock-quality evidence on a compact synthetic screen, not a general quality verdict. Some failures are representation/schema-policy candidates, while the NLL threshold cannot be repaired by response formatting. Lowering or recalibrating the frozen threshold after observing the result would be post hoc and is not admitted. MTP was therefore withheld under v9's preregistration.

The archive's remote/local SHA-256 agrees at `a9dedff6...ce41` and its internal 51-file manifest passes. Allocation exposure was 1,123.712 seconds, for a derived `$0.920819551`, pending invoice. Teardown passed with zero final instances and disks. Conservative Nebius spend is `$7.473336189` of `$25`, leaving `$17.526663811`. The c8 point implies `$2.694/M` output tokens compute-only and remains neither quality-adjusted nor provider-matched.

The next experiment isolates the still-untested MTP mechanism as a diagnostic paired intervention. It may be admitted after fixed SLO and artifact gates even though the frozen absolute quality screen fails, but it must retain the same 32K reasoning-off capture in both arms and require exact normalized paired identity. This can falsify a model-specific decode speedup while preserving the absolute quality failure; it cannot produce a quality-adjusted business claim.

### Nebius diagnostic MTP allocation v10 — external model-delivery failure

V10 did not test stock inference or MTP. The exact image, native runtime, telemetry, and model revision resolution passed, but anonymous Hugging Face Xet delivery failed after 34 of 52 files with an HTTP 401 from the CAS reconstruction service. The prior three allocations downloaded the same public revision successfully, so this is classified as a changed external artifact-delivery failure rather than a checkpoint identity, provider GPU, model load, quality, or MTP result.

The small failure archive was retrieved and its remote/local sidecar matched, but its typed result and full manifest contract are incomplete because execution stopped during download. MTP was not admitted. Allocation exposure was 819.208 seconds, for a derived `$0.671295096`, pending invoice. Teardown passed with zero final instances and disks. Conservative Nebius spend is `$8.144631285` of `$25`, leaving `$16.855368715`.

The changed retry disables Xet and uses the Hub's standard HTTP delivery path without adding credentials. It retains every scientific variable and diagnostic MTP gate from v10. An unchanged Xet retry is not admitted.

### Nebius HTTP diagnostic MTP allocation v11 — delivery lineage stopped

V11 changed the Hub client path by disabling Xet, but the standard HTTP client was still redirected to a signed `cas-bridge.xethub.hf.co` shard URL that returned HTTP 401 after 5 of 52 files. The preregistered delivery stop rule is met: no third model-delivery retry is admitted. This is not evidence for or against MTP, stock performance, quality, or the GPU provider.

The failure archive and traceback were retrieved before teardown. The typed result is absent because failure occurred during download. Allocation exposure was 544.223 seconds, for a derived `$0.445960184`, pending invoice. Final inventories contain zero instances and zero disks. Conservative Nebius spend is `$8.590591469` of the authorized `$25`, leaving `$16.409408531` deliberately unspent.

### Nebius campaign decision — STOP_OR_PIVOT

The terminal decision is `STOP_OR_PIVOT`, recorded in `campaign_100/DECISION_NEBIUS_2026-07-14.json`. Three valid replications place stock fixed-workload c8 throughput between 303.857 and 304.134 output tok/s with the scoped SLO passing. At `$2.95/hour`, that is analytically `$2.694-$2.697/M` output tokens compute-only. The historical `$0.88/M` anchor would require about 3.06x throughput or 67.4% lower cost at the same rate.

The campaign has no quality-adjusted point because the prospective compact absolute screen failed, and no matched Fireworks/Baseten point because no external provider control was measured. MTP remains untested; even its preregistered 5% positive gate would be far short of the current analytical gap. More identical H100 stock or artifact-delivery allocations therefore have low information value.

Resume only with a materially different cost mechanism: a quantized representation or cheaper GPU with a credible >=3x path and prospectively calibrated quality gate, or a managed exact-model provider control that can run the same workload/quality/SLO. If MTP is revisited, stage the exact artifact in authenticated storage before GPU allocation. Do not infer provider competitiveness, agent/tool-call TPOT, general model quality, or MTP performance from this campaign.

### Checkpoint completeness correction and trace-guided continuation

The user explicitly reopened the campaign. A live official-repository audit then found that the revision used by v1-v11, `75fce703...`, was not a complete checkpoint: it exposed only 44 of 48 weight shards and 57,361,582,192 weight bytes. The unchanged index already referenced all 48. The first complete commit, `33faccf4...`, adds four shards totaling 5,082,593,312 bytes and changes none of the 52 existing paths. The coordinator downloaded all 48 shards, verified 62,444,175,504 weight bytes and every SHA-256 against the official Hugging Face blob metadata, and cross-checked byte identity with ZhipuAI's official ModelScope mirror. The durable audit is `campaign_100/analysis/CHECKPOINT_COMPLETENESS_AUDIT_2026-07-14.json`.

This invalidates the prior H100 quality, throughput, and cost point as evidence for the intended complete model. V9's server log confirms that SGLang loaded only 44 discovered shards. The missing weights plausibly explain its NLL 7.708 result, but that is an inference pending a complete-checkpoint rerun. The old profiler remains diagnostic only: its batch-one decode trace attributes 27.8% of summed kernel duration to fused MoE experts, 14.8% to MoE routing/sort, 24.0% to dense GEMM/GEMV, and 18.1% to attention/MLA. Those shares identify representation and MoE routing as the strongest software leads but cannot support intended-model economics or a c8 attribution claim.

Nebius's authenticated calculator also corrects the earlier `$2.95/hour` GPU-only anchor. A regular one-H100 VM is `$3.85/hour`; its 250 GiB network SSD is `$0.0243055/hour`. Reconstructing prior exposures gives approximately `$11.281` spent before this continuation, leaving approximately `$13.719` of the authorized `$25`, pending invoices and excluding public IPv4/egress. At the full-VM rate, the malformed v9 c8 point would have implied about `$3.516/M` output tokens before disk and ancillary charges, but that figure is now diagnostic-only.

### Nebius complete-checkpoint stock allocation v12 — transfer permission failure

V12 preregistered a stock-only corrective control on the first complete commit. Before provider mutation, the coordinator rehashed all 48 local shards. The H100 VM allocated, SSH became ready, and the pinned container runtime passed. The changed model-delivery step then failed before transferring model bytes: the unprivileged SSH user could not create `/workspace/model-bf16`, so remote tar exited and the local tar process received SIGPIPE. No checkpoint load, inference, quality, throughput, SLO, profiler, or model-economic result exists.

The failure is classified as an orchestration/permission defect, not model or capacity evidence. Allocation exposure was 403.854 seconds. At the authenticated full-VM plus disk rates, derived cost was `$0.434626083` (`$0.431899451` compute plus `$0.002726632` disk), with public IPv4/egress and invoice settlement still excluded. Teardown passed: instance lookup returned not found and final instance/disk inventories were zero. Reconstructed Nebius spend is approximately `$11.715626083/$25`, leaving `$13.284373917`.

An unchanged retry is not admitted. V13 must change the transfer target or ownership, prove the write/extract path with a tiny hash-verified probe before streaming 62 GB, retain complete-checkpoint checksum enforcement, and preserve the same stock-only scientific contract.

### Nebius complete-checkpoint stock allocation v13 — fixed SLO passes; absolute quality still fails

V13 corrected remote ownership and required a tiny SHA-verified transfer probe before streaming the model. The probe passed, the 62,444,175,504-byte model transfer completed in 1,191.044 seconds, all 48 remote shard hashes matched the official complete revision, and SGLang loaded all 48 shards. The internally validated 53-file artifact was retrieved and hash-matched at `f4f6e198...9b5ab` before teardown.

The complete model passed both frozen fixed-workload service gates. C1 completed 4/4 exact 8,192-input/1,024-output requests at 87.116 output tok/s, with TTFT p50/p95 183.980/186.176 ms and ITL p50/p95/p99 7.690/7.760/8.088 ms. C8 completed 16/16 requests at 305.045 output tok/s, with TTFT p50/p95 750.236/1,358.107 ms and ITL p50/p95/p99 9.116/9.382/9.696 ms. Its c8 throughput is only 0.30% above malformed-revision v9, so checkpoint completeness did not explain the fixed-workload performance gap.

The absolute quality screen still failed, although completeness materially changed the outputs. Exact long-context retrieval (`amber-orbit-17`) and continuation (`value, low, high`) now pass, raising the compact screen from 0.000 to 0.333. Tool-call and serving JSON are semantically correct but fenced and therefore malformed under the prospective exact parser; correct code is also fenced and fails the executable-code category. Teacher-forced NLL improved only from 7.708 to 7.646 against the unchanged 2.0 ceiling. The model therefore remains ineligible for any quality-adjusted cost or provider-competitiveness claim. The absolute NLL fixture is also now recognized as an uncalibrated synthetic sentence; its threshold will not be lowered post hoc. A subsequent quantized arm may use a newly preregistered paired non-regression diagnostic against this valid complete BF16 control, while carrying the absolute failure forward.

The complete-model batch-one trace attributes 27.99% of summed decode-kernel duration to fused MoE experts, 24.26% to dense GEMM/GEMV, 17.97% to attention/MLA, 14.61% to routing/sort, 7.02% to norms, and 4.61% to copy/cast. Decode annotations have 7.893 ms p50 and 8.126 ms p95 duration. CUDA graphs are active, and the runtime falls back to a Triton 3.5.1 H100 MoE configuration because Triton 3.6 lacks the exact `E=65,N=1536` shape. These measurements bound single-kernel tuning to a modest Amdahl ceiling; a representation change that also permits a much cheaper GPU has higher information value.

Across 296 telemetry samples, measured GPU utilization averaged 32.36% and reached 100% at p95/max; VRAM averaged 48,623.6 MiB and peaked at 75,544 MiB; power averaged 188.95 W, peaked at 694.47 W, and had 369.52 W p95. The full-VM-plus-disk steady-state c8 arithmetic is `$3.52799/M` output tokens (`$3.85/hour` VM plus `$0.0243055/hour` disk), excluding setup, IPv4, egress, and invoice reconciliation. Matching the historical analytical `$0.88/M` anchor at those rates would require 1,222.95 output tok/s, or 4.009x the measured c8 throughput. This is a derived fixed-workload estimate, not a matched or quality-adjusted provider comparison.

Allocation exposure was 1,907.882 seconds, costing a derived `$2.053254722` (`$2.040373605` VM plus `$0.012881117` disk). Teardown passed with instance not found and fresh zero instance/disk inventories. Reconstructed Nebius spend is `$13.768880805/$25`, leaving `$11.231119195`, before public IPv4/egress and pending invoice reconciliation. The next allocation changes both representation and hardware: the already-audited GLM-specific AWQ loader intervention gets a bounded smoke gate on the cheapest viable Nebius L40S before any performance or paired-quality work.
