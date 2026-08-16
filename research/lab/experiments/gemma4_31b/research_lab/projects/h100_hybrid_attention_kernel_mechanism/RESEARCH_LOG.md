# Research log

## 2026-07-17 — director admission

Activated as the independent deep lane while the L40S direct-FP8 owner executes. It must replace the prior generic fused-attention label with a source/chip causal chain and one exact-shape falsifier or close the branch.

## 2026-07-17 — pinned paged-KV mechanism terminal

- **Question:** can a source-level H100 hybrid-attention change clear 5% of the 1.8249 request/s planning service time without inventing a fused boundary?
- **Action:** traced `gemma4.py` through `Attention`, SM90 backend selection, paged FlashAttention, and Triton unified attention at pinned vLLM revision `ab0a20d...`; ran the deterministic exact-geometry byte/roofline simulation in `derive_mechanism.py`. No GPU, provider, checkpoint, image pull, or compilation was used.
- **Evidence:** local K+V is 16,384 BF16 bytes/token/layer (16 heads x 256 x K/V x 2 bytes), while global K+V is 8,192. Exact decode reads are therefore 429.133 GB/request, 1.538x the earlier constant-8,192-byte floor. FP8 E4M3 halves this to 214.566 GB. At the H100 SXM 3.35 TB/s vendor peak, the reduction is 64.050 ms/request; even granting BF16 the full 50 MiB L2 on every decode step and FP8 none leaves 58.447 ms, 10.67% of the 547.975 ms planning service time versus the 27.399 ms hurdle.
- **Interpretation:** FP8 paged KV is a plausible >=5% HBM mechanism, not a throughput result. Exact arithmetic intensity is 3.80 BF16 FLOP/byte versus the 295.37 FLOP/byte H100 roofline balance. Cross-layer five-local/one-global fusion is source-falsified because o-projection, residual/norm, and MLP dependencies separate the six layer calls; K=V one-copy caching is also invalid after distinct K norm+RoPE and V norm.
- **Next move:** if later admitted, execute only the content-bound BF16-vs-FP8 actual paged producer/consumer contract in `MECHANISM.json`; require the output oracle, >=40% measured DRAM-byte reduction, >=10% component gain, and >=27.399 ms architecture-weighted request saving. Bind an immutable image to the pinned source first because the cached image reports a different vLLM build.

## 2026-07-26 — execution-equivalent source readmission terminal

- **Decision:** `source_complete_start_ready`; a later director may admit one H100 run, but this terminal authorizes neither a GPU claim nor provider creation.
- **Implementation:** replaced the immutable rejected packet with fresh project-local source. The program enters `set_current_vllm_config`, registers native `Attention` with the common Triton paged consumer for both arms, obtains `layer.get_kv_cache_spec`, builds audited `CommonAttentionMetadata`, fills every local 16x256 or global 4x512 cache slot through `unified_kv_cache_update`, and consumes it through `unified_attention_with_output`.
- **Gates:** deterministic matched full-context BF16/E4M3 arms; finite/nonzero BF16-versus-dense-reference and FP8-versus-BF16 cosine/NRMSE oracles; balanced 20-warmup/100-pair CUDA-event timing; exact NVTX-filtered NCU metrics with missing-counter rejection; atomic local/global c8 sentinel; seven-minute reserve; conditional c8/c16/c32 sweep; increasing context-byte reduction; and 50-local/10-global by 358-step economics against 27.3987616 ms/request.
- **Evidence:** 17 narrow static/CPU-mocked tests pass, including each deterministic rejection from the audit. `H100_PAGED_FP8_EXECUTION_READY.json` SHA-256 is `b26a26d28c6062b3bca58c8ae201f4471b1cfeeef82875576819e35a79fad379`.
- **Boundary:** zero provider queries or mutations, zero accelerator seconds, zero spend, and no scientific sample consumed. H100 performance, counters, quality, and economics remain unmeasured until a later director admits the content-bound execution.

## 2026-07-26T07:10Z — execution prerequisite boundary

- **Question:** can the admitted exact H100 component run begin this turn?
- **Action:** inspected the project binding, readiness hashes, live pool inventory, and shared `detached-owner` interface once. The reservation is recorded by the current harness contract as durable for `$3.25`; no compatible live H100 bench is registered.
- **Evidence:** `runtime/gpus.json` at `2026-07-26T07:09:22.144926Z` has zero non-retired `nvidia-h100-sxm` records. The only live accelerator is the unrelated claimed H200. No claim, provider query, SSH, GPU invocation, or spend occurred; `actual_spend_usd` remains `0.0` and scientific samples remain `0`.
- **Interpretation:** typed external scheduling boundary before claim, not a scientific result and not a packet defect. The exact H100 entrypoint remains unchanged and must be run only after the director creates/registers the sole H100 bench.
- **Next move:** director creates/registers the H100 under the durable reservation; then claim once and execute the prescribed local/global c8 sentinel followed only by the conditional sweep, terminalize atomically, and release by the binding deadline.

