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

### Nebius L40S AWQ smoke allocation v14 — full load passes; cold-JIT watchdog rejects readiness

V14 was the first GPU execution capable of reaching the completed four-part GLM-specific AWQ loader patch. Live Nebius capacity reported eight available preemptible L40S slots, the VM reached SSH in 96.716 seconds, the tiny transfer probe passed, and the locally SHA-verified 20.17 GB checkpoint transferred in 454.976 seconds. Inside the pinned runtime, all file hashes, four-shard/byte geometry, compressed Q/KV-A metadata, native SGLang class, CUDA capability, and three patched source identities passed.

The model then loaded all four shards in 18.25 seconds. SGLang reported 17.36 GB model memory, 26.50 GB remaining after weights, and 26.29 GB after the 4,096-token KV cache. This is measured GPU evidence that the patch correctly reaches and executes its compressed KV-B dequantization/post-load path on L40S; the prior loader incompatibility is resolved for this checkpoint/runtime/device geometry. It does not yet establish correct generation, quality parity, throughput, SLO-goodput, or cost improvement.

Readiness failed for a distinct measured reason. The first L40S `sm_89` GPTQ/Marlin JIT specialization compiled for about 286 seconds; a second specialization then began. SGLang's default 300-second scheduler watchdog fired while that second compile was still active, before health or either deterministic request. The artifact records the watchdog dump attempt and a BF16-on-pre-SM90 Marlin performance warning. This is a cold-JIT/runtime-timeout interaction, not an OOM, provider capacity problem, checkpoint rejection, or observed model-output failure. An unchanged retry is not admitted; v15 changes only the scheduler watchdog to 1,800 seconds and retains the same cold placement, patch, checkpoint, deterministic requests, and smoke-only claim limit.

The 16-file failure artifact was retrieved and internally validated; remote/local SHA-256 agrees at `e726b29b...4aa3a`. Across 607 telemetry samples, GPU utilization averaged 0.22% and peaked at 34% because CPU kernel compilation dominated; VRAM averaged 16,278 MiB and peaked at 18,733 MiB; power averaged 93.72 W and peaked at 107.30 W. Allocation exposure was 1,807.984 seconds, costing a derived `$0.430964118` at authenticated preemptible VM plus disk rates. Teardown passed with instance not found and zero final instances/disks. Reconstructed Nebius spend is `$14.199844923/$25`, leaving `$10.800155077` before IPv4/egress and invoice reconciliation.

### Nebius L40S AWQ smoke allocation v15 — readiness passes; semantic smoke falsified

V15 changed only the scheduler watchdog from 300 to 1,800 seconds. It reproduced the clean four-shard load in 18.65 seconds at 17.36 GB model memory, survived both cold `sm_89` Marlin specializations, and reached health after 632 seconds in the model-load phase. The first internal warmup's measured forward duration was 574,993.51 ms, showing that the JIT dominates a genuinely cold start. This validates v14's timeout diagnosis.

The semantic smoke then failed decisively. Both identical temperature-zero, seed-bound requests returned HTTP 200 with exactly 21 prompt and 64 completion tokens, but their normalized messages differed. Both outputs were repetitive gibberish dominated by `que`, `QUE`, and HTML-escaped fragments rather than the requested JSON. Response hashes are `b7934a0d...50ca7` and `63d598fe...b522d`. Forward durations were 5,522.28 and 5,451.42 ms, or only about 11.6 output tok/s for this diagnostic c1 request. The exact GLM-specific SGLang patch plus this public AWQ checkpoint is therefore rejected for correct serving; no throughput profile, paired quality suite, profiler, SLO-goodput, or economic comparison is admitted.

This result does not by itself identify whether the public checkpoint is semantically faulty or the custom SGLang fusion/dequantization logic changes its meaning. The short prompt is unaffected by the AWQ tokenizer's separately discovered 1,024-token truncation setting, and its vocab/merges/chat template match the authoritative model, so that setting does not explain this smoke failure. The highest-information distinct control is the checkpoint author's recommended stock vLLM runtime on the same L40S geometry. A correct vLLM output would falsify the custom SGLang loader; repeated gibberish would reject the checkpoint path. Another identical SGLang retry, FP16-for-performance toggle, or benchmark is not admitted.

The 22-file artifact was retrieved and internally validated; remote/local SHA-256 agrees at `c2eb532b...244ee`. Across 678 samples, GPU utilization averaged 0.31% and peaked at 11% because CPU JIT again dominated; VRAM averaged 16,576 MiB and peaked at 18,733 MiB; power averaged 97.87 W and peaked at 119.02 W. Allocation exposure was 1,882.282 seconds, costing a derived `$0.448674410`. Teardown passed with instance not found and zero final instances/disks. Reconstructed Nebius spend is `$14.648519333/$25`, leaving `$10.351480667` before IPv4/egress and invoice reconciliation.

An offline audit also found that the existing `paired_non_regression_gate()` interprets `control - candidate` with reversed inequalities. Before any future paired claim, it must require overall regression at most 0.02 and each category regression at most 0.05; the complete BF16 NLL control implies an additional prospective AWQ ceiling of 8.027789274. No past decision relied on that helper to promote a candidate.

### Nebius L40S stock-vLLM control v16 — CUDA runtime/driver incompatibility before load

V16 changed the serving implementation to the checkpoint author's recommended stock vLLM 0.15.0 image while retaining the exact four-shard AWQ bytes and L40S class. Nebius placed the preemptible L40S, SSH became ready in 97.322 seconds, the pinned image pulled, its `nvidia-smi` probe saw the L40S, and the checkpoint transferred in 398.386 seconds. The container then failed before checkpoint verification or model load: importing Torch and calling `torch.cuda.get_device_name()` returned CUDA error 803, `system has unsupported display driver / cuda driver combination`. The host exposed driver 580.159.04 with CUDA 12.9, while this vLLM release image uses a CUDA 13 runtime. This is measured runtime-placement incompatibility, not evidence about checkpoint semantics, vLLM loading, quality, throughput, or cost per token.

The seven-file archive is hash-matched at `a9a07745...1ea2`; the typed result is absent because failure preceded model identity and telemetry startup. Allocation exposure was 900.472 seconds, costing a derived `$0.214643101` at the authenticated preemptible VM-plus-disk rates. Teardown passed with instance GET not-found and fresh zero instance/disk inventories. Reconstructed Nebius spend is `$14.863162434/$25`, leaving `$10.136837566`, excluding IPv4/egress and pending invoice reconciliation.

An unchanged image retry is not admitted. The official image exposes `VLLM_ENABLE_CUDA_COMPATIBILITY=1` for professional/datacenter GPUs with an older driver interface. The next allocation must test that switch with a sub-minute Torch/CUDA probe before transferring weights. If it passes, the already-loaded model should be retained for a preregistered conditional sequence—semantic disambiguation first, then matched quality/performance/profiling only if semantics pass—to amortize image, checkpoint, and model-load overhead without weakening fail-closed gates.
+

### Nebius L40S batched vLLM control v17 — CUDA fix passes; dependency validation rejects before transfer

V17 changed the vLLM 0.15 compatibility mechanism based on source inspection: that release predates the advertised environment switch and instead unconditionally inserts a CUDA forward-compatibility linker path. Removing its two linker entries and rerunning `ldconfig` made the exact image resolve the host driver library successfully. The retained-allocation strategy also worked once: after the first derived runtime failed, the primary driver opened the preregistered ten-minute repair window and the coordinator launched a changed repair on the same L40S rather than paying for another placement and cold image pull.

The first derived image installed the checkpoint-era Transformers source with `--no-deps`; preflight then failed because the base image's older `huggingface_hub` lacked an API required by that source. Repair 01 installed the full dependency closure and reached Transformers 5.3.0.dev0, but a blanket `pip check` rejected the environment because vLLM 0.15 declares `transformers<5` and the base image has an unrelated PyGObject/pycairo metadata defect. The checkpoint author explicitly recommends vLLM 0.15 with Transformers main for this model, so package metadata consistency is not the causal runtime gate. V17 is an orchestration-validation failure before model transfer, not evidence about checkpoint load, semantics, quality, throughput, SLO, or economics.

