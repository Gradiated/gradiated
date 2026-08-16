# Runtime/AWQ causal audit

Timestamp: 2026-07-13T11:32:04Z

Scope: offline audit only. No RunPod API or pod endpoint was accessed or mutated, and no existing runtime, campaign-control, ledger, prediction, report, or mirror file was edited.

## Controlling contract

This audit follows `CAMPAIGN_100_PLAN.md` SHA-256 `c30350ca1426253165c2c987076868b00c1c10dd65222ff893313d178ae970d6`. The applicable workspace and durable-mirror `AGENTS.md` files were read completely. The controlling constraints for this boundary are: preserve the active pre-plan worker's files, do not duplicate its GPU run, require a failing regression test and source-level causal evidence for a compressed-tensors change, and kill the AWQ branch if full-checkpoint semantics remain unresolved after one new causal runtime defect.

## Durable evidence reviewed

- Latest `REPORT.md` snapshot SHA-256: `35166257006876aac22170d84a7cfb09c4f75a9dfe23b47569e141363d3c4d6c`.
- Secure L40S attempt-2 artifact: `phase3-attempt2-awq-smoke.tar.gz`, 18,615 bytes, SHA-256 `4faabdb314871c02e68aea0be64a976f0c4688d08f1891ed44155df0fde7e918`; its remote checksum agrees.
- Attempt-2 orchestration record SHA-256: `c2eadfade7a67c80cd4e4f2ff570d6ceb8de07926d8a6b51305407dacf41036f`.
- Current four-part patcher SHA-256: `541834f89efe8dfb0e4f24db84ade858d4932eeed259ede3f1c203e4834a3b00`.
- Exact-source patch/compile validation record SHA-256: `fa26c2ea1eca279f1915d10835412525aab0e3c064ad33bb4f47d4b882f81ce4`.
- Current attempt-3 payload audit SHA-256: `f7c12d453430d5060ebe39b29ed3862ebb36e4b947c98f33c6b6a376bb5aa314`.

