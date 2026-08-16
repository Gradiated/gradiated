# Research log

## 2026-07-27T05:11Z — current SGLang exact-c32 L40S rebase closed offline

- Decision: `none`. No GPU was claimed; no SSH, provider API, CUDA, endpoint,
  checkpoint-shard read/copy, or provider spend occurred.
- Revision search was capped at two official candidates:
  `v0.5.12.post1` (`5a15cde858ea...`) and current official `main`
  (`c6a6200a1a77...`). The current commit was selected and its direct
  Gemma/FP8/KV/attention/logits/sampler/parser/Dockerfile hashes were bound.
- Source evidence confirms dynamic FP8 has an SM80 minimum, so SM89 is
  supported; E5M2 maps to `torch.float8_e5m2`; Gemma uses separate full/SWA
  pools and separate K/V buffers; and the exact parser/logits/sampler path is
  present. These are reachability facts, not performance claims.
- The decisive analytical lower bound uses only FP8 transformer matrices
  (`29,396,828,160` bytes), one tied BF16 embedding/head (`2,818,572,288`),
  exact full-cache K/V (`5,311,979,520`), and exact rolling-window K/V
  (`13,421,772,800`). Total: `50,949,152,768` bytes
  (`47.450096130371094 GiB`) versus the previously measured exposed L40S
  capacity of `48,305,799,168` bytes (`44.98828125 GiB`), a
  `2,643,353,600`-byte deficit.
- The bound deliberately omits every other positive resident term, including
  FP8 scales, norms, multimodal weights, CUDA context, graph allocations,
  workspaces, scheduler state, fragmentation, and allocator reserve. The
  fixed representation therefore cannot reach the consumer; current-runtime
  timing, completion cost, and reliability are structurally unavailable.
- Implemented and checked `exact_c32_consumer.py`,
  `l40s_endpoint_owner.py`, `offline_audit.py`, and `test_offline.py`.
  The owner is positive-terminal-gated, shared-pool-only, heartbeat-bounded,
  hash-reconciling, retrieval-before-release, and same-claim repair-aware.
  The terminal intentionally contains typed lifecycle `none`, so it must not
  be detached or launched.
- Focused checks: Python compile passed; three unit tests passed; all 32
  canonical request hashes matched the qualified workload; source gates
  passed; terminal/program/hash consistency passed. Durable terminal:
  `L40S_CURRENT_RUNTIME_FP8_REBASE_OFFLINE_TERMINAL.json` at SHA-256
  `f7a7960ae8f07f22eea2eaa2e6e77d96692351c18542e471a6cf46e07bb076f5`.
