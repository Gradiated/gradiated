# Kimi K3 custom-chip simulation stack

- Date: 2026-08-26
- Status: recommended starting architecture
- Decision: use a layered stack. Keep the existing Foundry ledger as the
  system-level authority. Add SystemVerilog and OpenROAD for selected hardware
  blocks. Use measured B300 runs as the GPU control. Use detailed simulators
  only after a candidate survives the fast tiers.

## Decision question

What environment can support a Kimi K3-specific accelerator, explain its
tradeoffs, compare it fairly with NVIDIA B300, and later support a path to
fabrication?

## Scope and non-scope

The first target is a KDA accelerator slice and its memory system. It is not a
claim that one small chip can contain the full Kimi K3 model. The full model is
2.8T parameters, and Kimi recommends deployments with 64 or more accelerators.
One B300 has 288 GB of HBM3e, so a full K3 deployment is a multi-accelerator
system problem even before runtime state, replication, and communication are
included.

The Kimi article's chip is a proof of concept for a nano model. It reports
4 mm², 0.277 MB SRAM, an INT4 MAC array, 100 MHz timing closure, and over 8,700
decode tokens/s in simulation. Those results do not describe a complete
2.8T-parameter K3 chip.

## Recommended stack

```text
Exact K3/KDA reference model
        |
        v
Foundry action ledger and fast analytical search
        |
        +--> Timeloop + Accelergy: mapping, SRAM, area, energy
        +--> SCALE-Sim: matrix-array and dataflow checks
        +--> ASTRA-Sim/Chakra: multi-chip communication checks
        |
        v
SystemVerilog block RTL + Verilator tests/formal checks
        |
        v
Yosys + OpenROAD + OpenRCX + KLayout/Magic + Netgen
        |
        v
Post-route timing, area, DRC/LVS, and power estimates
        |
        v
Real B300 kernels and serving measurements with Nsight
```

### 1. Exact model reference

Implement KDA, Gated MLA where needed, routing, quantization, and state updates
first in a clear Python or PyTorch reference. Keep this implementation slow
and easy to inspect. Every RTL block must match it on randomized tests and
golden vectors.

Use the released K3 checkpoint and exact tensor shapes for any full-model
claim. Use a smaller KDA nano model only as a fast hardware-development target.
Label the nano result as a proxy.

### 2. Fast system search

Use the existing Foundry action ledger for the full request and model view. It
should account for tensor work, weight traffic, KDA state, KV traffic, expert
routing, communication, queueing, power, and cost.

Use Timeloop/Accelergy and SCALE-Sim for shortlisted matrix-engine mappings.
Use ASTRA-Sim/Chakra for expert-parallel and scale-up traffic. These tools
validate parts of the design. They are not complete K3 or B300 oracles.

The agent should search parameters such as:

- MAC-array dimensions and pipeline depth;
- SRAM capacity, banking, and port count;
- weight and activation precision;
- tile shape and dataflow;
- DMA width and double-buffer depth;
- expert placement and routing policy;
- HBM channels and on-chip network topology;
- chip count and memory capacity.

Keep the model semantics, quality tests, and measurement contract fixed while
the agent changes these parameters.

### 3. RTL and virtual chip implementation

Write the performance-critical units in SystemVerilog. Use Verilator for fast
cycle and functional tests. Use Yosys for synthesis. Use OpenROAD for
floorplanning, placement, clock-tree synthesis, routing, and final layout.
Use OpenRCX for post-route resistance and capacitance extraction. Use KLayout
or Magic for physical checks and Netgen for LVS where the selected PDK supports
the flow.

Start with Nangate45 for cheap flow development. Move selected blocks to SKY130
or GF180 for a real-node open-PDK exercise. Do not shrink Nangate45 or SKY130
numerically to claim a 5 nm or 3 nm design. A lower-node process needs its own
foundry PDK, libraries, design rules, extraction decks, SRAM macros, and signoff
tools.

ASAP7 is useful for predictive 7 nm research, but its official documentation
says that designs made with it are not manufacturable. A real fabrication path
requires a foundry engagement and its proprietary PDK, usually with commercial
tools such as Cadence Innovus or Synopsys Fusion Compiler.

### 4. B300 control

Use a real B300 as the primary GPU control whenever possible. Run the same
KDA/MLA kernels, tensor shapes, precision, context lengths, batch sizes, and
request schedule. Collect wall time, tokens/s, memory traffic, power, clocks,
and temperature. Use Nsight Compute for kernel metrics and Nsight Systems for
end-to-end overlap and host effects.

Accel-Sim is useful for a GPU-like counterfactual, but it is not an exact B300
oracle today. Its current public validation reports 99% Pearson correlation
and 13.4% mean absolute cycle error against H100 silicon. Its public roadmap
lists Blackwell B200 and RTX 5090 support as experimental and incoming. Do not
label an Accel-Sim B300 result as measured B300 performance.

## Apples-to-apples comparison contract

Compare one of these two scopes. Do not mix them:

| Scope | Custom design | GPU control |
|---|---|---|
| Nano-model block | One custom accelerator plus its memory | One B300 running the same nano model and precision |
| Full K3 service | A specified multi-chip custom system with external memory | A specified multi-B300 system with the same model and service target |

Lock these inputs:

