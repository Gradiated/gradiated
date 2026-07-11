# vLLM Cost Dissection — the abstraction tax, quantified

*Distilled 2026-07-11 from a 12-agent dissection (11 subsystem readers + 1 critic) of the vLLM clone at `vendor/vllm-study` (= `/Users/js/dev/vllm-study`). All `file:line` citations below are relative to that repo. Raw findings: workflow journal `wf_00a8fab0-872/journal.jsonl`.*

---

## 1. Executive summary — where cost-per-token is lost

vLLM v1 is a three-process pipeline (API server ⇄ ZMQ+msgpack ⇄ EngineCore ⇄ shm+pickle ⇄ Workers) whose hot loop is orchestrated in Python. Every structural mitigation it ships — CUDA graphs, async scheduling, msgspec `gc=False` structs, `stream_interval`, `--api-server-count` frontend scale-out, and now an entire Rust rewrite of the northbound serving layer (`rust/`, 12 crates) — exists to hide or escape Python/GIL/IPC overhead, not to reduce the work. The tax splits into four buckets:

**1. Per-step host CPU (Python interpreter in the hot loop).** Each engine step burns milliseconds of Python that produces no tokens: the scheduler runs two full O(batch) loops with ~10 feature-branch checks per request (~0.3–1 ms at B=256; `scheduler.py:442-624`, plus `update_from_output` at `scheduler.py:1566-1763`, self-flagged as "a performance bottleneck" at `scheduler.py:1561-1563`); KV `allocate_slots()` costs 5–15 µs/request/step even when nothing is allocated (1–4 ms at B=256; `kv_cache_manager.py:269-488`); the model runner's `_update_states` + `_prepare_inputs` add another 0.5–2 ms plus a hard CPU↔GPU event sync per step in sync mode (`gpu_model_runner.py:7644-7657`). Total: **~1–5 ms of Python per step**, hidden only by async scheduling and CUDA graphs — machinery that itself costs padded-token FLOPs and reserved memory. On the CPU backend, where orchestration and compute share cores, this is a naked 3–15% throughput loss (cpu reader, `cpu_model_runner.py:22`).

**2. Per-token serialization and object churn.** One generated token crosses: GPU→`tolist()` (B boxed Python ints), scheduler dict surgery, stdlib queue, msgpack encode, ZMQ syscall, msgpack decode, asyncio queue, detokenizer wrapper (PyO3 call + str concat, 2–5 µs), `RequestOutput`/`CompletionOutput` allocation, per-request asyncio wakeup, pydantic `model_dump_json` (10–30 µs/chunk), SSE write — **3–4 full serialize passes and ~5 queue handoffs across 2–3 process boundaries** (`core.py:1589-1654`, `core_client.py:1005-1010`, `completion/serving.py:402-441`). Streaming costs 20–80 µs of Python per token per request; at B=256 the JSON pass alone is 2.5–7 ms/step of single-core Python — comparable to a small model's decode forward.

**3. GPU bandwidth wasted off the model.** The sampler upcasts the full [B,V] logits to fp32 every step (128 MB at B=256, V=128k; `sampler.py:96`) and the native random-sampling path touches 3–4 such tensors (~400–500 MB of alloc+bandwidth/step). One request with `frequency_penalty` allocates 2×(B,V+1) int64 zero tensors (~524 MB/step; 10–30% step regression; `penalties.py:47-56`, in-code admission "quite inefficient"). Paged KV forces a scatter cache-write kernel per layer per step (32 MB/step for Llama-8B at 256-token decode; `flash_attn.py:1063-1096`) and full-width block-table H2D re-copies (512 KB/step at B=256 to communicate ~1 KB of change; `block_table.py:186-187`).

**4. Structural memory left on the table.** `gpu_memory_utilization=0.92` idles 8% of VRAM (6.4 GiB on 80 GiB ⇒ ~10% fewer concurrent sequences; `config/cache.py:68`) plus a 150 MiB fudge (`gpu_worker.py:799-802`) and a permanent worst-case activation reservation — all because empirical profiling of a nondeterministic Python/PyTorch allocator can't be exact. Batch ceiling is the dominant cost lever, and vLLM structurally shaves it.

**The generality tax underlies all four**: 12,384 lines of config, 2,209-line `envs.py`, 14k lines LoRA, 10.5k multimodal, 49k distributed, 15k torch.compile, ~40 attention backends, 100+ model registry. Every optional feature is "cheap but not free": a per-step or per-request branch that runs even when disabled, and collectively these branches *are* the milliseconds in bucket 1. The clearest self-admission is `rust/`: vLLM rewrote HTTP, chat templating, tokenize, incremental detok, and SSE in Rust (axum + tokenizers + minijinja) but stopped at the engine boundary — so it still pays msgpack+ZMQ per step. A from-scratch single-process Rust engine deletes buckets 1–2 outright (~µs instead of ms), halves bucket 3 by construction, and reclaims bucket 4 with deterministic allocation.

---

## 2. Serving-layer overhead constants (simulator parameters)

Extracted quantified overheads, named for `crates/perf`/`crates/cost`. Values are the readers' estimates from code inspection (calibration status: **uncalibrated — verify against live vLLM before trusting in sim**). B = batch size, V = vocab size, L = layers.

