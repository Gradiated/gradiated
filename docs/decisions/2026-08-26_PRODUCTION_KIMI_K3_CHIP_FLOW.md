# Production Kimi K3 chip-design flow

- Date: 2026-08-26
- Status: production-flow recommendation
- Decision: keep OpenROAD and the Foundry simulators for research. Move a
  finalist to a foundry-certified Cadence, Synopsys, or Siemens flow only
  after the target process, memory, package, and volume assumptions are fixed.

## Question

What would replace the open research flow when a Kimi K3 accelerator moves
toward a real production ASIC?

## Core distinction

Production does not use one “virtual fabrication environment.” It uses a
foundry PDK plus a certified collection of EDA tools, IP, rule decks, and
reference scripts. The foundry PDK defines the process, cell libraries, SRAM
macros, IO, extraction, design rules, reliability rules, and supported corners.

The tool vendor and foundry must certify the combination for the selected node.
Changing only the tool while keeping an academic PDK does not create a
production flow.

## Typical production flow

```text
Model and workload specification
  -> architecture and compiler model
  -> RTL and IP integration
  -> simulation, formal, lint, CDC/RDC, DFT planning
  -> synthesis and physical planning
  -> placement, CTS, routing, optimization
  -> extracted timing, power, IR/EM, thermal analysis
  -> signoff DRC/LVS/DFM and package verification
  -> GDSII/OASIS tapeout
  -> wafer, package, bring-up, and silicon correlation
```

For a Kimi K3 accelerator, HBM, interposer, die-to-die links, power delivery,
cooling, and package thermal behavior are first-order design constraints. The
flow must therefore include 2.5D/3D package design and verification, not only
RTL-to-GDSII.

## Common commercial tool stacks

Choose one primary digital implementation stack after the foundry is selected.

| Function | Cadence stack | Synopsys stack | Siemens stack |
|---|---|---|---|
| RTL simulation and debug | Xcelium, SimVision, Verisium | VCS, Verdi | Questa |
| Formal and equivalence | Jasper, Conformal | VC Formal, Formality | Questa Formal |
| Synthesis | Genus | Design Compiler NXT or Fusion Compiler | Oasys |
| Physical implementation | Innovus | Fusion Compiler or IC Compiler II | Aprisa/Nitro |
| Signoff timing | Tempus | PrimeTime | Typically paired with other signoff tools |
| Parasitic extraction | Quantus | StarRC | Calibre xACT |
| Power and reliability | Voltus | PrimePower, RedHawk integration | Calibre PERC and partner tools |
| DRC/LVS | Pegasus | IC Validator | Calibre nmDRC/nmLVS |
| DFT | Modus | TestMAX | Tessent |
| Emulation/prototyping | Palladium, Protium | ZeBu, HAPS | Veloce |

Cadence documents a unified Genus–Innovus–Tempus flow with Quantus extraction,
Voltus power analysis, and Pegasus verification. Synopsys documents Fusion
Compiler with integrated signoff timing, parasitic extraction, and power
analysis. Siemens positions Aprisa as a detailed-route-centric place-and-route
platform and Calibre as a foundry-supported verification family. These are
vendor descriptions, not independent accuracy guarantees.

## What changes from the research flow

| Research flow | Production replacement | Why it matters |
|---|---|---|
| Nangate45 or ASAP7 | Foundry PDK for the selected node | Real design rules, libraries, corners, and manufacturability constraints |
| Yosys | Genus or Design Compiler/Fusion Compiler | Physically aware synthesis and stronger foundry/library integration |
| OpenROAD | Innovus, Fusion Compiler/ICC2, or Aprisa | Production-scale timing, routing, multi-corner optimization, and foundry enablement |
| OpenRCX | Quantus, StarRC, or Calibre xACT | Foundry-qualified RC extraction and advanced interconnect effects |
| Magic/KLayout checks | Pegasus, IC Validator, or Calibre | Foundry signoff DRC/LVS/DFM decks |
| Fakeram or generated research SRAM | Foundry or licensed SRAM compiler/macro | Real density, timing, leakage, redundancy, repair, and yield behavior |
| Analytical package model | 2.5D/3D package, SI/PI, and thermal tools | HBM and interposer effects can dominate system performance |
| Verilator-only testing | VCS/Xcelium/Questa plus formal, emulation, and production regressions | Larger verification scope and software bring-up |

