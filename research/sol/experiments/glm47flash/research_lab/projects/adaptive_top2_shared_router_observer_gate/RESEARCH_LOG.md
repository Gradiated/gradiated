# Research log

## 2026-07-16 — Director opening handoff

The measured global top-2/shared row changes the old adaptive bound: `8.262%` wall-time savings means a 3% throughput target needs roughly `35.253%` qualification at zero observer overhead, not `74.918%`. Audit only whether the exact pinned router path admits a bounded, device-resident, non-synchronizing confidence histogram. Do not implement or run an observer; close if the hot path needs host synchronization, per-token export, or insufficient overhead margin.

## 2026-07-16 — Pinned-source observer audit: OBSERVER_SOURCE_OVERHEAD_FAILURE

**Question.** Does the exact current GLM/vLLM route admit a confidence histogram that is bounded, device-resident, and non-synchronizing with enough margin for the 3% opportunity?

**Action.** Audited the content-bound checkpoint/config/runtime identities and the local pinned `Glm4MoeLite` source. The router computes FP32 logits on device, and `Glm4MoeLiteMoE.forward` has an exact pre-expert route point. The source-defined candidates are the sigmoid score gap between rank 2 and rank 3 or the normalized rank-2 weight. No host `.item()`, CPU export, or per-token logging occurs in the pinned route.

**Evidence.** The source has no fixed histogram buffer or update primitive. A framework implementation would require temporary bucket/scatter tensors; a custom atomic update would be a runtime/kernel edit outside scope, with contention and wall-time unmeasured. Derived sensitivity from the director's `8.262%` signal and `35.253%` zero-overhead qualification bound reaches about `47.354%` at 1% overhead, `71.557%` at 3%, and `95.760%` at 5%. These are bounds, not observer measurements. Full identities and calculations are in [OBSERVER_SOURCE_AUDIT_2026-07-16.json](OBSERVER_SOURCE_AUDIT_2026-07-16.json).

**Interpretation.** `OBSERVER_SOURCE_PASS` is not supportable: source inspection identifies the statistic and insertion point but cannot prove a bounded update or preserve the narrow overhead margin. This is a typed source/overhead close, not a quality or endpoint claim.

**Next move.** Close adaptive observer routing; do not spend, implement, or prepare an observer successor. Preserve the unconditional top-2/shared result as an unqualified performance bound only.

## 2026-07-16 — Director source-identity correction

Keep the project terminal, but replace `OBSERVER_SOURCE_OVERHEAD_FAILURE` with `OBSERVER_SOURCE_IDENTITY_FAILURE`. The paid server identifies the executed model as native `vllm.model_executor.models.glm4_moe_lite`, routing through `Glm4MoE` and `SharedFusedMoE`; this audit instead hash-bound the Hugging Face implementation. It also interpreted `topk(..., sorted=False)` outputs as exact rank order. Preserve only the arithmetic `8.262%` wall-time opportunity and roughly `35.253%` zero-overhead qualification bound. The artifact does not prove an exact native statistic, insertion point, or overhead/impossibility claim. No reopen or successor.
