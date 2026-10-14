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

A voltage difference can drive electrons through a circuit. Let us hold the left wire at 0 volts and the right wire at 1 volt. Picture a landscape where height represents the electrons’ potential energy. Electrons would flow downhill towards the lower ground on the right, but a hill between the two pockets blocks their path. By raising or lowering this hill, we can control whether or not they cross.

<!-- scene: blocked -->

With the central gate also at 0 volts, this barrier is high and electrons struggle to flow between the two pockets.

<!-- scene: flowing -->

Raising the gate to 1 volt lowers this barrier, opening a conducting path between the pockets. Electrons can now flow through the transistor and around a connected circuit, lighting a bulb. This is the basic picture of an n-type MOSFET, an electrically controlled switch with no moving parts. With no mechanism to move, the switch can be built as a microscopic pattern of materials and repeated across a chip.

<!-- scene: symbol -->

We now have a switch that we can control with a voltage input. To make larger circuits easier to draw, we will represent each transistor with a simple symbol, shown on the left. The next step is to connect these switches so that, together, they can calculate, remember and think. We will build towards these abilities one layer at a time, showing how each new structure makes more complex tasks possible.

## Logic

<!-- scene: not -->

To calculate with electrical signals, we first need a way to represent information. We use a low voltage to represent 0 and a high voltage to represent 1. Each of these binary digits is called a bit.

By connecting transistors, we can build circuits called logic gates that turn input bits into output bits according to a simple rule. The simplest example is the NOT gate, which flips its input. A 0 becomes a 1, and a 1 becomes a 0.

Let’s zoom out one step and connect two transistors to make our first logic gate. The lower one is the n-type switch we have just introduced. The upper one, drawn with a small circle on its gate, is its mirror image, a p-type MOSFET made with the dopants swapped. In this circuit, it turns on (lowers the energy barrier) when the input is 0, while the n-type turns on when the input is 1. Together, they make the output the opposite of the input. This is a NOT gate.

<!-- scene: nand -->

Add two more transistors and we can build a NAND gate. It takes two input bits, A and B, and produces a 1 unless both inputs are 1, in which case it produces a 0.

<!-- scene: nand-symbol -->

Let’s zoom out again and give this four-transistor circuit a symbol. The two inputs enter on the flat side, and the output exits after the small circle. It can be shown that NAND gates alone can be combined to implement any function that maps a finite set of input bits to output bits. This makes them universal building blocks. From this one simple circuit, we can build the logic for everything from a calculator to a computer running an AI model.

## Arithmetic

<!-- scene: adder -->

Let’s zoom out further and combine NAND gates into a circuit that adds. In binary, we have only two digits, 0 and 1, so adding 1 and 1 gives 10. We write down 0 and carry 1 into the next column, just as we carry digits in ordinary addition.

Our circuit handles one column at a time. It adds two input bits, aᵢ and bᵢ, along with any carry from the previous column, cᵢ. It produces the answer bit sᵢ and a carry for the next column, cᵢ₊₁. This three-input, two-output circuit is called a full adder.

<!-- scene: chain -->

Connect several full adders in a row, passing each carry cᵢ₊₁ into the next column, and we can add entire binary numbers. Here, four adders calculate 0011 + 0110 = 1001, or 3 + 6 = 9. More columns let us work with larger numbers. With addition as a building block, it is a short step to circuits that subtract and multiply, and our toolset has grown.

<!-- scene: heat -->

We have combined small groups of transistors into a circuit that adds numbers, but each calculation has a physical cost. Every calculation involves voltage flips as some of the transistors switch. These flips charge or discharge the tiny capacitances of the transistors and wires, expending energy that is dissipated as heat.

The faster we switch, the more heat we produce each second. This switching power scales with C V² f, where C is the capacitance being switched, V is the voltage swing, and f is the clock speed, which sets the pace of computation. Smaller capacitances and lower voltages reduce the energy needed, while switching less often reduces the rate at which we generate heat. Heat is a budget we will keep encountering as the counts climb.

## Memory

<!-- scene: latch -->

We can now calculate an answer, but how do we remember it? Let’s zoom back in and connect a few NAND gates so that their outputs feed back into their inputs. This circuit is called a latch. It has a data input D, a write-enable input WE, and an output Q. While WE is 1, Q becomes D. When WE becomes 0, Q holds its last value, even if D changes.

