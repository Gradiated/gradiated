# How to get an answer out of sand

<!-- Editorial: copied from the live page on 2026-10-12 without rewriting the prose. Visual cue blocks and scene markers are editing notes, not article copy. This file builds the website automatically while preview.sh runs; see web/README.md. -->

How do we get from the silicon atoms in a grain of sand to a machine that can answer a question? This overview will follow a path through progressively larger and more complex structures that can calculate, remember, and ultimately think.

## Sand and metal

<!-- scene: quartz -->

We start with quartz, the main ingredient in sand. Quartz is silicon dioxide: one silicon atom for every two oxygen atoms, arranged in a repeating crystal structure. Our first task is to separate the silicon from the oxygen.

<!-- scene: ingot -->

We heat the quartz with carbon to extract silicon, then purify it. We melt the purified silicon and grow it into one large crystal, called an ingot.

<!-- scene: wafer -->

We then slice the ingot into thin wafers: the blank canvases for our chips.

<!-- scene: boron -->

We can change how silicon conducts electricity by adding small amounts of other elements. This is called doping. Here is a cross-section of our wafer, lightly doped with boron which was mixed into the liquid silicon before crystal growth.

<!-- scene: implant -->

We can also implant dopants into selected parts of the wafer by firing electrically charged atoms into the silicon. Here we create two pockets of phosphorus-doped silicon within the boron-doped silicon. Phosphorus and boron respectively donate and accept electrons. By carefully arranging distinct regions of silicon doped with these two elements, we can shape how current flows.

<!-- scene: wires -->

We can now build our first transistor. We add a wire to each of the two pockets and place a third wire, called the gate, above the silicon between them. The gate is slightly separated from the silicon, allowing it to control the flow of current between the other wires without making direct contact.

<!-- scene: voltages -->

A voltage difference can drive electrons through a circuit. Let us hold the left wire at `0` volts and the right wire at `1` volt. For electrons, higher voltage means lower energy, so picture the `0`-volt side as higher ground and the `1`-volt side as lower ground. Electrons would flow downhill from left to right, but a hill between the two pockets blocks their path. The gate lets us lower this barrier and allow them through.

<!-- scene: blocked -->

With the central gate also at `0` volts, this barrier is high and electrons struggle to flow between the two pockets.

<!-- scene: flowing -->

Raising the gate to `1` volt lowers this barrier, opening a conducting path between the pockets. Electrons can now flow through the transistor and around a connected circuit, lighting a bulb. This is the basic picture of an n-type MOSFET, an electrically controlled switch with no moving parts. With no mechanism to move, the switch can be built as a microscopic pattern of materials and repeated billions of times across a chip.

<!-- scene: symbol -->

We now have a switch that we can control with a voltage input. To make larger circuits easier to draw, we will represent each transistor with a simple symbol, shown on the left. On the right, we show what this switch does. With its gate at `1` volt, it connects the two ends like an unbroken wire. With its gate at `0` volts, the connection is broken. The gate controls this connection without joining it.

Wires connected through an on switch share the same voltage. Connecting a wire to a supply held at `1` volt brings it to `1` volt, and connecting it to a supply held at `0` volts brings it to `0` volts. An off switch keeps the two sides separate.

<!-- scene: switch-types -->

We can also make a p-type MOSFET by swapping the two types of doped silicon. In the circuits we are about to build, the n-type switch turns on for an input of `1` volt and off for `0` volts, while the p-type does the reverse. The small circle on its gate distinguishes the p-type symbol. We now have two switches that respond in opposite ways to the same input.

The next step is to combine these switches into larger and larger structures so that, together, they can calculate, remember and think. We will build towards these abilities one layer at a time, showing how each new structure makes more complex tasks possible.

## Logic

<!-- scene: not -->

To calculate with electrical signals, we first need a way to represent information. We use a low voltage to represent `0` and a high voltage to represent `1`. Each of these binary digits is called a bit.

