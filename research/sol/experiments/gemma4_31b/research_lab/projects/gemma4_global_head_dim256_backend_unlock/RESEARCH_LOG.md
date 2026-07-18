# Research log

## 2026-07-18 — director start

Opened a deep exact-shape architecture/backend discriminator after the canonical serving-flag frontier exhausted its distinct supported candidates. The immediate falsifier is global head dimension 512 to 256 across the ten full-attention layers, with the candidate required to select the actual non-repeating Hopper XQA path and save at least 5% of the canonical endpoint in a conservatively weighted measured subgraph. This is not a quality-preserving or deployable-model claim.

The director started and verified replacement watchdog `gemma-global-head256-h200-202607182110z-watchdog.service` (PID `2626523`), atomically extended bench inventory through `22:30Z`, then stopped and verified the prior watchdog inactive. The extension adds at most `$2.46` beyond the previous `21:30Z` deadline and preserves the same provider instance, disk, checkpoint, and image.

## 2026-07-18 — exact H200 discriminator terminal

Question: does head-256 unlock the actual non-repeating Hopper XQA path and conservatively save at least `0.045972870` seconds/request?

Action: claimed the retained H200, stopped the healthy canonical container only after claim, and ran a project-local exact-shape discriminator in the pinned SGLang image. It timed BF16 QKV/O at prompt chunk 2,048 and decode c32, exact c32 cached-prefix Triton prompt attention (`535` cached plus `3,679` fresh tokens/request), then invoked FlashInfer `trtllm_batch_decode_with_kv_cache` with `backend="xqa"`, head-256, 32 Q heads, four KV heads, page 64, context 4,571, and native non-repeated FP8-E5M2 HND cache. The first discovery helper exceeded H200 shared memory for head-512; the bounded repair switched to the serving path's `extend_attention_fwd` and corrected its native int64 page indices.

Evidence (measured): current/candidate cached-prefix prompt attention was `294.646332`/`80.616829` ms for c32. QKV/O plus prompt attention alone derived `0.125247795`/`0.043547897` seconds/request, a partial `0.081699898` seconds/request reduction. The mandatory XQA call then raised a CUDA illegal-address fault on synchronization; no XQA output or oracle exists. Typed result: `artifacts/global-head256-xqa-20260718t2130z/RESULT.json`; the raw staged terminal is nested beside it. GPU telemetry reached 100% utilization and about 490 W during valid component stages. Post-container H200 health was 0 MiB used, 28 C, 0% utilization.

Interpretation: halving the global dimension has ample measured arithmetic/prompt-attention leverage, but the pinned actual candidate kernel is not runnable at the admitted exact geometry. Candidate support and oracle are hard gates, so the partial savings cannot promote the model change and the architecture/backend line closes. This makes no quality claim.

Next move: none in project scope. The bench was released ready without teardown after `899.141321` claimed seconds, conservatively `$0.614413` at `$2.46/hour`; the image and eight-file checkpoint remain resident and the canonical server container remains retained stopped.
