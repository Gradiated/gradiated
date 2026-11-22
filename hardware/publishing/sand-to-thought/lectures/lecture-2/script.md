# Lecture 2 — From reliable circuits to a programmable computer

**Opening:** “We have circuits that calculate and circuits that remember. How do we make them work reliably together and follow a program?”

## Timing, delay and glitches

- **Why timing matters:** circuits take time to calculate. The correct answer must be stable when a register captures it.
- matters for design choices 

  
[L6 slide 47: glitches.](https://safari.ethz.ch/ddca/spring2026/lib/exe/fetch.php?media=onur-ddca-2026-lecture6-timing-and-verification-afterlecture.pdf)
Add the redundancy to show that you can avoid glitches but at a cost
[L6 slide 61: two registers with logic between them.](https://safari.ethz.ch/ddca/spring2026/lib/exe/fetch.php?media=onur-ddca-2026-lecture6-timing-and-verification-afterlecture.pdf)

- **Draw:** register → combinational logic → register. Both use clocked flip-flops.
- **Too fast — hold:** new data must not replace the old result immediately after the clock edge. Check the **shortest path**.
- **Too slow — setup:** the new result must settle before the next clock edge. Check the **longest path**.
- **Keep old and new values separate.** A slower clock gives more settling time, but generally does not fix a hold problem. *(L6 61, 65, 72.)*

[L6 slide 67: critical path and clock speed.](https://safari.ethz.ch/ddca/spring2026/lib/exe/fetch.php?media=onur-ddca-2026-lecture6-timing-and-verification-afterlecture.pdf)

- **Critical path:** the slowest path limits clock speed. Each cycle needs time for the logic, register delays and setup. *(L6 67.)*
- **Useful work:** too much logic makes cycles slow; too little work between registers wastes time on clocking and storing results. *(L6 67.)*
- **Design principles:** shorten the slowest path; balance stages; optimise common cases without breaking unusual ones. *(L7 8.)*
- **Clock skew:** the shared clock reaches different registers at different times. Designers must allow for this lag. *(L6 89.)

if critical path too long, design runs slowly. if critical path too short, then each cycle is limited by how complex a task it can do. 

- **Glitches:** signals take different routes and arrive at different times. The output can briefly be wrong. *(L6 47.)*
- **Redundancy:** extra gates can hold the output at 1 during the handover. This fixes some glitches, but costs space and energy and affects timing. *(L6 51.)

- Also depends on temperature

## Verification

- **Goals:** correct answers, safe timing and a layout that can be manufactured.
- **Process:** test → compare with expected results → find the fault → fix → repeat.
- **Functional verification — is the answer correct?** Simulation runs test inputs through the logic model; formal methods mathematically check rules within stated assumptions.
- **Timing verification — is the answer ready at the right time?** Check signal paths against setup and hold requirements. Detailed circuit simulation can model electrical switching delays.
- **Physical verification — is the layout correct and manufacturable?** Check that the connections match the design and that shapes meet factory rules, such as minimum wire spacing.
- **Pitfalls:** rare cases get missed; the checker can be wrong; passing logic tests does not prove safe timing. Layout checks also matter—for example, wires placed too close together.
- **Why it is hard:** huge numbers of cases; detailed simulations are slow. Testing can be the most time-consuming design stage.
- **Future chapter:** “I want to explore this deeply, especially how AI could help write tests, find missed cases and debug failures before manufacture.”

*References: L6b 4–6, 8–10, 34–38.*

## Von Neumann model

- **The next step:** we have circuits that calculate and remember. Now we organise them into a computer that follows a program.
- **The point:** A von Neumann model is a way of organising a computer so that the same hardware can perform different tasks by following a program stored in memory


[L7 slide 58: the two key properties of the von Neumann model.](https://safari.ethz.ch/ddca/spring2026/lib/exe/fetch.php?media=onur-ddca-2026-lecture7-vonneumann-isa-afterlecture.pdf)

- **Stored program:** instructions are bits stored in memory alongside data. Change the program to make the same hardware do a different job.
- **Sequential instruction processing:** in this simple model, fetch a command, carry it out, then move to the next. A jump or branch can change where we go next.
- **Main parts:** memory; processing unit; input/output; control unit. *(L7 58, 65.)*
- **Trade-off:** flexibility, but fetching instructions and moving data cost time and energy. Memory traffic can become a bottleneck.

### Other approaches and extensions

- **GPUs:** still follow stored instructions, but run many similar calculations in parallel. Useful for graphics and AI; need enough parallel work to keep the hardware busy. Parallelism alone does not make them non-von-Neumann.
- **Dataflow:** run operations when their inputs are ready. Can expose parallel work; tracking readiness and moving results add overhead.
- **Specialised arrays:** a TPU's matrix unit passes values between many arithmetic units. Efficient for matrix calculations; less flexible for unrelated tasks.
- **No universal winner:** efficiency depends on the task. Real systems combine approaches—for example, a programmable controller directing a specialised array.

*Comparison background: [CPU foundations](https://diveintosystems.org/book/C5-Arch/von.html), [Arm's mixed designs](https://developer.arm.com/community/arm-community-blogs/b/architectures-and-processors-blog/posts/caches-and-self-modifying-code), [GPU execution](https://docs.nvidia.com/cuda/archive/12.9.2/cuda-c-programming-guide/index.html#simt-architecture), [dataflow](https://csg.csail.mit.edu/pubs/memos/Memo-316/Memo-316.pdf), [TPU arrays](https://cloud.google.com/blog/products/ai-machine-learning/an-in-depth-look-at-googles-first-tensor-processing-unit-tpu). These comparisons are supplementary to ETH L7.*

## Inside LC-3: microarchitecture

**Microarchitecture** is how the hardware parts are arranged and connected to carry out instructions. The von Neumann model gives the broad organisation; this diagram shows one concrete machine. 

[L7 slide 65: the parts of the LC-3 computer.](https://safari.ethz.ch/ddca/spring2026/lib/exe/fetch.php?media=onur-ddca-2026-lecture7-vonneumann-isa-afterlecture.pdf)

[Open the full-size LC-3 diagram](https://safari.ethz.ch/ddca/spring2026/lib/exe/fetch.php?media=onur-ddca-2026-lecture7-vonneumann-isa-afterlecture.pdf).

### Memory

[L3 slide 116: a two-location, three-bit-wide memory array with read and write circuitry.](https://safari.ethz.ch/ddca/spring2026/lib/exe/fetch.php?media=onur-ddca-2026-lecture3-combinational-logic-ii-and-sequential-logic-afterlecture.pdf)

*L3 116 — “Putting it all Together”: two three-bit words, with address selection and read/write circuitry.*

- **The large store:** numbered locations hold instructions and data. An address selects a location; each LC-3 location holds 16 bits. *(L7 33.)*
- **16-, 32-, 64-bit:** usually describes the processor's working register size—2, 4 or 8 bytes. In x86-64, registers hold 64 bits, but each memory address identifies one 8-bit byte. Address width and the amount of RAM are separate.

### Processing unit and fast storage 

- **ALU:** does the calculation—LC-3 supports ADD, AND and NOT.
- **Registers:** eight small, fast working stores, **R0–R7**, each holding 16 bits. Keep intermediate answers here while doing the next step of a calculation, such as working through brackets in BIDMAS.
- **Storage hardware:** a simple register uses one D flip-flop per bit. With only a small register set, fast access can justify the extra space and energy. Size still matters. *(L7 42, 45–46, 49.)*

### Input and output

- **Connection to the outside world:** a keyboard supplies input; a display shows output. Both exchange bits with the computer. *(L7 53, 65.)*

### Control unit

- **Coordinates the work:** reads the instruction and sends signals to select registers, choose the ALU operation and move or store values. Its controller is a finite-state machine.
- **PC and IR:** the program counter holds the next instruction's address; the instruction register holds the fetched command. *(L7 65.)*

### How instructions are stored and processed

- **An instruction is one command**, encoded as a 16-bit pattern in memory. `ADD R0, R1, R2` is its readable notation: add R1 and R2; put the answer in R0.
- **Fetch → decode → carry out:** fetch the command using the PC, read what it asks for, then coordinate the hardware to do it. Normally continue at the next address; branches and jumps can redirect the PC.
- **Example:** R1 holds 3, R2 holds 6. Control selects those registers and addition; the ALU produces 9; R0 stores it for a later instruction.
- **Several steps:** an instruction can take more than one clock cycle. Keep the detailed steps and bit encoding for a later talk. *(L7 69, 73, 84–87.)*

---

## Talk metadata and references

- **Created:** 14 October 2026. **Updated:** 15 October 2026. **Status:** working notes.
- **Audience:** software engineers and salespeople; no assumed physics or advanced mathematics.
- **Course:** ETH Zürich DDCA, Onur Mutlu, **Spring 2026**, lectures **6, 6b and 7**, with the memory-array example from **L3 116**.
- **Our numbering:** this is teaching talk 2. [Talk 1](../lecture-1/script.md) combined the earlier combinational and sequential logic lessons.
- **Coverage so far:** timing and glitches; verification; the von Neumann model; LC-3 parts and a brief instruction walkthrough.
- **Images:** L3 **116**, L6 **47, 61, 67** and L7 **58** are small (**336 × 252 pixels**); the LC-3 diagram, L7 **65**, uses a separate full-size image (**1400 × 1050 pixels**). All preserve their original **4:3** proportions. L3 116 checked on 15 October 2026; earlier slide references checked on 14 October 2026.

| ETH lecture | YouTube | Official slides |
| --- | --- | --- |
| **L3 — Combinational Logic II and Sequential Logic** | — | [Slides — page 116](https://safari.ethz.ch/ddca/spring2026/lib/exe/fetch.php?media=onur-ddca-2026-lecture3-combinational-logic-ii-and-sequential-logic-afterlecture.pdf#page=116) |
| **L6 — Timing and Verification** | [Watch](https://www.youtube.com/watch?v=smY30P4inhk) | [Slides](https://safari.ethz.ch/ddca/spring2026/lib/exe/fetch.php?media=onur-ddca-2026-lecture6-timing-and-verification-afterlecture.pdf) |
| **L6b — Verification and Testing** | [Watch](https://www.youtube.com/watch?v=7FZ-A4wMXlk) | [Slides](https://safari.ethz.ch/ddca/spring2026/lib/exe/fetch.php?media=onur-ddca-2026-lecture6b-verification-and-testing.pdf) |
| **L7 — Von Neumann Model and ISAs** | [Watch](https://www.youtube.com/watch?v=fOl5MLoUzco) | [Slides](https://safari.ethz.ch/ddca/spring2026/lib/exe/fetch.php?media=onur-ddca-2026-lecture7-vonneumann-isa-afterlecture.pdf) |

**Keep this file concise.** Detailed study notes stay in [the notebook](../../../../learning/courses/chip-architecture-notebook.md); extra slide references stay in [the preparation notes](../standup_lectures.md). Instruction encoding, memory loads and the detailed instruction cycle are saved for later talks or blogs.
