# B200 dynamic-FP8 endpoint placement

## Question

Can the exact Gemma 4 31B checkpoint serve the campaign c32 workload on one
B200 with runtime dynamic-FP8 weights at a price-normalized sustainable cost
at least 20% below the fixed qualified denominator?

## Why it matters

The campaign requires a complete endpoint result against
`0.625149101968745 s/request`, with an H200-equivalent target of
`0.500119281574996 s/request` or the same 20% improvement after accelerator
price normalization. The native-NVFP4 project never submitted an endpoint:
its official producer completed but emitted BF16 shards without the required
W4A4 group-16 representation. That rejects that producer/representation, not
B200 placement or runtime FP8.

## Bound evidence and resources

- Exact checkpoint: `google/gemma-4-31B-it` revision
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Predecessor terminal:
  `../b200_nvfp4_gemma4_endpoint/artifacts/b200-nvfp4-endpoint-v2-20260728t1323z/TERMINAL.json`.
- Reusable endpoint machinery:
  `../b200_nvfp4_gemma4_endpoint/endpoint_owner.sh` and
  `../b200_nvfp4_gemma4_endpoint/artifacts/native-nvfp4-endpoint-packet-v1/endpoint_driver.py`.
- Protected retained bench:
  `b200-nvfp4-computeinstance-i00rqcq5yzr6xc991j`, funded and returned to
  ready state for only this project under
  `DIRECTOR_B200_DYNAMIC_FP8_EXECUTION_20260728T1454Z.json`, with only its
  lifecycle and runnable-owner envelope superseded by
  `DIRECTOR_B200_DYNAMIC_FP8_TERMINAL_ADOPTION_AND_LAUNCH_20260728T1507Z.json`.
- Pinned resident-capable image:
  `docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79`.

## Scope

- Preserve the exact checkpoint, tokenizer, campaign c32 requests, response
  accounting, and timing boundary.
- Adapt the existing endpoint owner for one contemporaneous BF16 control
  followed by one runtime dynamic-FP8 weight candidate on B200. Do not use
  the rejected llmcompressor native-NVFP4 producer or its saved shards.
- Reuse the retained checkpoint/image state when its identities match; do not
  restage settled bytes.
- Require a tiny real-runtime FP8 consumption proof before the candidate c32
  arm, then capture complete request, latency, throughput, memory, power,
  failure, and price-normalized cost evidence.
- Use only cheap coherence/numerical sanity needed to reject an obviously
  broken candidate; broad quality replay remains deferred.
- After the exact recorded local snapshot owner terminates validly, implement
  and hash-bind `b200_dynamic_fp8_owner.sh` plus
  `dynamic_fp8_endpoint_driver.py`, claim the retained bench by
  `2026-07-28T15:32:00Z`, and release it by `2026-07-28T16:35:00Z`. Do not
  perform provider lifecycle operations or start another checkpoint
  materialization.

## Decision

Produce a typed BF16-control/dynamic-FP8 endpoint pair and compare both the
raw service time and committed-price-normalized sustainable cost with the
fixed campaign denominator. A candidate that does not consume FP8, cannot
start in the pinned runtime, produces incoherent output, or misses the
price-normalized target is a scoped negative; ordinary launcher or runtime
API defects remain mutable same-claim repairs.

## Budgets

- Wall clock: 104 minutes from the funded ready handoff.
- Compute: one B200 for at most 67 claimed minutes.
- Storage: 40 GiB additional; reuse the existing checkpoint and image.
- Spend: at most `$8.00`, including retained-bench exposure assigned to this
  project after reservation.
