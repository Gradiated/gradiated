# Model-Specific Inference Chip Microarchitecture

Status: working draft

This document starts as a plan for a model-specific inference accelerator. It
will become the clear, simple description of the microarchitecture after we
run enough experiments to support the conclusions. Values marked `TBD` are not
design decisions.

The first target is efficient inference for sparse Mixture-of-Experts models.
The design may include specialised KDA or attention units where the workload
benefits from them.

We will not choose an architecture because it sounds plausible. We will model
options in software, test selected options in RTL, and measure the most useful
options on the KV260. The final document must explain what we built, why we
built it, what it improves, and where it does not help.

## 1. What we are designing

The design target is a silicon accelerator, not a complete server or rack.

```text
Model workload
    ↓
Chip microarchitecture
    ↓
SystemVerilog RTL and memory/IP choices
    ↓
ASIC or FPGA implementation
    ↓
Package, board, server, and rack
```

This document focuses on the second layer. It records the requirements that
the later RTL and physical design must satisfy.

The design must answer four questions:

1. Which model operations are worth specialising?
2. Where is each tensor stored while it is used?
3. How many operations and bytes can the chip process per cycle?
4. What is the cost in area, power, latency, and flexibility?

## 2. Evidence rules

Every important value must have one evidence label:

- `measured`: observed on a real FPGA, GPU, or other test system.
- `simulated`: produced by an RTL or cycle-accurate simulator.
- `analytical`: calculated from an explicit model.
- `vendor-reported`: supplied by a hardware vendor.
- `derived`: calculated from another labelled value.
- `inferred`: a reasoned estimate that still needs validation.

Do not present an analytical estimate as a chip measurement. Do not transfer a
result from one model, batch size, precision, or device to another without
marking the transfer as an assumption.

## 3. Working process

We will develop the design in this order:

1. Specify a representative model workload.
2. Count operations, tensor bytes, and communication bytes.
3. Define a simple performance and power model.
4. Sweep architectural choices in Python.
5. Select a small set of candidates.
6. Implement the candidates in SystemVerilog RTL.
7. Verify RTL against a software reference model.
8. Synthesize RTL and check area, memory, DSP use, and timing.
9. Run selected candidates on the KV260 FPGA.
10. Compare measured results with the analytical model.
11. Refine the microarchitecture and repeat.
12. Move to ASIC synthesis only after the workload and interfaces are stable.

Each iteration must produce:

- The workload and assumptions.
- The candidate parameters.
- The expected result before the run.
- The measured or simulated result.
- The difference from the prediction.
- The next question that the result answers.

The document has two jobs during this process:

1. Keep the current assumptions and experiments easy to understand.
2. Preserve the evidence needed to explain the final design.

As evidence improves, replace provisional text with short factual statements.
Keep important rejected options and their reasons, but do not leave old
speculation mixed with the current architecture.

## 4. Workload contract

The first workload contract is incomplete. We will fill it from real model
traces and published model information.

| Parameter | Initial value | Evidence | Notes |
|---|---:|---|---|
| Model family | Kimi K3 text model | vendor-reported | Use the released model at revision `a590ce0`. |
| Decode or prefill | Decode first | inferred | Decode exposes token latency and state movement. |
| Number of experts | 896 routed and 2 shared | vendor-reported | There are 92 sparse MoE layers. |
| Experts selected per token | 16 routed | vendor-reported | Routing overlap still needs a real trace. |
| Hidden dimension | 7,168 | vendor-reported | This is the text hidden size. |
| Latent MoE dimension | 3,584 | vendor-reported | Shared projections surround the routed experts. |
| Expert intermediate dimension | 3,072 | vendor-reported | Each routed expert has three matrices. |
| Batch size | 1 and 16 | analytical | Batch changes weight reuse and tile utilisation. |
| Sequence length | 8K, 128K, and 1M | analytical | These cases expose MLA cache growth. |
| Activation precision | MXFP8 target | vendor-reported | Exact intermediate formats still need measurement. |
| Weight precision | MXFP4 with exclusions | vendor-reported | The released config excludes several blocks from compression. |
| Target latency | TBD | TBD | Use per-token latency for decode. |
| Target throughput | TBD | TBD | Use tokens per second for the chosen batch. |
| Target power | TBD | TBD | Include chip power and state the boundary. |

### 4.1 Required operation counts

For each workload, calculate:

- Router operations per token.
- Expert dispatch and combine operations.
- Expert matrix multiplications.
- Activation and gating operations.
- Attention or KDA operations.
- KV-cache or recurrent-state reads and writes.
- Weight bytes read.
- Activation bytes read and written.
- Inter-expert communication bytes.
- Host and device transfer bytes.

The model must report both total work and the work on the critical path.

### 4.2 First analytical workload result

The first model converts the released Kimi K3 matrix shapes into operation,
weight, recurrent-state, and MLA-cache counts.