The recovery wrapper then tore down immediately instead of opening a second repair window. This violated the newly adopted keep-alive policy and is recorded as a harness defect. Both primary and recovery paths now share the rule: an untyped failure keeps the allocation alive for up to 600 seconds for a materially changed in-place test; a completed scientific negative result, safety/spend stop, or repair requiring more than ten minutes tears down.

No checkpoint bytes were transferred. The locally retained bootstrap, repair, event, and summary files are content-addressed in `bootstrap-evidence.sha256`; the final summary hash is `0cc97e40...85f6`. Allocation exposure was 726.896 seconds, costing a derived `$0.173268141` (`$0.171305078` compute plus `$0.001963063` disk). Cleanup passed with instance GET not-found and zero final instance/disk inventories. Reconstructed Nebius spend is `$15.036430575/$25`, leaving `$9.963569425`, excluding IPv4/egress and pending invoice reconciliation.

V18 removes only the invalid blanket metadata gate and replaces it with targeted checks of the exact Transformers source version, GLM AutoConfig registration, vLLM's GLM loader module, vLLM import, host-driver CUDA execution, and a real GPU tensor. It retains the one-allocation conditional semantic, paired-quality, fixed c1/c8 SLO, economics, and trace sequence. This is a materially changed validator, not an unchanged retry.
+

### Nebius L40S stock-vLLM batched control v18 — semantic control passes; quality observer stops before performance

V18's targeted preflight passed before transfer: the derived image imported vLLM 0.15.0 and Transformers 5.3.0.dev0, registered `glm4_moe_lite`, resolved the native vLLM GLM loader, executed a real CUDA tensor through the host-driver library, and identified one L40S with compute capability 8.9. The 20.17 GB checkpoint transferred once in 455.986 seconds and all four shard hashes matched remotely.

The first in-container run then exposed a harness-only identity defect: awk rendered the exact 20,170,199,928-byte shard sum in scientific notation, so string equality rejected it. The allocation stayed alive. Repair 01 was preregistered, changed only the formatter to `printf "%.0f"`, passed 134 tests, and restarted from the cached image and already-transferred checkpoint four minutes after classification. No second placement, image pull, or checkpoint transfer occurred.

The changed identity gate passed. Stock vLLM resolved `Glm4MoeLiteForCausalLM`, loaded all four shards in 10.84 seconds, reported 17.87 GiB model memory, and selected Marlin WNA16 dense kernels, Marlin compressed-tensors MoE, and Triton MLA attention. Model-load phase time, including compile and CUDA-graph capture, was 108 seconds.

Most importantly, the semantic disambiguation passed. Two temperature-zero, seed-bound requests both normalized to the requested `{"alpha":17,"beta":"smoke"}`; both used 24 prompt and 22 completion tokens and their normalized messages were identical. Raw response hashes differ because request IDs and timestamps differ, but the measured semantic content and tool/reasoning fields match. This falsifies the public AWQ checkpoint as a sufficient explanation for V15's gibberish and strongly implicates the custom SGLang AWQ loader/kernel path. It does not yet prove which custom patch component is wrong.

The subsequent quality observer requested teacher-forced prompt logprobs from `/v1/completions` but read `prompt_token_ids` and `prompt_logprobs` from the top-level response. vLLM 0.15 returns both on the first completion choice, so the observer stopped before scoring or performance. The recovery driver then mislabeled the typed wrapper as `SCIENTIFIC_FAIL` and deleted without opening another repair window. This is an orchestration-policy defect: an embedded harness error is not a completed scientific negative result. Both primary and recovery drivers now inspect nested error state before teardown, and quality failure no longer suppresses the already-sunk fixed-performance arm.

The 24-file artifact is internally validated and remote/local SHA-256 agrees at `56fcf609...9f18c`. Across the 210 repair-run telemetry samples, GPU utilization averaged 5.60% and peaked at 100%; VRAM averaged 8,520 MiB and peaked at 44,899 MiB; power averaged 73.03 W and peaked at 351.26 W. These include identity hashing and startup and are not serving-utilization estimates. Allocation exposure was 1,547.821 seconds, costing a derived `$0.368949945`. Cleanup passed with instance GET not-found and zero final instances/disks. Reconstructed Nebius spend is `$15.405380520/$25`, leaving `$9.594619480`.

V19 changes only the source-confirmed completion-choice logprob parser and error isolation. It retains the proven stock-vLLM semantic path and batches paired quality, c1/c8 fixed SLO/economics, and conditional tracing after one setup cycle.


### Nebius retained L40S AWQ arm v19 — paired quality and fixed SLO pass; $0.693/M derived

V19 corrected the vLLM completion-choice prompt-logprob parser and retained the L40S after evidence retrieval. Its one-shot owner completed preflight and transferred the checkpoint in 436.101 seconds; a preregistered ownership handoff then ran the scientific arm from the resident image and checkpoint and deliberately kept the VM for the next arm.

Stock vLLM again passed deterministic semantic JSON. The paired compact screen matches complete BF16 exactly at 0.333 overall with zero category regression. AWQ teacher-forced NLL is 7.6300 versus BF16 7.6455 and passes the prospective 8.0278 ceiling. Both representations still fail the absolute compact gate, so this is paired non-regression evidence only, not a general quality or provider-competitiveness claim.

C1 completed 4/4 exact 8,192/1,024 requests at 59.181 output tok/s, TTFT p95 580.93 ms, TPOT p95 16.446 ms, and negligible mean queue time. C8 completed 16/16 at 344.211 output tok/s, TTFT p95 4,904.01 ms, TPOT p95 20.500 ms, and 595.4 ms mean server queue time. Both SLOs passed with prefix caching disabled and zero query/hit deltas.

At the authenticated L40S VM-plus-disk rate, c8 analytically implies `$0.692503/M` output tokens. On the exact fixed geometry this is 80.4% below V13 complete BF16 H100's `$3.52799/M`, while throughput itself is 12.84% higher. This is a matched campaign representation/hardware result, not a matched Fireworks/Baseten result and not yet a custom co-design gain.

The admitted 13.95 MB PyTorch trace is hash-bound at `b75a0445...434a`. Summed GPU event duration is led by `_fwd_grouped_kernel_stage1` at 36.53%, BF16 GEMV families at about 15%, flash prefill at 6.18%, Marlin MoE kernels at about 13.6%, and Marlin dense kernels at about 9.4%. Because the traced request includes 8K prefill plus 128 decode tokens, these shares are mixed-phase diagnostics rather than pure decode attribution.

The 39-file artifact is internally validated and hash-matched at `fe546ceb...02f8c`. Across 411 arm samples, utilization averaged 34.96% and reached 100% at p95/max; VRAM averaged 25,502 MiB and peaked at 44,899 MiB; power averaged 128.86 W and peaked at 333.11 W. Exposure through artifact retrieval was 1,400.426 seconds for a provisional derived `$0.333815732`; final session cost remains open while the retained VM is running. The next immediate arm changes only activation dtype from BF16 to FP16, testing vLLM's measured pre-SM90 Marlin warning on the resident image/checkpoint.

### Nebius retained L40S AWQ FP16 arm v20 — dtype hypothesis falsified

V20 reused the exact V19 L40S, runtime image, checkpoint bytes, tokenizer, quality suite, server flags, and request geometry, changing only vLLM activation dtype from BF16 to FP16. Deterministic semantic JSON and paired quality passed again: overall score remained 0.333 with zero category regression and NLL was 7.6375 versus the BF16 control's 7.6455. The absolute compact quality failure remains unchanged.

FP16 completed all exact requests and passed both SLOs, but performance regressed. C1 was 58.600 output tok/s versus V19's 59.181 (-0.98%). C8 was 334.406 versus 344.211 (-2.85%), with TTFT p95 5,026.29 ms, TPOT p95 21.445 ms, and mean server queue 864.3 ms. Derived steady-state cost worsened from `$0.692503/M` to `$0.712807/M`. The preregistered useful threshold was at least +5% c8, so FP16 is rejected and BF16 remains the control.