## 2026-07-26T07:44Z — registered H100 execution boundary

- **Action:** claimed the exact registered bench four times only to repair ordinary launcher/retrieval defects under the same execution contract. Preserved attempts 1–3: image-default `vllm` CLI parsing, missing mounted workdir, and duplicated `python3` entrypoint argument. The final corrected invocation reached the hash-bound program.
- **Measured evidence:** image digest, vLLM version, source hashes, and signatures passed. The first `pair-worker` failed before a scientific result because pinned vLLM rejects the program's `VllmConfig(model_config=None)` with a Pydantic validation error. The child artifact is preserved at `artifacts/h100-paged-fp8-execution-20260726t0724z/attempt4-remote/local1024-c8.timing.json`; the typed terminal is `integration_error`, `scientific_sample_consumed: false`.
- **Decision:** no scientific performance, quality, counter, or economic sample was consumed. The director admission explicitly forbids source repair or a readiness successor, so this is a typed pinned-runtime incompatibility requiring director disposition. The bench was released to maintenance; conservative cumulative exposure recorded as `$0.70`.

## 2026-07-26T08:01Z — bounded ModelConfig repair lifecycle

- **Action:** applied the director-bound ModelConfig proxy repair and updated readiness hashes. Four narrow proxy generations were exercised without replaying any scientific producer: read-only `head_dtype`, `use_mla`, tokenizer-string validation, and architecture hashing boundaries were localized and preserved in the repair manifest.
- **Evidence:** runtime source identity passed on every generation, but the final exact run reached another pre-science `TypeError: unhashable type: 'list'` from the synthetic architecture proxy. `H100_PAGED_FP8_EXECUTION_TERMINAL.json` remains `integration_error` with `scientific_sample_consumed: false`; no candidate CUDA or registered Attention construction completed.
- **Disposition:** harness paused the lifecycle and the bench is now draining with no claim. No further reclaim or provider mutation was attempted. Conservative cumulative exposure is `$1.00`; director must choose a source-justified ModelConfig construction before another paid run.

## 2026-07-26T08:03Z — offline consumer-contract adapter repair

- **Action:** replaced the synthetic `ModelConfig` subclass with a plain exact-geometry consumer contract. The adapter allocates the pinned Pydantic `VllmConfig` object without invoking its producer-side constructor/`__post_init__`, then supplies only the declared attention context: model geometry, cache, parallel, compilation, and attention configuration.
- **Source basis:** the pinned `VllmConfig` declaration separates `model_config` from the attention-context fields, while the bound Triton attention backend consumes the geometry methods/dtype and those context fields. No tokenizer, architecture registry, model resolution, or download is performed.
- **Evidence:** the unchanged geometry/gate program parses successfully and all 17 CPU-mocked construction/contract tests pass. Updated program SHA-256 is `116bbfed88bf18ada2a503bf5626d0cea0577eb4efc0c508a769eaafb7820b8b`. The typed artifact is `H100_OFFLINE_VLLM_CONFIG_CONSUMER_CONTRACT_REPAIR.json`.
- **Disposition:** this is offline integration evidence only, not a scientific sample. H100 execution remains paused, no bench is available or claimed, cumulative provider exposure remains `$1.00`, and a new director lifecycle/spend decision is required.

## 2026-07-26T15:35Z — H100 readmission verification boundary

- **Action:** verified every hash binding in `DIRECTOR_H100_READMISSION_20260726T1531Z.json` against the project-local offline repair, readiness, execution program, and contract files.
- **Evidence:** all four bindings match: offline repair `071f64c8…e237`, readiness `3df9df18…e93f`, program `116bbfed…b8b`, and contract `bc993832…95d6`. The shared inventory has no registered compatible preemptible H100; its H100 records are retired. The project has no durable `$3.25` reservation in `STATUS.json`.
- **Disposition:** remain GPU-ineligible. No claim, provider mutation, SSH, CUDA invocation, or scientific sample occurred. The next action is director/harness reservation plus creation and registration of exactly one compatible bench.

## 2026-07-26T15:46Z — current-record controller binding repair

- **Action:** removed the retired predecessor bench, host, known-hosts, user, and remote-path constants from `run_h100_controller.py`. The eventual owner now atomically claims the bench named by the registered director binding, re-reads `runtime/gpus.json`, and derives all mutable connection and remote-path values from the claimed record.
- **Fail-closed gates:** retired, non-H100, unclaimed/foreign, stale or expired, missing, and director-binding-mismatched records are rejected before SSH/SCP/Docker. The exact project-relative `paged_fp8_execution.py run` command, readiness file, image digest, and scientific gates are unchanged.
- **Evidence:** controller hash `31f258a5…a900`; synthetic validator checks reject retired, available/unclaimed, wrong-accelerator, wrong-fingerprint, and expired records. Existing project tests remain 17/17 passing. Typed binding: `H100_CURRENT_RECORD_CONTROLLER_BINDING.json`.
- **Disposition:** no claim, guest contact, provider mutation, CUDA invocation, or scientific sample occurred. Remain GPU-ineligible until the full `$6.00` reservation and director watchdog extension are durable.