By connecting transistors, we can build circuits called logic gates that turn input bits into output bits according to a simple rule. The simplest example is the NOT gate, which flips its input. A `0` becomes a `1`, and a `1` becomes a `0`.

Let’s zoom out one step and connect two transistors to make our first logic gate. The top bar is held at `1` volt and the bottom bar at `0` volts. Our input `A` controls both gates, and the output `Ā` is the wire joining the two transistors.

When `A` is `0`, the p-type switch is on and the n-type is off. The output is connected to the top bar, so it settles to `1`. When `A` is `1`, their roles reverse and the output connects to the bottom bar, settling to `0`. The output is always the opposite of the input. We have made a NOT gate.

<!-- scene: nor -->

Add two more transistors and we can give our circuit two inputs, `A` and `B`. Each input controls one p-type switch and one n-type switch. The two p-type switches at the top are connected one after another, so both must be on to connect the output to `1`. The two n-type switches at the bottom are side by side, giving two separate routes to `0`. Either one can make that connection.

When both inputs are `0`, both p-type switches are on and both n-type switches are off. The output connects to the top bar and becomes `1`. If either input is `1`, its p-type switch breaks the upper path while its n-type switch connects the output to the bottom bar, making it `0`. This is a NOR gate. Its output is `1` when neither `A` nor `B` is `1`.

<!-- scene: nand -->

Now rearrange the same four transistors. Put the two n-type switches one after another and the two p-type switches side by side. The output can reach the bottom bar only when both n-type switches are on, which requires both inputs to be `1`. It then becomes `0`.

If either input is `0`, its n-type switch breaks that lower path and its p-type switch provides a connection to the top bar. The output becomes `1`. This is a NAND gate. Its output is `1` when `A` and `B` are not both `1` simultaneously.

A truth table lists the output for every possible combination of inputs. These tables collect the rules we have just built from switches.

**NOT**

| `A` | NOT output `Ā` |
| --- | -------------- |
| `0` | `1`            |
| `1` | `0`            |

**NOR and NAND**

| `A` | `B` | NOR output | NAND output |
| --- | --- | ---------- | ----------- |
| `0` | `0` | `1`        | `1`         |
| `0` | `1` | `0`        | `1`         |
| `1` | `0` | `0`        | `1`         |
| `1` | `1` | `0`        | `0`         |

<!-- scene: nand-symbol -->

Let’s zoom out again and give this four-transistor NAND circuit a symbol. The two inputs enter on the flat side, and the output exits after the small circle.

It can be shown that NAND gates alone can be combined to implement any function that maps a finite set of input bits to output bits. In other words, we can specify a truth table and build a circuit that follows it using only NAND gates. One NAND with its two inputs tied together makes NOT. Two make AND by using the second to invert the first’s output. Three make OR by inverting each input before feeding them into the third. A fourth inverts that result to make NOR. NOT, AND and OR are enough to build any truth table, so NAND alone is enough too.

This makes NAND gates universal building blocks. From this one simple circuit, we can build the logic for everything from a calculator to a computer running an AI model.

## Arithmetic

<!-- scene: adder -->

Let’s zoom out further and combine NAND gates into a circuit that adds. In binary, we have only two digits, `0` and `1`, so adding `1` and `1` gives `10`. We write down `0` and carry `1` into the next column, just as we carry digits in ordinary addition.

Our circuit handles one column at a time. It adds two input bits, `aᵢ` and `bᵢ`, along with any carry from the previous column, `cᵢ`. It produces the answer bit `sᵢ` and a carry for the next column, `cᵢ₊₁`. This three-input, two-output circuit is called a full adder.

<!-- scene: chain -->

Connect several full adders in a row, passing each carry `cᵢ₊₁` into the next column, and we can add entire binary numbers. Here, four adders calculate `0011 + 0110 = 1001`, or `3 + 6 = 9`. More columns let us work with larger numbers. With addition as a building block, it is a short step to circuits that subtract and multiply, and our toolset has grown.

<!-- scene: heat -->