The FP16 trace is hash-bound at `15939089...3fd8`; `_fwd_grouped_kernel_stage1` remained the largest named GPU event family at 25.49%, while FP16 GEMV plus launch/synchronization overhead remained material. This falsifies the simple interpretation that BF16 arithmetic was the principal removable pre-SM90 bottleneck. The 39-file arm artifact is internally validated and hash-matched at `4703691b...58f`. Across 414 samples, utilization averaged 35.42%, VRAM averaged 25,583 MiB and peaked at 44,899 MiB, and power averaged 130.06 W and peaked at 348.7 W.

The retained-arm exposure was 503.150 seconds and derived `$0.119934495`; the VM remains live for one serving-geometry falsification. V21 returns to BF16 and changes only `max_num_batched_tokens` from 32,768 to 65,536 so all eight 8K prefills can be scheduled in one token-budget wave. It is accepted only if c8 improves by at least 5% without quality, exact-geometry, or SLO regression.

### Nebius retained L40S AWQ 65K scheduler arm v21 — small serving gain below promotion threshold

V21 returned to BF16 and changed only the vLLM scheduler token budget from 32,768 to 65,536. Deterministic semantic JSON, paired compact quality, exact request geometry, both SLOs, and zero prefix-cache deltas passed. C1 was effectively unchanged at 59.231 output tok/s (+0.08% versus V19). C8 improved from 344.211 to 355.772 output tok/s (+3.36%) and derived cost fell from `$0.692503/M` to `$0.670000/M`.

Mean c8 server queue time fell from 595.4 ms to 0.013 ms, but TTFT p95 was roughly flat at 4,951.38 ms and TPOT p95 improved to 18.789 ms. This means the larger scheduler budget removed measured queueing but did not turn all of that latency reduction into end-to-end throughput. The preregistered useful threshold was +5% c8, so V21 is a small tuned-serving improvement and the best observed point, not a promoted material gain.

The 39-file artifact is internally validated and hash-matched at `001dd8a5...d8b30`; its trace is `faede248...bfa9`. Across 410 samples, utilization averaged 35.47%, VRAM averaged 25,257 MiB and peaked at 44,795 MiB, and power averaged 129.17 W and peaked at 332.78 W. Arm exposure was 627.722 seconds for derived `$0.149628439`. The instance remains retained for V22, which keeps the V21 tuned server and changes one source-pinned parameter in the trace-dominant Triton MLA grouped decode kernel: `BLOCK_N=32` to `64`.

### Nebius retained L40S MLA tile v22 — measured shared-memory infeasibility

V22 source-pinned vLLM's grouped MLA decode kernel and changed exactly one occurrence of `BLOCK_N=32` to `64`. Model load and CUDA-graph capture passed, but the first semantic request triggered Triton compilation of the affected decode shape and failed before a response: the 64-token tile required 159,744 bytes of shared memory against the L40S limit of 101,376 bytes. The 22-file failure artifact is hash-matched at `576626d4...e16d4`. This is measured hardware/kernel feasibility evidence, not semantic or performance evidence.

The allocation remained live. Repair V22R1 follows Triton's causal diagnostic and changes the 64-token candidate's pipeline stages from 2 to 1, which is expected to reduce shared-memory demand while preserving the larger tile. The stock V21 control remains `BLOCK_N=32`, two stages.

### Nebius retained L40S MLA tile repair v22r1 — feasible but 4.21% c8 regression

V22R1 changed the candidate's grouped-decode pipeline stages from two to one while retaining `BLOCK_N=64`. The source-pinned one-occurrence patch is hash-bound before and after; the model loaded, the formerly failing decode executed, deterministic semantic JSON passed, paired compact quality passed at NLL 7.6300, and all exact c1/c8 requests passed the SLO with zero prefix-cache deltas.

The feasible candidate nevertheless regressed. C1 reached 58.682 output tok/s versus V21's 59.231 (-0.93%). C8 reached 340.791 versus 355.772 (-4.21%), and derived cost worsened from `$0.670000/M` to `$0.699452/M`. The trace-dominant grouped kernel still accounted for 25.72% of mixed profiler GPU duration, so the larger tile did not remove the bottleneck. The candidate and this direct kernel lineage are rejected.

The 40-file artifact is internally validated and hash-matched at `e3a7eb4f...14a12`; trace hash is `4f3f636e...c7d60`. Across 411 samples, utilization averaged 35.79%, VRAM averaged 25,003 MiB and peaked at 44,955 MiB, and power averaged 131.86 W and peaked at 341.48 W. Arm exposure was 566.027 seconds for derived `$0.134922392`.

Final retained-session cleanup passed: instance `computeinstance-e00wfcpr1va34g7tvd` returns not-found and fresh inventories contain zero instances and zero disks. Conservative session exposure was 4,451.142 seconds and derived VM-plus-disk cost `$1.061006497`. Campaign spend is `$16.466387017/$25`, leaving `$8.533612983`, excluding IPv4/egress and pending invoice reconciliation.

Decision: `CONTINUE_NARROWLY`, content-addressed at `afc33c57...8cbe2`. Public AWQ plus cheaper L40S hardware has a quality-paired, SLO-passing campaign signal, with the best tuned point at 355.772 tok/s and derived `$0.670000/M`; however, both representations fail the absolute compact quality gate, no provider-matched comparison exists, and neither FP16 nor the first model-specific MLA tile beats the tuned general stack. No custom co-design or provider cost advantage is claimed.

Exact next experiment: a correctness-checked standalone microbenchmark of vLLM's pinned grouped MLA decode kernel at GLM's exact 20-head/512-latent/256-value long-context shapes. Sweep only hardware-legal tile, warp, stage, and KV-split configurations. A >=10% component lead admits a true c8 phase trace; no end-to-end prediction is valid until that trace or an empirical matched A/B supplies scope-matched evidence.

### Nebius L40S MLA microbenchmark v23 — proactively invalidated before science

V23 allocated the cheapest no-weights L40S geometry and reached SSH in 82.527 seconds. While the pinned image was still bootstrapping, a local oracle audit found that the FP32 reference flattened complete 16-token KV pages but did not mask padding after each exact sequence length. Because all five preregistered lengths are nonmultiples of 16, this would have compared the kernel's length-bounded result with a reference that included random padded tokens and could falsely reject stock.

The coordinator interrupted before the harness or any candidate kernel ran. No artifact, correctness, latency, resource, telemetry, performance, or scientific result exists. This is a proactive harness invalidation, not evidence for or against MLA. Cleanup passed: instance GET returned not-found and fresh inventories contained zero instances and disks. Exposure was 119.007 seconds and derived cost was `$0.025088137`, bringing conservative Nebius spend to `$16.491475154/$25` and leaving `$8.508524846`, excluding IPv4/egress and pending invoice reconciliation.

V23R1 masks all physical-page positions beyond `sequence_lengths` before the FP32 softmax, adds a regression test for nonmultiple final pages, and changes no candidate space, stock kernel, hardware, timing gate, or scientific hypothesis. This is a materially changed oracle repair, not an unchanged retry.

### Nebius L40S exact-shape MLA microbenchmark v23r1 — eight KV splits are a 40.27% component lead

V23R1 executed the repaired no-weights sweep on one L40S. The pinned stock vLLM grouped MLA configuration and every legal candidate were tested at batch sizes one and eight for sequence lengths 8,193, 8,449, 8,705, 8,961, and 9,215 with the absorbed GLM geometry: 20 query heads, 576-wide query/key, parent-strided 512-wide value, 16-token pages, BF16 inputs, and shuffled physical pages. Stock passed the padding-masked independent FP32 output/LSE oracle on all ten shapes.

