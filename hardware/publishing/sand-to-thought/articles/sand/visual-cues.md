# Private scene cues

These directions were moved out of the authoring script when it became a link to the canonical website script. They remain private and are not included in either website build. Keep detailed visual decisions in [visuals.md](visuals.md).

> **Visual cue — quartz:** Rotate the line-drawn quartz cluster. This scene is fixed.

> **Visual cue — ingot:** Transform the material into the growing silicon ingot. This scene is fixed.

> **Visual cue — wafer:** Slice a wafer, turn it edge-on, and approach its cross-section. This scene is fixed.

> **Visual cue — boron:** Show the silicon cross-section with hollow circles for boron.

> **Visual cue — implant:** Implant filled phosphorus dots into two pockets.

> **Visual cue — wires:** Bring in the two contacts and the insulated central gate.

> **Visual cue — voltages:** Show 0 V on the left wire and 1 V on the right. Overlay the electron-potential-energy curve inside the silicon. The dots follow this landscape as an energy analogy.

> **Visual cue — blocked:** Show the gate at 0 V and a high energy barrier inside the silicon. The animated dots meet and retreat from the barrier.

> **Visual cue — flowing:** Lower the energy barrier, show dots following the lowered energy landscape, and illuminate the bulb. Briefly highlight the gate voltage in soft green as 0 V becomes 1 V, then fade the highlight away.

> **Visual cue — symbol:** Keep the transistor symbol on the left. On the right, show two equivalent switches with a separate gate control. At 1 V the conducting path is a straight, continuous wire. At 0 V the two ends stop at a visible gap. No mechanical lever.

> **Visual cue — switch-types:** Compare the two transistor symbols and their open/closed wire equivalents. N-type has a broken path at 0 V and a continuous one at 1 V. P-type has a continuous path at 0 V and a broken one at 1 V. Keep each control gate separate from the conducting path.

> **Visual cue — not:** Combine the complementary transistors into the NOT circuit. Raise A and Ā above their wires and place the changing digits below. Loop through A = 0 and A = 1, with the conducting path from output to the corresponding supply highlighted yellow. Fade between states and pause during scrolling.

> **Visual cue — nor:** Rearrange into two p-type switches in series above two n-type switches in parallel. Cycle through 00, 01, 10 and 11, showing both input values and the output. Highlight every complete conducting path from the output to its supply in yellow. Keep input wires unhighlighted.

> **Visual cue — nand:** Move the same four symbols into two parallel p-type switches above two series n-type switches. Cycle through 00, 01, 10 and 11, with yellow highlighting from the output through the complete conducting path to the top or bottom supply. Keep this circuit visible alongside the truth tables. As it shrinks into the NAND symbol, fade its connecting wires, highlighted routes and labels, leaving only the four transistor symbols inside.

> **Visual cue — nand-symbol:** Draw the NAND symbol around the shrinking circuit.

> **Visual cue — adder:** Place NAND symbols inside an adder; show the three inputs, two outputs, and worked digits.

> **Visual cue — chain:** Connect four addition blocks through their carry wires.

> **Visual cue — heat:** Keep the adder visible and introduce the heat marks and P ∝ C V² f.

> **Visual cue — timing:** An abstract grid of wires carries scattered 0s and 1s, with faint red and green highlights respectively. A yellow pulse begins at the top-left input and spreads across the grid along paths with different delays. Some values crossfade to their opposite digit and colour as the pulse passes. Leave the final values still after the pulse has faded. No labels, gates, clock waveform or receiving register in this overview image.

> **Visual cue — latch:** Draw the feedback paths of the gated D latch.

> **Visual cue — register:** Shrink the NAND latch into one D-latch block, then repeat it into a row of four. Retain the D, WE and Q terminals and show the four stored bits.

> **Visual cue — memory-two:** Keep the first row and add a second. Draw the shared data wires, address selection, address AND WE gates, and per-bit read AND/OR paths. Loop through reading each row, writing only the selected row, and holding it. Yellow marks the selected routes, not a bit value.

> **Visual cue — memory-array:** Retain both rows and extend the same column wiring to two more rows. Grow the decoder to four outputs and expand each read selector. Keep addresses separate from stored bits. Cycle through all four addresses and a selected write.

> **Visual cue — stored-answer:** Make room above the same sixteen latches for four full-adder blocks. Keep 0011 + 0110 = 1001 fixed. Loop through reads, writing 1001 at address 10, holding it, and reading another row. Retain the stored answer across repeated cycles.

> **Visual cue — memory-buses:** Smoothly shrink and fade the detailed array into a memory block, and merge the four parallel adder-output wires into a thick bus. Add diagonal slashes and width labels. Continue the same read/write loop with address, WE, input and output values visible.

> **Visual cue — computer-overview:** Fade the compact memory view into a simple map of the whole computer. Show a CPU containing calculation, registers and control, one memory holding instructions and data, and input/output connections. Fade the overview as we look inside the registers.

> **Visual cue — memory-width:** Recall the four-row, four-bit array. Keep its low bits and slide them apart to reveal four additional bit positions in each row. Fade in one-byte and total-capacity labels. Play once on entry and hold, replaying on re-entry.

> **Visual cue — memory-interface:** Compress individual storage cells into four wider rows. Fade the detailed wiring first as latch boxes compress into each row. Then add MAR on the address path and MDR lower on separated data paths. Label the address column. Keep WE as a distinct memory write control and defer the clock.