How does a loop create memory? The two gates on the right feed their outputs into each other, each reinforcing the other’s state. With writing disabled (WE = 0), this feedback holds Q at its last value for as long as power is supplied. We have added memory to our toolset.

<!-- scene: register -->

Let’s zoom out again and place four latches side by side, each holding one bit. Together, they form a four-bit register that can remember an entire binary number. By sharing a write-enable signal, all four latches can copy their inputs at D simultaneously, then hold the number while those inputs change.

<!-- scene: stored-answer -->

We can now connect our register to the four-bit adder. With write-enable at 1, the register copies the answer, 1001. Set write-enable to 0 and that answer is held. The adder can calculate something new while the register remembers the previous result. We can now both calculate and keep the answer.

<!-- scene: timing -->

As circuits become larger and more complex, timing challenges appear to show. Changing an input does not change every part of a circuit at once. The change takes time to spread, and different values settle at different moments. These delays can result in incorrect information processing as old data gets used for computation, or glitches.

We now have circuits that calculate and circuits that remember. Our next step is to combine them into a machine that follows instructions, choosing which values to use, what to calculate, and where to store each result.

## Building a computer

<!-- scene: select-values -->

Our computer follows the von Neumann model, with instructions and data stored in the same memory.

Our adder calculates with whatever values reach its inputs. To choose those values, we need another circuit called a multiplexer. It takes several inputs and passes one of them to its output, according to a selection signal at the bottom. We can build this selection circuit from the logic gates we already know. Here, each value travels through a bundle of four wires, carrying the four bits of its binary number. The idea of selectively choosing which input data to pass will be very common going forward.

<!-- scene: working-registers -->

Let’s zoom out again and give our machine several registers for its working values. For our example, we will use a small teaching computer called LC-3. It has eight general-purpose registers, named R0 to R7, each holding sixteen bits. More bit positions let us represent larger numbers using the same binary rules.

We will begin with 3 in R1 and 6 in R2. The register name identifies the slot, while its contents are the value stored there.

<!-- scene: alu -->

We can also group our adder with circuits that perform logical operations. Together, they form an arithmetic and logic unit, or ALU. Control signals select which operation it performs. The registers supply its inputs, and another register can capture the result. A path marked 16 represents sixteen parallel wires, one for each bit.

<!-- scene: addressed-memory -->

Registers hold our immediate working values. We also need memory for a larger collection of information. Each memory location has an address that lets us select it. In LC-3, each addressed location holds sixteen bits.

The address identifies the location. The bits stored there are its contents. Selection logic connects the chosen location to the wires carrying those contents.

<!-- scene: program -->

The same memory can hold both data and instructions. An instruction is a bit pattern specifying an operation and the values or locations involved. Storing a sequence of instructions gives us a program.

A register called the program counter, or PC, holds the address of the instruction to fetch next. Another register, the instruction register, or IR, holds the instruction we have fetched.

<!-- scene: control -->

The instruction bits enter decoding logic, which identifies the operation and its operands. The control unit uses this information to select paths, choose an ALU operation and enable the required register updates.

The controller also remembers which step it is performing. State stored in registers, combined with logic that determines the next step, forms a finite-state machine. Our familiar calculation and memory circuits now coordinate the work of the larger machine.

<!-- scene: execute -->

Let’s follow the instruction ADD R0, R1, R2. It tells the machine to add the contents of R1 and R2, then place the answer in R0. We have already put 3 in R1 and 6 in R2.

The machine fetches the instruction into IR and decodes its fields. Control signals select R1 and R2, direct the ALU to add, and enable R0 to capture the result. R0 now holds 9. During the fetch, PC advances to the following instruction address, ready for the machine to continue.

<!-- scene: computer -->

Let’s zoom out once more. The calculation circuits, working registers and control unit form our central processing unit, or CPU. Connected memory holds its program and data, while input and output connect it to the outside world.

We have built a machine that can follow stored instructions. Our next step is to see how a task written by a person becomes the instruction bits that direct these circuits.

<!-- footer -->

From a switch to logic, calculation, memory and now a computer, each larger structure gives us a new ability. Next, we will follow the connection from code to physical action.

The LC-3 example and the organisation of our computer diagram follow ETH Zürich’s [Digital Design and Computer Architecture course](https://safari.ethz.ch/ddca/spring2026/), particularly lecture 7 and its LC-3 diagram on slide 65. The illustration is simplified to introduce the parts one step at a time.
