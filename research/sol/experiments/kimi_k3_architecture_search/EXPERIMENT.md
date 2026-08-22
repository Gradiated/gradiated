# Experiment contract

## Decision

Select a Kimi K3 microarchitecture v0 that minimizes modeled dollars per output
token subject to a decent-speed floor, and identify the next measurement that
can most cheaply falsify its advantage over current NVIDIA hardware.

## Hypothesis

At decode concurrency relevant to the observed OpenRouter workload, useful K3
throughput is constrained by sparse-expert weight movement, recurrent-state
traffic, skinny-matrix utilization, launch/control overhead, and collectives.
A tiled, statically scheduled hierarchy with local SRAM, modest dual-mode
matrix datapaths, fused KDA state engines, and explicit HBM DMA can reduce
logic, power, and interconnect cost while retaining enough useful bandwidth to
beat the dollar/token of a general-purpose B300 deployment. Hierarchical BSP
is expected to retain Graphcore's local-state and deterministic-placement
advantages without imposing a pod-wide barrier around every HBM transfer.

## Control and exact scope

- Model: `moonshotai/Kimi-K3`, Hugging Face revision
  `9f62e4e9fffbd0a83ddd60e1c209d828994b3569`.
- Software semantics: released `modeling_kimi_linear.py`; no model or quality
  change.
- NVIDIA latency calibration: vLLM's public 8K-input/1K-output, batch-one,
  TP8, non-speculative result of 111 output tokens/s on GB300/B300-class GPUs.
- Canonical request: 76,435 cached input, 5,873 uncached input, 985 output
  tokens; text-only; FP8 MLA cache; no speculation.
- Decode frontiers: concurrency 1, 32, 128, and 512 at an 82,308-token starting
  context.
- Decent-speed floor: c1 TPOT <=15 ms; c128 TPOT <=85 ms and throughput >=1,500
  output tok/s. This is an explicit design choice, not a workload measurement.
- Economic objective point: c128. Current NVIDIA market control is eight B300s
  at $7.39/GPU-hour; candidate ownership uses a four-year, 65%-productive,
  5%-maintenance, $0.10/kWh, PUE 1.2 scenario.
- Evidence: analytical and synthetic except for source identities, vendor
  specifications, public vLLM endpoint measurements, and measured OpenRouter
  traffic geometry.

## Gates and falsifiers

- Parameter arithmetic must reconcile to within 2% of the released 2.8T count,
  and routed-expert arithmetic to within 0.5% of the released U8 inventory.
- The B300 calibration point must reproduce 111 tokens/s by construction and
  the uncalibrated resource diagnosis must remain explicit.
- A candidate advances only if it fits model plus canonical cache/state in HBM,
  meets the decent-speed floor, and minimizes the explicit design-to-cost
  dollars/token scenario among admissible candidates. The raw physical B300
  comparison must remain visible even when a candidate is slower.
- A candidate is killed if its advantage requires unmeasured expert skew,
  altered weights, unavailable HBM, impossible SRAM bandwidth/capacity, or a
  fabric assumption beyond its stated physical envelope.
- A synthetic pass admits only an FPGA/RTL slice, package/BOM sourcing, and
  target-GPU calibration experiment, never a product or tapeout claim. The
  dollar result is a design-to-cost target and cloud break-even, not a sourced
  ASIC BOM or an owned-NVIDIA TCO claim.

## Budget, timeout, artifacts, cleanup

- External spend: $0.
- Local wall time: four hours; each command at most ten minutes.
- Seed: 20260816.
- Artifacts: `evidence/tensor_inventory.json`, `results/search_results.json`,
  and the dated decision brief in `research/sol/docs/`.
- No provider resource or persistent external mutation. Temporary HTTP payloads
  remain in memory. The tensor payload is never downloaded.