> **Visual cue — memory-word:** Expand eight-bit contents into two grouped bytes. Widen MDR and both data-bus width labels to 16. The two-bit address still selects only four locations.

> **Visual cue — memory-address-space:** Widen MAR and its address-bus label from 2 to 16. Replace middle rows with an ellipsis and show the last address, 65535. State the full 65,536-location range without drawing every row.

> **Visual cue — memory-access:** Separate Read and Write buttons access location 1. Animate address capture into MAR. Writes capture 9 into MDR and copy it into the selected location under WE. Reads copy the current stored value into MDR after memory responds. Hold after completion and retain writes across button presses.

> **Visual cue — working-registers:** The green memory block stays in the upper left. One sixteen-bit register expands into eight labelled rows. A faint right-hand column shows each value as sixteen binary digits grouped in fours, and fades away before selection begins. R1 holds 3, R2 holds 6, R3 holds 2 and R0 starts at 0.

> **Visual cue — select-values:** The same register bank shifts left. Two sixteen-bit selection paths lead through MUX blocks to an adder. Yellow paths and travelling copies of 3 and 6 show the selected inputs. Once they arrive, 9 emerges smoothly below the adder and holds until the loop resets. Selection signals identify R1 and R2.

> **Visual cue — alu:** The adder becomes an ALU with ADD selected. The first operation reads R1/R2 and saves 3 + 6 = 9 in R0. Every following operation reads R0/R3, adds 2 to the stored total and writes back on arrival. R0 keeps its value while the transfer labels fade between additions. Values wrap at sixteen bits; larger numbers stay clear of the wires. Leaving and returning to the scene restarts the example. The memory miniature remains visible; no control-unit content is developed.

> **Visual cue — processing-block:** A faint red frame draws around the same registers, MUXes, ALU and return path. Finish the current addition before simplifying the diagram. The red PU shrinks above the green memory miniature as the instruction appears. Neither block is labelled CPU. Introduce a small orange I/O block at the upper right and keep it alongside the shelved building blocks.

> **Visual cue — instruction:** Keep the PU and memory miniatures visible. Align ADD R0, R0, R3 with its full sixteen-bit encoding, grouped as 0001 000 000 0 00 011. Matching curly braces above and below the binary fields connect them to the comma-free instruction names and the labels for operation, destination, input registers and format bits. Faint AND/NOT and alternate register names sit above the selected fields, fading with height. Keep this introductory instruction diagram static without yellow attention pulses. Fade alternatives, bits and braces before the selected names travel to the CU.

> **Visual cue — instruction-control:** Keep the two corner miniatures and unfold an enlarged red PU view. A faint sixteen-bit encoding sits above the readable instruction. A simple CU box receives it. Thin control paths select R0/R3 and ADD, with the write control entering the horizontal centre of the top of the register bank without a WE label or number. Source fields glow during selection and input transfer, ADD during calculation, and destination R0 only during write enable. Keep the right-hand ADD label beside its ALU control input, place fast storage registers below the bank and omit the write R0 caption. Yellow data paths carry 9 and 2 through the ALU and return 11. R0 stays 9 after the result arrives, then updates to 11 only during the write-enable interval. Hold the result before fading and replaying. IR, PC, FSM and clock are deferred to fetching and sequencing.

> **Visual cue — addressed-memory:** Replace the earlier combined-machine draft. Expand memory into a readable green table with ADD R0 R0 R3 stored at decimal addresses 12288 and 12289. The third displayed location, 16384, holds data 6. Do not relabel instructions as a different storage medium. Keep a small red PU in the top-left corner. Retain the table only in this opening scene, then collapse it into a compact green block with MAR and MDR. Shrink the full PU around its centre, then slide it into the upper-left block. Expand the shelved green memory outline into the table before revealing its contents, with both outlines aligned during the crossfade. Keep orange I/O smaller and centred on the same shelf.

> **Visual cue — program:** Introduce PC alone, then copy 12288 down its yellow route into MAR. The stored bits stay still. Hold after this transfer. Keep the fetch increment for the following passage.

> **Visual cue — instruction-fetch:** Keep the MAR selection while PC advances to 12289. Copy the selected instruction into MDR, then into IR. Pause on the fetched instruction. The source memory row remains unchanged. Animate once on entry and replay on re-entry, in either scroll direction.

> **Visual cue — execute:** Move the small red PU down, then expand it beneath the rectangular blue CU. Hide unused register detail and selection circuits within the block. Show R0 = 9, R3 = 2, copies travelling to the ALU, then the returning 11. Enable the R0 write only around capture. Preserve PC = 12289, MAR = 12288 and the fetched instruction in IR.

> **Visual cue — control:** Replay two complete instruction cycles from R0 = 9, ending at 13 with PC = 12290. The FSM strip highlights fetch, decode and execute as groups of steps, not literal LC-3 states. A regular clock pulse accompanies enabled captures. Do not infer the exact LC-3 cycle count from the slowed teaching sequence. Hold after the second instruction rather than clearing R0 to loop.

> **Visual cue — computer:** Frame PC, IR and the controller in blue as CU, with the red PU alongside it inside the CPU. Frame the memory array, MAR and MDR together in green outside the CPU. Keep the combined view focused on CPU and memory without separate input/output boxes. Hold R0 = 13 and PC = 12290. Keep chapter 5 behind the existing public boundary.
