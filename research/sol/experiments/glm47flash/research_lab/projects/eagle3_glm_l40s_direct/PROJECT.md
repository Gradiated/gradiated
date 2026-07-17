# Exact-model EAGLE3 direct L40S measurement

## Question

Can the pinned exact-model EAGLE3 draft, admitted by one narrow vLLM target-type intervention, raise the exact current-AWQ L40S c16 workload to at least `594.466` output tok/s without changing target-verified quality or exceeding the 300-second envelope?

## Why this matters

N-gram speculation is now a valid scientific negative: it accepted `27,844` draft tokens but disabled asynchronous scheduling and collapsed the endpoint to `90.800` output tok/s. The external EAGLE3 lead is different and materially stronger: its 32k proposal space has a measured exact mapping into the `154,880` target IDs, and its model card reports `54.9%` acceptance and `1.66x` on H200 for GLM-4.7-Flash. Pinned vLLM already contains the mapping/verification implementation but rejects `glm4_moe_lite` in a target-type allowlist before load. One fail-fast source/residency/scheduler gate followed immediately by a single candidate endpoint is the shortest honest test; the H200 result is only a prior.

## Fixed identities and evidence

- Target root: `/root/.cache/glm47flash-awq-ab31d120`; revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`; manifest SHA-256 `e201edca069d0cfd91c81a7407e40a1b09808448704b2fc8c31e99ff6d9d0a86`; tokenizer/config/template identities from the r3 project remain fixed.
- Draft: `thoughtworks/GLM-4.7-Flash-Eagle3@c43b5f18f59b8fba69e8c0d585fb0e614cf42af1`; config SHA-256 `543261d86f82efef374e9ee50ae02f225d16d759b1407c0d339f9c1725efd7ee`.
- Mapping: `d2t` SHA-256 `b4ea5be5246a3ad4fc4732f594bcca2518e735ead381455234f1cca6a1bfc5d0`; `t2d` SHA-256 `20444040bb3e216418bf28cee084a1f89ea60f0f57f16a3c4e909e2718a82940`; all 32,000 mapped IDs are unique target IDs. Consume `../eagle3_compressed_vocab_bridge/eagle3_mapping_runtime_audit_2026-07-16.json`.
- Runtime: pinned vLLM `0.15.0` plus Transformers revision `1618d44b9295361607ec74d7be860ba886aac039`; EAGLE3 mapping code exists, while `speculative.py:666-678` omits target type `glm4_moe_lite`.
- Proven launcher: `/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius/vllm_smoke_control.py`, direct external systemd ownership/watchdog, L40S profile, methodology off, and the same local Ed25519/provider bindings used by the terminal n-gram arm.
- Workload: cache off, thinking disabled, 8,192 input/1,024 output, 32 requests, c16, 300 seconds, `num_kv_splits=4`.
- Economics: planning `$1.10/hour`; absolute pass `594.466` output tok/s and `$0.514/M`; actual experiment accounting at the provider-metered rate. Contextual r3 is `552.1710554232396` output tok/s.
- Residency prior: native one-layer MTP added `1.543 GiB`, reached `44.22 GiB` in use with `167.38 MiB` free, and failed a `562-MiB` allocation during c16.

## Execution contract

This project authorizes at most `$1.00` and 3,900 seconds under one durable owner. Before create, in the same researcher turn:

1. materialize the pinned public draft under a new content-addressed local root and record every file/whole-manifest hash; no mutable `main` reference;
2. derive exact draft tensor bytes plus mapping, draft KV, activation, graph/workspace, and fragmentation bounds from its headers/source, reconcile them to the measured MTP failure, and close `MEMORY_CLOSE` at `$0` unless the exact c16 workload has conservative residence headroom;
3. make only the narrow target-type admission needed for `glm4_moe_lite`, with a source-bound planner/config fixture proving the exact target/draft pair, mapping, method, proposal length, and no second target copy; any further model, loader, kernel, or verification implementation need closes `RUNTIME_CLOSE` at `$0`;
4. prove from pinned source/config that EAGLE3 does not inherit the n-gram endpoint's asynchronous-scheduling disable/fallback or otherwise produce a conservative scheduler/verification ceiling below `594.466`; close before spend if it does;
5. add one explicit fail-closed shared-launcher switch for this exact draft/method/config, preserving stock and n-gram-off behavior, and pass focused tests plus the execution-equivalent no-mutation terminal.

Bind exactly one source/card-defined EAGLE3 proposal length before create; do not sweep proposal length, acceptance settings, scheduler knobs, or runtime versions. If all pre-create gates pass, launch immediately using the proven controller. Return after one grouped durable-owner snapshot as required by the shared handoff contract; do not poll bootstrap, transfer, load, or workload.

The sole scientific arm is target-verified EAGLE3 c16. Require all 32 requests, exact input/output geometry, reasoning/cache identity, semantic determinism, complete output-token histograms, proposal and accepted-token counts by position, draft/verify and scheduler telemetry where exposed, peak VRAM, request timing, provider spend, authenticated archive, and verified zero instance/disk inventory. Methodology remains off.

Return exactly one terminal result:

- `ECONOMIC_PASS`: all correctness/artifact/cleanup gates pass, wall time is at most 300 seconds, and throughput is at least `594.466` output tok/s;
- `SCIENTIFIC_FAIL`: a valid complete endpoint misses either absolute gate;
- `MEMORY_CLOSE`: the pre-create bound or actual exact load/workload cannot reside;
- `RUNTIME_CLOSE`: the one narrow admission cannot produce the exact target/draft execution path;
- or one typed provider/operational terminal before the workload, with no scientific inference.

No adjacent stock arm, second create, runtime upgrade, additional source patch, retry, setting sweep, methodology suite, training, model conversion, alternate draft, retained instance, or successor controller. Quality remains mandatory; target verification plus semantic evidence is required but does not replace later full quality certification.

## Available resources

Use the fixed projects above, pinned public draft repository, local target/cache, proven campaign launcher/provider tools, `hardware/L40S.md`, `/root/workspace/research/factory/tools`, and `/root/workspace/research/sol/experiments/glm47flash/campaign_100`.