The attempt-2 artifact is internally coherent: its manifest hashes its members; it identifies SGLang `0.5.15` at source commit `f63458b5beaceabbd9d749b9fc956370e1b649e6`, PyTorch `2.11.0+cu130`, compressed-tensors `0.17.1`, checkpoint revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`, and a real NVIDIA L40S with compute capability 8.9. The artifact's runtime-patch hashes match the prior three-part patch record.

## Causal status

The earlier fused Q/KV-A metadata hypothesis is GPU-validated, not merely fixture-supported. Attempt 2 passed the checkpoint metadata gate, instantiated native SGLang with `CompressedTensorsWNA16`, and loaded all four checkpoint shards. Therefore the former physical `[4]` versus required semantic `[2]` `weight_shape` failure was crossed by composing `[768, 2048]` and `[576, 2048]` as `[1344, 2048]`; packed weights and scales continued down their ordinary dimension-zero concatenation path.

The current boundary is later and narrowly identified. After shard loading, `DeepseekV2WeightLoaderMixin.post_load_weights` reached pinned `deepseek_weight_loader.py:522` and unconditionally evaluated `self_attn.kv_b_proj.weight`. The actual compressed-tensors `ColumnParallelLinear` has `weight_packed`, `weight_scale`, and `weight_shape`, not dense `weight`, producing:

`AttributeError: 'ColumnParallelLinear' object has no attribute 'weight'`

This is a representation/post-load incompatibility, not evidence of corrupt quantized values, a Marlin capability problem, failed shard loading, insufficient VRAM, expert fusion, tensor parallelism, or request-time kernel failure. No server health, completion, deterministic correctness, throughput, quality, or economic claim follows from attempt 2.

The selected correction is causally aligned with compressed-tensors 0.17.1's canonical `PackedQuantizationCompressor.decompress` inverse: use `kv_b_proj.scheme.quant_type.size_bits` to unpack `weight_packed` to the stored `weight_shape`, then call compressed-tensors `dequantize` with `weight_scale`, `zero_point=None`, and `g_idx=None`. The guards requiring INT4, symmetric weights, no activation-order group index, a positive two-element shape, and exact restored shape fail closed. The existing AWQ `qweight` path and dense path remain unchanged. Pinned SGLang assigns a `CompressedTensorsWNA16` scheme to this linear layer, and that scheme exposes `quant_type`, `symmetric`, and `has_g_idx`, so the branch's attribute contract is source-supported.

Confidence is high that this is the minimum semantic correction for the observed exception, but GPU validation is still mandatory. The unit dequantization fixture independently checks signed INT4 group scaling, while the patch regression checks branch construction and exact-source cardinality; neither executes compressed-tensors 0.17.1 on a real checkpoint tensor. Temporary and retained VRAM effects from materializing dense KV-B matrices also remain unmeasured.

## Offline test result

Command:

`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v`

Result: 19 tests passed in 0.001 seconds. This includes the original metadata-failure reproduction, fused descriptor composition, unchanged packed/scale behavior, exclusion inheritance, packed representation detection, signed INT4 groupwise fixture, fail-closed exact-source patching, and RunPod error-sanitization tests. No test failure was hidden or retried.

## Active pre-plan work and reconciliation requirement

At the audit snapshot, the durable pre-plan ledger ended with `pod_created` for `phase3_attempt3_secure_l40s_kvb_dequant_patch` at `2026-07-13T11:23:47.302818+00:00`, pod ID `kjcomsx6wz40ro`, quoted rate `$0.99/hour`, and maximum recorded deadline cost `$0.66`. No terminal attempt-3 artifact, finish row, cost, or teardown proof was yet durable locally. A separate pre-plan harvesting process appeared briefly and had exited without producing the artifact at this snapshot.

This unresolved allocation is not authorization for any campaign resource. Before a new campaign pod request, the coordinator must let the owning worker finish or safely harvest/terminate it, reconcile its authoritative lifetime cost as historical pre-plan spend, prove teardown, and only then create the new signed campaign baseline and spend guard. Do not launch a duplicate dequantization test.

## Exact next hypothesis and terminal rule

Hypothesis `AWQ-KVB-DEQUANT-1`: on the pinned SGLang/runtime/checkpoint tuple, applying only the already-tested compressed KV-B unpack/dequantize branch after the three validated loader corrections will cross `post_load_weights`, complete full-model initialization on an Ada 48 GB device, reach health, and return two identical normalized greedy smoke completions with MTP off.

Kill condition: if the already-running attempt 3 is harvested with a deterministic, model-semantic loader or post-load failure after this correction, or if it reaches health but deterministic smoke correctness fails, kill the patched-SGLang AWQ branch for this campaign. Do not add a fifth loader fix under Phase C. An infrastructure-only loss, invalid artifact, or teardown failure does not falsify the runtime hypothesis, but it blocks another resource until reconciliation and the new baseline/spend guard are complete; any corrected retry must change and record the causal infrastructure/artifact variable.

Pass condition: complete load, health, two identical normalized greedy responses, complete telemetry/artifact validation, exact allocation cost, and verified deletion. Passing establishes compatibility only. It does not establish quality retention, serving performance, economic performance, or a model-specific performance moat.

## Cheapest valid GPU test

The cheapest valid GPU test is the one already in flight before the new campaign: harvest `phase3_attempt3_secure_l40s_kvb_dequant_patch`; its frozen contract is one Secure L40S at `$0.99/hour`, 4K context, one running request, CUDA graphs disabled, radix cache disabled, shared-expert fusion disabled, MTP off, forced native SGLang/compressed-tensors, two deterministic greedy completions, telemetry, fail-closed artifact collection, and verified deletion. Its maximum recorded deadline cost is `$0.66`, entirely historical to the new authorization once reconciled.

If and only if that allocation is irrecoverably infrastructure-invalid rather than runtime-terminal, the cheapest later campaign test is one corrected 48 GB AWQ smoke with the same model/runtime semantics and no throughput matrix, after Gate A's baseline, spend guard, immutable prediction, validator, watchdog, and maximum-cost checks exist. No new RunPod resource should be created to duplicate a valid terminal attempt-3 result.