The sweep evaluated 58 configurations over head tile, sequence tile, warps, stages, and KV splits. Six BLOCK_H=32 configurations were resource-illegal on all ten shapes, producing 60 retained `OutOfResources` rows; 520 candidate-shape rows were hardware-legal. The strongest candidate changed only KV splits from four to eight while retaining BLOCK_H=16, BLOCK_N=32, four warps, and two stages. It passed correctness on every shape. Across all five B8 lengths, its conservative worst-case stage-1 reduction was 41.39% and its conservative worst-case complete grouped-attention reduction was 40.27%. At B8/9,215 tokens, stock full-attention p50 was 186.080 microseconds versus 109.792 microseconds for eight splits; at B8/8,193 it was 168.064 versus 100.384 microseconds. Maximum observed output absolute error for those B8 candidate points was approximately 0.00104 and LSE absolute error approximately 0.03124 under the shared prospective tolerance. A later harness audit found that V23R1 retained only aggregate timing summaries and timed candidates in fixed blocks rather than retaining randomized/interleaved raw stock-candidate samples and compile-resource metadata. The large lead remains sufficient to admit the empirical server falsifier, but it is single-run aggregate component evidence, not a stability interval.

This is a measured exact-shape L40S component result, not an end-to-end result. The prior 37.38% mixed c1 summed-duration diagnostic remains prohibited as an Amdahl coefficient; `promotable_candidate` is deliberately null. The component lead only admits a true synchronized fixed-8K/128 c8 trace and then an empirical matched server A/B if the runtime uses the intended eight-split launch.

The scientific sweep took 137.952 seconds. Its 135 phase-aligned one-second telemetry samples measured mean/p95/max GPU utilization 21.96%/98%/100%, mean/p95/max VRAM 698/1,077/1,131 MiB, and mean/p95/max power 114.78/215.34/259.70 W. P50 utilization was zero because compilation and candidate transitions were host-bound; the GPU was saturated in active bursts. The reusable telemetry tool now records and corrects the observed driver-local timestamp offset, and future harnesses force `TZ=UTC` at capture.

The 13-file remote artifact is internally validated and remote/local SHA-256 agrees at `cccaab68...79804c`; the locally derived phase telemetry summary is `373935fa...a000`. Allocation exposure was 712.733 seconds and derived cost was `$0.150252487`. Teardown passed with instance GET not-found and zero final instances/disks. Conservative Nebius spend is now `$16.641727641/$25`, leaving `$8.358272359`, excluding IPv4/egress and pending invoice reconciliation.

Next action: patch only vLLM's source-pinned non-batch-invariant `num_kv_splits` default from four to eight, run the tuned V21 stock control with a true synchronized c8 profiler capture, validate that grouped-MLA launches have grid batch dimension eight, then run alternating/repeated server control versus candidate only if the trace and component evidence remain scope-consistent. No cost claim is admitted before semantic, paired quality, exact geometry, SLO, and empirical throughput pass.

### Nebius retained split A/B session v24 — wrong tokenizer staging invalidates A1 before load

V24 created the strict L40S session, passed CUDA/Transformers preflight, hash-probed the transfer path, transferred and verified the 20.17 GB AWQ checkpoint once, and applied the source-pinned four-split stock patch as an exact no-op. The first stock arm then failed in model identity before load because the coordinator staged the AWQ repository's tokenizer files instead of the campaign's authoritative complete-BF16 tokenizer. All checkpoint hashes and the quality-suite identity passed; the three measured tokenizer hashes exposed the mismatch before model load.

No semantic, quality, performance, SLO, trace, or scientific result exists for A1. The 13-file failure artifact was retrieved, internally validated, and remote/local hash-matched at `8509e7bc...700a`. The instance, pinned runtime, and verified checkpoint remain retained under the original independent watchdog. Exposure through failure classification was 1,051.439 seconds and provisional full-session cost was `$0.250628572`; this will be superseded by final session reconciliation. V24R1 changes only the staged tokenizer directory to the source-verified complete-BF16 tokenizer and reuses the resident runtime/checkpoint. The failure is a coordinator invocation defect, not a split or model result.

V24R1 corrected only the tokenizer staging and produced a valid stock performance point: c1 57.841 output tok/s and c8 364.105 output tok/s, with exact geometry, zero prefix-cache deltas, negligible queueing, TTFT p95 4,796.56 ms, TPOT p95 17.926 ms, and all fixed SLOs passing. Derived steady-state arithmetic is `$0.654667/M` at the authenticated VM-plus-disk rate. This is a useful repeated stock measurement, 2.34% above V21, not a candidate effect.

The compact paired quality gate failed because the long-context response was `K-4702: amber-orbit-17` rather than exact `amber-orbit-17`; it contains the requested key but fails the prospectively frozen exact scorer. Overall fell from the complete-BF16 control's 0.333 to 0.167 while NLL remained non-regressed at 7.6300. The failure correctly blocks a quality-adjusted claim, but it also suppressed the observer-only profiler, leaving no true c8 trace. The 38-file artifact is hash-matched at `3228eb76...fc9f`; provisional arm exposure was 373.566 seconds and `$0.089045883`. The instance remains retained.

The next amendment does not recalibrate the frozen quality gate. It carries that failure forward, measures session-local output identity/NLL as a diagnostic only, decouples observer admission from business quality, and uses a content-addressed checkpoint integrity marker after one full verification so repeated arms spend time on inference rather than rehashing unchanged weights. No result from this amended sequence can establish general or provider-matched quality-adjusted cost.

### Nebius retained split stock trace v24r2 — true c8 geometry and grid validated

V24R2 reused the retained L40S, pinned runtime, checkpoint, and authoritative tokenizer, changing only observer admission and checkpoint verification. Its first marker creation still performed the complete 20.17 GB hash check; later arms can reuse the marker only while both the manifest digest and filename/size/mtime fingerprint remain identical. Semantic JSON, exact performance geometry, fixed SLOs, and the paired diagnostic passed. C1 measured 59.037 output tok/s. C8 measured 364.871 output tok/s, TTFT p95 4,800.77 ms, TPOT p95 17.874 ms, mean queue 0.0156 ms, and derived `$0.653293/M`. The absolute compact point screen still fails and no provider or quality-adjusted claim is admitted.

The observer captured eight barrier-synchronized 8,192-input/128-output requests and a 15.14 MB trace hash-bound at `bd57a18...c4eff`. Independent validation passed: 5,922 of 6,016 grouped-MLA stage-one launches (98.44%) used the intended c8 grid `(8,2,4)`, with the stock 202-register/89,088-byte shared-memory signature. The remaining 94 launches used batch dimensions two or six. Summed duration is retained only as a diagnostic; the trace does not yet provide non-overlapping phase wall-time or an Amdahl coefficient. The validator result is hash-bound at `c7e6550b...a4fdd`.

The immediately preceding stock arm failed the long-context exact screen while V24R2 passed it, despite identical model, checkpoint, runtime flags, seed, and scorer. This is measured output/scorer instability and limits the quality evidence; it is not averaged into a pass. The 41-file artifact is internally validated and remote/local SHA-256 agrees at `b89016cd...c9e79`. Phase-scoped science telemetry measured 216 samples with GPU utilization mean/p95/max 64.94%/100%/100%, VRAM mean/p95/max 42,543/42,827/42,827 MiB, and power mean/p95/max 188.52/321.98/331.67 W. V24R2 arm exposure was 453.299 seconds and provisional `$0.108051641`; final session reconciliation will supersede overlapping arm estimates. The instance remains retained for a prospectively amended diagnostic split-8 bracket.

### Nebius retained split-8 candidate v25r1 — large component change, only 0.81% initial c8 gain

V25R1 changed only the source-pinned non-batch-invariant grouped-MLA KV split count from four to eight on the retained L40S. The integrity marker matched in approximately one second, avoiding the previous 97-second full checkpoint rehash. Semantic JSON, the paired diagnostic, exact geometry, cache gate, and fixed SLO passed. C1 measured 58.557 output tok/s, 0.81% below V24R2 stock. C8 measured 367.829 output tok/s, 0.81% above V24R2's 364.871 before the required adjacent A2 control; TTFT p95 was 4,847.78 ms, TPOT p95 17.664 ms, mean queue 0.0125 ms, and derived arithmetic `$0.648038/M`.

