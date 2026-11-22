# Study recap: ETH Digital Design and Computer Architecture, Lectures 6–7

Our earlier material followed transistors → gates → arithmetic → feedback and memory → LUTs and FPGAs.

Since then, we have explored how circuits operate reliably and how those circuits form a computer that follows instructions.

## 1. Finite-state machines

An FSM stores its current state and uses that state, together with inputs, to determine its next state and outputs.

Flip-flops can store the state; combinational logic calculates the next state.

A finite number of states does not limit how long the machine can run: it can repeat forever. FSMs later reappear as controllers that coordinate instruction processing.

## 2. Timing and delay

Correct logic must produce its answer at the right time.

Delays vary with manufacturing, voltage, temperature, load, and input transitions. “Statistical delay” does not mean every switching event receives an arbitrary new random delay.

- The longest path determines how long a result can take to settle and helps limit clock speed.
- The shortest path determines how soon new data can arrive.
- Setup time requires stable data before capture.
- Hold time requires stable data after capture.

Data can arrive too late or too early. Slowing the clock generally does not fix a hold violation.

The storage element’s design and characterisation determine its setup/hold requirements. These concepts apply to latches and other capturing interfaces as well as flip-flops.

Clock skew means the clock reaches different registers at different times. Distributing a shared clock therefore costs engineering effort and timing margin.

Lower supply voltage can slow switching enough to threaten setup timing. Incorrect captures can cause wrong results, crashes, hangs, or silent data corruption.

The closing timing principles were: shorten critical paths, balance delays, and optimise common cases while preserving correctness.

## 3. Glitches

Unequal path delays can briefly produce an incorrect output during a transition.

Redundant logic can hold the output steady while other paths hand over. K-maps help identify certain hazards in simple implementations.

However, a stable simplified Boolean function does not guarantee a stable physical signal. A complicated circuit may contain paths through the changing input that briefly glitch.

We must consider the actual gates and connections. Timing design is broader than glitch prevention: even a clean transition can arrive too late.

## 4. Verification and testing

We need both functional correctness and timing correctness.

A testbench generates inputs, runs the device under test, and checks outputs. A golden model supplies expected results.

Different tools address different questions:

- Simulation checks exercised input sequences.
- Formal tools check specified properties or equivalence under assumptions.
- Synthesis maps a hardware description into implementation resources.
- Timing analysis checks paths against clock and capture requirements.
- Physical checks assess layout and manufacturing rules.

Tests can miss rare cases. Checkers and reference models can themselves be wrong. Functional simulation does not automatically establish physical timing correctness.

Offline testing happens outside normal service. Online checking happens while a system operates; it does not mean internet-connected.

After manufacture, testing can still be offline—for example, maintenance diagnostics.

## 5. The von Neumann model

The computer combines memory, a processing unit, a control unit, and input/output.

Its two key properties in the introductory model are:

1. Stored program: instructions and data share an addressable memory.
2. Sequential instruction processing: fetch, execute, and complete an instruction, then proceed to the next, unless a control-transfer instruction redirects execution.

Instructions and data are both bit patterns. Control signals determine how the processor interprets them.

The PC holds one instruction address at a time, not a list. IR holds the fetched instruction itself.

The model describes the computer’s organisation. An ALU or memory array is a component, not independently a von Neumann machine.

Contrasts include Harvard processors with separate instruction/data memories, dataflow machines driven by operand readiness, and fixed-function circuits without instruction fetching.

Modern processors can overlap instructions internally while preserving the required architectural behaviour.

## 6. Memory organisation

We separated:

- Address space: locations that can be named.
- Addressability: data represented by each addressed location.
- Installed RAM: storage physically provided.

A byte is eight bits. Word size depends on the architecture:

- Original LC-3: 16-bit words and word-addressable memory.
- MIPS32: 32-bit words and byte-addressable memory.

One hexadecimal digit represents four bits; two hex digits represent one byte.

Address width and data width are separate. A 64-bit processor need not implement 64 independent address bits.

The slide’s 48-bit x86-64 example reflects four-level address translation. Supported five-level implementations can use 57 bits.

MAR holds the address to access. MDR holds data read from memory or awaiting a write.

## 7. Processing, registers, and instructions

The ALU performs arithmetic and logical operations.

Registers provide fast temporary storage (FTS). LC-3 has eight general-purpose registers, R0–R7, each holding 16 bits. Main memory provides much more storage; dedicated registers such as PC and IR have separate roles.

A three-bit register ID selects one of eight registers. The ID is the slot’s label, not its contents.

MIPS names can be aliases: $t2 means register 10, because $t0–$t7 correspond to registers 8–15.

An instruction is a command encoded as bits. It specifies an operation and the operands or locations involved.

For ADD R0, R1, R2, R1 and R2 supply values, the ALU adds them, and R0 receives the result.

A register can be both source and destination: ADD R6, R2, R6 uses old R6, then replaces it with the answer.

## 8. ISA and instruction encoding

ISA means Instruction Set Architecture: the programmer-visible rules for instructions, encodings, registers, and behaviour.

LC-3 and MIPS have different ISAs.

An assembler translates assembly into machine-code bits according to the selected ISA.

LC-3 instructions are 16 bits. Four opcode bits give 16 possible opcode patterns; the remaining bits specify operands and other details.

There are 65,536 complete 16-bit patterns, not 65,536 different operations. Some patterns are invalid.

For ADD, bit 5 selects a register operand or an embedded immediate value. Bits 4–3 are unused and encoded as zero in the register form, but participate in the immediate form.

## 9. Instruction processing and microarchitecture

The conceptual phases are:

Fetch → Decode → Evaluate address → Fetch operands → Execute → Store result.

Instructions use the phases they need. These are not automatically six clock cycles.

During LC-3 fetch:

- MAR receives the old PC address.
- PC increments to the next address.
- Memory supplies the instruction through MDR.
- MDR’s contents are copied into IR.

The thick processor bus represents 16 parallel wires. Control signals choose which source drives it and which register captures the value.

The CPU includes both the control unit and the processing unit. The control unit coordinates; the datapath moves and computes values.

One instruction can take several clock cycles. Pipelining can produce one completion per cycle even when each instruction takes several cycles individually.

## 10. Our worked memory-load example

LDR R3, R0, #2 uses the contents of R0 as a base address.

If R0 holds 100 and memory[102] contains 30, the instruction calculates 102 and copies 30 into R3.

In binary:

R0 address:      0000 0000 0110 0100
Offset:       + 0000 0000 0000 0010
Calculated address:
                0000 0000 0110 0110

Data at that address:
                0000 0000 0001 1110

R3 receives those data bits. R0 remains unchanged.

The address is held in FTS; the source data is in main memory; the load copies that data into FTS.

In LC-3, +2 advances two word locations, not two bytes. Actual MIPS uses byte offsets; reaching the third 32-bit array element requires an offset of eight bytes.

## Blog direction

Use LC-3 instruction encoding as a worked example and slide 65 as the diagram connecting the machine’s components.

Preserve the binary load example.

Instruction processing will have its own focused blog post.

Organise explanations around three questions:

- Von Neumann model: what makes up the computer?
- ISA: what commands can software give it?
- Microarchitecture: how do particular circuits carry out those commands?