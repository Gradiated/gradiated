# Kimi K3 microarchitecture v0: StreamTile-E12

Date: 2026-08-16
Decision: advance a cost-optimized hierarchical-BSP tile machine to package
costing, matched NVIDIA measurement, and one RTL/FPGA dataflow slice. Do not
claim a hardware or TCO win yet.

## Bottom line

The first architecture should not try to beat NVIDIA at its own maximum-speed
game. Kimi K3 decode is a memory-capacity and useful-bandwidth workload with
comparatively modest useful arithmetic. The selected v0, **StreamTile-E12**,
therefore spends silicon on many small compute-plus-SRAM tiles, explicit data
movement, native low-precision formats, and just enough matrix throughput. It
accepts lower peak speed in exchange for a lower logic, power, fabric, and HBM
bandwidth target.

The system is twelve modules. Each synthetic module target has 192 GB of HBM,
3 TB/s nominal HBM bandwidth, 768 tiles, 192 KiB local SRAM per tile, 0.25 PF
BF16 and 0.50 PF MXFP4 peak, and a 0.5 TB/s scale-up endpoint. The complete pod
has 2.304 TB installed HBM, 36 TB/s nominal bandwidth, 9,216 tiles, about 1.7 GB
distributed SRAM, and a 6.5 kW power envelope. These are allocation targets,
not a sourced package or PPA result.