For batch 1 at an 8,192-token context, it estimates:

- `analytical`: about 111 billion MACs per generated token.
- `analytical`: about 130 GB of active weight reads per token under the
  stream-active-weights assumption.
- `analytical`: about 30.6 billion MACs in KDA projections and gates.
- `analytical`: about 0.5 billion MACs in the KDA recurrence itself.
- `analytical`: about 48.6 billion MACs in routed experts.
- `analytical`: about 12.2 billion MACs in shared experts.

These values are operation and byte counts. They are not measured latency.
They suggest that projection and expert matrix operations need more attention
than the recurrence alone. A real trace must test whether their memory traffic
is on the critical path.

Reference artifacts:

- [Workload model report](../research/sol/experiments/kimi_k3_microarchitecture/results/report.html)
- [Machine-readable workload](../research/sol/experiments/kimi_k3_microarchitecture/workload.json)
- [Analytical result](../research/sol/experiments/kimi_k3_microarchitecture/results/workload_analysis.json)

## 5. System boundary

The chip must be evaluated inside a defined system boundary.

### 5.1 Inside the chip

The candidate chip may contain:

- Token ingress and egress interfaces.
- A router and dispatch engine.
- Expert compute engines.
- KDA or attention engines.
- Local SRAM and scratchpad banks.
- Weight movement and decompression engines.
- An on-chip network.
- DMA and external-memory controllers.
- Synchronisation, counters, and error reporting.

### 5.2 Outside the chip

The first design does not include:

- The accelerator carrier board.
- The server CPU.
- External memory modules.
- Power supplies.
- Fans and chassis.
- Rack networking.

Those systems still impose requirements on the chip. We must record their
memory bandwidth, power, cooling, package, and interface limits early.

## 6. Candidate microarchitecture

The initial architecture has four major paths:

```text
                 ┌──────────────┐
Input tokens ───▶│ Router       │
                 └──────┬───────┘
                        │ token/expert assignments
                        ▼
                 ┌──────────────┐
                 │ Dispatch     │◀── expert state and capacity control
                 └──────┬───────┘
                        │ local token groups
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
     ┌─────────┐   ┌─────────┐   ┌─────────┐
     │ Expert  │   │ Expert  │   │ KDA/     │
     │ engine  │   │ engine  │   │ attention│
     └────┬────┘   └────┬────┘   └────┬────┘
          └─────────────┼─────────────┘
                        ▼
                 ┌──────────────┐
                 │ Combine      │
                 └──────┬───────┘
                        ▼
                   Output tokens
```

This is a starting structure. We will remove or split blocks when the
workload model shows that they are not on the critical path.

### 6.1 Expert engine

The expert engine must specify:

- Matrix-engine shape: `TBD`.
- Number of engines: `TBD`.
- Accumulator width: `TBD`.
- Weight format: `TBD`.
- Activation format: `TBD`.
- Tile sizes: `TBD`.
- Local weight capacity: `TBD`.
- Local activation capacity: `TBD`.
- Reuse policy for weights and tokens: `TBD`.
- Support for expert imbalance: `TBD`.

The key choice is whether experts remain near their compute engines or move
through a shared compute array. This choice affects SRAM, interconnect,
weight bandwidth, area, and utilisation.

### 6.2 Router and dispatch

The router must specify:

- Top-`k` selection method.
- Routing precision.
- Capacity factor and overflow policy.
- Token ordering.
- Expert queue depth.
- Arbitration policy.
- Backpressure behaviour.
- Duplicate-token handling.
- Communication path and bandwidth.

The router is part of the performance design. A fast matrix engine does not
improve throughput if tokens wait in dispatch queues.

### 6.3 KDA or attention engine

The current FPGA prototype implements one state-local KDA recurrence head.
It uses banked on-chip state and fixed-point arithmetic.

Current evidence:

- `measured`: KV260 execution has zero mismatches against the software oracle.
- `measured`: the 8-lane design completes one D=128 head in 14,336 core cycles.
- `measured`: the 8-lane design closes timing at 100 MHz on the KV260.
- `inferred`: the current design is a block-level prototype, not a full model
  implementation.

Reference artifacts:

- [KDA FPGA README](../research/sol/experiments/kimi_k3_kda_fpga/fpga/README.md)
- [Dataflow comparison](../research/sol/experiments/kimi_k3_kda_fpga/fpga/results/dataflow_comparison.html)
- [Measured KV260 result](../research/sol/experiments/kimi_k3_kda_fpga/fpga/results/kv260/d128_l8/board_run.json)

The next KDA questions are:

- Does KDA remain a major share of end-to-end time after projections and
  routing are included?
- Is state-local SRAM worth the area compared with streamed state?
- Does a two-dimensional tiled data path improve utilisation?
- Which precision preserves model quality?
- How many independent heads or tokens are needed to use a tiled engine?

## 7. Memory hierarchy