Independent trace validation passed and proved the intervention executed: 5,922/6,016 grouped stage-one launches used grid `(8,2,8)`, versus stock `(8,2,4)`. The candidate's summed c8 grouped-stage duration was 699,605 microseconds versus stock 1,055,044 microseconds, a 33.69% diagnostic reduction; because this is overlapping summed profiler work, it is not wall-time share or a serving prediction. A vLLM-aware annotation parser further measured decode-region summed spans of 3,999.08 ms stock versus 4,014.31 ms candidate (+0.38%), even while summed attention/MLA kernel work fell from 1,073.25 to 714.43 ms (-33.43%) and all summed decode kernel work fell 14.09%. Dense GEMM/GEMV work was flat at about 733 ms. This is not a dependency-union critical path, but the unchanged execution-region span directly shows the saved MLA work is overlapped or replaced by another constraint. Region analyses are hash-bound at `7c56b418...f80ad` stock and `521d598b...06187e` candidate. A2 is required to separate request-level drift.

The 41-file artifact is internally validated and hash-matched at `9ce5d882...3eb2e9`; trace validator hash is `5e79e6c...efad9`. Science telemetry had 217 samples and 97.31% expected one-hertz coverage with no gap over two seconds. GPU utilization mean/p95/max was 52.75%/100%/100%, VRAM 42,935/44,795/44,807 MiB, power 187.79/318.84/332.66 W, and integrated phase energy 41.64 kJ. Arm exposure was 359.628 seconds and provisional `$0.085723627`; the retained A2 control is already running.

V26R1 restored stock four splits for the adjacent A2 control and passed all diagnostic gates. C1 measured 59.165 output tok/s and c8 363.161 output tok/s, with c8 TTFT p95 4,908.51 ms, TPOT p95 17.903 ms, mean queue 0.0131 ms, and derived `$0.656368/M`. Bracketing B1 by A1 and A2 gives a drift-adjusted c8 effect of **+1.05%**, far below the prospective 5% gate. The 41-file artifact is hash-matched at `1deb1968...15af80`; trace validation hash is `9e23fb2c...0db97`. Science telemetry covered 215 samples at 96.85% expected one-hertz coverage, with 65.08% mean GPU utilization, 42,753 MiB mean VRAM, 189.99 W mean power, and 41.74 kJ phase energy. Provisional arm exposure was 356.881 seconds and `$0.085068704`. The second split-8 replication is running because the fixed amended sequence requires both bracketed effects before the terminal split decision.

V27R1 repeated split eight and passed semantic, paired diagnostic, exact geometry, SLO, cache, and trace gates. C1 measured 57.999 output tok/s and c8 364.077 output tok/s, with TTFT p95 4,859.77 ms, TPOT p95 17.911 ms, mean queue 0.0129 ms, and derived `$0.654717/M`. The 41-file artifact is hash-matched at `b2e58997...0f225b`; trace validation hash is `0f543080...fbbb5`. Science telemetry covered 219 samples at 97.33% expected one-hertz coverage, with 51.39% mean GPU utilization, 42,545 MiB mean VRAM, 188.12 W mean power, and 42.13 kJ phase energy. Provisional arm exposure was 356.750 seconds and `$0.085037451`. Final stock A3 is running and owns verified teardown.

V28R1 restored four-split stock for A3 and passed all gates at 58.359 c1 and 357.464 c8 output tok/s. C8 TTFT p95 was 4,826.09 ms, TPOT p95 18.754 ms, mean queue 0.0133 ms, and derived `$0.666829/M`. The 41-file artifact is hash-matched at `25548ed7...969dbd`; trace validation hash is `22edc48d...ab28c8`. Science telemetry covered 218 samples at 97.32% expected one-hertz coverage, with 64.54% mean GPU utilization, 42,970 MiB mean VRAM, 180.50 W mean power, and 40.25 kJ phase energy.

The two drift-corrected split-8 c8 effects are **+1.0476%** and **+1.0447%**, median **+1.0461%**. The descriptive bracket analysis is hash-bound at `4bbe7da2...fd4de` and deliberately reports no bootstrap interval because only two independent candidate repetitions exist. Both effects are positive but far below the 5% materiality gate, so the eight-KV-split lineage is stopped. The result is stronger than a simple null: the intervention verifiably cut summed attention/MLA profiler work by 33.43% and all summed decode kernel work by 14.09%, while decode annotation span changed +0.38%. That falsifies the assumption that this large component win controls the current end-to-end path.

Final cleanup passed. Instance `computeinstance-e00ryn9r7gcjnecedr` returns not-found and fresh inventories contain zero instances and disks. Full session exposure was 4,257.181 seconds and derived VM-plus-disk cost `$1.014772742`, superseding every provisional arm estimate. Conservative Nebius campaign spend is `$17.656500383/$25`, leaving `$7.343499617`, excluding IPv4/egress and pending invoice reconciliation.

Decision: **CONTINUE_NARROWLY** for the overall research campaign and **STOP** for eight MLA KV splits, content-addressed at `e51b5324...31131`. Dense GEMM/GEMV is the largest residual measured decode family, but the causal resource constraint remains unknown because dependency-union wall time, profiler perturbation, host scheduling, and deep HBM/L2/occupancy counters are missing. The next GPU dollar is not another guessed kernel flag: first calibrate the prospective quality holdout off GPU, then add a matched profiler-off/on vLLM phase trace with Nsight Systems, available DCGM utilization/memory-controller/power/energy fields, host/scheduler timing, attribution coverage, and explicit unavailable counters. Only that resource signature can admit a dense/MoE exact-shape intervention. No provider or quality-adjusted cost advantage is claimed.

### Factory bootstrap and zero-cost falsification cycle

The completed campaign ledger was replayed into the repository's new research factory without promoting legacy claims. A deep content audit passes for all 22 currently referenced artifacts, and the provider inventory remains empty. The factory budget ledger carries `$25.000000` authorized and `$17.656501` settled, leaving `$7.343499` available after integer-microdollar normalization. This is coordinator state, not an invoice reconciliation.

Four zero-cost scouts were completed before admitting another GPU. First, all 10 archived AWQ compact scores were reproduced, but one of four nominal stock pairs changed the long-context retrieval decision from 1/6 to 2/6 while teacher-forced NLL remained exactly 7.6300405363. The archived paired scorer is therefore not repeat-stable enough to support a quality-adjusted cost claim. A prospective 120-fixture synthetic calibration did establish scorer mechanics: three response representations reproduced 120/120 across three runs, 30/30 negative controls were rejected, a 4% NLL increase passed and 6% failed, and one category flip passed while two same-category flips failed. A separately preregistered content scout then authored 18 development fixtures, exactly three in each of six serving-relevant categories; all 18 positive vectors scored 1.0 and all 18 targeted adversarial negatives scored 0.0 on deterministic replay. Those are content/oracle and synthetic calibration measurements only; they are not GLM quality evidence, and stock repeatability plus a disjoint holdout remain unmeasured.

Second, checkpoint headers show that the public AWQ representation leaves 46 repeated shared-expert MLP blocks in BF16: 868,220,928 bytes, or 4.305% of the checkpoint. A first loose trace ceiling for W4 on layers 5-42 was corrected after launch-shape attribution. The defensible structural range is 3.563%-5.601% of decode annotation span, straddling the 5% campaign gate. Applying the observed split-8 component-to-server transfer as a skepticism calibration predicts only 0.898%-1.292% end-to-end effect for the middle-layer policy. That transfer is cross-mechanism analytical evidence, not a hard bound.

Third, replay of the retained raw c8 trace measured 12,448 target launches and 511.375 ms of target duration with 99.642% decode-phase coverage and 100% CUDA correlation. It reproduced the prior 509.544 ms decode target exactly, but only 0% of target duration had explicit module/layer ownership. CUDA Graph replay preserved useful correlation while collapsing unique model identity. Shape/cardinality evidence is consistent with shared experts but does not meet the preregistered 90% attribution gate. The existing trace therefore falsifies evidence sufficiency, not the representation mechanism.

