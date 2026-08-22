## 2026-07-28 — exact global K=V projection discriminator

Question: can the five-local/one-global decode attention/KV path expose a semantics-preserving SM100 component candidate independent of M32 dispatch and RMSNorm/FP8 fusion?

Action: traced the exact 60-layer config and pinned vLLM producer/consumer path. Implemented a TP=1 source patch that replaces each global `QKVParallelLinear` materialization with Q+raw-K once, aliases raw-K before the unchanged distinct K/V norms, and preserves the unchanged paged-attention consumer. Added a hash-failing generator and a future exact B200 component runner that consumes the real FlashAttention output.

Evidence: [B200_FP8_HYBRID_ATTENTION_DISCRIMINATOR.json](B200_FP8_HYBRID_ATTENTION_DISCRIMINATOR.json) binds the exact local d256/16-KV-head/16-token-page and global d512/4-KV-head/32-token-page geometry. Across 358 c32 decode steps, the patch removes 39,415,971,840 logical FP8 weight bytes, 469,237,760 BF16 raw-V output bytes, and 2,522,622,197,760 useful GEMM FLOPs from 3,580 global calls. It removes zero launches and changes none of the 13,732,243,046,400 logical KV-read bytes or 10,323,230,720 KV-write bytes. Patch application, source hashes, config equations, and Python compilation pass. CUDA, endpoint replay, bench claims, and provider operations were not performed.

Interpretation: retain as a cheap stackable B200 component discriminator, not a target-closing claim. The peak-HBM sensitivity is only 0.0001558016 seconds/request and is not a measured bound; the decisive risk is that N=20480 and N=18432 remain in the same launch wave.

Next: if the director reserves a component, materialize the exact production M32 hidden capture and checkpoint bytes under this project before claiming, then run `b200_k_eq_v_component.py`. If timing is negative, move to the materially distinct local-window page-traversal/KV-append boundary.

## 2026-07-28 — local-window paged-KV discriminator

Question: can a semantics-preserving 64–65-page local-window rebase remove meaningful recurring work from the exact c32 B200 decode path?

Action: traced the pinned slot producer, BF16 HND append, metadata builder, and first consumer through FlashInfer 0.6.6. Built a deterministic oracle for whole-page rebasing, production lengths 4214–4571, block boundaries, and zero-length CUDA-graph padding.

Evidence: [B200_FP8_LOCAL_WINDOW_KV_DISCRIMINATOR.json](B200_FP8_LOCAL_WINDOW_KV_DISCRIMINATOR.json) binds 50 local layers, five ten-layer groups, 16-token pages, 22 steps with 64 pages, 336 with 65, 17,900 attention calls, and 17,900 append calls. Mandatory local KV traffic is 9,609,989,324,800 BF16 read bytes plus 9,384,755,200 append bytes. External compaction changes neither and removes no source submission. On the SM100-preferred TRT-LLM route it adds 1,790 launches and 30,229,760 explicit metadata bytes; its most generous unmeasured page-ID bound is 481,292,800 bytes, 0.0050083% of KV reads.

Interpretation: typed rejection `adds_recurring_launch_without_proven_consumer_work_removal`. The consumer already receives `window_left=1023`; a contiguous table materialization is semantically valid but physically unsupported as a win. The native fallback can shrink its existing page-list copy, but that does not establish an exact B200 production benefit.

Next: do not reserve B200 for external page-table compaction. Reopen page traversal only with hash-bound TRT-LLM kernel evidence or counters proving old pages are traversed; otherwise use a materially distinct local-attention computation or fusion boundary. The retained global K=V patch is unchanged.

## 2026-07-28T18:07Z — paid-component reservation gate

Question: may the retained global K=V component generation claim the released B200?

Action: validated the project's structured state, checked the project directory for a reservation or lifecycle binding, read the applicable 18:01Z director decision, and queried the exact B200 through `gpu_pool show`.

Evidence: no project reservation or binding file exists; `STATUS.json` still requires one. The director explicitly makes the project non-claimable until both a durable `$2` reservation and fresh lifecycle handoff exist. Bench `b200-nvfp4-computeinstance-i00rqcq5yzr6xc991j` is `maintenance`, reserved in its contents for `gemma4_b200_fp8_residual_hotpath`, and remains under its existing `18:10Z` watchdog.

Interpretation: this is a typed external scheduling/authority blocker, not evidence about the global K=V mechanism. No GPU claim, remote access, CUDA invocation, endpoint request, or provider spend occurred; `actual_spend_usd` remains `0.0`.

Next: director must persist the project-specific `$2` reservation and a fresh exact-B200 lifecycle binding/watchdog. Then resume with one hash-bound M32 production-hidden capture and the prescribed stock/candidate component generation.

## 2026-07-28T18:29Z — global K=V component incomplete

Action: claimed the funded B200, loaded the exact checkpoint, captured one BF16 `[32,5376]` layer-5 input (`cd84ccd1…776a3`), and repaired isolated hook, checkpoint-name, CUTLASS-layout, standalone normalization/rotary, and cache-selector defects without recapturing it.

Evidence: the repaired projection path reached the real attention consumer, but the pinned FlashAttention entrypoint rejects Gemma global `head_dim=512` (`FlashAttention forward only supports head dimension at most 256`). No stock/candidate pair or interpretable component result persisted. [REPAIR_TERMINAL.json](artifacts/b200-global-kv-20260728t1807z/REPAIR_TERMINAL.json) binds the capture and complete failure trail.

Interpretation: incomplete exact-consumer backend integration, not a global K=V mechanism result. The bench was released to maintenance by the bound fence; conservative project exposure is `$1.90`.

Next: bind an exact d512 FlashInfer first-consumer repair that consumes the retained capture only.

## 2026-07-28T18:31Z — d512 reservation gate remains closed

Action: read `DIRECTOR_B200_GLOBAL_KV_D512_RESERVATION_GATE_20260728T1830Z.json` and inspected the exact B200 once.

Evidence: although `STATUS.json` now shows a `$4` ceiling, the named gate itself records that a durable larger reservation is still required before execution and provides no fresh lifecycle binding. The B200 remains unclaimed in maintenance under the existing watchdog.

Interpretation: no researcher execution, claim, hidden recapture, or provider mutation is authorized. This is an authority/scheduling gate, not new scientific evidence.

Next: wait for the director to persist the durable reservation plus fresh B200 lifecycle/watchdog binding, then resume only the d512 FlashInfer consumer using the retained capture.
