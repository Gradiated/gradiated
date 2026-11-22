# LED pulse generator walkthrough

Saved from *Inside our FPGA* as a draft for a future practical guide. The original chapter below keeps its scene markers and citation keys. The references are linked at the end.

The interactive figures and circuit model are in the [FPGA figure source](./figures). [ClockFigures.tsx](./figures/ClockFigures.tsx) contains the pulse and clock timing figures. [SystemFigures.tsx](./figures/SystemFigures.tsx) contains the implementation figures, [DeviceFigures.tsx](./figures/DeviceFigures.tsx) the configuration figure, and [ChipContinuation.tsx](./figures/ChipContinuation.tsx) and [ContinuationWorld.tsx](./figures/ContinuationWorld.tsx) the shared chip scenes. [model.ts](./figures/model.ts) holds the pulse simulation. The existing [article references file](./script.references.json) holds the citation metadata.

<!-- scene: pulse-generator -->

## From a description to a circuit

We know which building blocks a calculation needs. How do we describe that circuit and load it onto the FPGA? Before tackling the network, let’s take one smaller example through the complete design process: a circuit that controls a light-emitting diode, or LED.

An adder and a four-bit register form a counter. At each clock edge, it saves its previous value plus `1`, returning from `15` to `0`. A stored number called `width` determines how much of each sixteen-count repetition the output stays high.

Between clock edges, the adder prepares the next count. A comparison circuit checks whether that prepared number is below `width`, producing `1` if it is and `0` otherwise. At the edge, the counter saves the new count and an output flip-flop saves the comparison result. Both then hold their values until the following edge.

With `width` set to `4`, counts `0`, `1`, `2` and `3` have a high output. Counts `4` through `15` have a low output. That gives four high intervals in every sixteen. Choose `12` under Width in the figure, then select Advance to next period. The new width takes effect when the count returns to `0`, giving twelve high intervals. This avoids changing the pulse partway through a repetition.

The slash marks on the wires show how many bits travel together. The count needs four bits for `0` through `15`. The width needs five so it can also specify `16`, keeping the output high for the whole repetition.

Varying this on-time is called pulse-width modulation, or PWM. Repeated quickly enough, the pulses can control an LED’s apparent brightness through a suitable driving circuit. More of each repetition spent on generally means a brighter light.

<details>
<summary>Why save the output in another flip-flop?</summary>

Several counter bits can change at an edge, reaching a comparison circuit at slightly different times. That can briefly produce a wrong answer, called a glitch. We compare the prepared next count and capture the result only after it has settled, keeping those intermediate changes away from the output pin.[@registered-outputs]

</details>

<!-- scene: hardware-description -->

We could draw every component, but engineers usually describe larger circuits in a hardware description language. Here is pseudocode for our circuit, rather than code for a particular tool. We begin with the count at `0` and the output high for our example widths.

```text
between clock edges
    next_count = (count + 1) modulo 16
    next_output = 1 if next_count < width else 0

at each rising edge
    count captures next_count
    output captures next_output
```

The first part describes the connected adder and comparison circuitry. The second describes the registers that capture their results together. These circuits work as signals pass through them. They do not need a processor to fetch and execute a new instruction for every increment or comparison. Our inference circuit uses clocked control in a similar way, choosing which memory addresses to read, when to save a sum and which calculation comes next.

<!-- scene: simulate -->

Before configuring a chip, we can simulate the design on a computer. A test supplies a clock and input values, then checks the counter and output waveforms against the behaviour we expect.[@simulation]

For example, a test can check the wrap from `15` to `0` and verify that `width = 4` produces four high periods per repetition. Simulation checks the cases we test. It does not by itself prove that the physical circuit meets its timing requirements.

We can also reuse one software calculation to check several circuit designs. Take a sum of thirty-two products. In software, we calculate the expected answer once. Then we can test a circuit that gives all thirty-two pairs a turn through one multiplier, or try a version that uses two in parallel. An AI assistant can help us write and test another version quickly. We keep the inputs and expected answer the same.

<!-- scene: synthesis -->

Synthesis tools convert our hardware description into a connected circuit using the target FPGA’s resources. For our pulse generator, they identify storage for the count and output, plus logic for adding and comparing. They can simplify logic and remove parts whose results are unused.[@synthesis]

