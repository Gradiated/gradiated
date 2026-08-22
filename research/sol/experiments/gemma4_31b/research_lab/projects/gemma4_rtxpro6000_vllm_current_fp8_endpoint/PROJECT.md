# Current vLLM FP8 endpoint on RTX PRO 6000

## Question

Can the current official vLLM stack serve the exact pinned Gemma 4 31B
checkpoint with stock dynamic FP8 on the resident RTX PRO 6000 Blackwell
Workstation and materially improve the exact concurrent-c32 endpoint economics
over the measured SGLang 0.5.16 placement?

## Why this matters

The exact SGLang result is decision-bearing but far outside the campaign
target: 32/32 complete requests measured `2.23382165625 s/request` and
approximately `$0.233737806/M` total tokens at 90% utilization, versus
`1.048637203302411 s/request` and approximately `$0.109725035/M`. This closes
only the tested Workstation/SGLang stack. A current full-stack runtime is a
materially distinct scheduling, kernel, graph, and memory-management
realization and can reuse the costly resident checkpoint and CUDA environment.

## Authoritative evidence and identities

- Predecessor terminal:
  `../gemma4_rtxpro6000_fp8_endpoint/artifacts/rtxpro6000-fp8-endpoint-20260729t0338z/RTXPRO6000_FP8_ENDPOINT_TERMINAL.json`,
  SHA-256 `c79a2f6067cf85b9e073d2bf9bc39a1906d84dfe3626887427dcf0c1f16ab9f8`.
- Predecessor pair run SHA-256:
  `47d62e6556387695c57158eb6d71a396e535c1ecd87e98ffc04a3696a008a9a0`.
- Checkpoint: `google/gemma-4-31B-it` revision
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`, manifest SHA-256
  `864f24f4631315cd17cc8a3ff1ea57b2725d2a24f29c45778b101f16b5228a4f`.
- Workload SHA-256:
  `357f22f350a8c0f11df5e1a93f1cd19e4b2eb2d329c75ed993f8dda2cf72338c`.
- Request identity SHA-256:
  `7a05fa6218a5fbfd87744bca1ac491949ddd64bf0d58007b4d3569594f08225d`.
- Payload identity SHA-256:
  `60630a80335d5a95ebae87dd2d852c6cb8749a0b92e8617261ec6750b64a794c`.
- Candidate warm bench:
  `rtxpro6000-gemma4-fp8-f4nbtoufbwf66f`; staged checkpoint, CUDA 13
  runtime, and caches are resident. The bench remains director-controlled in
  maintenance through watchdog deadline `2026-07-29T08:13:34.346354Z`.

## Scope

Use `$researcher` with the execution profile. Work offline first; do not claim
or SSH to the bench. Inspect the current official vLLM release/source once for
exact Gemma 4 hybrid-attention, Blackwell sm_120, BF16 activations, and FP8
weight support. Mechanically bind the identities above and implement
`run_vllm_sm120_fp8_endpoint_owner.py` as a lifecycle-pure owner for the
existing registered bench.

The owner must reuse the exact staged checkpoint, stop only the recorded
resident SGLang server after a future atomic claim, require quiescent GPU
memory before vLLM launch, retain through ordinary runtime repairs, expose one
private endpoint, and run exactly one true concurrent-c32
`research/factory/tools/lab-endpoint-pair` sample after a future director
execution binding. It must preserve 4,214 prompt and 358 output tokens per
request, the frozen request/payload identities, and application-error-aware
classification.

Persist `VLLM_SM120_FP8_ENDPOINT_OFFLINE_RESULT.json` with the exact vLLM
version/source identity, support conclusion, final owner hash, runtime
arguments, resident checkpoint path, expected memory geometry, target
endpoint command, bounded repair/release paths, and the exact detached-owner
command. Return typed `unsupported` if current official vLLM cannot reach the
exact model/FP8/sm_120 consumer without changing model semantics.

## Decision rule and budget

Offline preparation budget: 35 minutes wall clock, no GPU, no provider
mutation, and at most 10 GiB of project-local source/wheel cache. Requested
paid ceiling for a later same-bench execution is `$7`, covering remaining
provider exposure through the existing watchdog. A reservation is not claim
authority.

A future measured run advances if it produces 32/32 valid generated responses
and improves cost or service time versus the exact SGLang control. It meets
the campaign target only at or below `1.048637203302411 s/request`. Any
pre-science runtime incompatibility is retained mutable repair while the
watchdog window fits; a valid slower result closes only this exact vLLM
placement.
