# Gemma 4 31B OpenRouter provider precision — 2026-07-18

## Question and decision

What weight/endpoint precision do the lowest-priced active providers report for `google/gemma-4-31b-it`, and does OpenRouter evidence establish BF16, FP8, or MXFP4?

Decision use: choose economically relevant precision experiments without assuming that every low-price provider uses the same representation. A provider's own more-specific disclosure or a newer endpoint snapshot falsifies this snapshot.

## Scope and method

- Retrieved the public OpenRouter endpoint API at `2026-07-18T20:13:02Z`.
- Kept endpoints with `status == 0`.
- Ranked them by the campaign's representative request: 3,679 fresh prompt tokens, 535 cache-read prompt tokens, and 358 output tokens. Missing cache-read prices were charged at the ordinary prompt price.
- Treated `quantization` as provider-reported metadata. OpenRouter's provider integration documentation requires providers to supply this field and accepts only broad values including `fp4`, `fp8`, and `bf16`.

## Result

| Rank | Provider | OpenRouter tag | Reported quantization | Input/output $/M | Matched request retail |
|---:|---|---|---|---:|---:|
| 1 | OpenInference | `open-inference/bf16` | BF16 | $0.10 / $0.35 | $0.000546700 |
| 2 | Chutes | `chutes/fp4` | FP4, subtype unspecified | $0.12 / $0.37 | $0.000606040 |
| 3 | WandB | `wandb/bf16` | BF16 | $0.12 / $0.35 | $0.000614930 |
| 4 | Venice | `venice/bf16` | BF16 | $0.12 / $0.36 | $0.000618510 |
| 5 | DeepInfra Turbo | `deepinfra/turbo` | FP4, subtype unspecified | $0.12 / $0.37 | $0.000638140 |
| 6 | SiliconFlow | `siliconflow/fp8` | FP8 | $0.13 / $0.40 | $0.000691020 |
| 7 | Friendli | `friendli` | Unknown | $0.14 / $0.40 | $0.000733160 |

The low-price frontier is mixed: three of the first five endpoints report BF16 and two report generic FP4. The first active endpoint explicitly reporting FP8 ranks sixth on this workload. OpenRouter exposes only `fp4`, not an MXFP4/NVFP4 subtype, so neither Chutes nor DeepInfra can be classified as MXFP4 from this evidence.

Inactive endpoints are not part of the ranking. At retrieval, DeepInfra also had an FP8 endpoint, Novita a BF16 endpoint, and Parasail an FP8 endpoint with `status == -2`.

## Sources

| Source | Retrieved | Evidence type | Use |
|---|---:|---|---|
| `https://openrouter.ai/api/v1/models/google/gemma-4-31b-it/endpoints` | 2026-07-18T20:13:02Z | OpenRouter-reported live API | Endpoint status, price, tag, and quantization |
| `https://openrouter.ai/docs/guides/community/for-providers` | 2026-07-18 | OpenRouter documentation | Establishes that providers submit a broad quantization field and lists valid values |
| `https://openrouter.ai/docs/guides/routing/provider-selection#quantization` | 2026-07-18 | OpenRouter documentation | Defines OpenRouter's public quantization categories and precision filtering |

## Uncertainty and limitations

- OpenRouter's provider integration contract makes the quantization label provider-reported, not an independent audit of checkpoint bytes, GEMM operands, accumulators, activations, or KV-cache dtype.
- `fp4` does not identify MXFP4 versus NVFP4, calibration recipe, selective exceptions, or higher-precision layers.
- `bf16` does not prove that every internal tensor and KV-cache is BF16; it most safely identifies the advertised model representation.
- Price rank is not throughput, uptime, routing share, benchmark quality, or profitability rank. The endpoint set and status can change quickly.

## Next action

Treat BF16, FP8, and FP4 as separate live frontier arms. Request implementation-specific disclosure or perform output/quality fingerprinting before claiming that an FP4 endpoint is MXFP4 or that a BF16 endpoint uses no lower-precision internal cache or kernels.