These tools search for efficient implementations, but do not guarantee the best possible circuit. The choice and order of optimisation steps affect the result. AI could help guide this search: researchers have trained models to choose optimisation sequences that seek smaller circuits while meeting a timing target.[@ai-synthesis]

An FPGA can also help test a chip before committing to manufacture. Engineers can map a proposed processor onto it and run software, checking whether its arithmetic, instructions and control work together.[@fpga-prototyping]

The starting point is the same kind of hardware description we used earlier: it specifies calculations, stored values and their updates at clock edges. One synthesis flow maps it to FPGA resources. Another maps it to a library of gates and storage circuits for the custom chip. Those circuits are then placed and connected by metal wires.[@synthesis]

Our AND rule, for example, can use a LUT on an FPGA. An ASIC can use an AND gate, with no LUT answer memory. Both implement the same input-output rule, using different physical circuitry.

<details>
<summary>How closely does an FPGA prototype match an ASIC?</summary>

Engineers can correct mistakes and reload the prototype without manufacturing another chip. OpenHW’s open-source CVA6 processor family provides a RISC-V example, targeting both FPGA and ASIC implementations.[@processor-prototype]

Some parts, including specialised memories and clock circuitry, need adaptation for the FPGA.[@prototype-adaptation] The prototype tests the design’s behaviour, but does not reproduce the eventual ASIC’s physical timing or power consumption. Those require separate checks before manufacture.

</details>

<!-- scene: map-and-route -->

The description has become a connected circuit. Return to the chip map to see where the tools put it. Placement assigns these resources to locations on the chip. Routing selects the available wires and switches that connect them.[@design-flow]

The resulting design uses a particular collection of LUTs, flip-flops and other blocks. We can inspect the tool’s reports to see what it actually built.

<!-- scene: timing-window -->

We also specify the required clock period, the time between successive rising edges, and the timing of external connections. At each receiving flip-flop, data must remain stable for a short time before the capture edge (the setup time) and after it (the hold time).[@sequential-logic]

<!-- scene: timing-check -->

Timing analysis checks paths through the placed and routed design against these requirements, accounting for logic and wire delays and differences in clock arrival time. Violating these timing requirements can make the circuit unreliable, even when its logical description is correct.[@timing-analysis]

A passing result depends on correctly specifying those requirements, called timing constraints. Signals arriving independently of our clock, such as a button press, need suitable input handling as well.

<!-- scene: configure -->

The tools package the placed and routed design into the bitstream we introduced earlier. We can send it through a configuration interface such as JTAG, a standard connection also used for testing. The configuration circuitry then loads the settings into the chip.[@configuration-physical; @configuration-load]

<details>
<summary>Why load more than the bits we change?</summary>

Our earlier LUT close-up followed one answer cell being rewritten, then showed the completed change to OR. In AMD UltraScale devices, configuration storage is organised into groups called frames, which are written as a whole. Changing two LUT answers can therefore require much more than two bits of loading data.[@configuration-frames]

</details>

After losing power, our SRAM-based FPGA must reload its configuration when power returns, often from flash memory on its circuit board.[@fpga-configuration]

We can then measure the real output and compare its pulses with the simulation. That checks the implemented design and its board connections, rather than merely the description we intended to build.

<!-- scene: running-parameters -->

Changing `width` while the counter runs changes working data. We can arrange for a new value to take effect when the next sixteen-count repetition begins. The counter, comparison and connections stay in place. Loading a different bitstream can change that circuit itself.

This distinction matters when we say an FPGA is programmable. Some changes update values used by an existing circuit. Others configure different hardware behaviour from the chip’s available resources.

## References

