# Research log

Scope: establish or reject legitimate current-scope 8K prefix reuse; duplicated synthetic prompts and the short historical V2 identity are inadmissible promotion evidence.

## 2026-07-15 — Current-scope 8K prefix bound

**Question.** Can legitimate tenant-safe reuse in the authoritative 8,192-input/1,024-output workload clear the 594.466 output tok/s / 10% cost gate?

**Action.** Validated the frozen workload bundle, audited its provenance and both splits, checked the measured c16 control and retained prefill/decode wall mix, and computed an optimistic linear prefix-reuse bound. No provider or live launcher was changed.

**Evidence.** [current_8k_prefix_reuse_bound.json](current_8k_prefix_reuse_bound.json) records the bundle identity and calculations. The bundle passes validation, but both fixed-8K records are `length_only` with unavailable prefix identity; the only content-bearing prefix records are synthetic-owned. The strongest synthetic proxy has 176 cacheable full-block tokens on a 4,392-token prompt. The c16 control is 535.286 tok/s with 14.8305% prefill wall share. Reaching 594.466 requires removing 67.1262% of prefill work, or about 5,499 reusable tokens per 8K request. Even an inadmissible optimistic transfer of 176 tokens yields only 0.3186% wall reduction and 536.997 equivalent tok/s. The historical V2 binding is additionally non-reproducible (164 observed vs 183 expected input tokens for all 24 requests), and its frozen schema does not convey cache-salt isolation.

**Interpretation.** There is no source-backed, tenant-safe current-runtime 8K replay in repository-owned evidence. The duplicated synthetic 8K prompt is an upper stress case only and cannot justify a cache-on arm. Prefix reuse is closed for current control without provider work.

**Next move.** Reopen only after a legally usable source-backed 8K bundle binds exact tokenizer/runtime identity, tenant/session cache isolation, and reusable-token/scheduler distributions capable of supporting roughly 5,499 reusable prefix tokens per request. Otherwise spend the slot on a materially different intervention.
