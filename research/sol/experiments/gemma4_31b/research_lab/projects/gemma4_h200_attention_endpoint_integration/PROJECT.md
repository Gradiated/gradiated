# Gemma 4 H200 attention endpoint integration

## Question

Does the promoted H200 attention route survive its missing production boundary—global GQA KV expansion or an equivalent fusion—and reduce exact cache-flushed Gemma 4 c32 endpoint service time by at least 20% versus a contemporaneous stock SGLang control?

## Why this matters

The exact-shape discriminator explains the prior attention floor: local native GQA can use Flash SDPA, while global native GQA at head dimension 512 falls back to Math. Explicit repeated KV makes Efficient attention legal and cuts the frozen attention proxy by 80.10%; combined component margin is 69.92%. That proxy excludes repeated-KV materialization and is not an endpoint result. The campaign should pay next for the real consumer boundary, not another microbenchmark.

## Scope and evidence

- Exact model: `google/gemma-4-31B-it` at revision `b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Exact checkpoint: eight files, 62,578,655,208 bytes, terminal SHA-256 `5f0765fa37f308e21d665571a92c29ba1998b22b5ee67d1edbfac103dafec481`; local source is the content-bound checkpoint named in `IDENTITIES.json`.
- Runtime: SGLang v0.5.12 source commit `127b9e3283f7c2a43234b852ff5c9f1796d53624`, immutable image `docker.io/lmsysorg/sglang@sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a`, TP1, BF16 weights, FP8-E5M2 KV.
- Promoted route: local layers preserve native GQA and select Flash; global layers use the mathematically equivalent repeated-KV layout and Efficient attention, with expansion or fusion included inside the measured runtime boundary. The source component terminal is SHA-256 `92fa69d260407343a2d9defe742e61a89d33068644bc8896774fdffde059e01c`.
- Workload: exact cache-flushed c32, 4,214 prompt and 358 output tokens per request, runner SHA-256 `be4baf081267ca230db1357ed30ff2fe0ab947732ba5fe06396db5706c189a56`, stock terminal SHA-256 `4315123c4eebca244f306adad19c05199e70eec381d4210a53300b8f002fe317`.

Inspect the pinned model and attention backend source, implement the smallest exact route that keeps KV expansion/fusion and memory traffic inside the timed forward path, and bind its diff/source identity. Run a contemporaneous stock control and candidate on the same H200 with cache flush, identical requests, server geometry, and telemetry. A source-typed unsupported result, materialization OOM, or failure to reach the actual endpoint is a valid terminal; do not fall back to another isolated SDPA benchmark.

## Decision rule

The stock reference is `0.7757958429062342` service seconds/request at c32; the candidate must reach at most `0.6206366743249874`, complete all 32 requests with 358 output tokens, preserve nonempty/finite output and a bounded local/global numerical oracle, and report expansion/fusion wall time plus peak memory. Passing promotes an endpoint performance candidate for later GPQA-Diamond and TauBench. Failure closes this exact layout route.

## Limits

150 wall minutes, at most 135 provider minutes, `$6.00`, one H200 bench, 6 local CPU-hours, and 10 GiB artifacts. Use one durable development owner for transfer, image, build, model load, control, candidate, retrieval, and release. Never create or destroy provider resources; release without teardown after the typed terminal.
