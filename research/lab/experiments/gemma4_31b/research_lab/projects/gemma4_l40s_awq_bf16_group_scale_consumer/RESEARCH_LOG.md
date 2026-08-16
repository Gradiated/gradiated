# Research log

## 2026-07-24 — director admission

- The fixed AWQ-to-QServe representation is closed offline: convertible output
  channels are `0/21504`, `0/21504`, and `0/5376`; even the easiest channels
  require byte multipliers `163`, `166`, and `251`, with stage-1 magnitudes
  well outside int8.
- Admitted a distinct exact consumer, not a conversion repair: keep original
  AWQ codes, zeros, and BF16 group scales; form one int32 K-group partial,
  apply the original group and activation scales, and accumulate FP32.
- Bind one fixed SM89 design and immutable packet offline while priority-6300
  owns the L40S. Paid execution is capped at 1.5 L40S hours and remains behind
  the existing claim plus a valid director lifecycle. No sweep or provider
  mutation is authorized.

## 2026-07-24 — exact consumer frozen; typed queue/lifecycle boundary

- Question: can the admitted exact consumer preserve the original AWQ
  representation in QServe packed staging and become the sole executable SM89
  candidate without calibration, requantization, or a schedule sweep?
- Action: adapted the pinned QServe SM89 path to one fixed
  `CTA[32,64,128]`, `warp[32,32,64]`, four-warp, three-stage consumer. Each
  K=128 group produces an int32 partial; the two K slices reduce serially
  through one 8 KiB scratch, multiply by the original BF16 group scale and
  FP16 token scale, and accumulate FP32 before BF16 output. Gate/up flows
  through the unchanged tanh GeluAndMul dynamic-int8 producer into down.
- Measured offline evidence: the project-local layer-0 AWQ snapshot hash is
  `871a79d70b4fe23a5b036a765a129556ff2b4a2affc86606e843dbae215e04f8`.
  All real gate, up, and down codes, zero points, and BF16 scale bits
  round-trip exactly into the candidate compute layout
  (`inputs/exact_consumer/producer/layer0_exact_compute_v1/PREPARE_TERMINAL.json`).
  A nonperiodic mutation-resistant unit fixture exposed and corrected an
  inverse QServe unpack permutation that the predecessor's periodic synthetic
  fixture had masked; the packed producer bytes themselves were unchanged.
- Immutable artifact: deterministic source/reference/runner packet
  `EXACT_CONSUMER_PACKET.tar.gz` is
  `e3bc8fe9fef4efcca329fa82eb475cef086238ba012cee3e233171b583c49061`;
  its separately content-addressed project-local data bundle is
  `a98b0ca99d8e4f2d335dffb546931f072dc17d269d3d1b46723ac9eb17254753`;
  manifest `EXACT_CONSUMER_GPU_INPUT_MANIFEST.json` is
  `d314db7affe5bca4e6ccf37da826b898a3e08533a0edfbdc8158a9f68edd0060`.
  It contains the project-local admitted AWQ bytes, exact compute arrays,
  candidate source, pinned reference source/bindings, runner, producer audit,
  and license. Rebuilding it produced the same digest.
- External boundary: priority-6300's owner ended at `08:10:16Z` without a
  repair request and released `l40s-qserve-e00a74kcbps8v00fk4` to
  `maintenance`; that project still reports `active`. The remaining
  director-owned watchdog expires at `08:30:59Z`, so the queue and lifecycle
  contract both prohibit this project from claiming. No CUDA invocation,
  pool claim, or provider spend occurred (`actual_spend_usd=0.0`).
- Next: the director must settle priority-6300, return this retained L40S to
  `available`, and install a lifecycle covering packet `e3bc8f…` plus data
  bundle `a98b0c…`. Then run
  the component, fixed register/shared/spill/tensor/traffic/barrier counters,
  and only the conditional coherence/c32 continuation under one bounded
  claim.

## 2026-07-24 — director admits the immutable packet on retained L40S

- KV4 closed at its `08:15Z` repair deadline without a scientific terminal.
  One-shot provider reconciliation verified the retained instance RUNNING and
  its 150-GiB managed disk READY.
- A replacement cleanup watchdog is active through `14:00Z`; the project
  owner must finish by `13:45Z`. The existing image, exact checkpoint, and
  compiled SM89 caches remain resident.
- The next work is fixed execution, so routing is `execution`. Claim
  `l40s-qserve-e00a74kcbps8v00fk4` once, run packet `e3bc8f…` with bundle
  `a98b0c…`, collect only the bound counters, and start new coherence/c32 only
  after a correct positive component. No calibration, requantization, tile,
  representation, or schedule sweep is authorized.

## 2026-07-24 — consumed candidate closes inconclusively

- The candidate compiled at 127 registers with zero spills and began the first
  M=1 CUDA chain, but no candidate row persisted. The FP8 control never began:
  `sgl_kernel.fp8_scaled_mm` rejected its non-column-major `mat_b`.
- The owner then failed while packing an archive inside its own source
  directory and released the claim. A later retrieval recovered the compile
  and invocation evidence, but not a candidate output. A control-only repair
  therefore cannot produce a valid comparison without replaying the consumed
  candidate.
- Close this project without a performance inference after
  `$0.024948443867448687`. No compatible L40S successor remains. Director
  cleanup verified zero compute processes, zero MiB, and zero utilization,
  deleted and verified absent instance `computeinstance-e00a74kcbps8v00fk4`
  and disk `computedisk-e00svftc564m2pcp68`, stopped the cleanup watchdogs,
  and retired the pool record.

## 2026-07-24 — consumed candidate; control API and controller boundary

- Action (measured): atomically claimed the admitted L40S, verified and
  staged immutable packet `e3bc8f…` and data `a98b0c…`, and invoked the
  fixed container worker. The packet compiled for SM89: `dense_kernel0` used
  127 registers with zero spill loads/stores.
- Evidence (measured): remote `component/INVOCATION_STATE.json` records
  `candidate_cuda_started=true` and `candidate_science_started=true` with no
  completed row. The first M=1 candidate chain therefore executed. Its FP8
  control then failed before `control_science_started` with
  `RuntimeError: mat_b must be a column major tensor` from
  `sgl_kernel.fp8_scaled_mm`. The retained raw worker output, compile terminal,
  invocation state, and post-fault retrieval are under
  `artifacts/exact-awq-consumer-20260724t0829z/`.
- Interpretation: this is an ordinary control-consumer API defect, but the
  outer controller mishandled its retrieval-pack error and released the claim
  to maintenance. Since candidate CUDA bytes partially executed, replay is
  forbidden; since the uninterrupted claim no longer exists, its same-session
  repair exception cannot be applied. No counters, coherence prompts, or c32
  endpoint ran. Conservatively derived provider exposure is
  `$0.024948443867448687`.
- Next: typed director disposition; do not replay the fixed candidate.