These results keep the campaign at **CONTINUE_NARROWLY** and change the exact next experiment. The next paid allocation is diagnostic-only: one retained L40S running a fixed off/on/off c8 observer bracket, with request-to-scheduler-to-NVTX-to-CUDA correlation, CUDA Graph node identity, operator/shape attribution where the runtime preserves it, host scheduling, GPU/VRAM/power telemetry, and a prospective perturbation gate. It cannot score a model candidate or establish a cost improvement. A representation or dense-kernel arm is admitted only if this observer run identifies dependency-critical work and preserves enough ownership to name the intervention.

### Nebius L40S observer diagnostic allocation v31 — Nsight repository-key preflight failure

The factory admitted one diagnostic-only retained L40S allocation for the preregistered A1 observer-off / B1 Nsight-on / A2 observer-off bracket. The exact workload was eight barrier-synchronized requests per arm at c8, 8,192 input tokens and 32 output tokens, after an excluded matching 16-output-token warmup. The causal gate permitted at most 3% absolute throughput and median-latency perturbation and 5% p95-latency perturbation. This allocation could not score a model intervention or support a quality, economics, or provider comparison claim.

Immediately before creation, deep verification passed for 30 factory references and Nebius inventory contained zero instances and zero disks. The factory reserved `$0.55`, including a `$0.07` cleanup reserve, under a 2,000-second hard watchdog. The provider resource and boot disk were durably labeled with the exact program, campaign, and run identities, and the allocation was registered in the factory.

The host passed the pinned vLLM, Transformers, CUDA, driver, and GLM-native-module probes on an L40S with 46,068 MiB VRAM: vLLM 0.15.0, Torch 2.9.1+cu129, CUDA 12.9, driver 580.159.04, and the intended Transformers development revision were observed. The subsequent Nsight image build rejected the NVIDIA devtools repository with `NO_PUBKEY F60F4B3D7FA2AF80`. The bootstrap had used the unrelated CUDA repository key `3bf863cc.pub`. This was an operational preflight failure before any checkpoint bytes, model load, inference request, or science arm, so it yields no quality, SLO, performance, bottleneck, provider, or cost-per-token evidence.

Measured allocation exposure was 513.467 seconds. Derived compute cost was `$0.121007156` and disk cost `$0.001386676`, for `$0.122393832` total, excluding public IPv4, egress, and pending invoice reconciliation. The evidence was retrieved and packed before teardown at factory bundle SHA-256 `596269cc2cf239093952e895cd8ff88e721ef40997b3fab505c6d20b36f5f6c8`; its cost object is `97217b1e10c9773dfb12b3b6e4eb9c221c701bd530fb8fd6196900aea4528b74`. Direct instance lookup returned not-found, labeled final instance and disk inventories were zero, and a fresh provider inventory was empty. The factory marked cleanup verified and settled the run as `operational_failure`, leaving `$7.221105` in its integer-microdollar campaign ledger.

An unchanged retry is not admitted. V32 changes only the failed bootstrap and immutable run identity: it retrieves the NVIDIA devtools key, verifies the complete fingerprint `AE09FE4BBD223A84B2CCFCE3F60F4B3D7FA2AF80`, and uses the Ubuntu 22.04 devtools repository matching the runtime base. A clean local Ubuntu 22.04 build installed and executed the exact pinned `NVIDIA Nsight Systems version 2026.3.1.157-263138048394v0`. The scientific observer contract remains unchanged.

### Nebius L40S observer diagnostic allocation v32 — stale status-text preflight failure

The factory admitted the operationally amended diagnostic under immutable run `glm47-observer-diagnostic-l40s-v2`, exact paid-spec SHA-256 `562e39e3c00598deb9b417d3d19441cb5f59a64d04af4502ad4c39f3aabebaf1`, and a `$0.55` reservation including `$0.07` cleanup reserve. Immediately before admission, deep verification passed for 31 factory references and fresh Nebius inventory measured zero instances and zero disks. The single preemptible L40S and boot disk were labeled with the exact program, campaign, and run identities, the provider resource was registered in the factory, and the independent 2,000-second deletion watchdog was active.

V32 passed the exact repair that v31 was designed to test. The complete signing-key fingerprint matched, the Ubuntu 22.04 devtools repository signature was accepted, and the exact 215 MB package installed. The on-host L40S then executed Nsight Systems `2026.3.1.157-263138048394v0`; `nsys status -e` reported root privilege enabled, kernel paranoid level 0, `perf_event_open` available, sampling trigger available, and `CPU Profiling Environment (process-tree): OK`. The harness nevertheless required the obsolete literal `Sampling Environment: OK`, so `set -e` stopped before the remaining help/trace/export probe. This is a second operational preflight failure, not evidence that profiling is unavailable. No checkpoint bytes were transferred and no model load, inference request, quality gate, SLO, performance arm, or bottleneck measurement occurred.

Measured allocation exposure was 587.086 seconds. Derived compute cost was `$0.138356582` and disk cost `$0.001585491`, for `$0.139942073` after line-item summation, excluding public IPv4, egress, and pending invoice reconciliation. Direct lookup returned not-found, final labeled instance and disk inventories were zero, and fresh provider inventory was empty. The factory bundle is `1257e0783d719a26f47c3fde0feb2246fb6578ad23f46e45732d71ddc049c611`, the cost object is `f994e43dc68ad6cc819711bb4c01b95503a89d25053868b1ef82dbbe7225ef67`, cleanup is verified, and the settled integer-microdollar ledger leaves `$7.081162` available.

An unchanged retry is not admitted. V33 changes the compatibility assertion to the exact measured Nsight 2026.3 process-tree status text and preserves the v32 output as its fixture; local inspection also verified that the installed 2026.3.1 binary exposes every requested flag. The remaining actual CUDA Graph/GPU-metrics trace and export still must pass on the target L40S before checkpoint transfer. The scientific observer contract remains unchanged.

### Nebius L40S observer diagnostic allocation v33 — L40S GPU Metrics unsupported

The factory admitted immutable run `glm47-observer-diagnostic-l40s-v3` at exact paid-spec SHA-256 `7da7f17c7cdd7f3e18708b6c6a6646032d76b6e6964dab2772517531646432b8`, reserving `$0.55` including `$0.07` cleanup reserve. Immediately before admission, 32 deep artifact references passed and fresh Nebius inventory measured zero instances and zero disks. The single labeled preemptible L40S resource was factory-registered and protected by the independent 2,000-second deletion watchdog.

V33 passed the v32 status compatibility check and every requested profiler flag was present. Its actual target-hardware probe then failed with `None of the installed GPUs are supported` when Nsight evaluated `--gpu-metrics-devices=all`. Thus Nsight Systems GPU Metrics is unavailable on this L40S/runtime combination. This is measured collector capability evidence, not a general statement about the L40S, CUDA tracing, or provider health. CUDA/NVTX/OSRT, node-level graph, and process-tree collectors were accepted by the command parser, but the invalid GPU Metrics selection stopped before their probe completed. No checkpoint bytes were transferred and no inference or science arm ran.

Measured exposure was 529.517 seconds. Derived compute cost was `$0.124789541` and disk cost `$0.001430020`, totaling `$0.126219561`, excluding public IPv4, egress, and pending invoice reconciliation. Direct lookup returned not-found and final labeled instance/disk inventories were zero. Factory bundle `f922e2d9a6f1b2cc59110eb649b7f25e01145a9a74ab60f23dd4e27c89aa8f6e` and cost object `5dac1451c6a6bdaeacbf0fa08c5a4b65e55fce696b6f2d9632ee01eabbf371e5` are deep-verifiable; cleanup is verified and the settled factory ledger leaves `$6.954942` available.