| Parameter | Value / range | Evidence |
|---|---|---|
| `vllm.sched.per_step_python_ms` | 0.3–1 ms @ B=256 (schedule() loop, ~10 branches/req; scales O(B)) | `scheduler.py:442-624` |
| `vllm.sched.update_from_output_ms` | O(B)+O(tokens) second loop; ~0.1–1 ms/step; per-token stop-check fn call | `scheduler.py:1566-1763,1903-1919`; bottleneck admission `:1561-1563` |
| `vllm.sched.dict_ops_per_step` | >1200 string-hash dict ops @ B=256; ≥5 dicts keyed by request_id string | `scheduler.py:415,588-589,985-988,1178-1179,1566-1568` |
| `vllm.sched.preempt_recompute_frac` | 1.0 — preemption resets `num_computed_tokens=0` (full prefill recompute mod prefix cache) | `scheduler.py:1143-1165` |
| `vllm.kv.alloc_slots_us_per_req_step` | 5–15 µs pure Python, even no-op steps (⇒ 1–4 ms/step @ B=256) | `kv_cache_manager.py:269-488`, `kv_cache_coordinator.py:131-372` |
| `vllm.kv.block_size_tokens` | 16 default (CPU backend: 128) | `config/cache.py:47`; `platforms/cpu.py:119-126` |
| `vllm.kv.hash_us_per_block` | 1–3 µs (CBOR+SHA256; ≈0.1–0.2 µs/token; 10–50× vs xxh3 over flat u32s) | `kv_cache_utils.py:591-618`, `utils/hashing.py:43-58` |
| `vllm.kv.py_objects_per_block` | 1 heap `KVCacheBlock` per 16-token page (~300k objects for a 40 GB cache); free of 32k-token req touches 2048 objects | `kv_cache_utils.py:117-176`, `block_pool.py:175-181` |
| `vllm.runner.update_states_ms` | 0.5–2 ms @ B=256 (dict/set churn, condense(), sampling-metadata rebuild) | `gpu_model_runner.py:1172-1483`, `gpu_input_batch.py:686-937` |
| `vllm.runner.prep_python_ms` | 1–3 ms/step total Python preamble (branch forest + numpy temporaries) | `gpu_model_runner.py:4090-4343,1946-1987` |
| `vllm.runner.h2d_copies_per_step` | 8–12 separate `cudaMemcpyAsync`, 2–5 µs driver each ⇒ 20–50 µs launch overhead | `gpu_model_runner.py:2041-2149` |
| `vllm.runner.blocktable_h2d_bytes_per_step` | num_reqs × (max_model_len/16) × 4 B full-width recopy: 512 KB/step @ B=256, 8k ctx (~2 KB/token redundancy; ~30–50 µs PCIe) | `block_table.py:186-187`, `v1/utils.py:139-142` |
| `vllm.runner.d2h_syncs_per_step` | 1 hard event-sync + `.tolist()` (sync mode) ⇒ step = host_prep + GPU, not max() | `gpu_model_runner.py:7644-7657` |
| `vllm.runner.cudagraph_pad_waste_frac` | few % (bucket padding; wasted-token counter exists) | `gpu_model_runner.py:3888-3949` |
| `vllm.sampler.fp32_upcast_bytes_per_step` | B×V×4 (128 MB @ B=256, V=128k), unconditional | `sampler.py:96` |
| `vllm.sampler.random_path_bytes_per_step` | 3–4 × B×V×4 ≈ 400–500 MB alloc+BW, 10–20 kernel launches (native path) | `topk_topp_sampler.py:141,384,430-456` |
| `vllm.sampler.penalties_bytes_per_step` | 2 × B×(V+1)×8 int64 zero-fill+scatter ≈ 524 MB @ B=256 ⇒ 10–30% step regression if ANY request penalized | `penalties.py:47-56`, `model_executor/layers/utils.py:35-48` |
| `vllm.sampler.logprobs_extra_passes` | ~2 full B×V fp32 passes (whole batch) if any request wants logprobs | `sampler.py:86-88,334-347` |
| `vllm.attn.python_ops_per_layer_step` | dozens (unbind/expand/branch tree before the one kernel call) ⇒ ~50–100k dispatcher ops/s @ 32L, 50 steps/s | `flash_attn.py:845-1004` (self-warning at 845-852) |
| `vllm.attn.metadata_build_ms` | ~270-line Python build()/step/group; ms-scale at large B (vLLM added a cache layer to amortize itself) | `flash_attn.py:439-707`, `gpu_model_runner.py:2428-2512` |
| `vllm.attn.kv_append_bytes_per_step` | 2×tokens×kv_heads×head_dim×dtype per layer, separate scatter kernel (≈1 MB/layer, 32 MB/step, Llama-8B @ 256-tok decode) | `flash_attn.py:1063-1096` |
| `vllm.ipc.serialize_passes_per_token` | 3 (msgpack enc + dec + JSON); 4–5 with TP>1 (adds pickle↔shm) | `core.py:1645`, `core_client.py:1010`, `completion/serving.py:440`, `shm_broadcast.py:743,790` |
| `vllm.ipc.queue_handoffs_per_token` | 5 queues, ≥3 context/task switches; B asyncio wakeups/step | `core.py:1306`, `core_client.py:1043`, `async_llm.py:579,660-663` |
| `vllm.ipc.wire_bytes_per_req_step` | 50–150 B each direction (full request_id string repeated per token) | `v1/engine/__init__.py:175-201` |
| `vllm.ipc.encode_decode_us_per_step` | 10–50 µs msgpack + zmq syscalls | `core.py:1645`, `core_client.py:824-826` |
| `vllm.api.stream_python_us_per_token` | 20–80 µs/token/request (8–12 allocs + pydantic + JSON + asyncio wakeup); saturates a core at 10–20k tok/s | `output_processor.py:272-411`, `completion/serving.py:402-441` |
| `vllm.api.json_ms_per_step` | 2.5–7 ms single-core @ B=256 (pydantic `model_dump_json`, 10–30 µs/chunk/req) | `completion/serving.py:440`, engine-arch reader |
| `vllm.api.validate_ms_per_request` | 0.1–1 ms (~1000-line pydantic model, 8+ validators, wrap-validator field diff) | `chat_completion/protocol.py:196-970`, `engine/protocol.py:28-43` |
| `vllm.api.jinja_ms_per_chat_request` | 0.1–1 ms (sandboxed jinja2; minijinja ≈ 10–50 µs) | `renderers/hf.py:266-316` |
| `vllm.detok.wrapper_us_per_token` | 2–5 µs/token/req (PyO3 call + Python str concat; Rust DecodeStream core itself is fast) | `detokenizer.py:95-142,183-186` |
| `vllm.mem.gpu_util_default` | 0.92 ⇒ 8% VRAM idle (6.4 GiB on 80 GiB ≈ 10% of KV budget for a 7B) | `config/cache.py:68`, `gpu_worker.py:533` |
| `vllm.mem.profiling_fudge_mib` | 150 MiB explicit slack, on top of 0.92 | `gpu_worker.py:799-802` |
| `vllm.mem.frag_tokens_per_seq` | block_size/2 ≈ 8 tokens avg tail waste per live seq | `config/cache.py:47`, mem reader |
| `vllm.cpu.per_step_python_ms` | 1–5 ms; 3–15% of a 20–60 ms M4-Pro step; no overlap possible (async sched force-disabled) | `cpu_model_runner.py:22`, `platforms/cpu.py:144` |
| `vllm.cpu.gemm_python_calls_per_step` | ~200 for a 7B (7 linears × 28 layers, per-call Python lambda; macOS = raw `F.linear`, no prepacking) | `model_executor/layers/utils.py:281-320`, `cmake/cpu_extension.cmake:444-451` |
| `vllm.cpu.kv_zero_bytes_per_new_block` | ~14 MiB + 28 Python dispatches (7B, block 128) | `cpu_model_runner.py:170-189` |
| `vllm.api.server_rss_gb` | 1–2 GB per extra `--api-server-count` process | engine-arch reader; `cli/serve.py:99-109` |

---

## 3. Per-subsystem findings

### 3.1 Scheduler (`vllm/v1/core/sched/`)

**Summary.** No prefill/decode phase distinction: each request tracks `num_computed_tokens` vs `num_tokens`; each step hands out tokens from one budget (`max_num_batched_tokens`) until requests catch up (`scheduler.py:398-407`). Chunked prefill is implicit (`num_new_tokens = min(remaining, token_budget)`); prefills and decodes mix freely. Running list served first, then FCFS/priority admission. Preemption is LIFO with full recompute. Results return through `update_from_output`, a second full O(batch) Python loop. The file (2,683 lines) is drenched in optional-feature branches (KV connectors, LoRA, multimodal, mamba, spec decode, DP balancing, streaming sessions) that execute in the hot loop even when unused.

**Top overheads.** Per-step O(B) loop with ~10 branch checks/req (~0.3–1 ms @ B=256; `scheduler.py:442-624`); `update_from_output` per-token appends + stop checks + one `EngineCoreOutput` alloc/req/step (`scheduler.py:1566-1763,1744-1760`); >1200 string-keyed dict ops/step (`:1051-1074,1095-1112`); SchedulerOutput serialized across the process boundary every step (`multiproc_executor.py:310-320,377`); preemption = full recompute (`:1143-1165`); O(n) queue rebuilds on any finish (`request_queue.py:109-116,175-184`).

