# Virtual chip implementation environments

- Date: 2026-08-26
- Status: explanatory comparison
- Decision: use OpenROAD-flow-scripts with a real-node open PDK for learning
  physical design. Use Nangate45 or ASAP7 only for controlled benchmarking and
  flow study.

## Question

Which popular chip-design environments should a learner use, and how closely do
their results predict real silicon?

## Scope and limits

This note covers digital RTL-to-GDSII implementation. It does not compare FPGA
tools, analog custom-layout tools, packaging tools, or foundry shuttle prices.
There is no universal accuracy percentage. Accuracy depends on the PDK, the
analysis stage, the process corner, the workload, and the metric.

## Environments

| Environment | Typical target | What it is good for | Silicon relevance |
|---|---|---|---|
| OpenROAD-flow-scripts + Nangate45/FreePDK45 | Academic 45 nm model | Learning synthesis, placement, routing, timing reports, and RTL-to-GDS flow control | Low absolute relevance. Nangate45 is a representative, non-fabricable technology. It is useful for relative comparisons. |
| OpenROAD-flow-scripts + ASAP7 | Predictive 7 nm model | Research on advanced-node algorithms and design-space exploration | Low absolute relevance. It is predictive, not a foundry production process. |
| OpenROAD-flow-scripts or OpenLane + SKY130 | SkyWater 130 nm open PDK | Open-source ASIC learning, test chips, and realistic physical-design practice | Medium. The node and many design rules are tied to a real foundry process, but the open PDK is distributed as-is and still needs foundry-specific validation. |
| OpenROAD-flow-scripts or OpenLane + GF180MCU | GlobalFoundries 180 nm open PDK | Mature-node mixed-signal and digital experimentation | Medium for geometry and rules; timing and power remain model-dependent. |
| OpenROAD-flow-scripts + IHP SG13G2 | IHP 130 nm SiGe BiCMOS PDK | Open research with a foundry-oriented open PDK | Medium, subject to the PDK and library coverage used. |
| Cadence Genus + Innovus + Tempus/Quantus/Voltus | Proprietary foundry PDKs | Commercial digital implementation and signoff | High for pre-silicon closure when the correct foundry PDK, corners, extraction, and signoff decks are used. This is still a prediction, not a guarantee. |
| Synopsys Fusion Compiler + PrimeTime/StarRC/IC Validator | Proprietary foundry PDKs | Commercial RTL-to-GDSII implementation and signoff | High for the same reason. The result depends more on the PDK and signoff setup than on the product name alone. |

OpenROAD-flow-scripts currently documents support for Nangate45, ASAP7, SKY130,
GF180, and SG13G2, plus several proprietary platforms. OpenLane is an
automated flow built from tools including OpenROAD, Yosys, Magic, and Netgen.

## What “accurate” means

| Result | What you can usually trust | Main limitation |
|---|---|---|
| RTL or gate-level logic simulation | Functional behavior and cycle counts, if the testbench and models are correct | It does not predict physical delay, power, yield, or thermal behavior. |
| DRC and LVS | Whether the layout obeys the supplied rules and matches the supplied netlist | Passing the supplied checks does not prove yield, reliability, or compatibility with a real foundry. |
| Area | Relative area within one PDK and one cell library | Final area also includes macros, power grids, fillers, IO, clock structures, and packaging constraints. |
| Pre-layout timing | Early rough ranking of architectures | Wire delay is estimated from generic or placement-based RC values. |
| Post-route timing with extracted parasitics | The strongest digital timing estimate before tapeout | It still depends on library characterization, RC extraction, PVT corners, variation models, IR drop, clock uncertainty, and modeling assumptions. |
| Dynamic power | A workload-specific estimate when switching activity is realistic | Activity, voltage, temperature, leakage, memory behavior, and package effects can make the estimate wrong. |

OpenROAD distinguishes placement-based parasitic estimation from post-route
extraction. Its OpenRCX extractor uses process-specific extraction rules to
estimate wire resistance and capacitance from the routed layout. That is why a
post-route number deserves more trust than a number reported immediately after
synthesis.

## Practical accuracy ladder

```text
RTL simulation
  < synthesis timing estimate
  < placed timing with estimated RC
  < routed timing with extracted RC
  < foundry signoff across corners
  < measured silicon
```

The ordering is about physical prediction, not functional correctness. RTL
simulation can be more trustworthy for logic behavior than every later stage.

## Interpretation for the Kimi K3 article

The article's Nangate45 results support claims such as “this RTL can be routed
in the model” and “this structural change improves modeled timing.” They do not
support claims such as “a manufactured Kimi chip would run at this frequency.”
The article itself calls Nangate45 an academic PDK that does not correspond to a
real fab process. The Nangate library was generated from the FreePDK45 base kit
and characterized with the Predictive Technology Model.

## Method and falsification rule

This is a source review, not a silicon experiment. The claims above would be
falsified by an authoritative source showing that Nangate45 is a production
foundry PDK, or by a controlled study showing that the listed accuracy ordering
fails under matched PDK, corner, extraction, and silicon conditions.

## Sources

| Source | Evidence type | Retrieved |
|---|---|---|
| https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts/blob/master/docs/index.md | Current tool and platform documentation | 2026-08-26 |
| https://github.com/efabless/openlane | Current project description and component list | 2026-08-26 |
| https://github.com/google/skywater-pdk | Current PDK contents, design-rule, library, and license documentation | 2026-08-26 |
| https://cornell-ece5745.github.io/ece5745-S01-front-end/ | Teaching documentation identifying Nangate45 as a fake, non-fabricable technology | 2026-08-26 |
| https://foss-eda-tools.googlesource.com/third_party/freepdk45/+/refs/heads/main/Low_Power/README | Nangate library provenance and characterization documentation | 2026-08-26 |
| https://openroad.readthedocs.io/en/latest/main/src/est/README.html | OpenROAD parasitic-estimation documentation | 2026-08-26 |
| https://openroad.readthedocs.io/en/latest/main/src/rcx/README.html | OpenRCX post-route extraction documentation | 2026-08-26 |
| https://www.cadence.com/en_US/home/resources/datasheets/innovus-implementation-system-ds.html | Vendor-reported Innovus implementation and signoff integration | 2026-08-26 |
| https://www.synopsys.com/implementation-and-signoff/physical-implementation/fusion-compiler.html | Vendor-reported Fusion Compiler RTL-to-GDSII and signoff integration | 2026-08-26 |

## Next action

For learning, run the same small accelerator through Nangate45 and SKY130.
Compare area, post-route timing, congestion, and DRC results within each PDK.
Do not compare the raw frequency numbers across the two PDKs as if they were
measurements of the same manufactured chip.