- `registered-outputs` — Altera. [Register combinational logic outputs](https://docs.altera.com/r/docs/683082/25.1/quartus-prime-pro-edition-user-guide/register-combinational-logic-outputs#:~:text=glitches%20generated%20by%20the%20combinational%20logic%20are%20blocked%20at%20the%20data%20input%20of%20the%20register) (Quartus Prime Pro Edition User Guide, version 25.1, section 3.2.3.1, 2026).
- `simulation` — Amaranth contributors. [Simulator](https://amaranth-lang.org/docs/amaranth/v0.5.0/simulator.html#simulating-circuits) (Amaranth language and toolchain documentation, version 0.5.0).
- `synthesis` — Yosys contributors. [A primer on digital circuit synthesis](https://yosyshq.readthedocs.io/projects/yosys/en/stable/appendix/primer.html#behavioural-level:~:text=The%20synthesis%20result%20however%20will%20contain%20an%20adder) (Yosys documentation, sections on behavioural, register-transfer and physical gate levels).
- `ai-synthesis` — Hosny, A., Hashemi, S., Shalan, M., Reda, S.. [DRiLLS: Deep reinforcement learning for logic synthesis](https://arxiv.org/html/1911.04021v2#:~:text=Logic%20synthesis%20requires%20extensive%20tuning,subject%20to%20a%20timing%20constraint.) (Proceedings of the 25th Asia and South Pacific Design Automation Conference; author manuscript, arXiv:1911.04021v2, abstract and sections I–II, 2020).
- `fpga-prototyping` — Synopsys. [FPGA prototyping and the SoC design/verification process](https://www.synopsys.com/blogs/chip-design/scalable-performance-for-soc-design.html#:~:text=As%20its%20name%20implies,real-world%20interface%20connectivity.) (Silicon to Systems Blog, introduction and “Fastest Path to a Prototype”).
- `processor-prototype` — OpenHW Group. [CVA6: an application class RISC-V CPU core](https://docs.openhwgroup.org/projects/cva6-user-manual/#:~:text=The%20CVA6%20targets%20both%20ASIC%20and%20FPGA%20implementations) (CVA6 documentation).
- `prototype-adaptation` — Synopsys. [FPGA-based prototyping](https://www.synopsys.com/content/dam/synopsys/services/datasheets/fpga-based-prototyping-ds.pdf#page=1) (Professional Services datasheet, adapting ASIC-targeted RTL for FPGAs, 2015).
- `design-flow` — AMD. [Placement and routing](https://docs.amd.com/r/en-US/ug892-vivado-design-flows-overview/Placement-and-Routing#:~:text=optimize%2C%20place%2C%20and%20route%20it%20onto%20the%20target%20device%20resources) (Vivado Design Suite User Guide: Design Flows Overview, UG892, version 2026.1, 2026).
- `sequential-logic` — Computation Structures. [Sequential logic](https://computationstructures.org/notes/sequential_logic/notes.html#:~:text=The%20flip%20flop%20shown%20above%20has%20the%20effect%20of%20loading%20new%20data) (Course notes, chapter 8, sections 8.2.1.4 and 8.3).
- `timing-analysis` — AMD. [Running timing analysis](https://docs.amd.com/r/en-US/ug892-vivado-design-flows-overview/Running-Timing-Analysis#:~:text=logic%20relationships%2C%20and%20constraints%20applied%20to%20your%20design) (Vivado Design Suite User Guide: Design Flows Overview, UG892, version 2026.1, 2026).
- `configuration-physical` — AMD. [Overview](https://docs.amd.com/r/en-US/ug570-ultrascale-configuration/Overview#:~:text=After%20programming%2C%20the%20FPGA%20bitstream%20is%20stored%20in%20highly%20robust%20CMOS%20configuration%20latches) (UltraScale Architecture Configuration User Guide, UG570, revision 1.20.1, 2025).
- `configuration-load` — AMD. [Configuration packets](https://docs.amd.com/r/en-US/ug570-ultrascale-configuration/Configuration-Packets#:~:text=The%20configuration%20logic%20consists%20of%20a%20packet%20processor) (UltraScale Architecture Configuration User Guide, UG570, revision 1.20.1, 2025).
- `configuration-frames` — AMD. [Configuration memory frames](https://docs.amd.com/r/en-US/ug570-ultrascale-configuration/Configuration-Memory-Frames#:~:text=FPGA%20configuration%20memory%20is%20arranged%20in%20frames,all%20operations%20must%20therefore%20act%20upon%20whole%20configuration%20frames.) (UltraScale Architecture Configuration User Guide, UG570, revision 1.20.1, 2025).
- `fpga-configuration` — AMD. [7 Series FPGAs configuration user guide](https://docs.amd.com/v/u/en-US/ug470_7Series_Config) (UG470, revision 1.17, 2023).
