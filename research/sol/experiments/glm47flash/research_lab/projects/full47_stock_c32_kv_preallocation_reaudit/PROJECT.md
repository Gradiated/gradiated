# Full47 stock-c32 KV-preallocation re-audit

## Decision question

Is the inherited `46,875.7-MiB` full47 c32 projection double-counting live-request KV/state that vLLM already reserves in its fixed startup KV pool, making unchanged stock BF16-KV c32 directly admissible on L40S?

This is a `$0` accounting/source falsifier with a direct unchanged-model endpoint decision. The valid full47 maxseq16 server loaded at `17.87 GiB`, reserved `16.82 GiB` / `333,488` GPU KV tokens, and captured graphs in `1.26 GiB`. The exact 32-request workload needs at most `32 * (8192 + 1024) = 294,912` tokens before block rounding. A valid depth42 maxseq32 server reserved `412,704` tokens and measured essentially identical c16/c32 peaks while its larger graph set cost only about `1.31 GiB`. These observations conflict with linearly adding request KV occupancy to peak HBM.

## `$0` contract

Within 900 seconds, hash-bind the full47 r3 and depth42/depth43 archives, the original c32 projection derivation, and exact pinned vLLM source. Do not run CUDA/model/provider code, edit the runtime, prepare a controller, or spend.

- Reconstruct vLLM startup memory profiling, available-memory calculation, KV block sizing/rounding, graph/input-buffer allocation, scheduler admission, and whether request KV is drawn from rather than added to the preallocated pool.
- Compute exact full47 BF16-KV bytes per block/token and conservative block demand for 32 complete 8,192+1,024-token requests, including block rounding and a named reserve. Bind the effect of changing `max_num_seqs` 16 to 32 and the measured/source-constrained graph/input-buffer delta.
- Keep model identity and runtime scope exact. Do not transfer depth-model throughput or capacity; use depth42/43 only to falsify or support allocator behavior in the same pinned runtime.
- Locate the provenance of `46,875.7 MiB` and state precisely which term is already resident, incremental, or unsupported. If an exact incremental allocation restores the deficit, name it and close.

Return `NOMINATE_STOCK_C32_DIRECT` only if unchanged full47 maxseq32 startup has a conservative capacity path and the fixed pool admits all 32 complete requests. That result nominates one later unchanged full47 c32 L40S arm against `594.466 tok/s`, complete requests, and the 300-second envelope; it is not throughput evidence. Otherwise return `STOCK_C32_ADMISSION_CLOSE` or `STOCK_C32_ACCOUNTING_UNIDENTIFIABLE` with the exact unresolved allocation. Do not open capture pruning: matched logs show the >32 buckets add only roughly 41–51 MiB, far below the inherited deficit.

If a later stock-c32 arm is nominated, preregister stock c24 on the same unchanged runtime/checkpoint only for a typed maxseq32 initialization/admission OOM and only when this audit proves c24 fits. It must be ready within ten minutes and run through the same sequential retained-session owner/watchdog; successful c32, provider/bootstrap failure, or any other outcome cleans immediately.

## Starting evidence

- `../near_stock_c32_memory_frontier/artifacts/near_stock_c32_memory_frontier_r3_control/`
- `../minimal_depth42_v2_l40s_direct/`
- `../minimal_depth43_v2_l40s_direct/`
- `../minimal_depth44_runtime_memory_tax_gate/`
- pinned vLLM `0.15.0` source and `campaign_100/nebius/`