An unchanged retry is not admitted. V34 removes only the unsupported Nsight GPU Metrics collector, retains 100 ms `nvidia-smi` utilization/VRAM/power/clocks/temperature telemetry, and records the unavailable signal explicitly. B1 retains CUDA/NVTX/OSRT, node-level CUDA Graph, and process-tree sampling/context switches. If observer overhead breaches, the conditional B2/A3 bracket removes CPU sampling/context switching while preserving device tracing to localize perturbation. This changes the candidate configuration and requires a new identity; it does not retroactively satisfy v33's gate or support a model claim.

### Nebius L40S narrowed observer diagnostic allocation v34 — retained repair validates full trace/export

The factory admitted immutable run `glm47-observer-diagnostic-l40s-v4` at paid-spec SHA-256 `d879e2dc777130e25d934aeb38d6e6378bf1dd63860f808d12c4bd8f853e9ff4`, reserving `$0.55` including `$0.07` cleanup reserve. Immediately before admission, 33 deep artifact references passed and Nebius inventory measured zero instances and zero disks. The labeled preemptible L40S was factory-registered with an independent 2,000-second deletion watchdog. A bounded ten-minute retained repair window was enabled only for an already-tested amendment after failure.

V34 correctly omitted GPU Metrics. The target Nsight command produced a report, but the PyTorch process failed CUDA initialization with error 803 because this particular probe invocation omitted the runtime's established removal of CUDA-compat `ld.so` entries and `ldconfig`. The retained repair window was then used rather than immediately deleting the GPU. On the same L40S and derived image, the exact cleanup made PyTorch CUDA return `1.0`; the full CUDA/NVTX/OSRT, node-level graph, process-tree trace then passed and exported a 539,965-byte `.nsys-rep` and 2,015,232-byte SQLite file. Those retained-window probes validate the repair and profiler capability only. No checkpoint transfer, inference, observer bracket, quality/SLO result, or model bottleneck claim occurred.

The coordinator determined that safely resuming the full controller required more than a small in-place command, wrote an explicit teardown decision after 145 seconds of retained diagnosis, and did not idle for the remaining repair window. Measured allocation exposure was 686.283 seconds. Derived compute cost was `$0.161733916` and disk cost `$0.001853382`, totaling `$0.163587298` by line-item sum, excluding public IPv4, egress, and pending invoice reconciliation. Direct lookup returned not-found and final labeled instance/disk inventories were zero. Factory bundle `640db45c78997f29d4dd3cacb77fdd66f4650daae053e5441d007b3a3597f272` and cost object `20fee2712a78d16a153a691baa1a7be5ef0f8371318e36d5bf5310270470b09f` are deep-verifiable; cleanup is verified and the settled ledger leaves `$6.791354` available.

An unchanged retry is not admitted. V35 binds the exact target-validated CUDA-compat cleanup into the preflight before PyTorch or Nsight. All other narrowed-observer variables remain fixed. This is the first retry for which the entire pre-transfer profiler path has already passed on the target hardware.

### Nebius L40S narrowed observer diagnostic allocation v35 — user-requested stop

The factory admitted immutable run `glm47-observer-diagnostic-l40s-v5` at paid-spec SHA-256 `2ccbca18f3a0a9bdb60765bac92e481317af1755875484252a0e99419145ac75`, reserving `$0.55` including `$0.07` cleanup reserve. Immediately before admission, 34 deep references passed and Nebius inventory measured zero instances and zero disks. The labeled preemptible L40S was factory-registered and protected by the independent 2,000-second deletion watchdog.

The user requested an immediate stop while the fresh host was still executing the pre-transfer bootstrap. The coordinator sent SIGINT to the controller; its `finally` path requested factory cleanup, deleted the instance and labeled disk, verified direct not-found and zero labeled final inventories, and marked teardown verified. No checkpoint bytes, inference request, science arm, or additional profiler result was produced, so V35 is recorded as `user_requested_stop`, not a preflight or scientific failure.

Measured exposure was 290.481 seconds. Derived compute cost was `$0.068456674` and disk cost `$0.000784476`, totaling `$0.069241150`, excluding public IPv4, egress, and pending invoice reconciliation. Factory bundle `ad7a920e3ddcd0326966eb5d75a5c17bb2b124bb4246806c2081b04df086dd69` and cost object `3a663c44d4baaaca5f2fae374adae50857d75e4ef2f1b5fe6d97712894e39b7a` are deep-verifiable. The settled factory ledger leaves `$6.722112` available with zero reserved spend and no live allocation.

Resume contract: do not reuse immutable run V35. When the campaign is explicitly reopened, bump the controller and artifact contract to V36, recompute the harness-bound preflight objects, and rerun the already target-validated narrowed observer contract. The exact CUDA/NVTX/OSRT, node-graph, process-tree probe plus SQLite export passed during V34's retained window after the cleanup now present in source. No new scientific variable needs to change before that retry.

### Nebius L40S narrowed observer diagnostic allocation v36 — post-transfer server-health failure

The supervisor recovered under exact owner `supervisor-glm47`, passed a 35-reference deep audit, and freshly reconciled zero Nebius instances and zero disks before admitting immutable factory run `glm47-observer-diagnostic-l40s-v6`. The V36 paid spec is SHA-256 `7cc984b6e2877885ef5ac6f32435a48d4733fca9a7f8089cbd0081a87999d6be`; it preserved the diagnostic A1/B1/A2 geometry, `$0.55` reservation, `$0.07` cleanup reserve, 2,000-second absolute deadline, observer perturbation gates, telemetry, and artifact contract. The only planned change from stopped V35 was the immutable run identity. All 196 campaign tests passed before admission.

V36 passed the exact target-hardware path that prior repairs were intended to establish. Nsight Systems `2026.3.1.157`, CUDA/NVTX/OSRT, node-level CUDA Graph tracing, process-tree sampling/context switches, CUDA-compat cleanup, and the tiny transfer probe passed before checkpoint bytes. The verified 20.17 GB AWQ checkpoint then transferred exactly once in 356.302 seconds. The model endpoint subsequently remained connection-refused throughout the bounded health window, so no request, warmup, observer arm, quality gate, SLO result, deep trace, or scientific measurement ran. The remote final archive was therefore absent. This is an operational failure after transfer and before scored arms; it does not update the dense-device versus host/scheduler hypotheses.

The controller exposed the allocation for 1,203.863 seconds. Derived compute cost was `$0.283710331` and disk cost `$0.003251165`, totaling `$0.286961496`, excluding public IPv4, egress, and pending invoice reconciliation. It requested factory cleanup, direct instance lookup returned not-found, fresh labeled inventories contained zero instances and zero disks, and reservation settlement passed. The compact failure bundle is deep-verified at SHA-256 `6b69151c9f6ebf59e83a09995e963291106111cb9c802223a7b4667b625ff315`. The factory ledger is `$18.564850/$25` settled with `$6.435150` available and zero reserved.

The next step is offline and zero-cost: make partial remote server exit status and logs retrievable even when the final archive is never produced, then audit the V36 launch/health path. Another paid run requires a new immutable identity and a materially changed operational variable; the scientific observer contract remains unchanged.

### V36 offline launch-health recovery — readiness timeout falsified, evidence contract repaired

The bounded offline audit classified V36 more narrowly without treating the operational failure as science. The immutable outer log contains exactly 54 connection-refused health attempts. The remote command returned well before its 180-by-two-second readiness allowance and science deadline; successful V24R2–V28R1 model loads took 108–112 seconds. Given the harness control flow, V36 therefore lost the tracked A1 server process before readiness rather than exhausting its readiness window. The old contract did not recover the launcher return code or per-arm server logs, so the actual server failure remains unknown. The observer patch around scheduler and model-forward execution is the highest-risk changed launch variable, but that causal explanation remains inferred.

The repaired remote harness creates an atomic, content-manifested partial archive before readiness and refreshes it periodically and on exit. It retains server status and exit history, raw server stdout/stderr, per-attempt health events, phases, and partial classification metadata. The controller first attempts the normal archive, then verifies both the outer hash and internal manifest of the partial archive, records it as `FAIL`, and prohibits scoring. The observer A1/B1/A2 geometry and health window are unchanged.

