# Research log

## 2026-07-17 — exact market normalization and typed fallback

Question: what current exact-model component target and safe venue fallback should the portfolio use while the Nebius L40S correction runs?

Action: captured the exact OpenRouter endpoint feed and Artificial Analysis provider page; normalized current prices to 4,214 prompt / 358 output tokens with 12.7% prompt cache reads; performed one read-only RunPod control-plane check. No provider was created, reserved, polled for readiness, or mutated.

Measured evidence: OpenRouter exposes 15 exact-model endpoints. WandB is $0.12/$0.09/$0.35 per million fresh/cache/output and normalizes to $0.000614925/request ($0.134498/M total tokens). DeepInfra FP8 normalizes to $0.000614287/request ($0.134358/M) while its cache component is missing and conservatively charged at fresh input. Artificial Analysis lists eight providers, a $0.14/M lowest 7:2:1 blend, 10K single-stream methodology, and Parasail as cheapest; its rendered capture does not expose component prices. RunPod returned HTTP 200 with zero pods; the attempted `/v1/gpus` read returned HTTP 400 invalid path, so no stock claim is made.

Interpretation: the current retail hurdle is about $0.134–$0.136/M campaign-mix tokens, consistent with AA’s $0.14/M methodology view. It does not change the active L40S paid decision. No venue is immediately executable because RunPod creation remains inadmissible and this project has $0 mutation authority.

Next move: director should consume `DECISION.md`; keep the fallback closed unless the specified Nebius failure trigger and fresh RunPod admissibility evidence both occur.