We have combined small groups of transistors into a circuit that adds numbers, but each calculation has a physical cost. Every calculation involves voltage flips as some of the transistors switch. These flips charge or discharge the tiny capacitances of the transistors and wires, expending energy that is dissipated as heat.

The faster we switch, the more heat we produce each second. This switching power scales with `CV²f`, where `C` is the capacitance being switched, `V` is the voltage swing, and `f` is the clock speed, which sets the pace of computation. Smaller capacitances and lower voltages reduce the energy needed, while switching less often reduces the rate at which we generate heat. Heat is a budget we will keep encountering as the transistor populations climb.

<!-- scene: timing -->

As circuits become larger and more complex, timing challenges appear. Changing an input does not change every part of a circuit at once. The change takes time to spread, and different values settle at different moments. These delays can result in incorrect information processing as old data gets used for computation, or glitches. This will need to be carefully considered during circuit design.

## Memory

<!-- scene: latch -->

We can now calculate an answer, but how do we remember it? Let’s zoom back in and connect a few NAND gates so that their outputs feed back into their inputs. This circuit is called a latch. It has a data input `D`, a write-enable input `WE`, and an output `Q`. While `WE` is `1`, `Q` becomes `D`. When `WE` becomes `0`, `Q` holds its last value, even if `D` changes.

How does a loop create memory? The two gates on the right feed their outputs into each other, each reinforcing the other’s state. With writing disabled (`WE = 0`), this feedback holds `Q` at its last value for as long as power is supplied. We have added memory to our toolset.

<!-- scene: register -->

Let’s zoom out again and place four latches side by side, each holding one bit. Together, they form a four-bit register that can remember a four-bit binary number. The four data wires carry one bit each. A shared write-enable signal lets all four latches copy their inputs together, then hold the number when `WE` returns to `0`.

<!-- scene: memory-two -->

Now stack a second row underneath. We have two places to store a four-bit number, so we need a way to choose between them. A single bit, labelled `ADDR`, selects row `0` or row `1`. A decoder, shown in the box on the left, turns `ADDR` into one selection signal for each row. Only the chosen row’s signal is `1`. A NOT gate selects row `0` when the `ADDR` is `0`, while a direct wire selects row `1` when it is `1`.

Both rows receive the same four data inputs. To write a number, place its four bits `D0` to `D3` on these wires, select the destination `ADDR`, then set `WE` to `1`. An AND gate combines `WE` with each row’s selection signal, so only the chosen row copies the number at `D`. Return `WE` to `0` and both rows hold their contents, even if the input changes.

To read a number, select its `ADDR` and leave `WE` at `0`. At the right of each latch, an AND gate passes its bit only when that row is selected. An OR gate at the bottom of each column combines these paths. Unselected rows always contribute `0`, so each OR gate reproduces the selected bit, bringing the chosen number to output `Q`, where we read it. Reading does not change either stored number. These AND and OR gates, controlled by the decoder’s selection signals, form a multiplexer that chooses which row’s stored bits reach `Q`.

<!-- scene: memory-array -->

Zoom out once more and add two rows. We now have four locations, each holding four bits. Two address bits `ADDR` distinguish `00`, `01`, `10` and `11`. The same decoder now turns that two-bit `ADDR` into four selection signals, with exactly one active at a time. That signal chooses the row to read and, if `WE` is `1`, the row to write.

The `ADDR` tells us where to look. The contents tell us what is stored there. Each `ADDR` selects a complete four-bit number, rather than an individual bit. Two address bits choose among four locations, while each location stores four bits. The `ADDR` width and the number of bits stored at each location are separate choices.

Adding rows gives us more locations, while adding columns lets each location hold a wider number. Here, sixteen latches give us a small memory array with four locations, each storing a four-bit number.

<!-- scene: stored-answer -->

We can now connect our four-bit adder to the memory’s data inputs. It still calculates `0011 + 0110 = 1001`. Select `ADDR` `01` and set `WE` to `1`, and the four latches in that row store the answer. Return `WE` to `0` and they hold `1001`. The other rows keep their own numbers throughout.