**Steal.** The unified token-count model (one integer comparison subsumes chunked prefill, prefix hits, resumption, spec decode; `:398-407`); single admission knob (token budget + max_num_seqs; `:416,643-645`); running-first ordering (`:440,636`); continue-not-break on blocked requests (`:526-530`); diff-based worker state (send full data once, deltas after; `output.py:182-189`); LIFO preemption (`:572`); advance-then-reconcile `num_computed_tokens` (`:1167-1186`); sequence-number fencing for deferred frees under async execution (`:301-307,2136-2163`).

**Kill.** KV-connector/disagg plumbing (~600 lines, a quarter of the file; `:124-162,687-757,2351-2683`); encoder budget + `_try_schedule_encoder_inputs` (`:1319-1477`); LoRA constraint checks (`:626-634`); mamba chunk alignment (`:338-394`); priority queue ABC (`request_queue.py:20-208`); DP prefill throttling (`:396,436-438,461-471`); streaming-input sessions (`:1217-1258`); the scheduler/worker process split itself.

**Simplify.** Dense integer slot indices into SoA arrays instead of string ids + dicts (µs instead of ms); collapse schedule/update into one step function writing directly into runner buffers; avoid preemption via admission watermark (vLLM has it opt-in: `scheduler_reserve_full_isl`, `:291-293,914`); one waiting queue; branchless stop-check.

