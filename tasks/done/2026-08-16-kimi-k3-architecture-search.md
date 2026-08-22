# Task: 2026-08-16-kimi-k3-architecture-search

## Outcome

An exact-revision Kimi K3 text-serving workload is lowered into an auditable
per-token operation/byte/state/communication ledger, a deterministic
architecture-search simulator produces a physically constrained v0 accelerator
organization, and the result is compared with the strongest public NVIDIA
Kimi K3 control without upgrading analytical estimates into measured claims.

## Owner and coordination

- GitHub issue: unavailable; repository lookup returns repository-not-found
- GitHub project: unavailable to the configured token
- owner: root
- Codex thread:
- created: 2026-08-16T12:06:15+00:00
- started: 2026-08-16T12:06:15+00:00
- last updated: 2026-08-16T12:06:15+00:00
- scope: research/sol/experiments/kimi_k3_architecture_search, research/sol/docs/KIMI_K3_MICROARCHITECTURE_2026-08-16.md, tasks/active/2026-08-16-kimi-k3-architecture-search.md
- excluded paths: every pre-existing modified/untracked path and all active
  Gemma/GLM experiment directories
- dependencies: public Moonshot Kimi K3 revision
  `9f62e4e9fffbd0a83ddd60e1c209d828994b3569`; public vLLM and NVIDIA controls

## Contract

- hypothesis or user value: Kimi K3 decode at production concurrency is limited
  by movement and scheduling of sparse expert weights/state more than peak dense
  FLOPS; a Graphcore-inspired hierarchy of small compute-plus-local-SRAM tiles,
  static placement, explicit DMA, and local BSP groups can minimize dollars per
  output token while accepting lower peak speed than a B300-oriented design.
- acceptance checks: exact model identity and tensor geometry; per-operation
  FLOPs, compulsory reads/writes, arithmetic intensity, dependencies,
  parallelism, state, and SRAM breakpoints; deterministic B300 control and at
  least three candidate organizations; sensitivity/negative controls; one
  selected v0 with explicit physical and calibration blockers.
- quality gate: arithmetic invariants reconcile with released parameter counts
  and tensor headers; no numerical/model-quality change is permitted; every
  NVIDIA comparison is labeled vendor-reported, derived, or synthetic and uses
  a matched workload denominator.
- SLO or budget: canonical text-only agentic workload uses the measured
  OpenRouter average request geometry (76,435 cached input + 5,873 uncached
  input + 985 output tokens), with decode frontiers at concurrency 1/32/128/512;
  require c1 TPOT <=15 ms and c128 TPOT <=85 ms plus >=1,500 output tok/s; among
  passing designs minimize c128 dollars/output token; $0 external spend.
- timeout: four wall-clock hours for this first analytical/simulation rung;
  individual local commands <=10 minutes.
- artifact locations: `research/sol/experiments/kimi_k3_architecture_search/`
  and `research/sol/docs/KIMI_K3_MICROARCHITECTURE_2026-08-16.md`
- resume command: `python3 research/sol/experiments/kimi_k3_architecture_search/run_search.py --spec research/sol/experiments/kimi_k3_architecture_search/spec.json`
- rollback or cleanup: no provider resources; remove only the owned directory,
  report, packet, and lock. Cargo-generated build products were cleaned to
  recover 3.2 GiB after the shared filesystem reached capacity.

## Plan

1. Pin primary sources and reconstruct exact K3 workload geometry.
2. Implement and validate the analytical/event-resource simulator.
3. Search physically constrained organizations against B300 performance,
   energy, and current cloud-price controls.
4. Record the v0 architecture, uncertainty, and next FPGA/target-GPU gates.

## Result

- status: implementation and local verification complete; package/BOM sourcing
  and target-hardware measurement remain external gates
- verification: 13 architecture-search unit tests pass; exact 96-shard header
  inventory has zero size mismatches; opportunity register validates; DevEx
  checks pass; `cargo fmt --check` passes; workspace clippy is blocked by
  pre-existing dead code in `crates/foundry-core/src/qwen_int4_kernel.rs:1171`
- changed paths: `research/sol/experiments/kimi_k3_architecture_search/`,
  `research/sol/docs/KIMI_K3_MICROARCHITECTURE_2026-08-16.md`, and this packet
- limitations or blocked paths: all candidate performance/power/area/capex is
  synthetic; no owned B300 TCO, package quotes, PPA, route trace, RTL, or matched
  82K B300 measurement; GitHub issue/project unavailable to configured token
- commit: `a89dbcf5` (research artifacts; this packet was then released to done)
- next action: source the 2.304 TB / 36 TB/s memory-package envelope, then run
  a matched B300 trace and hierarchical-BSP routed-trace simulation.
- released: 2026-08-16T12:35:01+00:00