The execution model borrows the useful parts of Graphcore's
[Colossus/IPU organization](https://docs.graphcore.ai/projects/ipu-programmers-guide/en/latest/about_ipu.html):
code and live data are statically placed beside compute, movement is explicit,
and execution proceeds in deterministic compute/exchange epochs.
It does **not** copy strict chip-wide BSP. K3's 1.446 TB routed-expert store must
be streamed from external memory, and one slow or overloaded expert must not
stall all 9,216 tiles. StreamTile uses 48-tile local barrier groups, independent
double-buffered DMA groups, and pod-wide epochs only at layer and collective
boundaries.

At the canonical 82,308-token context and concurrency 128, the simulator gives:

| System | Output tok/s | TPOT | Power | Raw tok/J |
| --- | ---: | ---: | ---: | ---: |
| DGX B300 TP8, uncalibrated physical model | 2,980 | 43.0 ms | 14.5 kW | 0.205 |
| DGX B300 TP8, public-point calibrated | 1,804 | 70.9 ms | 14.5 kW | 0.124 |
| StreamTile-E12 economy point | 2,037 | 62.9 ms | 6.5 kW | 0.313 |
| StreamTile-E12 48 TB/s sensitivity | 2,791 | 45.9 ms | 7.5 kW | 0.372 |
| 64 TB/s StreamWeave speed reference | 3,929 | 32.6 ms | 9.0 kW | 0.437 |

The honest physical comparison is that the selected architecture is **32%
slower and 1.52x better in tokens/J** than the uncalibrated B300 model. Applying
the batch-one public B300 realization scalar makes the candidate appear 1.13x
faster and 2.52x better in tokens/J, but that scalar is not applied to the
candidate and should not be used for underwriting.

The selected point satisfies the deliberately moderate speed contract: c1
TPOT <=15 ms, and at c128 TPOT <=85 ms with at least 1,500 output tok/s. This
contract is an architecture-search choice, not a measured customer SLO.

## Dollar/token result and its boundary

The current observable market control is
[$7.39 per B300 GPU-hour on RunPod's secure tier](https://www.runpod.io/gpu-models/b300),
or $59.12/hour for eight GPUs. At the calibrated c128 throughput, that is
**$9.10 per million output tokens** before any separate serving software or
request-quality differences.

For StreamTile-E12 the simulator uses a transparent design-to-cost scenario:

- $260,000 target manufactured system capex;
- four-year life and 65% productive utilization;
- annual maintenance equal to 5% of capex;
- 6.5 kW active system power, PUE 1.2, and $0.10/kWh;
- $1.50 per active hour for the remaining modeled operating cost.

That produces $15.98 per productive hour and **$2.18 per million output
tokens** at c128, 4.18x lower than the current secure-cloud B300 control. The
hourly breakdown is approximately $11.42 capital, $2.28 maintenance, $0.78
electricity, and $1.50 other.

This is not yet a TCO claim. The $260k value is a target, not a BOM estimate.
The more decision-useful output is the break-even: under the same life,
utilization, maintenance, power, and PUE assumptions, StreamTile could cost as
much as **$1.22M** before losing to the $59.12/hour B300 cloud control at c128.
That large headroom mostly reflects the margin embedded in current scarce-GPU
cloud pricing; it does not prove an owned-custom system beats an owned DGX.

The 48 TB/s StreamTile sensitivity is faster but uses a synthetic $400k target
and models $2.34/million. It becomes preferable if its sourced incremental
memory/package cost is low enough. The search therefore selects 36 TB/s today,
but preserves 48 TB/s as a package-quote crossover rather than declaring it
architecturally inferior.

## Exact workload identity

- Model: `moonshotai/Kimi-K3` at Hugging Face revision
  `9f62e4e9fffbd0a83ddd60e1c209d828994b3569`.
- Text backbone: 93 layers, 69 KDA, 24 gated MLA, hidden 7,168, 96 heads.
- MoE: 896 routed experts, 16 selected, two shared experts, latent width 3,584,
  expert intermediate width 3,072.
- Precision: released MXFP4 routed-expert weights; BF16 attention, shared,
  latent, router, embedding, and head tensors; modeled FP8 MLA cache.
- Canonical traffic: 76,435 cached input + 5,873 uncached input + 985 output
  tokens, from the trailing-seven-day OpenRouter geometry captured 2026-07-28.
- Decode point: text-only, no speculative decoding, 82,308 starting context,
  concurrency 1/32/128/512.
- NVIDIA calibration: [vLLM's public non-speculative 111 output tok/s](https://vllm.ai/blog/2026-07-27-k3)
  at batch
  one, TP8, 8K input / 1K output on GB300/B300-class hardware.

The safetensors inventory was reconstructed with HTTP ranges over the prefix
and exact JSON header of all 96 shards; the 1.56 TB payload was not downloaded.
It found 497,220 tensors and no file-size mismatch.

| Released tensor class | Storage |
| --- | ---: |
| Routed experts | 1,446.456 GB |
| Attention | 72.404 GB |
| Shared experts | 24.310 GB |
| Latent MoE down/up | 9.454 GB |
| Embedding + LM head | 4.698 GB |
| Dense/shared FFN remainder | 1.907 GB |
| Router | 1.182 GB |
| Vision | 0.442 GB |
| Norm/bias/other | 0.008 GB |
| **Checkpoint shards** | **1,560.936 GB** |

The formula-derived total is 2,779,468,955,648 parameters, 0.0167% below the
released 2,779,931,837,184 count. Routed-expert arithmetic matches the released
2,722,740,830,208 logical U8 count exactly.

## Computation and movement for one output token

At the canonical context, useful work is about 305.9 GFLOP/output token:

| Operation family | Useful FLOP/token | Principal precision/state |
| --- | ---: | --- |
| 69 KDA projections, gates, output | 61.21 G | BF16 weights, MXFP8/BF16 activations |
| 24 MLA projections, gate, output | 11.15 G | BF16 weights |
| MLA context scan at 82,308 tokens | 97.10 G | FP8 latent KV + BF16/FP32 reductions |
| 92 routed expert selections | 97.24 G | MXFP4 weight, MXFP8 activation |
| Shared experts | 24.31 G | BF16 |
| Latent MoE down/up | 9.45 G | BF16 |
| Dense layer, routers, LM head | 4.98 G | BF16/FP32 top-k |
| KDA recurrence, AttnRes, norms/elements | about 0.56 G | BF16/FP32 state/reductions |

KDA state is **232.3 MB/live request**, including 69 x 96 x 128 x 128 BF16
recurrent state and short-convolution histories. The MLA cache scan is **1.138
GB/output token** at 82,308 context with 24 layers and a 576-byte FP8 latent
entry. Under independent uniform routing and perfect within-batch expert reuse:

| Concurrency | Unique experts/layer | Weight bytes/token | KDA HBM R+W/token | FLOP/HBM-byte |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 16.0 | 136.94 GB | 0 | 2.22 |
| 32 | 392.6 | 23.28 GB | 0.400 GB | 12.33 |
| 128 | 806.7 | 11.04 GB | 0.448 GB | 24.22 |
| 512 | 895.9 | 3.04 GB | 0.461 GB | 65.92 |

Real route skew may lower average bytes while worsening tail latency and tile
imbalance. A real expert-ID trace is required before fixing the scheduler.

At c128 the selected point needs roughly 26 TB/s of useful HBM traffic and only
about 0.62 PFLOP/s of useful arithmetic. Its aggregate 3 PF BF16 / 6 PF MXFP4
peak is already generous for decode. More MACs improve prefill and dense-model
coverage, but peak compute is not the scarce decode resource.

## StreamTile-E12 organization

### Pod and module

- Twelve equal modules in one scale-up domain; no layer pipeline baseline.
- 192 GB HBM and 3 TB/s nominal bandwidth per module; 2.304 TB and 36 TB/s pod.
- 768 independent tiles/module, arranged as sixteen 48-tile BSP groups.
- 192 KiB single-owner banked SRAM/tile; about 144 MB/module.
- 0.25 PF BF16 and 0.50 PF MXFP4 peak/module, targeting small matrix engines
  near 128 BF16 MAC/cycle/tile at a plausible clock rather than giant arrays.
- One 0.5 TB/s/module routed/collective endpoint with deterministic credits,
  multicast, reduction, and separate control and bulk-data virtual channels.
- Synthetic 275 mm2 logic target/module and 6.5 kW system envelope.

The package premise is deliberately unproven. Twelve 192 GB memory modules may
be worse than eight 288 GB modules once HBM stack count, substrates, reticles,
yield, cooling, boards, and scale-up ports are sourced. Module count is a search
variable, not a commitment.

### Tile

Each tile owns its SRAM address space and contains:

- a small dual-mode inner-product/systolic matrix block with BF16, FP8, INT8,
  MXFP4, and packed INT4 ingress;
- vector lanes for RMSNorm, SiTU, softmax, activation, scaling, sampling, and
  address generation;
- a DMA queue, two weight/activation buffers, dependency scoreboard, and route
  queue;
- local reduction, multicast receive, and barrier participation hardware;
- supervisor microcode and worker instruction slots generated by the compiler.

K3's 7,168, 3,584, 3,072, 1,536, and 12,288 dimensions are all divisible by
128. Decode maps 128 output rows across a tile group while broadcasting input
slices; prefill rotates the same MACs into output-stationary GEMM. Tail masks
and 32/64/128 subtiles preserve Llama, Qwen, DeepSeek, Gemma, dense, GQA, MLA,
and recurrent-model support.

No tile is a K3-specific hard macro. KDA recurrence, top-16 routing, AttnRes,
and quantization are microcoded vector/reduction programs with a few general
primitives: rank-one update, gated reduction, top-k, gather/scatter, and
in-place state commit.

### Hierarchical BSP schedule

A strict global `compute -> barrier -> exchange` sequence is attractive for
determinism but dangerous for sparse decode. StreamTile instead uses three
scales:

1. **Tile-local:** code, activations, scales, route metadata, and state shards
   remain in local SRAM while matrix/vector instructions execute.
2. **48-tile group:** a short BSP superstep performs an expert/projection tile,
   reduction, epilogue, and local exchange. A second DMA buffer prefetches the
   next expert wave while the current group computes.
3. **Module/pod:** dependency epochs occur only where the model requires them:
   completed projection reductions, MoE combine, KDA state commit, and the next
   layer's input. Independent groups may progress and drain route queues before
   the epoch closes.

The compiler knows tensor placement, liveness, HBM addresses, expert waves,
buffer parity, and collective routes. It emits per-tile programs plus epoch
tokens. A small dynamic escape path handles unexpected route imbalance,
failures, page misses, and irregular user kernels; the common path remains
static.

This structure aims to keep Graphcore's explicit ownership and low control
overhead while avoiding two failure modes for K3: pod-wide barriers around
every HBM copy and reserving nearly a gigabyte of SRAM per die when the added
capacity barely changes endpoint throughput.

## Memory hierarchy and dataflow

The default decode slice is:

`HBM weight page -> DMA buffer A/B -> tile-group matrix -> vector epilogue ->`
`local state/activation SRAM -> route/reduction network -> next tile group`

The 144 MB/module SRAM budget is conceptually divided into tile-local shares
for double-buffered weight fragments, current activations, reduction partials,
KDA/AttnRes state shards, route queues, code, and DMA descriptors. Exact shares
are compiler allocations rather than fixed hardware partitions.

Increasing SRAM from 72 to 576 MB/module changes modeled c128 throughput only
from 2,035 to 2,044 tok/s. The SRAM is valuable for determinism, fusion, local
bandwidth, and c1 state residency—not for caching a meaningful fraction of the
expert bank. This is the central difference from an all-on-chip wafer-scale
strategy.

At 90% usable memory, checkpoint plus cache/state requires 1.562 TB at c1,
1.605 TB at c32, 1.736 TB at c128, and 2.263 TB at c512. The pod exposes 2.074
TB usable, so **c512 is rejected** at the canonical 82K context. Prefix sharing,
cache compression/tiering, more installed HBM, or lower concurrency is needed.

## Why this can stay flexible

The ISA/compiler contract exposes:

- dense, grouped, routed, and batched GEMM/GEMV;
- BF16, FP8, INT8, MXFP4, packed INT4, programmable scale groups, and higher
  precision accumulation;
- full, grouped-query, multi-latent, sliding, recurrent, and convolutional
  attention-state operations;
- paged cache gather/scatter, prefix copy, DMA, multicast, reduction,
  all-to-all, expert dispatch/combine, and checkpoint/restore;
- configurable top-k, expert placement, tensor/expert/data parallel schedules,
  tails, and 32/64/128 tile shapes;
- programmable vector epilogues and a slow escape path rather than dedicated
  model-specific activation silicon.

The architectural bet is on explicit locality and cheap scheduling, not on one
attention flavor. A new open model should normally require a graph lowering,
placement, and microcode change. The test suite must include K3 plus at least
one dense GQA model, one DeepSeek-style MoE/MLA model, and one awkward-dimension
model before the tile shape freezes.

## Sensitivities and rejected directions

- **HBM is still the design knob.** At c128, 2/2.5/3/4/5.33 TB/s per module
  produces about 1,361/1,699/2,037/2,709/3,597 tok/s. Buy more only when the
  sourced incremental dollars per bandwidth improve dollars/token.
- **Useful bandwidth realization matters.** At the 3 TB/s point, 55/65/72/78/
  82% efficiency produces 1,558/1,840/2,037/2,205/2,317 tok/s. The selected
  speed floor requires roughly 53% realization.
- **Large SRAM is rejected.** Four times the selected SRAM changes throughput
  by less than 0.4% at c128.
- **Heroic fabric is rejected.** Exact starts, multicast/reduction support, and
  avoiding barrier tails matter more than terabytes of unused link bandwidth.
- **Compute-rich, memory-poor is rejected.** The negative control remains HBM
  bound despite more matrix peak.
- **Maximum-speed StreamWeave is a reference, not the baseline.** It reaches
  3,929 synthetic tok/s, but provisions B300-class 64 TB/s HBM and far more
  matrix silicon. It advances only if sourced cost per delivered token beats
  the economy point.
- **Pure layer pipeline is stopped.** The prior PP8 and TP2xPP4 mappings lost
  enough expert reuse and added enough autoregressive dependence to be poor
  baselines. They can return only with route-trace evidence.

## Decisive next experiments

1. **Memory/package cost gate.** Obtain two independent volume ranges for 2.304
   TB installed memory at 36 and 48 TB/s, including logic die, interposer or
   substrate, PHY, board, yield, cooling, host, scale-up, NRE amortization, and
   support. Kill the $260k scenario if the physically credible lower bound is
   above it; recompute the cloud break-even with deployment-specific
   utilization and electricity.
2. **Matched NVIDIA control.** Run the pinned K3 revision on eight B300s at
   c1/c32/c128 with the 82K trace. Capture profiler-off throughput/TPOT, HBM/L2
   bytes, tensor activity, launch gaps, power, exact memory, expert IDs, route
   skew, and failures. Do not transfer the 8K batch-one scalar afterward.
3. **Hierarchical-BSP event simulation.** Replay real top-16 expert IDs through
   48-tile groups with HBM banks, DMA buffers, barriers, route queues, tail
   tiles, collectives, and backpressure. Kill hierarchical BSP if barrier,
   imbalance, or starvation consumes more than 15% of endpoint time at c32 or
   c128.
4. **First RTL/FPGA slice.** Implement `DDR/HBM -> double-buffered local SRAM ->
   small MXFP4/MXFP8 matrix group -> SiTU/RMSNorm -> route/reduction -> KDA
   state update`, driven by static tile programs. Use exact 3,584x3,072 and
   7,168x12,288 shapes. Measure Fmax, MAC utilization, banks/ports, bytes/cycle,
   barrier tail, DMA overlap, numerical error, area, and watts.
5. **Flexibility regression.** Compile representative Llama, Qwen, DeepSeek,
   Gemma, K3, dense, and MoE blocks. Reject tile/ISA choices that need
   model-specific RTL or lose more than the agreed utilization threshold on
   non-128 dimensions.

## Claim and non-claim

Measured: released tensor headers and prior OpenRouter traffic.
Vendor/runtime reported: model summary, B300 specifications, Graphcore
programming/hardware organization, public vLLM K3 throughput.
Observed market: current RunPod B300 rental rate.
Derived: tensor categories, work/bytes/state/capacity, B300 calibration scalar,
cloud $/million, and break-even capex.
Synthetic: every StreamTile performance, power, area, capex, efficiency, and
comparison.

This supports a cost-oriented architectural hypothesis and falsification plan.
It does not support “cheaper than NVIDIA,” “faster than NVIDIA,” buildability,
availability, or tapeout.

## Sources and reproduction

Primary source identities and retrieval dates are machine-readable in
`experiments/kimi_k3_architecture_search/evidence/sources.json`. The principal
sources are Moonshot's K3 repository and pinned checkpoint, vLLM's serving
report, NVIDIA's DGX B300 guide, Graphcore's IPU hardware documentation, and
RunPod's current B300 rental page.

```sh
cd research/sol/experiments/kimi_k3_architecture_search
python3 tensor_inventory.py --output evidence/tensor_inventory.json
python3 run_search.py --spec spec.json --output results/search_results.json
python3 -m unittest -v test_search.py
```

The experiment contract, opportunity register, complete operation ledger,
sensitivity grid, capacity failures, economics, and limitations are stored
beside the simulator.
