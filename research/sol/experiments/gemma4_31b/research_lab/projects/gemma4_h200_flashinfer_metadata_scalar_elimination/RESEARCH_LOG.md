# Research log

## 2026-07-23 — exact scalar consumer, sole H200 pair, and minimum trace

Question: can the pinned SGLang v0.5.13 sliding-window metadata path remove the per-decode host read after `create_flashinfer_kv_indices_triton` while preserving the retained dense-add endpoint?

Action: materialized and verified the 62,578,655,208-byte immutable project-local snapshot, claimed `h200-sync-linear-e00vhh6h29fj68x91g`, and bound the exact scalar consumer to `triton_backend.update_sliding_window_buffer`: `window_kv_indptr[-1]` was converted to a Python slice bound before the `full_to_swa_index_mapping` gather. Froze one graph-safe Triton intervention that masks an in-place gather using the device-resident indptr count. Its actual-producer H200 test passed empty, odd, reordered/cache-hit, page-boundary, filter/merge, maximum exact-workload, complete-output-consumer, and dynamic CUDA-graph replay cases. One ordinary pre-science object-API defect was repaired under the durable owner; the persisted control was not replayed and no candidate endpoint invocation had begun.

Measured evidence:

- Exactly one profiler-off c32 control/candidate pair passed 32/32 outputs, semantic smoke tests, runtime-path proofs, and exact cache/token accounting. Control was `0.6772850433437725 s/request`; candidate was `0.6855998213125076 s/request`, a `1.2276630129%` regression. The retained `0.6762324541249995 s/request` frontier remains unchanged.
- The candidate path ran with a measured fixed workspace capacity of 32,736 int64 elements and read the valid count only inside the Triton kernel. Metadata equality and CUDA-graph replay passed.
- The minimum trace confirmed the causal prediction: four-byte D2H long-sync predecessors fell `358→0`, all D2H long-sync predecessors were zero, and long syncs fell `387→29`; long-sync time fell from `12.897130083` to `4.691957794 s`. The remaining 29 predecessors were 14 16-byte H2D copies, 14 8-byte H2D copies, and one missing predecessor—not replacement scalar reads.
- The removed synchronization boundary did not transfer to endpoint gain. The capacity-masked translation kernel is therefore an endpoint-negative replacement for the stock advanced-index gather/copy path at this geometry; this exact mechanism is closed.

Decision: do not retain, promote, replay, or sweep this intervention. Preserve the dense-add frontier and move to the already scheduled true two-stage local-attention work. Authoritative evidence is `artifacts/metadata-scalar-20260723t0107z/TERMINAL.json`; the persisted profiler-off producer is `PERSISTED_PAIR.json`, and the trace counter is `CANDIDATE_SYNC_COUNTER.json` in the same directory.

Spend and handoff: cumulative claimed exposure was `3533.409724 s` at `$2.46/hour`, conservatively settled as `$2.414496442223`. Retrieved artifacts total 46 MiB. The bench was released ready with the exact project checkpoint, pinned image, and SGLang/Triton/CUDA-graph caches retained warm for `gemma4_h200_local_attention_register_residency` iteration 2.
