# Research log

Opened from the 2026-07-16 user-directed architecture/kernel pivot. Prefer executable kernel evidence over runtime support surveys.

## 2026-07-16 — FP8 component launch blocker

Question: can the exact GLM-4.7 Flash MLA component measure matched BF16 control versus FP8 KV storage/read on L40S?

Action: added `exact_shape_fp8_component.py`, using the pinned vLLM grouped-MLA kernel at batch 8, context 8193, 20 heads, rank 512, rope 64, value 512, and a float8_e4m3fn cache with a matched dequantization path. Syntax validation passed. No timing was produced.

Evidence: the first provider create failed in 0.411 s with exit 3 because the PEM public key was interpolated into cloud-init (`UserData: YAML is invalid`, retained in `artifacts/fp8_component_l40s_20260716_r1/provider-create-diagnostic.json`). Deriving a one-line OpenSSH key corrected that input and created `glm47-sm89-fp8-mla-component-r2`, but the ad-hoc background owner was reaped before emitting an event; the resource entered `DELETING`, with no GPU process, archive, or benchmark result. A user-systemd relaunch did not leave a surviving unit in this harness.

Interpretation: this is an operational durable-owner blocker, not evidence for or against FP8. The project remains unintegrated; the component must be rerun under a harness-supported owner before any c32 claim.

Next move: retry the same bounded script once the execution harness can retain the launcher/session; preserve the one-line key correction and the existing diagnostic.

## 2026-07-16 — Frozen offline matrix reaches typed GPU boundary

Question: can the minimal source-pinned writer/scale/decode path clear the frozen B1/B8/B32 numerical and timing contract at `$0`?

Action: implemented `fp8_mla_triton.py` with a per-page/token/head max-abs scale (`max_abs / 448`, clamped to the smallest representable scale), an FP8 cache writer, and an in-loop FP8 dequantizing MLA decode kernel. Added `run_frozen_matrix.py` for the exact seed, geometry, 15 batch/context combinations, compile parameters, and exact cache-byte accounting. Both files pass Python syntax compilation.

Measured evidence: the runner executed locally in 4.7 ms and emitted `artifacts/frozen_matrix_20260716_r1/result.json`. All 15 exact byte rows were generated. FP8 storage including one FP32 scale per cache token is `49.6528%` of BF16 storage, i.e. `49.6528%` savings; for B32/context 9215 the rows are `339,738,624` BF16 bytes versus `171,048,960` FP8-plus-scale bytes. Numerical and timing rows are zero.

Typed boundary: this host has no `torch`, no `triton`, and no CUDA device (`decision=GPU_REQUIRED`). No provider resource or background owner was created, consistent with the `$0` contract. Therefore this run is neither COMPONENT_PASS nor a performance result; it is an implementation plus exact accounting result awaiting an already-authorized CUDA/Triton environment.

Next move: execute the same runner with the pinned vLLM/Triton runtime on an authorized GPU environment, then record numerical agreement, writer/stage-1/full-attention p50/p95, saturation, and fallback before any server nomination.

## 2026-07-16 — Final `$0` paged/split source correction

Action: replaced the unwired scalar source with a bounded paged implementation. `write_fp8_cache` now maps logical tokens through `block_table` into shuffled physical pages and writes one explicit per-page/token/head scale. `decode_fp8_mla` now consumes the same page table, tiles tokens by `BLOCK_N=32`, and launches independent `NUM_KV_SPLITS=4` programs. No provider, background owner, or server integration was attempted.

Static evidence: the cached image digest `97187c…` contains PyTorch `2.9.1+cu129` and Triton `3.5.1`. AST/static source checks pass for writer invocation, page table, page size, block-N tiling, and split decode. The actual Triton compiler preflight is retained in `artifacts/source_correction_20260716_r1/compile_diagnostic.json`; it fails closed with `RuntimeError: 0 active drivers ([]). There should only be one.`

Sampled numerical evidence: the image CPU path ran a B1/context-33 sample with non-identity page table `[2,0,1]`. All restored values were finite and mean absolute error was `0.01779998`, but max absolute error was `0.125` and the strict `atol=0.03, rtol=0.03` pass was false. The exact frozen 15-row byte matrix remains emitted; timing rows are zero because the host/container has no CUDA driver.

Decision: `IMPLEMENTATION_CLOSE_NUMERICAL_FAIL_GPU_BOUNDARY`. The previous paging/wiring defect is corrected, but this source does not earn `SOURCE_READY_FOR_SM89`, a timing claim, or provider nomination. The numerical failure is retained as negative mechanism evidence rather than hidden behind a readiness label.

## 2026-07-16 — Director re-scope to `$0` kernel evidence

The previous run is a pre-science operational null. Do not consume a second provider lane merely to replay it. Implement a source-pinned writer/scale/decode path at `$0` and decide the frozen exact-shape matrix first. The component pass requires numerical agreement, exact bytes, no saturation/fallback, and at least 10% p50 improvement in stage 1 and full attention at every B32 long-context point without p95 regression. Only that result can nominate a later full47 c32 endpoint; it cannot compete with the combined W4 owner this cycle.

## 2026-07-16 — Cycle 102 implementation correction, not GPU replay

Audit closes the current code as GPU-unready: the matrix runner intentionally never invokes either kernel, while the decode ignores the shuffled page table, `BLOCK_N`, and splits and uses a serial context loop; writer head indexing is also incomplete. Paid r3 was another operational null (`1,208.537 s`, `$0.254774` derived) at SSH/cloud-init readiness, followed by verified zero inventory. Keep the FP8 mechanism active, but allow exactly one `$0` correction in the cached pinned PyTorch/Triton/nvcc image. Correct scale-aware saving is `7,561.125 MiB`. Another paid arm is prohibited until the real paged runner compiles and emits sampled numerical evidence.

## 2026-07-16 — MECHANISM_UNTESTED_IMPLEMENTATION_CLOSE

Final audit finds that the correction still does not execute the Triton kernels: `writer_invoked` is static metadata and the runner returns a GPU-required label. More importantly, the contracted MLA cache is `[pages,16,1,576]`, while code and the CPU sample allocate/index 20 KV heads; the byte matrix omits that factor. Decode has no split-reduction/full-attention stage, and the `0.125` raw-cache reconstruction error is not the required attention output/LSE oracle. Thus neither the claimed scale-aware capacity nor the numerical classification is valid for this implementation. Close the exhausted source lineage as `IMPLEMENTATION_CLOSE`; FP8 MLA remains scientifically untested and earns no GPU nomination.