**Idea worth keeping:** steady-state fast path — when no request joined/finished, the schedule is "everyone +1 token"; barge can make the modal step near-free (vLLM can't; it rebuilds dicts every step).

### 3.2 KV cache / paging (`vllm/v1/core/`)

**Summary.** Single pool of fixed 16-token pages behind a 4-layer Python hierarchy (KVCacheManager → KVCacheCoordinator → per-group SingleTypeKVCacheManager → BlockPool), one Python object per page, a hand-rolled doubly-linked LRU free list, prefix caching via chained CBOR+SHA256 content hashes. Paging buys zero external fragmentation, block-granular prefix sharing, and hybrid-model coexistence — at the price of paged-kernel requirements, gather-based KV access, and ~7,000 lines whose generality (multi-group, DCP/PCP, connectors, eagle, kv-events) leaks into every hot path.

**Top overheads.** ~8-call allocate chain per request per step even when 15 of 16 steps allocate nothing (5–15 µs/req; `kv_cache_manager.py:269-488`, `single_type_kv_cache_manager.py:113-192,285-363,508-545`); ~300k Python block objects for a 40 GB cache with O(N) interpreted pointer surgery on alloc/free (`kv_cache_utils.py:117-422`, `block_pool.py:697-718`); CBOR+SHA256 per 16-token block (`kv_cache_utils.py:591-618`); full-width block-table H2D every step (`block_table.py:186-187`); paged access itself — a Triton slot-mapping kernel per group per step and scattered (non-contiguous) KV writes (`block_table.py:153-184,348-411`).

**Steal.** Integer block ids as the sole scheduler↔worker currency; chained incremental prefix hashes with walk-until-miss lookup (`request.py:247-250`, `single_type_kv_cache_manager.py:592-597`); lazy eviction — cached blocks sit in the free queue until reused (`block_pool.py:657-695`); reverse-order frees so tails evict before shared prefixes (`block_pool.py:697-718`); recompute-last-token rule on full hits (`kv_cache_manager.py:226-232`); admission-only watermark (`:388-395`).

**Kill.** The whole group/coordinator layer (860 + 1,561 lines for hybrid models); connector/external-KV params in every allocate call; kv-event emission (~40% of `block_pool.py`); DCP/PCP scaling; eagle handling; multimodal/LoRA/salt hash keys (~160 lines/hashed block); the union-typed duplicate-hash map; the Python-object free list.

**Simplify.** Block metadata as SoA (`ref_cnt: Vec<u32>`, `hash: Vec<u128>`, intrusive index list); steady-state alloc = one integer compare per request; hashing = xxh3_128 over raw token bytes ‖ parent hash (~50–100 ns/block); delta (or zero, on unified memory) block-table updates; watermark = arithmetic on two counters.

**Key idea for barge:** without a fused paged-attention kernel, do NOT page — contiguous per-slot KV in 1–4k-token chunks (worst-case round-up ≤25%, typical ~12%) beats paying a full KV gather (read+write of the whole cache) every step. Get prefix economics by hashing prompts in 256–1024-token chunks and memcpy-on-hit. Add paging only when a fused kernel lands. (See critic contradiction C1.)

### 3.3 Engine architecture & IPC (`vllm/v1/engine/`, executors)

**Summary.** ≥3 OS processes: API server (AsyncLLM: tokenize/detok/HTTP), EngineCoreProc (scheduler+executor busy loop, 3 threads to escape the GIL; `core.py:974-1001`), and per-rank WorkerProcs (TP>1). API⇄Engine is ZMQ + msgspec/msgpack with a custom zero-copy tensor extension (`serial_utils.py`, 628 lines); Engine⇄Worker is a shm ring buffer carrying pickle (`shm_broadcast.py:743,790`). One token crosses 3–4 serialize passes and ~5 queue handoffs. Because per-token frontend Python saturates a core, vLLM ships `--api-server-count` scale-out — an architectural axis that exists only because the frontend is Python.

**Top overheads.** Serialization hops (msgpack enc/dec 10–50 µs/step; pydantic JSON 10–30 µs/chunk/req ⇒ 2.5–7 ms/step @ B=256); queue/task chain with B asyncio wakeups/step (why `VLLM_V1_OUTPUT_PROC_CHUNK_SIZE` exists; `async_llm.py:654-683`); two full per-request loops per step in two different processes (`scheduler.py:1566` + `output_processor.py:606-688`); ~4k lines of process/IPC lifecycle (handshakes, monitors, buffer trackers) whose only purpose is escaping the GIL; string-reflection RPC (`getattr` dispatch + per-call signature inspection; `core.py:1392-1468`, `multiproc_executor.py:986-1002`); `tolist()` boxing of every sampled token (`gpu_model_runner.py:311`).

**Steal.** Thread-role separation without process separation (engine thread does only schedule→dispatch→collect; `core.py:974-1001` rationale); overlap output post-processing of step N with forward N+1 (`core.py:1589-1654`); async scheduling / batch queue (`core.py:519-632`) — "the single most important utilization trick"; `RequestOutputCollector` delta-coalescing mailbox (`output_processor.py:45-107`); dual-path eager aborts (`core.py:1579-1587`); `FastIncrementalDetokenizer` on tokenizers `DecodeStream` (`detokenizer.py:22-62`); msgspec `gc=False` + `freeze_gc_heap` (`core.py:232`) as validation of the zero-alloc steady-state goal.

**Kill.** The multi-process topology, 5-client hierarchy, 4-executor abstraction, `--api-server-count` + client_index routing, DP coordinator/waves, pickle fallbacks, KV-connector hooks in step().

**Simplify.** Token transport = one bounded channel of `(slot_index: u32, token: u32)`; one output loop in one place; single pinned-buffer readback; pre-rendered SSE JSON skeletons; request struct with ~6 fields instead of `EngineCoreRequest`'s 18 (`__init__.py:88-137`).

### 3.4 GPU model runner (`vllm/v1/worker/gpu_model_runner.py`, 7,733 lines)

**Summary.** Per step: `_update_states` (Python reconciliation of scheduler output into a persistent batch of dense pinned numpy arrays, with `condense()` row compaction), `_prepare_inputs` (numpy cumsum/repeat/index_select + 8–12 small H2D copies + Triton slot-mapping kernel), CUDA-graph bucket dispatch with padding, forward, sampling, `_bookkeeping_sync` (pinned D2H + event sync + per-request Python appends). Async-scheduling mode keeps sampled tokens GPU-resident (`prev_sampled_token_ids`) and scatters them into the next step's input on-device — the retrofit that removes the per-step sync. ~80% of the file is feature plumbing (3 spec-decode variants, mamba, M-RoPE, LoRA, pooling, enc-dec, prompt embeds, PP/DP/DBO, connectors, EPLB, structured output).

**Top overheads.** Full block-table row H2D every step (512 KB @ B=256, 8k ctx, ~99% of per-step H2D traffic redundant; `block_table.py:186-187`, overlapped-not-eliminated per comment at `gpu_model_runner.py:1942`); `_update_states` 0.5–2 ms @ B=256 (`:1172-1483`, `gpu_input_batch.py:686-937`); hard per-step CPU-GPU sync in sync mode (`:7644-7657` — "in the critical path of every single model forward loop"); ~10 separate H2D enqueues, several full-max-size (`:2041-2149`); CUDA-graph padding waste (`:3888-3949`); dense [max_reqs, max_model_len] CPU token matrix (512 MB-class at 1024×128k) with per-step index_select (`:1946-1987`); feature-branch forest (`:4090-4343`).

**Steal.** Persistent batch of preallocated SoA arrays (work ∝ changes, not batch size); GPU-resident sampled-token feedback loop + on-device scatter (`:3719-3721,1764-1876`) — **the single most valuable design for cost-per-token**; kick-off-copy-then-do-CPU-work overlap (`:1940-1942`); event-gated pinned-buffer reuse (`:3778-3790`); slot mapping on GPU (`block_table.py:153-184`); positions/seq_lens computed on device (`:2151-2158`); deferred bookkeeping after next forward is launched (`:4444-4445`); logits-indices gather BEFORE lm_head (`:4396-4397`).

**Kill.** CUDA-graph capture/dispatch/padding machinery (exists to amortize CPython + launch overhead a Rust engine doesn't have); the generality matrix (majority of lines); grammar-bitmask two-phase execute/sample split; per-layer slot-mapping dicts rebuilt per step (`:4052-4056`); sample-then-discard for partial prefills (`:2063-2068,2196-2200`).

**Simplify.** One packed pinned struct-of-arrays, ONE H2D memcpy/step; slot free-list + indirection instead of `condense()` row moves; GPU-resident per-slot sampling params with write-on-change; no dense token matrix (per-request Vec for detok only); explicit prep-N+1-while-N-runs pipeline instead of `ExecuteModelState`.

**Budget note:** vLLM spends 1–3 ms/step of Python and hides it; barge should target <50 µs so neither async-retrofit nor graphs are needed initially.

### 3.5 Attention backends (`vllm/v1/attention/`, csrc)

**Summary.** ~40 registered backends behind per-layer `AttentionImpl` objects. The decisive finding: **vLLM deleted its custom CUDA paged-attention kernels** — `csrc/attention/` holds only dtype headers (classic paged_attention survives only in `csrc/rocm/attention.cu`). The winning design is a varlen FlashAttention call taking `(cu_seqlens_q, seqused_k, block_table)` directly: one launch handles a mixed prefill+decode ragged batch with zero padding; paging became a kernel *input*, not a kernel family. A portable Triton "unified attention" kernel (1,189 lines) does the same, with split-KV + LSE-merge reduction for long-context decode.

**Top overheads.** Per-layer Python glue (unbind/expand/70-line branch tree) before every kernel call, self-flagged: "even view/slice ops are surprisingly slow" (`flash_attn.py:845-1004`); ~270-line metadata `build()` per step per group, ms-scale, with a caching layer added purely to amortize its own abstraction (`flash_attn.py:439-707`, `gpu_model_runner.py:2428-2512`); separate KV-append scatter kernel per layer per step (32 MB/step Llama-8B; `flash_attn.py:1063-1096`); `.item()` syncs in decode/prefill splitting (`utils.py:564-633`); CUDA-graph padding + permanently reserved split-KV workspace (`flash_attn.py:481-494`).

**Steal.** Varlen-shaped attention API from day one — `fn attention(q, kv, cu_seqlens_q, seq_lens_k, block_table_or_offsets, out)` — so bucketed-SDPA can be swapped for flash-attn FFI later; decode-first batch ordering with a single split point (`utils.py:564-633`); cascade/shared-prefix attention (≥8 reqs sharing ≥256-token prefix ⇒ compute prefix attention once + LSE-merge; `flash_attn.py:1563-1654` is a complete recipe); split-KV + logsumexp merge for long-context decode (`triton_unified_attention.py:685-800`); CPU backend's interleaved [blocks, kv_heads, block, 2×head] layout and block-size-as-SIMD-tile principle (`cpu_attn.py:88-96,459-499`).

**Kill.** The registry/plugin system (root cause of the per-layer glue); metadata-builder machinery; CUDA-graph accommodations; model-zoo features in the hot path (DCP, enc/cross, ALiBi, sinks, softcap, MLA); FlashInfer-style per-step host planning.

**Candle-without-custom-kernels cost model** (decode attention is memory-bound; bytes ≈ time): per-seq loop = 1× KV reads but B×L tiny launches/step (worst); naive padded SDPA = 2–4× waste on long-tail lengths; **length-bucketed padded SDPA (4–8 buckets) = ~1.1–1.3× waste, few launches — best without custom kernels**; gather-then-SDPA = ~3× KV traffic. Barge can sort/bucket freely because latency is a non-goal. Fold KV-append into the QKV-projection epilogue (possible only with contiguous KV) to eliminate one full K/V read+write per layer per step.

### 3.6 Sampler (`vllm/v1/sample/`)

**Summary.** GPU nn.Module after forward: optional full-vocab log_softmax, unconditional fp32 upcast, masks/bad-words/penalties, greedy argmax fast path, temperature, top-k/top-p (FlashInfer / Triton pivot / full-sort fallback), Gumbel-max exponential-noise trick to avoid `torch.multinomial`'s sync. Batch-level uniformity flags (`all_greedy`, `no_penalties`…) make unused features nearly free, but the framework (pluggable LogitsProcessor ABC with persistent-batch add/remove/swap protocol, 4 logprobs modes, multi-backend dispatch — ~250 of 516 lines in `topk_topp_sampler.py` is backend selection) adds hot-loop surface.

**Top overheads.** fp32 upcast B×V×4/step (`sampler.py:96`); native random path 3–4 full B×V fp32 tensors (~400–500 MB/step; `topk_topp_sampler.py:141,430-456`); penalties 2×(B,V+1) int64 zero+scatter (~524 MB/step, 10–30% regression; `penalties.py:47-56`); full-vocab sort fallback (`topk_topp_sampler.py:384`); one seeded request degrades the whole batch to the slow path + per-request Python RNG (`:158-165,463-467`); one logprobs request forces 2 extra full-batch B×V passes (`sampler.py:86-88,334-347`); structured-output bitmask with Python re-sorting + pinned alloc + H2D on the critical path (`structured_output/utils.py:112-143`); blocking D2H `.tolist()` per step (`gpu_model_runner.py:7644-7657`).

**Steal.** Gumbel-max via exponential noise — `argmax(probs / Exp(1))`, no sync, fusable (`topk_topp_sampler.py:446-468`); batch uniformity flags + specialized dispatch (`metadata.py:17-28`, `sampler.py:256-271`); metadata rebuilt only on batch-composition change (`gpu_input_batch.py:826-832`); in-place logits mutation; top-k-only via `torch.topk` + gather (`:407-427`); never sort the full vocab (pivot principle).

**Kill.** LogitsProcessor ABC + batch-move protocol; penalties as implemented; bad_words / allowed-token full (max_batch, vocab) bool masks / logit_bias / min_p / thinking-budget / logprobs modes; per-request seeds; multi-backend dispatch.

**Barge feature set:** greedy, temperature, top-p, top-k, optional single engine seed, EOS-suppression min_tokens, CPU stop sequences — covers ~99% of OpenAI-compatible traffic; reject the rest at admission. Keep sampling ≤2 vocab-wide passes: at V=128k, B=256, careless sampling costs a full transformer layer's worth of bandwidth per step. Pre-generate exponential noise during the forward. On unified memory, consider GPU top-k(64) + CPU finish per request.

### 3.7 API server / OpenAI serving (`vllm/entrypoints/openai/`, 13.6k lines)

**Summary.** FastAPI/uvicorn validates with ~1000-line pydantic models (8+ validators, `extra='allow'`, wrap-validator field-diff on every request), Jinja2 chat templating in Python, then the ZMQ hop. Return path per token traverses ~6 Python layers: msgpack decode → detokenizer wrapper → stop-string scan → `RequestOutput` graph → per-request asyncio generator → pydantic chunk → `model_dump_json` → SSE f-string. Mitigations (`stream_interval`, coalescing mailboxes, multi-API-server) are all workarounds for Python being too slow.

**Top overheads.** 20–80 µs Python/token/request streaming (`output_processor.py:272-411`, `completion/serving.py:402-441`); per-request pydantic validation 0.1–1 ms (`chat_completion/protocol.py:196-970`); per-token tool/reasoning `parse_delta` in Python when configured (`chat_completion/serving.py:595-599`); per-token stats/OTel bookkeeping in the only loop that touches every token (`output_processor.py:613-616,774-818`); ~10 conditional router families + 13 exception handlers + middleware stack (`api_server.py:196-349`); duplicate renderer objects + sandboxed jinja2 per request (`api_server.py:412-440`, `renderers/hf.py:266-316`).

**Steal.** `DecodeStream` primed with prompt ids + "Invalid prefix" reset recovery (`detokenizer.py:183-186,231-246`); stop-string holdback buffer (keep max(len(stop))−1 chars unstreamed, scan only the new suffix; `:84-90,309-344`); `RequestOutputCollector` one-slot merge mailbox (`output_processor.py:45-106`); `stream_interval` as *default posture* not option (`config/scheduler.py:163`); the single-hot-loop discipline (`output_processor.py:594-601`); detokenizer-triggered abort back into the scheduler — stops burning forward-pass slots (`output_processor.py:678-681`); `fake_stream_generator` trick (`completion/serving.py:271-278`).

**Kill.** The process split + core_client (1,700 lines) + dp_supervisor (556); pydantic layer → serde; the RequestOutput object graph; Responses API (5k+ lines), beam search, echo, plugins, parser zoo (`vllm/parser/`, dozens of model-specific modules), renderer registry (~3.5k lines); per-token tracing.

**Simplify.** 400-line stream generator → ~40 lines with n=1/no-echo/coarse chunks; skip incremental detok entirely for non-streaming requests without stop strings; usage on final chunk only; 2 error paths instead of 13 handlers; `max_tokens = min(user_max, ctx_len − prompt_len)`.

### 3.8 Generality tax (core-engine inventory)

Line counts as proxy for surface that leaks branches into the hot path: config 12,384 lines / 30 files; `envs.py` 2,209; LoRA 14,112; multimodal 10,573; distributed 49,085; `vllm/compilation` 15,312; model registry 1,463 (100+ architectures); platforms 4,720; spec decode 5,981; structured output 2,393. Every knob that *can* be on is *tested* per step or per request — the config empire is the root cause of the milliseconds in §3.1–3.4. Abstraction stack even in the minimal case: EngineCoreClient → zmq → EngineCoreProc → Executor → WorkerWrapperBase → Worker → ModelRunner, with Future indirection even when synchronous (`uniproc_executor.py:45-48`, `core.py:491-499`). Verdicts: barge needs ~20 config knobs, one call path (`engine.step()`), a match statement instead of registries, and a **closed, enumerable hot-loop feature set** — every extension point vLLM offers became a per-step branch or per-request dict lookup (`scheduler.py:1566-1732` is the cautionary tale). Notably killed-with-reasoning: spec decode (extra FLOPs per accepted token — but see critic contradiction C3), TP/distributed (genuine cost feature later, not an abstraction layer now), torch.compile/CUDA-graph machinery.

### 3.9 CPU backend (`vllm/v1/worker/cpu_*`, `csrc/cpu/`)

**Summary.** Reuses the entire GPU stack: `CPUModelRunner(GPUModelRunner)` monkey-patches `torch.Event`/Stream to no-ops, aliases `.gpu` buffers to `.cpu`, and swaps ~10 Triton kernels by mutating module globals (`cpu_model_runner.py:22-119`). Attention is one strong custom C++ backend (CPU_ATTN): plan-then-execute per-thread work items, flash-decode KV split with lock-free reduction, GQA decode fast path, 7-ISA template matrix. GEMMs: 4-level dispatch chain ending, on macOS, at plain `F.linear` (Accelerate) with **no weight prepacking** — oneDNN/sgl/shm-allreduce are compiled out on Apple Silicon. macOS is explicitly experimental; Apple GPU is delegated to the external vllm-metal (MLX) plugin.

**Top overheads.** Python control plane competes with compute for the same cores, no overlap (async sched force-disabled, `platforms/cpu.py:144`): 1–5 ms/step ⇒ 3–15% of a 20–60 ms M4-Pro step; ~200 Python-lambda GEMM calls/step for a 7B (`model_executor/layers/utils.py:281-320`); fresh output alloc per oneDNN GEMM call — tcmalloc LD_PRELOAD treated as required for performance (`_custom_ops.py:3362-3372`, `cpu_worker.py:110-137`); Python per-block KV zeroing (~14 MiB + 28 dispatches/new block; `cpu_model_runner.py:170-189`); multiproc executor forced on just to set OMP env ⇒ one IPC hop per step (`platforms/cpu.py:146-157`).

**Steal (directly applicable to barge-CPU/Metal).** Plan-then-execute attention (`cpu_attn.cpp:26-83`, `cpu_attn_impl.hpp:1467-1548`); **GQA decode fast path** — pack all query heads of one KV head per iteration so each KV block streams from memory exactly once per KV head, converting bandwidth-bound GEMV into small GEMM (`cpu_attn_impl.hpp:1499-1509`) — THE decode-throughput trick on CPU; flash-decode KV split (`envs.py:848`); interleaved KV layout, one pointer per block (`cpu_attn.py:88-101`); block 128 with hard 32-alignment; load-time weight prepacking (`utils.py:281-307`); thread pinning + 1–2 cores reserved for the frontend (docs `cpu.md:152-183`); BFMMLA/bf16 gated on `hw.optional.arm.FEAT_BF16` — M4 Pro has it (`cmake/cpu_extension.cmake:93-98`); caching allocator (mimalloc for barge).

**Kill.** The inheritance + monkey-patch layer; 7-ISA matrix + runtime string-ISA dispatch per op call (`cpu_attn.cpp:127-145`); NUMA machinery; LD_PRELOAD orchestration; torch.compile warmup; 14-parameter attention call signatures.

**Baseline framing.** vLLM-macOS = Accelerate `F.linear` for 100% of GEMMs + NEON/BFMMLA C++ attention + full Python engine on the same cores, no Metal. Honest comparison: barge-CPU vs vLLM-CPU; barge-Metal is free upside. Run the baseline with `--dtype=bfloat16`, explicit `VLLM_CPU_KVCACHE_SPACE`, 1 reserved core — else you benchmark its misconfiguration. Decode on M-series is bandwidth-bound: tokens/s ≈ bandwidth / bytes-touched-per-token (M4 Pro ≈ 273 GB/s).

### 3.10 Memory sizing & KV budgeting (`gpu_worker`, `mem_utils`, `kv_cache_utils`)

**Summary.** KV is sized empirically: snapshot free memory, take `total × 0.92`, run a dummy forward at `max_num_batched_tokens` (default 2048) inside a profiling context, subtract measured weights+activations+non-torch and an estimated CUDA-graph footprint (captured twice — once into a throwaway pool; `gpu_model_runner.py:6535-6594`), then `num_blocks = available // page_size // layers` (`kv_cache_utils.py:1001`). Batch ceiling emerges implicitly from pool exhaustion + `max_num_seqs`.

**Top overheads.** 0.92 default = 8% VRAM idle (`config/cache.py:68`; the residual is literally computed as `unrequested_memory` and never used, `gpu_worker.py:533`); permanent worst-case activation reservation dead during decode (`gpu_worker.py:474-502`); 150 MiB fudge (`:799-802`); double graph capture; tail fragmentation ≈ block_size/2 tokens/seq; hybrid page-size padding burns real bytes (`kv_cache_utils.py:1063-1076`).

**Steal.** The budget identity KV = requested − weights − peak_activations − runtime buffers (excellent explanatory comment at `mem_utils.py:242-282`); measure-once/pin-forever via `kv_cache_memory_bytes` + startup-plan persistence (`gpu_worker.py:821-845`, `startup_plan.py:134-186`); **quantized KV as a first-class sizing input** — fp8/int4 page sizes with scale storage in-page (`kv_cache_interface.py:184-214`): fp8 KV doubles the concurrency ceiling per GPU-dollar, the single highest-leverage lever here; fail-fast `estimate_max_model_len` binary search (`kv_cache_utils.py:747-847`); reporting `max_concurrency` (the batch ceiling = the cost floor; `:933-951`).

**Kill.** Empirical profiling entirely — candle/Rust memory is deterministic: compute weights (safetensors), KV bytes, and a fixed activation arena analytically; target **~98–99% of free VRAM** (recovers ~10% more concurrent sequences ⇒ ~10% lower $/token for memory-bound decode); `gpu_memory_utilization` as a fraction (keep only an absolute reserve); hybrid-group machinery; graph-memory estimation.

**Simplify.** `num_blocks = kv_bytes / (2·L·H_kv·D·block·dtype)`; admission = free-blocks check; skip CPU offload (recompute-on-preempt is usually cheaper than a swap path). On Apple unified memory, treat the budget as an explicit operator byte count and wire memory pressure into admission (`mem_utils.py:147-154` shows cudaMemGetInfo-style APIs mislead on UMA).

### 3.11 `rust/` frontend + benchmark methodology (`vllm/benchmarks/`)

**Summary.** vLLM's northbound layer is now a 12-crate Rust workspace (axum server, minijinja chat templates with pycompat, tool/reasoning parsers, HF/tiktoken/tekken tokenizers, incremental detokenizer, Prometheus, gRPC; mimalloc as global allocator) spawned as `vllm-rs` when `VLLM_USE_RUST_FRONTEND=1`. It replaces N Python API servers with one Rust process (mutually exclusive with `--api-server-count`; `cli/serve.py:263-266`) — but Rust stops at the engine boundary, so **every token still pays msgpack encode (Python) + ZMQ + msgpack decode (Rust) + SSE JSON** (`rust/src/engine-core-client/src/protocol/output.rs:134-161` faithfully mirrors the Python wire struct). The clearest compatibility-tax artifact: `rust/src/parser/python` embeds a Python interpreter in the Rust frontend rather than break parser plugins. Even the benchmark *client* fights Python: it freezes the GC heap and precomputes all inter-arrival delays (`benchmarks/serve.py:2092-2093,437-485`).

**Steal.** The validated Rust stack itself (axum + tokio + tokenizers 0.22 + hf-hub + minijinja + mimalloc + prometheus-client — de-risks barge's non-model layer completely; `rust/Cargo.toml`); the incremental detokenizer design (`rust/src/tokenizer/src/incremental.rs:1-60`: prefix-diff sliding window, `min_bytes_to_buffer` for multi-token UTF-8, push_token/next_chunk/flush trait); the **mock-engine crate pattern** — a fake engine emitting tokens at a configurable rate to profile scheduler/HTTP/detok at 100k+ tok/s with no GPU (`rust/src/mock-engine`); the prequeue/enqueue-then-drain batch API (`throughput.py:139-156`) as barge's *native* mode; `--disable-detokenize` exists because detok costs measurable throughput (`throughput.py:129`).

**Kill.** The frontend/engine boundary itself; DP wave/coordinator protocol; triple protocol surface (HTTP + gRPC + msgpack-ZMQ) — barge needs OpenAI HTTP only; the 28-backend benchmark request-function zoo.

---

## 4. Exact vLLM benchmark metric definitions (match these in barge's harness)

From `vllm/benchmarks/serve.py`, `throughput.py`, `benchmarks/lib/endpoint_request_func.py`, `datasets/datasets.py`:

- **TTFT** = `perf_counter(first SSE chunk with non-empty choices) − perf_counter(request send)` (`endpoint_request_func.py:197,231-236`).
- **ITL** = deltas between successive chunk arrival timestamps (`endpoint_request_func.py:240`).
- **E2EL (latency)** = last-chunk timestamp − send time (NOT connection close) (`endpoint_request_func.py:257`).
- **TPOT** = `(latency − TTFT) / (output_tokens − 1)`, only for output_tokens > 1 (`serve.py:607-611`).
- **request_throughput** = completed / dur; **output_throughput** = Σ output_tokens / dur; **total_token_throughput** = (input+output) / dur, where dur = wall clock around the whole gather (`serve.py:731-734,974-1048`).
- **goodput** = requests meeting ALL supplied ttft/tpot/e2el SLOs (ms) / dur (`serve.py:622-645`).
- **Percentiles**: default p99 over ttft, tpot, itl (`serve.py:1690-1697`).
- **Arrival process**: inter-arrival gaps ~ Gamma(shape=burstiness, scale=1/(rate·burstiness)); burstiness=1.0 ⇒ Poisson; `request_rate=inf` sends all at t=0; cumulative delays pre-sampled then rescaled so the last arrival lands exactly at num_prompts/rate (`serve.py:456-485`). Concurrency cap = semaphore applied AFTER arrival generation, so realized rate can be lower than requested (`serve.py:962-972`).
- **Random dataset defaults**: 1024 input / 128 output tokens, range_ratio 0 (fixed lengths), 1000 prompts (`datasets.py:1929-1941`).
- **Token accounting**: trust server-side `usage.completion_tokens` via `stream_options.include_usage` on the final chunk — otherwise the harness re-tokenizes output text and "may inflate the output token count" (`endpoint_request_func.py:244-247`, `serve.py:595-604`).
- **Offline ceiling** (`vllm bench throughput`): perf_counter around generate-all with temperature=1.0, top_p=1.0, ignore_eos=True, per-request max_tokens; reports requests/s, total tok/s, output tok/s (`throughput.py:122-131,142-164,1270-1284`).
- **Canonical online command**: `vllm bench serve --backend openai --endpoint /v1/completions --dataset-name random --random-input-len 1024 --random-output-len 128 --num-prompts 1000 --request-rate inf --ignore-eos --metric-percentiles 50,90,99`.
- **Barge server surface for compatibility**: OpenAI `/v1/completions` with stream + include_usage; `ignore_eos` and `max_tokens`; `/tokenize`, `/detokenize` (`serve.py:84-146`), `/v1/models` (`serve.py:149-176`). Then every vLLM-published number is directly comparable.
- **Primary cost metric**: $/1M output tokens = (hardware $/hr) / (output tok/s × 3600) × 10⁶ — the offline number.

---

## 5. Critic: ranked cost levers, gaps, contradictions

### Top cost levers (ranked, near-verbatim)

1. **Weight quantization (Q4–Q8) on a bandwidth-bound platform.** M4 Pro ≈ 273 GB/s; decode tok/s ≈ bandwidth / bytes-touched-per-token; bf16→Q4 cuts weight traffic ~4×. Prerequisite: verify candle's quantized Metal matmuls are near bandwidth-optimal (uncovered gap) — if they are 2× off, this lever is halved.
2. **Batch size via continuous batching + chunked prefill.** Weights are read once per step regardless of batch; B=64 amortizes weight bandwidth 64× vs B=1. The single-token-budget scheduler (`scheduler.py:398-407`) + always-topped-up steps is the core mechanism; everything else exists to keep B high.
3. **KV memory efficiency to raise the batch ceiling.** int8/fp8 KV with per-head scales (~2× batch), analytic ~98% budgeting vs vLLM's 0.92 + 150 MiB (~10% more KV), bounded fragmentation. The batch ceiling is the binding constraint on lever 2.
4. **Attention data-movement without custom kernels.** Contiguous per-seq KV + length-bucketed SDPA (1.1–1.3× padding waste) or GQA-packed decode, instead of gather-then-SDPA (~3× KV traffic) or per-seq loops (thousands of tiny launches).
5. **Forward-pass fusion / dispatch economy on Metal (uncovered gap).** Fuse RMSNorm+residual, SiLU·mul, rope; fold KV-append into the KV-projection epilogue. Each unfused elementwise op on candle/Metal = a dispatch + full hidden-state read+write; plausibly 10–30% of step time on a small model — comparable to everything the scheduler readers found combined.
6. **Zero host overhead, single process.** SoA scheduler state, dense slot indices, no IPC, prep N+1 while N runs, sampled tokens GPU-resident. Converts vLLM's 1–5 ms/step of Python into <50 µs; worth 5–20% on 10–40 ms small-model steps, and 100% of the reason vLLM needed async scheduling, CUDA graphs, and multi-process machinery.
7. **Prefix caching + cascade attention** for fat shared system prompts; prefer sharing (cascade) over copy-on-hit where memory is the constraint.
8. **Logits/sampler bandwidth discipline.** Gather hidden states by logits_indices before lm_head; never compute logits for non-final prefill chunks; ≤2 vocab-wide passes. At V=128k, B=256, careless sampling costs several hundred MB/step — a full transformer layer's bandwidth.
9. **Saturation-first admission** (latency non-goal): bin-pack prefill chunks into the budget left by decodes; admit by free-KV watermark sized so preemption never fires in steady state.
10. **Coarse, lazy output path.** 16–64-token SSE chunks, detok-on-completion for non-streaming, pre-rendered JSON skeletons. On Apple Silicon the CPU cores burned per token share the GPU's power/bandwidth budget — a real, if last-ranked, lever.

### Gaps (what the dissection did NOT cover)

- **The forward pass itself / fusion**: csrc is 110k lines, `vllm/compilation` 15.3k; nobody analyzed where GPU time goes inside a decode step or which fusions matter. Biggest omission for barge (see lever 5).
- **Weight quantization as a subsystem** (34.3k lines): formats, group sizes, dequant-in-GEMM vs to-bf16, and whether candle's GGUF Q4/Q8 Metal kernels are bandwidth-optimal. Weight bytes/token is THE dominant cost term and got least coverage.
- **LM head / vocab projection economics**: at V=128–150k the hidden→vocab GEMM is often the largest decode matmul (0.5–1 GB lm_head, 10–20% of weight traffic/step) and the B×V logits tensor dominates the activation arena. Never costed.
- **MoE** (`fused_moe`, 39.2k lines — largest kernel investment in the repo): unmentioned; a strategic model-selection constraint since candle has essentially no fused-MoE path (relevant to Qwen3-30B-A3B plans).
- **Model loading / cold start** (5.8k + 23.2k lines): mmap-vs-copy on unified memory (mmap'd weights GPU-readable zero-copy) untouched.
- **Metrics subsystem cost** (4.1k lines, per-step stats objects on the hot path) — and what minimal accounting barge needs to even measure $/token.
- **Metal/candle execution model**: all launch-overhead reasoning is CUDA-shaped. "Rust has µs launch paths so graphs buy little" is untested on Metal, where per-dispatch overhead is historically *worse* than CUDA. Command-buffer encode/commit costs, encoder batching in candle — unknown.
- **Encode-side tokenization**: ~1–5 ms per 10k-token prompt; at high admission rates with the 1024-input benchmark default this can saturate a core. No design anywhere.

### Contradictions (resolutions chosen for barge in §6)

- **C1 Paged vs contiguous KV**: KV reader says don't page (v1); memory reader says keep paging. Resolution implied by attention reader: contiguous now, paging only when a fused paged kernel exists.
- **C2 Preemption policy**: scheduler reader wants full-reservation admission so preemption never fires; KV reader prefers preempt-and-recompute. Full max_tokens reservation can cut occupancy 2–5× when actual output ≪ max_tokens — fighting the dominant batch-ceiling lever.
- **C3 Speculative decoding**: killed as "extra FLOPs, loss when compute-bound" — but every other reader says decode is bandwidth-bound, where spec decode raises tokens per weight-read and is a cost WIN. Defer for simplicity, not for the stated reason.
- **C4 Async scheduling**: KV reader claims µs-scale Rust bookkeeping removes the need; engine/runner readers call schedule-ahead the single most important trick. The D2H sampled-token sync forces host/GPU serialization regardless of scheduler speed — some overlap is needed either way.
- **C5 Logits dtype**: "f32 end-to-end" vs "argmax on bf16 / fp32-accum softmax". ~128 MB/step of bandwidth at stake @ B=256, V=128k. Unresolved; measure.
- **C6 Prefix-reuse mechanism**: copy-on-hit (spends the memory that is the dominant resource) vs cascade attention (one shared copy). Trade in opposite directions on the batch ceiling.
- **C7 Block size**: 16 / 32–64 / 128 / 256–1024-or-none recommended by different readers; deciding variable (kernel tile width vs fragmentation-vs-indirection) never stated.
- **C8 Incremental vs on-completion detokenization**: steal-the-DecodeStream vs detok-at-finish. Both right: incremental for streaming clients, batch-decode for non-streaming.

---

## 6. Implications for barge (our engine)

Design bets, each justified by findings:

**B1 — Single process, three threads, zero serialization.** HTTP+tokenize pool → SPSC channel → engine thread (schedule, batch, candle forward, sample) → SPSC channel → detok/SSE thread. Justified by: 3–4 serialize passes + 5 queue handoffs per token (§3.3); 2.5–7 ms/step of JSON at B=256; ~4k lines of GIL-escape lifecycle code; vLLM's own Rust frontend stopping at the engine boundary and still paying msgpack+ZMQ (§3.11); `--api-server-count` existing at all. Internal request identity = dense slot index; user request-id strings only at the HTTP edge (vLLM ships the full string per token, `__init__.py:181`).

**B2 — Slot KV: contiguous per-slot arenas, no paging (v1).** Chunked growth (1–4k tokens), length masking; prefix reuse via chained xxh3 chunk hashes + copy-on-hit; cascade attention later for fat shared prefixes (resolves C1/C6 pragmatically: copy-on-hit first for simplicity, cascade when memory-bound). Justified by: without a fused paged kernel, paged KV costs a full gather per step (~3× KV traffic, §3.5) vs ≤25% worst-case round-up waste (§3.2); the entire 7,000-line, 300k-object, 5–15 µs/req/step bookkeeping tower exists to serve a kernel we don't have; and vLLM itself deleted its paged kernels in favor of varlen-FA-with-block-table — paging is a kernel input we can add back behind the same varlen-shaped API (§3.5). KV-append folds into the QKV epilogue only with contiguous KV.

**B3 — Chunked prefill with a single token budget; saturation-first admission.** Steal `num_computed_tokens` catching up to `num_tokens` against one budget (`scheduler.py:398-407`) — the single best design idea in vLLM. Bin-pack prefill chunks into (budget − decodes) each step; admit by free-KV watermark with modest headroom so steady-state preemption ≈ never (splitting C2: no full max_tokens reservation — occupancy is the dominant lever — but watermark admission per `kv_cache_manager.py:388-395`); LIFO preempt-and-recompute as the rare fallback. Steady-state fast path: when membership is unchanged, the schedule is "everyone +1"; make the modal step near-free.

**B4 — Rust detokenization, coarse output.** tokenizers `DecodeStream` natively (the same crate vLLM calls through PyO3, `detokenizer.py:24`), with the holdback-buffer stop-string scan and reset-recovery stolen verbatim (§3.7); incremental only for streaming requests, single batch decode at completion otherwise (resolves C8); `stream_interval`-style 16–64-token chunks as default posture; pre-rendered SSE JSON skeletons; detok/SSE for step N overlapped with forward N+1. Justified by: 20–80 µs/token/req of Python (§3.7), 2–5 µs even for the wrapper alone, and `--disable-detokenize` existing in vLLM's own bench.

**B5 — Minimal sampling, bandwidth-capped.** Greedy, temperature, top-p/k, one engine seed, min_tokens EOS mask, CPU stop strings; everything else rejected at admission. ≤2 vocab-wide passes: Gumbel-max exponential-noise argmax (steal `topk_topp_sampler.py:446-468`), batch uniformity flags, in-place mutation, noise pre-generated during the forward. Measure C5 (bf16 argmax vs fp32) in week one. Justified by: vLLM's sampler can burn 400–500 MB/step — a transformer layer's bandwidth (§3.6); one penalized/seeded/logprobs request degrades the whole batch (§3.6).

**B6 — Analytic memory sizing at ~98–99%.** Closed-form: kv_bytes = free − reserve − weights − fixed activation arena; `num_blocks` (slots) by one division; fail-fast max_len check; persist per-(model, device, config) sizing record. Justified by: 0.92 + 150 MiB + worst-case activation reservation ⇒ ~10% concurrency left on the table (§3.10), all caused by nondeterminism barge doesn't have. KV dtype (f16→q8) as a first-class page-size parameter from day one (lever 3; experiment #7 in PLAN).

**B7 — Async-first step loop, zero steady-state allocation.** Prep N+1 while N runs (double-buffered batch state); sampled tokens stay GPU-resident, scattered into next input on-device (steal `gpu_model_runner.py:3719-3721,1764-1876`); one packed H2D struct copy per step (vs 8–12); per-step allocations = 0 via arenas (vLLM's `freeze_gc_heap` + msgspec `gc=False` validate the goal). Resolves C4: yes the Rust scheduler is µs-scale, but the D2H sync argument stands — overlap regardless. Target <50 µs host/step so CUDA-graph-equivalents are unnecessary; on Metal/unified memory the whole H2D category becomes a no-op trait impl.

**B8 — Attention: varlen-shaped API, bucketed SDPA now.** `fn attention(q, kv, cu_seqlens_q, seq_lens_k, offsets, out)` from day one so flash-attn FFI is a drop-in later (vLLM's own migration path, §3.5); decode-first ordering with one split point; length-bucketed padded SDPA (sort freely — latency is a non-goal); GQA-packed decode on CPU (steal `cpu_attn_impl.hpp:1499-1509`); split-KV + LSE merge only past a context threshold.

**B9 — Bench harness = vLLM's contract, exactly.** Implement §4 verbatim (metrics, gamma arrivals, semaphore concurrency, random 1024/128 dataset, server-side usage accounting) so every published vLLM number is comparable; offline drain-all as barge's native mode; mock-engine crate for GPU-free hot-path profiling at 100k+ tok/s (§3.11).

**Explicitly deferred (with reasons recorded):** spec decode (C3 — revisit in the bandwidth-bound regime; the sim should model it), TP/multi-GPU (real cost feature, not an abstraction layer), structured output (bitmask idea is sound if ever needed, §3.6), CUDA graphs (only if profiling shows launch-bound decode — and validate the Metal dispatch-overhead gap first, §5 gaps).

**Open work items from the gaps (feed WS1/WS2):** measure Metal dispatch overhead per op and candle encoder batching; verify candle GGUF Q4/Q8 matmul bandwidth efficiency; cost the lm_head GEMM + logits tensor explicitly in the sim's activation arena; decide the MoE story before the Qwen3-30B-A3B campaign; tokenize-pool design for long-prompt admission; mmap-vs-copy weight loading on unified memory.
