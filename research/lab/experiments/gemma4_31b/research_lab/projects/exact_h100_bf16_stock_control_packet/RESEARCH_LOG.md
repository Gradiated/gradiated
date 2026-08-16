# Research log

## 2026-07-17 — director delegation

Prepare one `$0` scope-matched BF16 H100 comparator packet while the materially different L40S online-FP8 experiment owns spend. Do not implement or mutate the shared controller and do not access provider state.

## 2026-07-17 — terminal typed none

Question: can the exact two-shard Gemma checkpoint and exact cache trace bind to the current proven shared lifecycle without code changes?

Action/evidence: audited the content-addressed checkpoint/trace, current `vllm_smoke_control.py`, its complete PASS+cleanup allocation, and the closed H100 canary terminals. The shared launcher's BF16 mode hard-requires a different GLM revision, 48-shard manifest, image, tokenizer/quality inputs, and runners; AWQ mode is also GLM-specific. No CLI/config path consumes the Gemma trace. Raw H100 HBM arithmetic does not itself reject c16 primary or single 10K, so capacity is not the terminal cause.

Interpretation/next: `H100_CONTROL_TERMINAL.json` is typed `none`; a packet would falsely imply an executable consumer. Consume no H100 successor for any L40S terminal. A later content-addressed BF16-compatible adapter emitted by the L40S project would be new evidence requiring fresh director binding, not a conversion of this terminal. `$0`, no provider/GPU/controller mutation, no successor.
