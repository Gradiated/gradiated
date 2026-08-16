# Research log

## 2026-07-24 — exact operation binding and offline harness

Question: can the dominant production local-attention and FP8 gate/up regions overlap across independent work from the c32 service batch?

Action: mechanically joined the authoritative Nsight trace, behavioral FP8 consumer audit, and pinned v0.5.13 sources. Materialized the admitted trace/source bytes and only the layer-0 gate/up tensor payloads under this project, then implemented the exact-consumer serial/two-stream harness and its immutable-input mutation test.

Evidence:

- Measured trace: the dominant local-attention geometry is `extend_attention_fwd._fwd_kernel`, grid `(1,32,32)`, block `(256,1,1)`, 255 registers/thread, 81,920 B dynamic shared memory, 1,400 launches and 1.479625184 s. Grid-z 32 with block-M 64 binds 2,048 query rows.
- Measured/derived join: all 1,400 selected attention launches join to the next production gate/up launch; median attention-end-to-gate/up-start is 201.344 us and maximum is 215.808 us. Pinned layer order binds the paired gate/up shape to `(M,K,N)=(2048,5376,43008)`.
- Measured trace/audit: the gate/up family uses the production `fp8_scaled_mm` consumer, grid `(132,1,1)`, block `(384,1,1)`, cluster `(2,1,1)`, 168 registers/thread, 214,016 B dynamic shared memory, 3,600 launches and 2.192004724 s.
- Content-addressed: `BINDING.json`, the pinned runtime sources, the 32 MiB trace, and a read-only 462,422,360-byte gate/up snapshot are project-local. Tensor payload bytes were copied without conversion.
- Offline measured: the builder, content verifier, mutation rejection, unit tests, and Python compilation pass. No CUDA or scientific invocation ran and spend remains `$0`.

Interpretation: the physical competition is now concrete. Attention is a high-register/high-shared-memory Triton region while gate/up is a full-SM persistent FP8 tensor-core region; useful concurrency remains uncertain and the exact H200 call is the cheapest discriminator.

Source-backed H200 prior: each attention CTA requests `255*256=65,280` registers and each FP8 CTA requests `168*384=64,512`, against 65,536 32-bit registers per SM; FP8 also requests 214,016 B of the roughly 228 KiB per-block shared-memory ceiling. Same-SM co-residency is therefore physically unavailable. Any gain must come from spatial CTA partitioning across 132 SMs and complementary pipe/memory pressure, not two resident CTAs sharing one SM. The concurrent tensor-pipe/DRAM/L2 and stall counters will falsify or support that narrower mechanism.

Next: keep the named queue boundary. After `gemma4_h200_ngram_production_validation` releases `h200-sync-linear-e00vhh6h29fj68x91g`, claim it atomically, transfer the immutable project-local snapshot once, and run the preregistered profiler-off component. Do not re-resolve another project's checkpoint or source path after claim.

## 2026-07-24 — exact H200 profiler-off component terminal

Question: does the exact local-extend attention and FP8 gate/up pair overlap enough on H200 to justify an integrated scheduling slice?

Action: after the named predecessor released the bench, atomically claimed `h200-sync-linear-e00vhh6h29fj68x91g`, transferred the project-local snapshot once (`ca99a41726abbf3b9f387989d6867919d7791907b29dae7e6ec6bd13f9723ff6`), and ran `EXPERIMENT_SPEC.json` profiler-off in the pinned SGLang v0.5.13 image. The owner heartbeated the claim and released the empty bench ready.

Measured evidence: exact H200, SM90, 132 SMs; attention median `1.104640 ms`, FP8 linear median `0.641760 ms`, component median sum `1.746400 ms`, serial-pair median `1.718176 ms`, and concurrent median `1.725440 ms`. Concurrent/component ratio is `0.987998`; concurrent/serial ratio is `1.004228`; overlap efficiency is `0.032660`. Both outputs are bitwise equal, finite, and fully consumed. Provider exposure was `0.100181 USD`.

Interpretation: the candidate reached the real consumers and the quality gate passed, but separate streams do not reduce the critical path; the pair is consistent with destructive interference or scheduler/resource time-slicing. The preregistered `>=0.90` close gate fires, so no integrated endpoint slice or counters are admitted. A materially different resource pair would need new admission.

Terminal: [`FINAL_TERMINAL.json`](artifacts/gpu-profiler-off-20260724t2341z/FINAL_TERMINAL.json). Raw worker captures and invocation markers are in the same artifact root.
