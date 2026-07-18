# Research log

## 2026-07-18 — director start

Opened the first actual endpoint realization after the supported Triton proxy measured `0.10425018715593391` seconds/request (`11.3382%`) complete savings with a passing native-GQA E5M2 oracle. The project may transform only the ten full-attention Q/K/O and Q/K-normalization tensors at load time; the original checkpoint remains immutable. Performance and cheap coherence are recorded separately, and no quality or deployment claim is authorized.

The director started and verified replacement watchdog `gemma-global-head256-endpoint-h200-202607182150z-watchdog.service` (PID `2637130`) through `23:30Z`, then atomically rebound the shared bench lifecycle before stopping the prior watchdog. Maximum incremental exposure beyond the former `22:30Z` deadline is `$2.46`; instance, disk, checkpoint, and image are unchanged.

## 2026-07-18 — sliced endpoint terminal

Question: can the ten full-attention layers run with head dimension 256 and clear the 5% canonical endpoint gate?

Action: materialized the immutable resident SGLang sources, implemented an environment-gated load-time transform in the actual `Gemma4ForConditionalGeneration` loader, and sliced per-head Q/K/O plus Q/K-normalization only. The runtime manifest records exactly 50 tensors across layers `5,11,…,59`, full/local dimensions 256/256, four global KV heads, and retained K=V sharing. Pre-request adapter defects (stale source binding, staged config idempotence, multimodal wrapper routing, vision namespace isolation, V-pool geometry, and coherence serialization) were repaired without invoking the canonical runner. The final healthy server then ran coherence, an HTTP-200 cache flush, and the frozen exact c32 runner once.

Evidence (measured): 32/32 requests completed with 4,214 prompt and 358 output tokens, exactly 17,120 cached / 117,728 fresh prompt tokens. Service time was `0.8354320380624358` s/request versus `0.9194573941250042`, a `9.13858%` reduction that passes the `0.8734845244187539` promotion ceiling and realizes `80.60%` of the proxy-predicted absolute saving. GPU telemetry was 99 samples at 99.404% mean utilization, 123,050 MiB mean memory, and 635.329 W mean power. All three cheap coherence rules failed with repetitive `laL`-like text. Checkpoint metadata was identical before/after under a read-only mount. Cumulative claimed exposure was 1,049.511 seconds, conservatively `$0.717166`, below `$3.75`. The typed terminal is `artifacts/global-head256-sliced-c32-resume-20260718t2225z/TERMINAL.json` (`ffecdc4a6072189e0156463ae8c17c5371124f360c4aaf76cee2855d1cef8142`).

Interpretation: performance promotes, but coherence decisively blocks quality nomination. The head-256 architecture retains measured runtime headroom for a separately authorized training/distillation project; this deterministic slice is research-only and must not serve user traffic. The bench was released available with the healthy candidate container, checkpoint, image, and Triton caches retained; no teardown occurred.