For each tensor, record its owner, location, access pattern, and movement.

| Tensor or state | Producer | Consumer | Preferred location | Access pattern |
|---|---|---|---|---|
| Router scores | Router | Dispatch | Local SRAM | Streaming |
| Token activations | Input/dispatch | Expert engine | Local SRAM | Grouped and reused |
| Expert weights | External memory or loader | Expert engine | SRAM/cache | Tiled reuse |
| KDA state | KDA engine | KDA engine | Banked SRAM | Persistent read-modify-write |
| KV cache | Attention engine | Attention engine | SRAM/DRAM | Sequence-dependent |
| Combined output | Expert engines | Output path | Local SRAM | Scatter/gather |

The design must report:

- Capacity in bytes.
- Read and write bandwidth.
- Number of banks.
- Bank width.
- Arbitration policy.
- Whether accesses are deterministic.
- Whether traffic is on the critical path.

## 8. Performance model

For each candidate, estimate:

```text
compute time = operations / effective operations per second
memory time = bytes / effective bandwidth
communication time = messages and bytes / network capacity
latency = critical-path time + queueing and setup time
```

For overlapping stages:

```text
stage time = max(compute time, memory time, communication time)
```

Do not add times that overlap. Do not use peak throughput as effective
throughput without an utilisation assumption.

The model must produce:

- Latency per token.
- Throughput at each batch size.
- Compute utilisation.
- Memory utilisation.
- Interconnect utilisation.
- On-chip state traffic.
- External memory traffic.
- Estimated energy per token.
- Sensitivity to routing imbalance.

## 9. Baselines and comparisons

The primary baseline is a general GPU-style architecture. The comparison must
use the same:

- Model and weights.
- Precision.
- Batch and sequence lengths.
- Quality target.
- Included and excluded operations.
- Host-to-device boundary.
- Latency or throughput metric.

The first structural controls are:

1. Generic vector or SIMT-style execution with separate kernels and explicit
   state traffic.
2. Tiled matrix execution with 16x16-style tiles.
3. Specialised persistent-state KDA execution.

The KV260 can compare dataflow and correctness. It cannot measure the
performance of a B300 or Vera Rubin GPU. GPU claims require an actual GPU
implementation or a clearly labelled vendor-reported or analytical result.

## 10. FPGA validation plan

The KV260 is the first hardware validation platform.

### Gate A: software model

- The recurrence and tensor operations have a reference implementation.
- Inputs and outputs have deterministic seeds.
- Quantisation and saturation rules are explicit.

### Gate B: RTL simulation

- RTL output matches the reference model.
- Reset and state-clear behaviour is tested.
- Boundary values and saturation are tested.
- Multiple recurrent tokens are tested.

### Gate C: synthesis

- Resource use is reported.
- The target clock is constrained.
- Timing closure is checked.
- Memory inference is checked.

### Gate D: board execution

- The bitstream loads successfully.
- Hardware output has zero reference mismatches.
- Core cycle count is measured.
- Host transfer time is measured separately.
- Board power is measured or clearly labelled as estimated.

The first FPGA candidates should share the same host interface and software
oracle. This makes the comparison easier to trust.

## 11. ASIC readiness path

FPGA success does not prove ASIC readiness. Before an ASIC decision, the design
must pass:

- RTL simulation and formal checks.
- Lint and clock-domain checks.
- Synthesis with the target standard-cell library.
- SRAM and memory-macro integration.
- Static timing analysis.
- Power analysis with realistic activity.
- Physical placement and routing.
- Signal-integrity and IR-drop analysis.
- Design-for-test insertion.
- Equivalence checking between RTL and gates.
- Manufacturing and package review.

A real PDK is required for process-specific area, timing, power, and layout
claims. FPGA resource counts are not ASIC area estimates.

## 12. Open questions

We will answer these in order of expected impact:

1. Which exact MoE workload and model define the first target?
2. What fraction of decode time is routing, expert compute, attention/KDA,
   memory movement, and communication?
3. Is the design limited by compute, memory, or token movement?
4. Which tensors must remain on-chip to meet the latency target?
5. What batch size makes tiled execution useful?
6. How much expert imbalance must the scheduler absorb?
7. Which precision gives the best performance without unacceptable quality
   loss?
8. What chip power, package, and external-memory limits are acceptable?
9. Which candidate is worth implementing in RTL next?

## 13. Current next actions

1. Calibrate the workload model with a real Kimi K3 routing and memory trace.
2. Add expert-parallel communication and scheduling imbalance to the model.
3. Implement the generic SIMT-style control/dataflow behind the existing FPGA
   test interface.
4. Verify it against the same software oracle.
5. Build and measure it on the KV260.
6. Replace the tiled analytical proxy with an RTL candidate after the first
   comparison.

The design is ready to progress when every major performance claim has an
explicit workload, evidence label, and reproducible artifact.
