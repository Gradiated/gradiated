# GLM-4.7-Flash vertical-stack campaign — 2026-07-13

## Final $100-campaign decision: STOP_OR_PIVOT

Gate A closed with 68/68 fail-closed campaign tests and 21/21 GLM experiment tests passing. The frozen workload, tokenizer bindings, quality screen, evidence schema, budget admission, independent watchdog, stock harness, and RunPod driver are content-addressed. Provider billing now contains 22 settled historical rows totaling $4.944724685. Conservative accounting remains larger at $5.153606502 account lifetime and $0.273464527 campaign-additional spend because the interrupted L40S allocation lacks a terminal record.

The first preregistered Phase-B stock request used one Community A100 80 GB PCIe. RunPod returned HTTP 500 before pod creation; inventory remained empty and cost was $0. The only allowed changed placement kept the model, runtime, GPU type, workload, quality gate, SLO, and artifact contract fixed while changing the cloud class to Secure. It also returned HTTP 500 before pod creation. The final inventory was empty, the billing row count stayed 22, and both requests added $0.

The two-placement limit is exhausted. The campaign therefore stops before Gate B rather than cycling through more A100 variants or returning to the repeatedly failed H100 placements. No valid stock throughput, TTFT, token-level ITL, SLO-goodput, provisional quality, tuned-stack, AWQ, provider, software, memory-hierarchy, or hardware cost comparison exists. No cost improvement is claimed, and $99.726535473 of the authorization remains deliberately unspent.

The exact pivot experiment is the same frozen 25-request native-BF16 stock harness on a guaranteed or provider-reserved 80 GB NVIDIA placement with the pinned image pre-pulled. A matched tuned control may run on the same machine only after stock passes. The source-supported AWQ KV-B smoke remains gated behind that baseline. Fireworks, Baseten, and Cloudflare figures remain vendor price/product anchors rather than matched evidence.

## Reconciled $100-campaign starting point

Provider-settled RunPod billing, including disk, raises the fourteen original GLM allocations from the earlier $4.11239 GPU-only ledger to $4.281754442. Adding conservative GPU-plus-disk ceilings for the two completed but not-yet-settled L40S allocations produces a pre-campaign GLM ceiling of $4.713011538 and an all-account ceiling of $4.880083828.

An extended-load L40S pod was created after the new coordinator began but before its required baseline was signed. The legacy worker was interrupted during migration and left no terminal artifact or DELETE receipt. Direct API checks now show zero pods and GET 404 for that pod. Its bounded GPU-plus-disk ceiling, $0.273464527, is charged to the new $100 campaign. It produces no model or economic evidence and may not be repeated unchanged.

The first allocated H100 run produced no throughput result. The model weights downloaded, but the CUDA 12.9 SGLang v0.5.15 image lacked the CUTLASS DSL Python module. Native model imports, including `glm4_moe_lite`, were suppressed; `model_impl=auto` then fell back to Transformers and failed on unsupported TP style `mla_kv_a_proj`.

The corrected smoke contract pins the linux/amd64 CUDA 13 SGLang image digest `sha256:655d004115e384b56b73ad6869bb04b29cce7ba3e597ce8f92eeeb49e2acb0af` and source commit `f63458b5beaceabbd9d749b9fc956370e1b649e6`. It gates `cutlass` and native GLM imports before downloading weights, forces native SGLang model implementation, limits context and concurrency to 4K/one, disables CUDA graphs and radix cache, captures telemetry, and requires two identical greedy completions plus artifact retrieval and verified teardown.

Authoritative pre-smoke spend is $2.072 against the $12 cap. Published economics and any later measured evidence remain explicitly separated in the campaign report.

The corrected smoke subsequently passed. SGLang loaded the model through native `Glm4MoeLiteForCausalLM`; two greedy 32-token completions were identical; the verified artifact was retrieved; and the H100 was deleted with follow-up 404. Whole-allocation smoke cost was $0.45476. This resolves runtime compatibility and admits the 16K BF16 economic baseline.

The first baseline allocation did not expose its container endpoint within five minutes and was deleted for $0.25437. No model/runtime result was produced. A single bounded retry was selected because the same digest had started within the deadline during the successful smoke.

The bounded retry failed similarly on a different H100 and was deleted for $0.25704. Rather than repeat the same request, the next attempt uses the verified `v0.5.15-cu130@linux-amd64-digest` reference. This preserves the required manifest while allowing a provider cache keyed by the explicit tag.