Changing the `ADDR` now lets us read a different stored number without erasing this answer. Yellow highlights follow the selected read path and, while writing is enabled, the path carrying the adder’s result into the chosen row. We can calculate, choose where to store the answer, and find it again.

<!-- scene: memory-buses -->

As these structures grow, drawing every wire becomes crowded. We can draw a bundle of wires as one thicker line, called a bus. A diagonal slash marked `4` means four separate wires, one for each bit. It is a drawing shorthand, not a break in the connection or four bits squeezed onto one wire. The `ADDR` bus is marked `2`, while `WE` still needs only one wire.

We can now draw the whole memory array as a single block, with its latches, decoder and read-selection gates inside. We have circuits that calculate and remember. Let’s zoom out again and combine them into a computer that follows instructions, choosing which values to use, what to calculate and where to store each result.

## Building a computer

<!-- scene: computer-overview -->

We have circuits that calculate and circuits that remember. Now we can organise them into a machine whose task is determined by a list of instructions stored in memory.

We will follow the von Neumann model, where both data and instructions are stored in the same "unified" memory. Data supplies the values to work on, while instructions tell the machine what to do with them. Changing those instructions lets the same circuits perform a different task without changing their physical connections.

The central processing unit, or CPU, carries out these instructions, using calculation circuits, working registers and control circuits. Memory holds the program and its data, while input and output connect the machine to the outside world.

<!-- scene: memory-width -->

Let’s return to our memory array. It has four locations, each holding four bits. We can make each stored number wider by adding more bit positions to every row. Doubling the width gives us eight bits per location. Eight bits make one byte, so this small array now holds four bytes in total.

<!-- scene: memory-interface -->

We can hide the individual latches inside four larger blocks, one for each stored number. `ADDR` still selects the location, `D` carries the number to write, and `Q` carries the number read. To connect this memory to a processor, we add two registers that hold the values on those wires during an access.

The memory address register, or `MAR`, holds the `ADDR` of the location to access. For now, it holds only `2` bits, enough to select one of our `4` memory locations. The memory data register, or `MDR`, holds either the 8-bit number to write or the 8-bit number just read.

A separate write control, `WE`, determines whether memory copies the number from `MDR` into the selected location.

<!-- scene: memory-word -->

Now widen each location again, from eight bits to sixteen. Each stored number occupies two bytes. The `MDR` and its data paths widen to sixteen bits too, so they can carry the whole number together.

For the rest of our example, we will use LC-3, a small teaching computer. It works with sixteen-bit groups called words. We have reached its data width, but our four-location example is still much smaller than LC-3’s memory.

<!-- scene: memory-address-space -->

To add more locations, we need more address bits. Two bits choose among four locations. Sixteen bits choose among `2¹⁶ = 65,536` locations, so LC-3 uses a sixteen-bit `MAR`. We show only a few of those locations here. Each `ADDR` selects one complete sixteen-bit word, or two bytes, rather than a single byte.

Address width and data width are separate choices. A sixteen-bit address can select 65,536 locations, while a thirty-two-bit address can select `2³²` locations. How many bytes that represents depends on the size of each location. In a byte-addressed system, thirty-two-bit addresses cover `4 GiB`. LC-3 instead addresses two-byte words.

Calling a processor “16-bit” or “32-bit” usually describes the width of its main working registers and integer operations. It does not, by itself, tell us the size of its address space or how much memory is installed. In LC-3, the working registers, memory contents and addresses all happen to be sixteen bits wide.

<!-- scene: memory-access -->

Let’s use these registers to access a location. Choose Write to place `1` in `MAR` and `9` in `MDR`. `MAR` then selects the second location, and the write control lets memory copy the number from `MDR` into it. The other locations keep their values.

Choose Read to put the same `ADDR` in `MAR`. Memory selects that location and sends its contents back to `MDR`, where the processor can use them. Reading leaves the stored number unchanged. Try reading before and after writing to see the difference.

