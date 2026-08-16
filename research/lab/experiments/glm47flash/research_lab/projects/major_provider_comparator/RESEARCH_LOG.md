# Research log

## 2026-07-15 — exact-model comparator audit

Question: can a current major-provider GLM-4.7-Flash offering supply a matched comparator for the frozen background-agent workload?

Action: performed a $0 Cloudflare official-documentation audit, content-bound in `COMPARATOR_AUDIT_2026-07-15.json`; no account access, requests, or provider mutation.

Evidence: Workers AI publicly documents the exact `@cf/zai-org/glm-4.7-flash` model, 131,072-token context, function calling, OpenAI-compatible chat completions, streaming, and $0.06/M input plus $0.40/M output. The 8:1 normalized price remains $0.88/M output-equivalent. Text generation is documented at 300 RPM. The frozen campaign scorer instead requires SGLang `/generate` and raw teacher-forced input-token logprobs; the provider documentation only documents chat-completion output logprobs.

Interpretation: retain Cloudflare as the strongest current exact-model vendor price anchor, but reject it as a technically runnable matched replay under the unmodified quality contract. No provider-quality, service, latency, or reliability comparison is claimed.

Next move: only if granted Cloudflare invocation authority, run a bounded capability probe with retained raw responses; a claimable matched replay additionally needs a provider-supported input-token-logprob route or explicit authorization for a new quality protocol.

## 2026-07-16 — OpenRouter traffic and current cost normalization

Public model-page data for exact permaslug `z-ai/glm-4.7-flash-20260119` records `60.164B` total tokens and `6.122M` requests across the seven complete UTC days ending 2026-07-15, including `24.326B` cached prompt tokens and `3.495B` completion tokens. The exact full47 c16 result costs `$0.5534/M` output-equivalent at the `$1.10/hour` planning rate and full utilization: above the `$0.40/M` output-only retail line, but below the `$0.88/M` 8:1 input/output retail anchor whenever utilization exceeds about `62.9%`. Depth43 and depth39 reach `$0.4801/M` and `$0.4160/M`, respectively, but remain quality-deferred structural proxies. The content-bound snapshot, formulas, source URLs, and claim limits are in `OPENROUTER_TRAFFIC_AND_COST_SNAPSHOT_2026-07-16.json`.