The tag-plus-digest placement reached native serving, but the benchmark fast-failed on an obsolete CLI flag and was safely harvested for $0.16880. After removing the flag, the next H100 placement again missed the five-minute startup deadline and was deleted for $0.25748. The campaign therefore pivots to a cheap A40 compressed-tensors AWQ smoke, with shared-expert fusion disabled and MTP off.

No A40 capacity was available. An A6000 Ampere proxy reached compressed-tensors initialization. Three semantics-preserving attribute guards advanced it to the intended WNA16 Marlin MoE method, but checkpoint loading failed on a fused metadata shape mismatch (`[2]` runtime versus `[4]` checkpoint). That branch is stopped because a shape patch could silently change quantization semantics. The verified BF16 H100 path is resumed.

The resumed H100 baseline and its immediate retry both missed the mandatory five-minute pinned-image startup deadline on different machines. They were deleted and verified absent. Final authoritative conservative campaign spend is $4.11239, with zero active pods. No measured throughput or $/token claim is admitted. The next valid continuation requires either a cached exact-image H100 placement or a credible fix for the compressed-tensors fused metadata mismatch; generic dense-model experiments remain out of scope.

## Phase-2 loader research

The AWQ assertion was localized to MLA Q/KV-A fusion, not expert fusion. Pinned SGLang concatenates two compressed-tensors `weight_shape` descriptors: `[768, 2048]` and `[576, 2048]` become a four-element tensor, while the fused projection requires `[1344, 2048]`. Packed weights and group-32 scales still require ordinary row concatenation; the symmetric checkpoint contains no zero points.

The credible fix also registers the fused projection mapping so layer 0 inherits its BF16 exclusions and recognizes compressed-tensors `weight_packed` during MLA initialization. A 12-test offline fixture passes against the exact pinned source. The selected next experiment is one fail-closed RTX A6000 smoke under a separate $4 phase cap; vLLM 0.15.0 remains the pinned fallback if the SGLang patch exposes a different causal failure.

The first A6000-only request was rejected before pod creation for $0. A single changed placement request using RunPod's availability-prioritized A40/A6000 48 GB pool is allowed; no further capacity retries are authorized.

The changed A40/A6000 availability request was also rejected before pod creation. Phase-2 spend is $0 of $4 and the account has zero active pods. The source-level loader result is causal and fixture-proven, but remains GPU-unverified; no throughput, quality, or cost claim is admitted.

## Phase-3 provisioning audit

The prior HTTP 500s were not evidence-backed capacity results because their bodies were lost. Both payloads pass the live REST schema, but current GPU metadata shows A40 is Secure-only while the second request specified Community; Community A6000 currently has no quoted availability. L40S is the only queried 48 GB Ada type with explicit current Community stock, at $0.79/hour. A single schema-valid L40S/CUDA-13 request is selected, with sanitized HTTP error capture and gzip-compressed startup inputs. Pinned WNA16 linear and MoE Marlin declare Ampere-or-newer capability 8.0, so Ada 8.9 is supported.

The Community L40S request returned and preserved the explicit body `create pod: There are no instances currently available`; no pod was created and spend was $0. One final Secure L40S request is justified by its separately reported Low stock at $0.99/hour. No further RunPod placement retry is authorized.
# Phase 3 GPU loader evidence

Attempt 3 did not exercise the new `kv_b` patch: a slow Secure L40S host took 321.64 seconds for the first of four checkpoint shards, and the 480-second model-health loop ended load without a model exception. The 20.19 GB download itself took 300 seconds. Cost was $0.319079, cumulative phase spend $0.423387; artifact SHA-256 `a266d75e24973d933c9d59b0b7bf930f4a409928f47dd4acbe9fbc738bf3d944`; teardown was 204/404. The next smoke preserves the five-minute provider startup and 40-minute allocation caps while extending only model-load allowance to a measured 20 minutes.


On a Secure L40S, the fixture-proven fused metadata patch loaded all four AWQ shards through native SGLang/CompressedTensors Marlin. It then exposed a separate MLA post-load incompatibility: compressed `kv_b_proj` has `weight_packed`, but the pinned loader only handles legacy AWQ `qweight` or dense `weight`. Cost was $0.104308; artifact SHA-256 is `4faabdb314871c02e68aea0be64a976f0c4688d08f1891ed44155df0fde7e918`; teardown was DELETE 204 then GET 404. A narrow canonical unpack/dequantize correction passes 19 offline tests and exact pinned-source compilation. No output, quality, throughput, or economic win is claimed.