The yellow paths show the transfer, while the moving bits show which value is being copied. Register updates and memory access are coordinated steps. The memory needs time to respond, so the processor must allow each transfer to finish before using its result.

<!-- scene: working-registers -->

The CPU also needs registers for the values it is currently working on. Alongside dedicated registers such as `MAR` and `MDR`, LC-3 has eight general-purpose registers, named `R0` to `R7`. Each holds one sixteen-bit word. These few working slots are separate from the much larger collection of locations in memory.

We will begin with `3` in `R1` and `6` in `R2`. The register name identifies the slot, while its contents are the value stored there.

<!-- scene: select-values -->

Our adder calculates with whatever values reach its inputs. We already used a multiplexer to select which stored number reaches the memory’s output. Here, another multiplexer chooses which value reaches the adder. Its selection signal chooses one input and passes it on. The four-wire bundles in this small example carry the same four-bit numbers we used earlier.

<!-- scene: alu -->

We can also group our adder with circuits that perform logical operations. Together, they form an arithmetic and logic unit, or ALU. Control signals select which operation it performs. The registers supply its inputs, and another register can capture the result. A path marked `16` represents sixteen parallel wires, one for each bit.

<!-- scene: addressed-memory -->

Now bring our memory and its interface alongside the working registers and ALU. The working registers keep the values needed immediately, while memory holds the larger collection of program instructions and data.

The processor supplies an `ADDR` through `MAR` and exchanges a sixteen-bit word through `MDR`. This is the same read-and-write connection we have just built, now serving the larger machine.

<!-- scene: program -->

The same memory can hold both data and instructions. An instruction is a bit pattern specifying an operation and the values or locations involved. Storing a sequence of instructions gives us a program.

A register called the program counter, or `PC`, holds the `ADDR` of the instruction to fetch next. Another register, the instruction register, or `IR`, holds the instruction we have fetched. To fetch it, the processor copies `PC` into `MAR`, reads memory into `MDR`, then transfers the instruction to `IR`.

The machine repeatedly fetches an instruction, decodes it and carries it out. Usually, `PC` advances to the next instruction. A jump directs execution to a different `ADDR`, while a conditional branch does so only when a condition is met. This lets a program choose between actions or repeat a sequence of steps.

<!-- scene: control -->

The instruction bits enter decoding logic, which identifies the operation and its operands. The control unit uses this information to select paths, choose an ALU operation and enable the required register updates.

The controller also remembers which step it is performing. State stored in registers, combined with logic that determines the next step, forms a finite-state machine. Our familiar calculation and memory circuits now coordinate the work of the larger machine.

<!-- scene: execute -->

Let’s follow the instruction `ADD R0, R1, R2`. It tells the machine to add the contents of `R1` and `R2`, then place the answer in `R0`. We have already put `3` in `R1` and `6` in `R2`.

The machine fetches the instruction into `IR` and decodes its fields. Control signals select `R1` and `R2`, direct the ALU to add, and enable `R0` to capture the result. `R0` now holds `9`. During the fetch, `PC` advances to the following instruction `ADDR`, ready for the machine to continue.

This addition is one step. A program combines many such steps, using stored results, choices and repetition to carry out a larger task.

<!-- scene: computer -->

Let’s zoom out once more. The calculation circuits, working registers and control unit form our central processing unit, or CPU. Connected memory holds its program and data, while input and output connect it to the outside world.

We have built a machine that can follow different programs using the same hardware. That flexibility has a cost. Choosing operations and moving instructions and data between memory and the CPU take hardware, time and energy. Data movement can limit how quickly the machine works, a constraint we will return to when exploring memory systems, parallel processors and specialised chips.

First, we will see how a task written by a person becomes the instruction bits that direct these circuits.

<!-- footer -->

From a switch to logic, calculation, memory and now a computer, each larger structure gives us a new ability. Next, we will follow the connection from code to physical action.
