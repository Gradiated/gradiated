# Research log

## 2026-07-27 — source-complete QKV-to-E5M2 cache epilogue

- **Decision:** Selected exactly one boundary: the accepted in-place QKV
  norm+RoPE producer to the indexed NHD E5M2 KV-cache commit. Scheduler
  synchronization was rejected because it waits for dependent model work, and
  previously tested norm/quantization, scheduler, overlap, graph, and tied-head
  candidates were not reopened.
- **Measured evidence:** Direct SQLite reconstruction matched all 3,660 QKV
  chains. Against the retained deferred-local-KV stack, the removable
  divide/cast/store work plus global clones is `0.322976317 s` in the
  `23.038600455 s` c32 window. It represents 19,520 launches and
  459,516,477,440 trace-weighted intermediate bytes; the fused producer still
  owes 54,942,187,520 compulsory E5M2 cache-write bytes.
- **Implementation:** `fused_qkv_kv_cache.py` extends the previously measured
  exact QKV Triton kernel so K/V CTAs store their live BF16 results directly
  into the E5M2 cache. `install_fused_qkv_cache.py` applies only to the pinned
  `gemma4_causal.py` hash and disables the now-redundant downstream cache
  write. `exact_consumer.py` is the sole target-H200 component consumer across
  local/global M=`32,118,1409,1631,2048`.
- **Offline result:** AST/source/installer validation passed. A conservative
  50%-realization transfer from the measured complete window predicts
  `0.6207671440689129 s/request`, a `0.700946%` complete-request reduction from
  `0.625149101968745`; it does not reach the locked
  `0.500119281574996 s/request` target.
- **Handoff:** The source-complete positive is eligible for one
  director-authorized H200 component call only. Use the exact hash-bound command
  in `FIXED_FLOOR_CROSSOP_OFFLINE_TERMINAL.json`. Reject on source mismatch,
  cache-byte mismatch, QKV NRMSE above `1e-5`, registers above 32, spills, or
  non-positive median reduction at any exact geometry. No GPU, checkpoint
  shard, SSH, provider, endpoint, or paid resource was used here.