Verification passed: Bash syntax, Python compilation, 19 focused tests, and the complete 200-test campaign suite. The zero-cost factory diagnostic is `glm47-v36-launch-health-recovery-c1-result`; its audit artifact is `8d1a39b1...00d1db` and hashed staging manifest is `392867bc...e68f0`. No provider resource was created, budget remains `$18.564850/$25` settled with `$6.435150` available and zero reserved, and no scientific belief was updated.

Next action: validate the exact observer patch inside the pinned derived image with compilation, imports, and a minimal NVTX invocation. If that passes, admit only a new immutable operational diagnostic that first proves unpatched stock startup before patched observer startup and retains the partial bundle. Do not lengthen readiness or change the observer science contract.

### V36 observer patch exact-pin smoke — basic incompatibility falsified

A zero-cost GPU-free smoke reconstructed the runtime from the exact V36 amd64 base image digest and pinned Transformers commit. The reconstructed image is content-identified at `4672d4aa...f3f62c`; its BuildKit provenance binds base digest `97187c95...f244543`. The pristine installed scheduler and GPU-runner hashes exactly matched the patch contract. Runtime identities also matched V36: Torch `2.9.1+cu129`, CUDA build `12.9`, vLLM `0.15.0`, and Transformers `5.3.0.dev0`.

The stock imports passed. The exact observer patch applied, both modified modules compiled, and fresh patched imports passed. A synthetic scheduler record retained prefill/decode composition and produced iteration ID `071d874fe8b55e73`; the runner produced the matching label `GRAD_RESEARCH_OBSERVER_V1:iteration:071d874fe8b55e73`. The host-side `torch.cuda.nvtx.range` context entered and exited successfully with `cuda_available=false`. The first attempt failed only because informational vLLM stdout preceded the JSON record; a content-recorded parser amendment reran the unchanged test and passed. This was a local harness failure, not patch evidence.

The valid result falsifies exact-source mismatch, patch-anchor, Python syntax, module import, scheduler/runner correlation, and basic host NVTX API explanations. It cannot test GPU model initialization, first forward, CUDA Graph capture, driver injection, the final Nsight layer, or the deleted V36 image bytes. No scientific belief changes. The factory result is `glm47-observer-patch-pinned-image-smoke-c1-result`; result artifact is `10912a65...fd681` and staging manifest is `1576d4f4...e3dad2`. Provider spend and inventory remain unchanged.

Next action: prepare a new immutable operational diagnostic on one retained L40S that transfers/verifies the checkpoint once, proves an unpatched stock server reaches health, stops it, applies the exact patch, and starts the patched observer path with verified partial evidence. Preserve the A1/B1/A2 science geometry, readiness window, existing budget, and cleanup deadline; admit only after fresh exact-owner resume and zero-resource reconciliation.

### V37 startup-isolation packet prepared — not admitted or executed

The bounded director cycle prepared immutable run `glm47-observer-diagnostic-l40s-v7` and stopped before admission. Its only operational change is an excluded `STOCK_STARTUP` stage before patching: exact same server command/checkpoint/runtime as A1, zero requests, the existing 180-by-two-second readiness limit, then bounded TERM/KILL teardown and verified process absence. Only after that gate may the exact observer patch apply and the unchanged A1/B1/A2 diagnostic begin. Startup-stage failures remain operational, are retained in the verified partial archive with health/status/stdout/stderr and low-overhead GPU state, and are never scored.

The paid packet preserves the `$0.55` cap, `$0.07` cleanup reserve, 1,760-second science/setup deadline, 240-second cleanup reserve, 2,000-second absolute deadline, observer bracket, quality/correctness/SLO gates, raw-event/telemetry/log contracts, and content-addressed manifest. Candidate harness identity is `60453752046ec3de2a68ab95041783f591c1f6152b7e75014cbbbb14a448ef9e`; the preparation-time admissible spec content hash is `819ea18fabe1ab91650012585cb25d686a51b782f71c9fad265464ee5048534d`; verification artifact is `cdc531225af29a3371eb132853eb799aaa184aff0d991563770eecdecc269f6a`; and plan manifest is `9550fbff6af5de4c94759a9926efe39b607074013be9a58146413205b241508d`.

DevEx, diff, Bash syntax, Python compilation, factory validation, and all 204 campaign tests passed. Fresh Nebius reconciliation measured zero instances and zero disks. No reservation or provider mutation occurred; spend remains `$18.564850/$25` settled, `$6.435150` available, and `$0` reserved. Factory result `glm47-observer-v7-preparation-c1-result` is diagnostic-only and cost `$0.00`. The generated preparation deadline must not be reused: the next cycle must resume as `supervisor-glm47`, deep-audit, reconcile zero resources, regenerate with a fresh clock, then admit and immediately execute through cleanup and settlement. No scientific belief changed.

### Nebius L40S observer diagnostic allocation v37 — startup isolated; B1 launch-option failure

The supervisor resumed under exact owner `supervisor-glm47`, passed a 52-reference deep artifact audit, reconciled zero Nebius instances and disks, regenerated the V37 clock, and admitted immutable run `glm47-observer-diagnostic-l40s-v7` at content SHA-256 `281f95d0d8735a8dedcbc51b2ea42fc97cc7ada57501df28b878edc6861b23d1`. The raw paid-run spec is `330092e64e583bf9a61add6977323bc089d49200b55640f922db6948e1c028e5`. The existing `$0.55` reservation, `$0.07` cleanup reserve, and 2,000-second deadline were preserved; no new budget authority was granted. All 204 campaign tests passed before admission.

Target Nsight/CUDA preflight and the tiny transfer probe passed. The verified 20.17 GB checkpoint transferred exactly once in 431.717 seconds. The excluded unpatched `STOCK_STARTUP` reached health, then passed bounded stop and process-absence gates. The exact observer patch applied, and patched A1 reached health and completed. These measurements falsify V36's failed-startup behavior at unpatched stock startup and at the patched A1 startup boundary.

The B1 observer-on wrapper then exited before server startup because Nsight Systems `2026.3.1.157` rejected `--force-overwrite=true` on `nsys launch` as an unrecognised option. No B1/A2 bracket completed. Although the remote phase record says A1 completed, the partial-archive allowlist omitted its exact raw request, workload, quality-gate, and scheduler files. A1 therefore cannot be scored or used for performance, quality, or scientific inference. This is strictly an `operational_failure`; dense-device versus host/scheduler beliefs are unchanged.

The controller exposed the allocation for 1,340.125 seconds. Derived compute cost was `$0.315822801` and disk cost `$0.003619157`, totaling `$0.319441958`, excluding public IPv4, egress, and pending invoice reconciliation. Its finally path requested cleanup, direct lookup returned not-found, and fresh inventories contained zero instances and zero disks. The verified partial archive is SHA-256 `50459d5f5162d1ba96382e65eb157b13846e1fa19e48b1518dc0e70441fc008c`; the deep-verifiable factory failure bundle is `89bcbafc38e8ae134bb4bf46cca8b76efbf75f5aba4eeae1fd2e5199d34827ab`. Settlement leaves `$18.884292/$25` settled, `$6.115708` available, and zero reserved.

Before another paid run, remove the unsupported `--force-overwrite=true` argument, add an exact-version pre-transfer `nsys launch --help` capability fixture/gate, and bind that repair to a new immutable run identity. Do not change the verified startup isolation, A1/B1/A2 science geometry, readiness window, budget, paid deadline, partial-evidence contract, or cleanup policy.

### Nebius budget authority amendment — 2026-07-14

The user explicitly increased the additional available Nebius balance to `$28.60` after topping up the account. The factory ledger now has total authority `$48.034292`: `$18.884292` settled, `$0.55` reserved by the active V8 run, and `$28.60` available for new admissions. This is a budget-only amendment; it changes no scientific scope, workload, run identity, quality gate, SLO, or provider-control rule. Historical decision artifacts retain their original `$25.00` authority and are not rewritten.

The preceding wording treated `$28.60` as the lifetime ceiling; that interpretation was corrected after the user clarified that it is the remaining balance available to spend in addition to prior spend.
