# B200 NVFP4 Gemma 4 endpoint

## Question

Can the exact `google/gemma-4-31B-it` revision
`b9ea41a2887d8607f594846523f94c6cc75ac8a4` run through the pinned vLLM
native-NVFP4 path on one B200 with a complete c32 service time at or below
`0.297928281214505 s/request`, while retaining finite, coherent outputs and
the campaign workload semantics?

## Why this matters

The exact-shape predecessor terminal
`../b200_nvfp4_exact_shape_direct_falsifier/artifacts/b200-nvfp4-source-audit-g6-20260728t1030z/TERMINAL.json`
(`sha256 0838a2262bffd0d2e800bbdd0cf857c28115ae0fc6e9677b50433c7a9ff8ecb1`)
passed all 24 production linear rows through the real vLLM
`scaled_fp4_quant` and `cutlass_scaled_fp4_mm` consumers. Its c32 linear
floor is `0.268294541296782 s/request`, below the price-normalized B200
component ceiling `0.29792828121450465 s/request`. This is a positive
component bound, not an endpoint or quality result; endpoint integration is
now the shortest decision-bearing test.

## Scope

- Use `$kernel-research`.
- Bind the exact checkpoint revision, tokenizer, non-reasoning text mode,
  campaign c32 workload, and Artificial Analysis 10K-input view.
- Preserve the pinned image
  `docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79`
  and vLLM commit `6d4a8e6d204a9b2827544003b26321fff62923da`.
- Integrate the same native W4A4 NVFP4 representation and exact consumers
  proven by the predecessor. Weight conversion/loading may be implemented or
  repaired, but request timing must not materialize BF16 weights.
- Measure a scope-matched BF16 or strongest runnable same-B200 control and the
  NVFP4 endpoint at c32. Record complete-request service time, prompt/decode
  throughput, TTFT, memory, power, utilization, failures, and provider cost.
- Run only cheap output/coherence checks until performance merits the
  campaign's later GPQA-Diamond, TauBench, tool-path, and reliability gates.
- Do not transfer the component floor into an endpoint claim, change the model
  revision, delete model capacity, or substitute a synthetic linear proxy.

## Immediate evidence path

Within 30 wall-clock minutes, inspect the pinned runtime's Gemma 4
compressed-tensors loader and implement the smallest content-addressed
checkpoint conversion/loading plus endpoint launcher that reaches the proven
NVFP4 consumer. Persist direct source hashes, immutable identities, storage
estimate, exact launch entrypoint, and a bounded lifecycle request. Do not add
another readiness/audit project. Once this project's reservation is durable,
the director may provision a verified B200 bench; ordinary runtime defects
then remain mutable inside one retained claim, followed directly by the first
tiny real request and c32 comparison.

## Decision

Promote the mechanism only if the complete measured endpoint meets the
price-normalized B200 threshold with coherent outputs and a credible
sustainable-cost path. A miss localizes the residual endpoint cost; it does
not invalidate the already measured NVFP4 linear result.