## 2026-07-26T16:27Z — diagnostic-first recovery generation 7 boundary

- **Action:** claimed the exact H100 once, retrieved the resident timing JSON, compact terminal, controller launch marker, and absence of in-program science markers before retry. The resident row was non-decision-bearing (`ValueError: Pointer argument (at 5) cannot be accessed from Triton (cpu tensor?)`).
- **Repair:** hash-bound the existing CUDA `_k_scale`/`_v_scale` normalization and ran only the new local1024/c8 recovery worker; no full replay or second decision-bearing submission was made.
- **Evidence:** recovery timing artifact `artifacts/h100-paged-fp8-execution-20260726t1551z/recovery7-retrieved/local1024-c8.timing.json` SHA-256 `b65af20d622f9c6d4e6e745c77b3c4c4b401c4f795d39888672218b621abd6b9` failed with an uninformative `AssertionError`; neither BF16 nor E4M3 in-program science marker exists, and raw stdout contains only the pinned vLLM FP8 cache notice. Typed terminal SHA-256 is `a4a7946329ed67cd740c9b600e635ed84950cad83e571a8641af884bf7d17ede`, `scientific_sample_consumed=false`.
- **Disposition:** persisted repair generation 8 `REPAIR_READY.json`, released the ownerless claim to `maintenance`, and stopped relaunches. The project remains unresolved and GPU-ineligible pending deliberate director recovery/traceback instrumentation; no provider resource was created or deleted.

## 2026-07-26T16:14Z — bounded H100 execution and retained pre-science repair boundary

- **Action:** the current-record controller claimed the exact H100 once and ran the unchanged local1024/c8 first stage. The pinned image/runtime identity and all bound source signatures passed. Three ordinary consumer-boundary repairs were applied under the retained claim: `is_mm_prefix_lm=False`, `use_mla=False`, and CUDA normalization of Triton `k_scale`/`v_scale` pointers.
- **Evidence:** the first two retries failed before CUDA on missing consumer-contract attributes. The third reached the native Triton cache-update call but returned `ValueError: Pointer argument (at 5) cannot be accessed from Triton (cpu tensor?)`; its timing artifact is preserved at `artifacts/h100-paged-fp8-execution-20260726t1551z/guest-retrieved-repair5.json`. The typed terminal is `H100_PAGED_FP8_EXECUTION_TERMINAL.json` SHA-256 `9824ef7ba156125c9736839d8c5cfc687882b0140362e6283f7aa1760cf0efd2`, `result=integration_error`, `scientific_sample_consumed=false`.
- **Boundary:** the next same-claim owner failed closed because the director/pool had already moved the H100 to `maintenance`; no reclaim, guest contact, provider mutation, or CUDA occurred in that attempt. All failed artifacts and owner states are retained; no performance, quality, counter, or economic result is claimed.
- **Disposition:** GPU execution is externally blocked pending a new director lifecycle decision. The repaired source remains local-only until that decision; current program SHA-256 is `091597f2d17e09c3fcb7d89e853364756c82685afd70e1701dffec9f6b051259`, and 17 narrow tests pass.

## 2026-07-26T16:37Z — primitive traceback recovery and typed NCU boundary

- **Action:** claimed the exact current H100 once, installed the hash-bound primitive diagnostic capture, and retrieved resident timing/terminal/marker evidence before any retry. A patch launcher defect was captured with full traceback and repaired in-claim; the concrete pinned-vLLM `CompilationConfig.custom_ops=[]` assertion was then repaired source-justifiably with `custom_ops=["all"]`.
- **Measured evidence:** the sole unstarted local1024/c8 primitive pair-worker returned `0` and persisted command, stdout, stderr, and empty traceback in `artifacts/h100-paged-fp8-execution-20260726t1632z-retry2/primitive-pair-worker.capture.json` (SHA-256 `75931b670c67f09968b123003e0b85442d7e5fc401288fef7838a4e4dc61115f`). Its timing/oracle artifact is `local1024-c8.primitive.timing.json` (SHA-256 `6d33a79b7b225ae1af57cdcfcb45d763de84e5b1abb1b88f3b06114028c68907`): native BF16/FP8 construction and numerical oracles passed, but counters are absent because `ncu` is unavailable both in the pinned container and on the guest PATH.
- **Decision:** this is not a complete counter-gated scientific sample; no second decision-bearing sample or replay occurred. Typed terminal `H100_PAGED_FP8_EXECUTION_TERMINAL.json` is preserved at the retry2 artifact root (SHA-256 `3db93743d65d8348ca56881c166b7bc568829930af86e968b78fc9374cb16486`, `scientific_sample_consumed=false`). The H100 was released to `maintenance`; provider resources were not created or deleted. Conservative cumulative exposure is `$5.771031118574266`.