OpenROAD remains useful for early architecture work, regression tests, and
portable RTL. Its PPA ranking may change after retargeting to the production
PDK and commercial implementation flow. Re-run all finalists in the production
flow before making a hardware claim.

## Where the agent belongs

The agent can safely operate as a flow controller and design-space explorer.
It can:

- generate or edit parameterized RTL;
- change legal mappings, buffer sizes, pipeline structure, and floorplan
  parameters;
- launch synthesis, implementation, and analysis jobs through Tcl/Python APIs;
- classify timing, congestion, power, and DRC failures;
- preserve reports, diffs, hashes, and tool versions;
- maintain a Pareto frontier and explain causal tradeoffs.

The agent must not silently edit PDK files, signoff rule decks, clock
constraints, quality gates, or measurement boundaries. A human must approve
changes that affect signoff assumptions or tapeout scope.

The production loop should be:

```text
agent proposal
  -> immutable experiment spec
  -> RTL/formal/DFT checks
  -> commercial synthesis and implementation
  -> signoff analyses
  -> independent report review
  -> human acceptance or rejection
```

Cadence and Synopsys both document scripted, integrated flows. This makes agent
orchestration practical, but automation does not remove the need for human
signoff ownership.

## Recommended transition for this project

1. Keep the current Foundry action ledger as the system-level model.
2. Use OpenROAD and Nangate45/SKY130 to mature the KDA RTL and testbench.
3. Validate the same KDA kernels on real B300 hardware.
4. Freeze one candidate block and its workload contract.
5. Select a foundry node, SRAM strategy, HBM/package strategy, target volume,
   power envelope, and tapeout schedule.
6. Obtain the foundry PDK and its reference flow through the foundry, an ASIC
   design service, or an experienced silicon partner.
7. Choose Cadence, Synopsys, or Siemens based on foundry certification, IP
   availability, team expertise, and license cost.
8. Re-run the candidate in the commercial flow. Do not transfer OpenROAD PPA
   numbers without this comparison.
9. Use emulation or FPGA prototyping for software and runtime bring-up.
10. Tape out only after timing, power integrity, thermal, DRC/LVS/DFM, DFT,
    package, yield, and economic gates pass.

## Production claim boundary

Commercial signoff improves confidence in the selected process and operating
corners. It does not prove the final silicon will meet every target. Silicon
still adds process variation, package effects, thermal behavior, manufacturing
yield, firmware behavior, and workload variation.

The current research handoff correctly keeps tapeout at `NO-GO` until the
candidate has measured software evidence, calibrated performance prediction,
PPA, package and memory evidence, yield assumptions, and a pessimistic economic
case. Use the production flow to validate a finalist, not to compensate for an
unproven workload advantage.

## Sources

| Source | Evidence type | Retrieved |
|---|---|---|
| https://www.cadence.com/en_US/home/resources/datasheets/innovus-implementation-system-ds.html | Vendor-reported Cadence implementation, extraction, timing, and power integration | 2026-08-26 |
| https://www.cadence.com/en_US/home/resources/product-briefs/genus-synthesis-solution-pb.html | Vendor-reported Genus/Innovus/Tempus correlation and scripting | 2026-08-26 |
| https://www.synopsys.com/implementation-and-signoff/physical-implementation/fusion-compiler.html | Vendor-reported Synopsys RTL-to-GDSII and signoff integration | 2026-08-26 |
| https://qacf-www.synopsys.com/implementation-and-signoff/lynxnxt-automation-system/flow.html | Synopsys flow-management and tool integration list | 2026-08-26 |
| https://eda.sw.siemens.com/en-US/ic/ic-design/place-route | Vendor description of Aprisa place-and-route | 2026-08-26 |
| https://eda.sw.siemens.com/en-US/ic/calibre-design/physical-verification/3dstack | Calibre 3D package DRC/LVS verification | 2026-08-26 |
| https://eda.sw.siemens.com/en-US/eda-cloud-solutions/ic-packaging/software/package-simulation/ | Package SI/PI, thermal, and parasitic analysis | 2026-08-26 |
| https://www.kimi.com/en/blog/kimi-k3 | Official Kimi K3 architecture and nano-chip scope | 2026-08-26 |
| https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts/blob/master/docs/index.md | Open research flow and supported public platforms | 2026-08-26 |
| ../../research/lab/docs/SIMULATOR_LANDSCAPE.md | Repository evidence and current tapeout decision boundary | 2026-08-26 |
