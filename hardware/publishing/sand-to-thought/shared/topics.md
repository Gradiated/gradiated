# Topic map

Working map revised after discussion on 2026-10-12, with a planning checkpoint on 2026-10-13. The ten broad subjects organise browsing; the working eleven-chapter roadmap in [Post 001's plan](../articles/sand/plan.md#chapter-plan) organises the introductory story. The current article covers chapters 1–5, including a simple timing bridge and one instruction executing. Chapter 6 is the next planned continuation. All chapter names and the ten subject names are retained. Later chapters remain revisable. Subjects and chapters are different views of the same knowledge.

Each subject should have an accessible overview and progressively deeper branches. Subtopics below are a starting scope, not a claim of exhaustive coverage or a fixed syllabus. Detailed explanations and quantitative models should be added where they answer useful questions.

Subject pages are planned reading guides: a short orientation, an introductory reading link, and an ordered selection of deeper articles. The relevant section of the opening journey can supply the introductory reading without duplicating its prose. A broader subject overview may be added later. See [the agreed navigation model](library.md#agreed-reading-and-navigation-model). Existing subject anchor IDs are retained as labels evolve, so current topic links remain useful.

## Subject map

| Subject | Central question | Connections |
| --- | --- | --- |
| [1. Physics, materials and devices](#physics-and-semiconductor-devices) | How can a physical structure control current? | Foundation for circuits; realised through manufacturing |
| [2. Circuits and reliable signals](#electronic-circuits-and-reliable-digital-signals) | How do physical voltages become dependable bits? | Builds on devices; supports logic, storage, and physical interfaces |
| [3. Information, logic and arithmetic](#logic-arithmetic-and-number-representation) | How do we encode information and build circuits that select, compare, and calculate? | Supports processors and specialised computation |
| [4. State, timing, and memory](#state-timing-and-memory) | How do circuits retain information and update it reliably? | Supports control, processors, and memory systems |
| [5. Processors and the software stack](#processors-and-the-hardware-software-interface) | How does a machine execute a program? | Combines computation, state, control, and software |
| [6. Performance, parallelism and communication](#performance-parallelism-and-data-movement) | What limits useful work, and what can improve it? | Crosses circuits, memory, processors, and systems |
| [7. Workloads and specialised architectures](#workloads-and-specialised-architectures) | How should hardware and software fit the work? | Uses the foundations to explain different machines |
| [8. Designing and verifying chips](#chip-design-verification-and-physical-implementation) | How does a design become a correct, implementable chip? | Connects architectural intent with physical constraints |
| [9. Manufacturing, packaging and systems](#manufacturing-packaging-and-complete-systems) | How are devices made and assembled into useful systems? | Connects devices, implementation, memory, and communication |
| [10. Real architectures and their trade-offs](#architecture-case-studies) | Why did a particular chip make its design choices? | Applies several subjects to one documented design |

## How topics connect

Give each topic one primary home. Use **Builds on** for knowledge a deeper explanation needs, and selected onward links when they help a reader continue. Avoid maintaining every possible association. A high-level overview can introduce a concept before its detailed prerequisites.

Example route: [MOSFET](#mosfet) → [CMOS logic gates](#cmos-logic-gates) → [NAND and functional completeness](#nand-and-functional-completeness) → [full adder](#full-adder) → datapaths and processors. Another branch goes from gates to [feedback](#bistability-and-feedback), the [D latch](#d-latch), and storage.

Posts link to these definitions. Actual article coverage and publication status live in post plans and are summarised in [LIBRARY.md](library.md#coverage-and-gaps). A topic is introduced, explained, or worked through in a particular article; it is not globally “finished”.

Maintain these boundaries when adding articles:

- **Memory:** subject 4 explains physical storage and timing; subject 6 explains hierarchy, access, and communication; subject 9 explains packaging and integration.
- **Software:** subject 5 explains execution and the supporting software stack; subject 7 explains how particular workloads map onto machines.
- **Creating hardware:** subject 8 explains design, verification, and implementation; subject 9 explains fabrication, production test, and integration. Testing and silicon bring-up connect both.
- **Energy and heat:** device and circuit mechanisms connect subjects 1–2 to the switching-power and performance treatment in subject 6 and power delivery/cooling in subject 9. Use contextual links without duplicating full explanations.

Across subjects, ask why a mechanism works, what its physical limits are, what it costs, and what evidence supports the explanation. Include correctness, reliability, security where relevant, and quantitative comparisons. Scope should support both tracing a computation through the stack and explaining how engineers create the hardware.

### Place of the lecture 6–7 notes

The [saved recap](../../../learning/courses/eth-ddca-lectures-06-07-recap.md) is study material, not new website coverage. Timing and state machines connect subjects 4 and 5. The computer model, ISA and instruction-processing example belong primarily to subject 5. Basic addressing is needed to explain the computer before subject 6 develops hierarchy and communication costs. Verification appears as an early principle and is revisited within subject 8's engineering flow. The detailed record and lecture references remain in the [learning notebook](../../../learning/courses/chip-architecture-notebook.md).

<a id="physics-and-semiconductor-devices"></a>
## 1. Physics, materials and devices

Scope: charge, fields, voltage, current, energy, materials, carriers, and device behaviour. Builds on everyday physical intuition at overview level. Deeper branches can introduce the mathematics they require.

### Silicon and doping

How a semiconductor's material structure and added donor or acceptor atoms affect its carriers and electrical behaviour. Deeper branches: crystal structure, electrons and holes, carrier concentrations, drift and diffusion, and junctions.

### MOSFET

How an insulated gate controls conduction between source and drain. Builds on charge, electric fields, semiconductor carriers, and voltage differences. Deeper branches: MOS capacitors, potential-energy barriers, energy bands, threshold behaviour, current–voltage models, short-channel effects, and modern device geometries.

Other planned topics: electrostatic potential versus carrier potential energy; capacitance; thermal behaviour; quantum effects where needed to explain device operation. Connect physical limits to circuit delay, energy, and reliability.

<a id="electronic-circuits-and-reliable-digital-signals"></a>
## 2. Circuits and reliable signals

Scope: circuits made from devices and the physical contract that lets us treat their signals digitally. Builds on subject 1. Leads to Boolean circuits and state storage.

### CMOS logic gates

Complementary transistor networks that establish output logic levels. The inverter and NAND gate are the first examples. Deeper branches: pull-up and pull-down networks, loading, transfer characteristics, and transistor sizing.

### Logic levels and noise margins

How ranges of voltage represent bits and permit reliable communication despite variation and noise. A logic value of 1 is distinct from a universal physical value of 1 volt.

### Signal propagation and settling

Changes take time to spread through a circuit, so different values can settle at different moments. The overview uses an abstract wire grid to introduce the need to wait before using or storing a result. The drawing is an illustration of propagation, not a literal netlist or a truth-table simulation. Detailed delay analysis and its connection to clocked capture belong in the deeper timing article.

Other planned topics: elementary circuit laws; resistance and RC behaviour; interconnect; signal restoration; fan-out; propagation delay; switching energy and leakage; analogue circuits; analogue-to-digital and digital-to-analogue conversion; electrical I/O interfaces and signal integrity. Link to [switching power](#dynamic-switching-power), timing, and physical system integration for their broader consequences.

<a id="logic-arithmetic-and-number-representation"></a>
## 3. Information, logic and arithmetic

Scope: what combinational circuits compute and how we encode the values they operate on. Builds on digital signals; its abstract explanations can initially treat gates as given building blocks.

### NAND and functional completeness

The NAND truth table and how NAND gates can express Boolean functions. Separate this explanatory construction from the particular cells and circuits used in a real implementation.

### Full adder

A combinational block that adds two input bits and an incoming carry, producing a sum bit and an outgoing carry. Builds on binary representation and Boolean gates. Deeper branches: truth table, equations, gate implementations, and delay.

### Ripple-carry addition

Combining full adders so the carry from one bit position enters the next. Builds on the full adder. Leads to carry propagation, faster addition structures, subtraction, and arithmetic datapaths.

### Multiplexers

Selection circuits that pass one of several input values to an output, according to selection signals. Builds on Boolean gates. Leads to selecting processor operands and other paths.

### Arithmetic and logic units

Groups of arithmetic and logical circuits with control selecting an operation. Builds on adders and logic. The opening journey selects ADD and connects its inputs and result to working registers.

Other planned topics: bits and encodings; binary place value; Boolean algebra; truth tables; multiplexers; decoders; logic simplification; signed integers; fixed and floating point; multiplication; division; rounding; overflow; and numerical precision. Explain only the prerequisites a particular article needs.

<a id="state-timing-and-memory"></a>
## 4. State, timing, and memory

Scope: stored state, time-dependent behaviour, and physical memory structures. Builds on gates and circuit behaviour. Memory performance and hierarchy connect onwards to subject 6.

### Bistability and feedback

How carefully designed feedback can produce stable states that retain information. Explain why arbitrary feedback does not automatically make useful memory.

### D latch

A storage circuit whose output follows its data input while enabled and holds the captured value when disabled. Builds on gates and bistability. Deeper branches: signal traces, implementation, timing, and the distinction from an edge-triggered flip-flop.

### Registers

Groups of bit-storage elements that retain a multi-bit value under shared control. The opening article introduces four level-sensitive latches sharing write-enable. Distinguish this from edge-triggered registers when clocks are developed. Builds on the D latch and binary representation; leads to stored arithmetic results and processor state.

### Clocked updates

Capturing stable values at selected clock edges to coordinate successive operations. Builds on storage and circuit delay. Planned for the deeper timing article, which distinguishes clocked registers from the earlier write-enable latches and develops flip-flops, setup/hold, glitches, skew and timing analysis. The current overview introduces only propagation and settling.

### Memory addressing

Selecting a storage location using an address, while distinguishing that address from the location's contents. Builds on binary representation and selection. Connects physical memory organisation to instruction and data accesses.

Other planned topics: flip-flops; clocks; setup and hold; metastability; state machines; reset; memory addressing and selection; SRAM; DRAM; non-volatile storage; error detection and correction. Do not imply that all memory is physically built from the illustrated latch.

<a id="processors-and-the-hardware-software-interface"></a>
## 5. Processors and the software stack

Scope: combining arithmetic, storage, and control into a programmable machine, and connecting software to that machine. Builds on subjects 3 and 4.

### Processor organisation

Combining working registers, an ALU, selected paths and control into a processor, connected to memory and I/O. Builds on arithmetic, storage, selection and coordinated updates. The opening uses a simplified LC-3 organisation.

### Stored programs

Instructions encoded as bits and stored at addressed locations for a machine to fetch. PC holds an instruction address and IR holds a fetched instruction. The opening's first model shares memory for instructions and data. Leads to ISA, assembly and software translation.

### Instruction processing

How a particular organisation fetches, decodes and carries out an instruction using data paths, control signals and state. The opening traces LC-3 ADD R0, R1, R2 with R1 = 3 and R2 = 6, retaining the inputs and writing 9 to R0. Detailed ADD/LDR/JMP traces and LC-3 internal transfers belong in the focused article.

Planned topics: datapaths; register files; control; instruction sets; fetch, decode, and execution; loads and stores; branches; assembly; compilers; procedures and stacks; runtimes and libraries; operating systems; firmware and drivers; accelerator programming; interrupts; exceptions; virtual memory; protection and isolation. Include hardware security mechanisms and link vulnerabilities and mitigations to the relevant circuit and architecture explanations. Begin with one small worked machine and a traceable instruction or program.

<a id="performance-parallelism-and-data-movement"></a>
## 6. Performance, parallelism and communication

Scope: time, throughput, energy, capacity, and communication costs. This subject revisits constraints introduced at lower levels; it is not a prerequisite for the opening device story.

### Dynamic switching power

The energy and average power associated with charging and discharging circuit capacitances. Builds on capacitance and voltage. Deeper treatment distinguishes activity, frequency, switching power, leakage, and the assumptions behind a proportionality such as C V² f.

Other planned topics: latency versus throughput; locality; caches and scratchpads; memory hierarchies; bandwidth; on-chip and off-chip communication; pipelining; hazards; speculation; out-of-order execution; vector and thread parallelism; coherence; memory consistency; atomics and synchronisation; arithmetic intensity; roofline reasoning; profiling and performance measurement. Data movement and energy recur across the entire library. Compare measured time, energy, and cost for stated workloads, and distinguish theoretical peaks from useful throughput.

<a id="workloads-and-specialised-architectures"></a>
## 7. Workloads and specialised architectures

Scope: how workload properties influence computation, storage, control, and programming. Builds on logic, state, processors, and performance as each explanation needs them. Specific commercial implementations belong in subject 10.

### Look-up tables

A stored table of output values indexed by input bits. A single-output k-input Boolean LUT has 2^k table entries. Builds on truth tables, binary selection, and storage. Deeper branches: multiplexers, configuration bits, and implementation costs.

### FPGAs

Programmable logic resources and configurable interconnect used to implement circuits. Builds on LUTs and storage. Deeper treatment includes state elements, dedicated memories and arithmetic resources, configuration, tool flows, and comparisons with other implementation choices.

Workload branches: graphics; AI; scientific computing; signal processing; networking; embedded and real-time control. Explain what each workload asks of computation, storage, communication, and timing. An AI response is one complete worked destination for the opening journey, not the limit of the library's scope.

Architecture and mapping branches: CPUs; GPU execution and programming; SIMD and SIMT; FPGAs; specialised accelerators; matrix multiplication; dot products; multiply–accumulate units; tiling; systolic arrays; dataflow; precision; sparsity; neural-network operations; attention; training and inference; prefill and decode; kernel and compiler mapping. Give advanced subjects accessible introductions before their detailed mechanisms.

Post 001’s LUT/FPGA material is saved in [a draft for later reuse](../articles/sand/drafts/programmable-logic.md), potentially here or in chapter 8 of the opening journey. It is no longer on the current website.

<a id="chip-design-verification-and-physical-implementation"></a>
## 8. Designing and verifying chips

Scope: turning requirements and architectural choices into a verified design and physical implementation. Connects subjects 1–7 to manufacturing.

Planned topics: requirements and workload modelling; architecture exploration; hardware description languages (HDL) and register-transfer level (RTL) design; simulation; formal methods; verification; synthesis; standard cells; floorplanning; placement and routing; clock and power distribution; timing closure; physical verification; design for test; silicon bring-up and validation; and trade-offs in area, power, performance, engineering effort, and cost. Follow one design through the flow so these stages connect to an engineering outcome.

<a id="manufacturing-packaging-and-complete-systems"></a>
## 9. Manufacturing, packaging and systems

Scope: producing devices, connecting dies and other components, and operating the resulting system. Physical interfaces link back to circuits; system behaviour links back to architecture and software.

### Wafer production

The introductory route from silicon-bearing material through purification, crystal growth, and wafer preparation. This is distinct from the subsequent patterning and fabrication of devices and interconnect on a wafer.

Other planned topics: deposition; lithography; etching; implantation; interconnect fabrication; fabrication variation; yield and production test; manufacturing costs; packaging; chiplets; external memory and high-bandwidth memory (HBM) integration; boards; on-chip and off-chip links; I/O and physical interfaces; power delivery; cooling; reliability and ageing; and system integration. Provide high-level maps before detailed process or system explanations. Link communication behaviour to subject 6 and physical signalling to subject 2.

<a id="architecture-case-studies"></a>
## 10. Real architectures and their trade-offs

Scope: specific products or generations, explained through the reusable topics above. This is an application of the foundations, not a further physical layer.

Initial destinations: NVIDIA GPUs, Google TPUs, and other contrasting chip designs. Case-study questions: intended workload; organisation of compute and memory; control and programming model; data movement; bottlenecks; measured evidence; benefits; costs; and conditions under which the design choice makes sense. Distinguish company strategy from an individual architecture. Avoid timeless conclusions about an entire product family based on one generation.

## Curriculum references

These resources informed the map; their lecture numbering does not dictate publication or reading order. Only the course-level scope was compared during planning, not every lecture or technical claim.

- [ETH DDCA, Spring 2025](https://safari.ethz.ch/ddca/spring2025/doku.php?id=schedule): the current learning backbone. The schedule could not be fetched during planning; the existing notebook and [Mutlu's GPU lecture announcement](https://www.linkedin.com/posts/omutlu_digital-design-and-computer-arch-l19-activity-7326214423231012864-UcUm) provided context. Exact lecture mapping remains to be checked.
- [MIT 6.012](https://web.mit.edu/6.012/www/): semiconductor devices and circuits, including carriers, electrostatics, MOS devices, and circuit models.
- [MIT 6.004](https://ocw.mit.edu/courses/6-004-computation-structures-spring-2017/pages/calendar/): the digital abstraction through processors, software interfaces, memory, and communication.
- [Berkeley EECS 151](https://www2.eecs.berkeley.edu/Courses/EECS151/): digital design, verification, and ASIC/FPGA implementation practice.
- [Stanford CS149](https://gfxcourses.stanford.edu/cs149/fall24/): parallel hardware and software, locality, performance, and specialised computation.

Use primary technical documentation and research papers to verify detailed explanations and contemporary product claims. Course outlines are scope references, not evidence for every claim in an article.