- checkpoint and tokenizer revision;
- model quality and numerical tolerance;
- precision, including scale metadata and accumulator precision;
- prefill and decode separately;
- context length distribution;
- batch or concurrency;
- input and output token counts;
- sampling and stopping rules;
- memory capacity and bandwidth;
- host, interconnect, and software boundary;
- power boundary and measurement method.

Report at least:

- p50, p95, and p99 latency;
- time to first token and time per output token;
- sustained output tokens/s;
- joules per output token;
- peak and resident memory;
- area, frequency, and utilization for the custom design;
- B300 utilization and achieved bandwidth;
- total system power;
- cost per million input and output tokens;
- uncertainty and calibration status.

Do not compare a single custom chip with one B300 if the custom chip uses
external devices or a different model-residency assumption.

## Agent iteration loop

Each candidate should produce an immutable record:

```text
candidate spec
  -> exact correctness tests
  -> fast ledger bound
  -> detailed mapping or network simulation
  -> RTL simulation and formal checks
  -> synthesis and post-route implementation
  -> timing, area, power, and DRC/LVS reports
  -> matched B300 comparison
  -> Pareto update and causal explanation
```

The agent may change RTL, mapping, buffering, precision, and topology inside
the declared design space. It must not change the quality gate, workload, PDK,
measurement boundary, or baseline after seeing results. If it changes the
experiment contract, start a new lineage.

Use a Pareto frontier instead of one score. A candidate that wins tokens/s but
loses energy/token, memory capacity, or cost may be a worse product.

## Evidence package for hardware and investment review

Every headline result should include:

1. A one-page architecture diagram.
2. Exact model, workload, and software identities.
3. A baseline and a candidate result under the same contract.
4. A waterfall showing gains from model, dataflow, memory, fabric, and serving.
5. RTL, synthesis, routing, extraction, and verification artifacts.
6. A B300 profiler report and raw timing measurements.
7. A sensitivity analysis for bandwidth, utilization, yield, power, and cost.
8. A clear label: measured, analytical, vendor-reported, derived, inferred, or
   synthetic.

Use the following claim levels:

| Claim | Required evidence |
|---|---|
| “The design is functionally correct” | Reference-model agreement and RTL/gate tests |
| “The design is routable” | Post-route layout and DRC/LVS under a named PDK |
| “The design is faster than B300” | Matched B300 measurement or a calibrated, held-out model |
| “The design uses less energy” | Same-boundary power measurement or calibrated power model |
| “The design is ready for fabrication” | Foundry PDK, signoff decks, SRAM/IP review, package/power review, and foundry acceptance |

## First implementation sequence

1. Freeze the nano-model versus full-K3 scope. Start with the nano-model KDA
   block for RTL progress.
2. Reproduce the exact KDA recurrence in a reference model and RTL testbench.
3. Measure the same kernels on a real B300.
4. Implement one 16x16 or 32x32 INT4/BF16 MAC tile, SRAM interface, and KDA
   state-update block in SystemVerilog.
5. Run the block through Nangate45 and SKY130. Compare post-route timing,
   area, and extracted wire costs within each PDK.
6. Calibrate the fast ledger against the RTL and B300 measurements.
7. Add SRAM streaming, buffering, routing, and expert traffic only when a
   measured bottleneck justifies each block.
8. Escalate the winning block to a foundry-specific PDK before making a
   fabrication claim.

## Sources

| Source | Evidence type | Retrieved |
|---|---|---|
| https://www.kimi.com/en/blog/kimi-k3 | Official K3 architecture and nano-chip claims | 2026-08-26 |
| https://www.luoluo.ai/blog/kimi-k3 | Article experiment, harness, and Nangate45 caveats | 2026-08-26 |
| https://docs.nvidia.com/enterprise-reference-architectures/hgx-ai-factory/latest/components.html | Official B300 memory, bandwidth, and system specifications | 2026-08-26 |
| https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts/blob/master/docs/index.md | OpenROAD platforms and RTL-to-GDS flow | 2026-08-26 |
| https://openroad.readthedocs.io/en/latest/main/src/rcx/README.html | OpenRCX post-route extraction method | 2026-08-26 |
| https://asap.asu.edu/ | ASAP7 predictive-PDK limitations | 2026-08-26 |
| https://accel-sim.github.io/ | Accel-Sim validation and current architecture coverage | 2026-08-26 |
| https://docs.nvidia.com/nsight-compute/ProfilingGuide/index.html | NVIDIA kernel metrics and achieved-throughput measurement | 2026-08-26 |
| https://www.cadence.com/en_US/home/resources/datasheets/innovus-implementation-system-ds.html | Commercial implementation and signoff integration | 2026-08-26 |
| https://www.synopsys.com/implementation-and-signoff/physical-implementation/fusion-compiler.html | Commercial RTL-to-GDSII and signoff integration | 2026-08-26 |

## Existing repository state

The existing [simulator landscape](../../research/lab/docs/SIMULATOR_LANDSCAPE.md),
[Kimi K3 microarchitecture](../../research/lab/docs/KIMI_K3_MICROARCHITECTURE_2026-08-16.md),
and [architecture-search handoff](../../research/sol/experiments/kimi_k3_architecture_search/HANDOFF.md)
already provide a Foundry ledger, a K3-specific system model, B300 controls,
and a candidate StreamTile-E12 architecture. Treat their current results as
analytical or measured only within the scopes declared in those documents.
