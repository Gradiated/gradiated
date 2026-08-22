# RTX PRO 6000 Blackwell Workstation dynamic-FP8 endpoint

## Question

Can the exact `google/gemma-4-31B-it` checkpoint at revision
`b9ea41a2887d8607f594846523f94c6cc75ac8a4` serve the campaign's true
concurrent-c32 workload on one 96-GiB RTX PRO 6000 Blackwell Workstation
Edition at or below `1.048637203302411 s/request`, the family-level
price-normalized equivalent of the fixed H200 target at the current committed
planning rates?

## Why this matters

The fixed qualified H200 denominator is `0.625149101968745 s/request`, and the
20%-better H200 target is `0.500119281574996 s/request`. The current planning
rates are `$3.25/GPU-hour` for H200 and `$1.55/GPU-hour` for RTX PRO 6000,
making `1.048637203302411 s/request` the equivalent service-time ceiling.
RunPod's authenticated inventory reported high-stock 1x RTX PRO 6000
Blackwell Server Edition capacity, but actual REST and GraphQL placement did
not allocate that SKU. The same controller allocated a 96-GiB RTX PRO 6000
Blackwell Workstation Edition at `$1.89/GPU-hour`. This remains a direct
`sm_120` runtime and placement falsifier, but its measured performance and
production economics are SKU-specific and must not be transferred to the
unavailable server edition.

## Bound evidence and identities

- Exact checkpoint revision:
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Controller checkpoint manifest SHA-256:
  `864f24f4631315cd17cc8a3ff1ea57b2725d2a24f29c45778b101f16b5228a4f`;
  expected bytes: `62,546,338,248`.
- Exact tokenizer SHA-256:
  `cc8d3a0ce36466ccc1278bf987df5f71db1719b9ca6b4118264f45cb627bfe0f`.
- Immutable c32 request-identity manifest SHA-256:
  `7a05fa6218a5fbfd87744bca1ac491949ddd64bf0d58007b4d3569594f08225d`.
- Exact materialized payloads SHA-256:
  `60630a80335d5a95ebae87dd2d852c6cb8749a0b92e8617261ec6750b64a794c`.
- Workload geometry: 32 genuinely concurrent requests, 4,214 prompt tokens
  and 358 output tokens per request, text-only, non-reasoning.
- Accelerator placement identity:
  `nvidia-rtx-pro-6000-blackwell-workstation`, expected `sm_120`, 96 GiB
  GDDR7. Exact device name, compute capability, SM count, clocks, and power
  limit must be measured during the director-owned identity handoff.
- Use `research/factory/tools/lab-endpoint-pair` for the actual concurrent
  schedule. A list of 32 requests executed sequentially is invalid.

The source of these identities is
`projects/gemma4_hybrid_attention_placement_codesign/DIRECTOR_H200_55L5G_ENDPOINT_EXECUTION_20260729T0047Z.json`.
The prior permanent-55L5G candidate and its outputs are not inputs to this
project; serve the exact stock model with a supported dynamic-FP8 runtime.

## Scope and immediate experiment

Use `$researcher` with execution profile. Prepare one lifecycle-pure RunPod
owner named `run_rtxpro6000_fp8_endpoint_owner.py` and an immutable execution
packet that:

1. creates no provider resource itself and claims only director-registered
   bench `rtxpro6000-gemma4-fp8-f4nbtoufbwf66f` after it is marked ready;
2. resumably stages the exact checkpoint and pinned packet identities;
3. uses the first tiny `sm_120` load/request as the mutable runtime-support
   discovery boundary;
4. runs one exact concurrent-c32 endpoint sample only after the model identity,
   FP8 activation, request hashes, and real 32-way schedule are proved;
5. records complete requests, failures, TTFT/decode where available,
   service time, throughput, memory, power/utilization, experiment cost, and
   production price-normalized cost; and
6. retains the claim through ordinary runtime repairs and releases only after a
   decision-bearing terminal or an unsafe/deadline disposition.

Prefer current vLLM or SGLang support that actually loads Gemma 4 dynamic FP8
on `sm_120`; do not build a custom kernel merely to get the first endpoint.
The provider create remains director-owned and is forbidden until the `$14`
reservation is visible in the spend snapshot.

## Budget and decision

- Cumulative project authorization: `$14.00`.
- Conservative provider itinerary after reservation: at most five hours at
  the allocated `$1.89/GPU-hour` plus bounded storage and cleanup, remaining
  below `$14`.
- One canonical concurrent-c32 sample; discovery failures before submission
  are mutable repairs, not samples.

Advance this Workstation placement if the exact endpoint is coherent and its
scope-matched cost meets or credibly approaches the fixed 20%-better target.
Close only this placement/runtime combination if the model cannot fit,
current `sm_120` software cannot execute it within budget, or measured
price-normalized cost is negative. A positive result motivates a separately
matched server-edition measurement when that SKU becomes allocatable.
