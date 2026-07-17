# Exact Gemma 4 31B quantized checkpoint delivery route

## Decision question

Is there one content-addressed, legally usable Gemma 4 31B FP8/W8A8 checkpoint plus supported runtime consumer that can reduce fresh endpoint staging enough to justify a later complete-request experiment, without transferring quality from the BF16 target or repeating the failed two-hour download route?

## Why now

The campaign still has no complete exact-model request. Two full-checkpoint owners spent roughly two hours in staging, while the new paid project measures only the actual component consumer. A parallel `$0` search can discover whether a smaller, producer-addressed quantized representation removes the dominant endpoint setup cost. It must not delay or mutate the paid owner.

## Scope and evidence contract

Start from the exact target `google/gemma-4-31B-it` revision `b9ea41a2887d8607f594846523f94c6cc75ac8a4`, its tokenizer/config/index identities, the pinned vLLM source/image in `../fp8_l40s_fit_economic_falsifier/FP8_L40S_PACKET.json`, the failed staging artifacts in `../direct_fp8_l40s_cuda/`, and the current first-party FP8 warnings recorded by that project.

Search current first-party, official-producer, and checkpoint-producer sources for exact-model FP8, W8A8, or another single-L40S representation. For each serious candidate, record repository/commit, producer, derivation recipe and base revision when disclosed, tensor format, total bytes and shard count, tokenizer/config identities, license/access terms, runtime version and exact load flags, CUDA/Ada support, and any measured quality evidence. Distinguish an exact quantized derivative from the BF16 target; no derivative inherits production eligibility.

Use metadata, manifests, HEAD/range requests, and pinned source inspection. Download no weight set. At most 512 MiB of bounded transfer probes and 2 GiB local storage may be used to measure delivery behavior. Do not create disks, instances, endpoints, accounts, or paid resources. Do not duplicate the fresh shared GPU-price inventory.

Nominate at most one later endpoint route only if all of these are true:

- content identity and base-model provenance are explicit enough to reproduce;
- total weight bytes materially reduce the 62.546 GB BF16 staging burden and fit the conservative L40S memory contract;
- the pinned or explicitly replacement runtime has a documented actual consumer on SM89;
- access/license permits the campaign experiment;
- a deterministic staging plan can be bounded by wall time and byte count rather than a researcher turn;
- raw-output quality and feature validation remain mandatory in the later paid experiment.

If no candidate clears the contract, publish that negative and rank one non-checkpoint endpoint alternative (for example a provider-resident exact endpoint or a durable pre-GPU materialization route) only when its identity, byte movement, and cost can be bounded. Do not author a provider controller or readiness successor.

Write `DELIVERY_ROUTE.json` and a concise `DECISION.md` with evidence labels, URLs/content hashes, uncertainties, measured probe bytes/time if used, expected staging bytes, exact runtime consumer, quality boundary, and the one nominated route or a typed `none`.

## Budgets

- Wall clock: 60 minutes.
- Compute: at most 1 local CPU-hour; no GPU.
- Storage/network: at most 2 GiB retained storage and 512 MiB transfer probes; no complete weight shards.
- Spend: `$0`; no provider mutation.
