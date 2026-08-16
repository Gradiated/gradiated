# False-rejection audit — 2026-07-24

## Decision

The lab has sometimes closed a mechanism when the evidence rejected only its observer, one implementation, or one recovery recipe. The recurring causes were:

- treating a final streaming delta as a complete sequence;
- treating raw identity as product quality without an A/A or semantic baseline;
- treating any candidate CUDA execution as an irrevocably consumed scientific arm even when no interpretable result persisted;
- promoting adapter, comparator, archive, compile, or deadline failures into scientific conclusions;
- generalizing one uncalibrated representation or short post-training recipe to the broader mechanism.

The correction is judgment-based: identify the causal level actually rejected, localize surprising failures for semantics-preserving transformations, and continue only when the cheapest discriminating repair has better expected value than alternative research.

## Audited decisions

| Route | Evidence established | Correct disposition |
|---|---|---|
| Native NGRAM grammar-safe routing | `gemma4_h200_ngram_grammar_safe_routing_endpoint/token_trace_hook.py` recorded `recv_obj.output_ids[index]` from the final streaming callback as complete output. Control c32 rows had `completion_counter=358` but one recorded ID; candidate rows had 4–12 final-delta IDs. `DIRECTOR_C32_TRACE_DISPOSITION.json` compared those chunk sizes and reported 1/32 matches. Raw delta concatenation later produced identical 358-token sequences and all 54 defined target-shadow argmax comparisons matched. | **False rejection.** The observer failed. Retain the measured NGRAM performance route and repair request-class routing/validation. |
| Native NGRAM production validation | `gemma4_h200_ngram_production_validation/TOKEN_TRACE_ANALYSIS.json` found a 24-versus-41-token tool rendering, but both parsed to the same `lookup_user(demo_user)` action. The earlier matched endpoint measured `0.7022385985 → 0.5967508053 s/request` (15.02%). | **Premature mechanism rejection.** Investigate verifier numerics or route grammar/tool requests to autoregressive decoding; use tool semantics and later TauBench, not JSON whitespace, as the product gate. |
| Persistent KV replay | `gemma4_agent_persistent_kv_replay` measured 47.6331% cached prompt-token reuse and 2.3108% lower endpoint time. Both arms returned empty token-ID arrays, no control/control baseline was run, and normalized tool structures matched 698/905. | **Premature.** Performance is positive; output variability was not causally attributed to KV reuse. Run a small A/A plus first-mismatch cache/position/KV/logit diagnostic if this route is reprioritized. |
| Contiguous SWA ring | The initial multi-token integration was incoherent. Producer-boundary repair in `gemma4_h200_swa_contiguous_ring_cache/artifacts/RING_PRODUCER_BINDING_FINAL_TERMINAL.json` made transitions exact and measured `0.67665 → 0.65566 s/request` (3.10%). | **False initial rejection, later disproven.** This is the precedent for localizing the first state boundary before closing an exact layout mechanism. |
| Block-paged SWA | `gemma4_h200_swa_block_paged_cache/artifacts/FINAL_TERMINAL.json` reported bit-identical valid rows, a 13.37% consumer gain, and an 11.02% complete decode-boundary gain; only an all-negative padded sentinel became nonfinite. | **Premature.** Repair mask-before-address handling for the invalid padded row, then run the endpoint if still valuable. |
| DFlash | `gemma4_h200_dflash_endpoint/.../FINAL_TERMINAL.json` reached prefill but produced zero complete requests and zero verification events because its sampler expected `weight` and `shard_indices` on Gemma's tied embedding head. | **Adapter rejection only.** DFlash remains unmeasured; a thin tied-head/single-TP sampler adapter is the smallest diagnostic. |
| QServe KV4 attention | `gemma4_l40s_qserve_kv4_attention_component/STATUS.json` closed after Triton rejected module-global `MIN_BLOCK_KV` as non-constexpr. No producer or scientific terminal completed; spend was `$0.6502` of `$4` authority. | **False mechanism closure.** This was a trivial pre-science compile defect. Reopen only if KV4 remains competitive, patch the constant, and measure. |
| Exact AWQ group-scale consumer | `gemma4_l40s_awq_bf16_group_scale_consumer/STATUS.json` records a 127-register, zero-spill candidate compile, but no candidate row persisted; the control rejected a non-column-major operand and archive creation then failed. | **Inconclusive implementation attempt.** Candidate execution without a result should not forbid a corrected discovery run. |
| QServe W4A8 | The real-weight component measured 1.87–1.92x speedup. The fused kernel matched its dequantized-W4 oracle, while uncalibrated all-layer W4 accumulated 15.42% relative L2 error at the first down projection and became incoherent. | **Justified representation rejection, not mechanism rejection.** Uncalibrated all-layer W4 is invalid; calibrated, selective, QAT, or other recovery routes remain open when training is in scope. |
| Mirrored E5M2 ring FA3 | `gemma4_h200_mirrored_ring_e5m2_local_fa3/artifacts/FINAL_TERMINAL.json` measured an 8.85% component reduction, but first-transition relative L2 was about 0.055 with cosine about 0.99847; no token or task discriminator ran. | **Premature.** Propagate the first transitions to logits and compare chosen tokens/top-two margins before deciding whether the numerical difference matters. |
| Local-window, head-dimension, KV-head, and MLP-width co-design | Several proxies measured 3–11% whole-request opportunity, while one raw surgery or short 24-update recovery recipe remained incoherent. | **Recovery-recipe failures.** Do not infer that the architectural mechanisms are impossible; revisit only with a materially better post-training hypothesis and sufficient expected value. |

## Valid negative controls

- `gemma4_h200_operation_overlap_discriminator`: bitwise-correct concurrent execution was `1.725440 ms` versus `1.718176 ms` serial. The exact overlap pair is genuinely negative.
- `gemma4_h200_scheduler_gap_pipeline_overlap`: a valid exact endpoint measured `0.674643` versus `0.674525 s/request`. The tested intervention is negative.
- `gemma4_h200_async_token_result_pipeline`: the two-slot lifetime bug was repairable, but observed gain was only 0.0169% with a zero conservative endpoint bound. Repair had poor expected value.
- `sglang_v0512_h200_gemma4_mtp_endpoint`: target verification alone cost `0.811780 s/request`, already 27.22% beyond the `0.638111` ceiling. Scheduler overlap that cannot remove target work is physically insufficient.
- `gemma4_h200_attention_endpoint_integration`: explicit repeated-KV materialization completed correctly at `3.312839` versus `0.784392 s/request`; that exact dataflow is decisively negative.

## Role changes

The director, researcher, and supervisor skills now:

- distinguish observer, attempt, candidate, representation/recovery, and mechanism closure;
- treat divergence from semantics-preserving transformations as localization evidence first;
- verify trace invariants and A/A behavior before attribution;
- separate debugging identity from task quality;
- allow amended retries of invalid discovery attempts while preserving costly completed stages and canonical measurements;
- use expected value to choose repair versus a different route.
