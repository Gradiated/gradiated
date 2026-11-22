# Standup Lectures

Whiteboard lesson preparation based on ETH Zürich DDCA. Earlier Lessons 1-2 use Spring 2025; the new five-minute L6-7 follow-up uses Spring 2026.

Updated: 2026-10-14  
Current task: prepare a five-minute follow-up from the L6-7 study recap. Last exact study checkpoint: Spring 2026 L7, slide 87. The earlier Lessons 1-2 remain preparation notes.

## Format

- Original plan: one lesson per three numbered ETH lectures. Lesson 2 now starts with sequential logic from ETH L3 at the user’s request; later bundle boundaries remain provisional. Lettered parts stay with their lecture number.
- Aim for one clear idea, three talking points, and one simple whiteboard example within two minutes.
- Each finished outline includes timed talking points, what to draw, and the exact lecture/slide reference for practice.
- Slide references use the official **after-lecture** decks, not video timestamps. Put the relevant ETH lecture and slide number beside each talking point and drawing where available; identify supplementary material separately. Slides are preparation aids; delivery uses the whiteboard.
- Companion notes: [Chip Architecture Notebook](../../../learning/courses/chip-architecture-notebook.md).

## Bundle queue

| Lesson | ETH lectures | Status |
| --- | --- | --- |
| 1 — Combinational Logic | L1–3 | L3 in progress; topics selected below, final timing pending. |
| 2 — Sequential Logic | Begins with sequential material in L3; remaining scope pending. | Started; add talking points as study progresses. |
| 3 | L7–9 | Outline after studying this bundle. |

Continue the same grouping as the course progresses.

## Lesson 1 — Combinational Logic

**Bundle:** ETH L1–3. Preparation bank for a two-minute whiteboard lesson.

**Theme:** From transistor switches to a standard recipe for logic.

### Start here: MOSFETs, energy bands, and the CMOS inverter

**Purpose:** the short script is for delivery; the explanation below preserves our band-physics discussion for practice and questions. The full preparation bank is longer than two minutes; final selection/timing is still pending.

**Say in about 30 seconds:** “A MOSFET is an electrically controlled switch. Its insulated gate changes an energy barrier: NMOS lets electrons through when its gate is sufficiently above its source; PMOS lets holes through when its gate is sufficiently below its source. In CMOS, PMOS connects the output to the positive supply and charges it up; NMOS connects it to ground and discharges it. Together they make an inverter.” *(Circuit practice: ETH L2, slides 10–16; band explanation: supplementary references below.)*

**Draw:** first sketch a source–channel–drain path with an insulated gate above the channel. Then draw the inverter: **+3 V → PMOS → output Y → NMOS → ground**, with input A connected to both gates. Add a small capacitor from Y to ground to represent the output's capacitance. Trace the two input cases below. *(ETH L2, slides 10–11, 13–16.)*

#### Reading the bands: what the lines mean

- A band diagram shows **position horizontally and electron energy vertically**. It is not the physical height of the silicon, and moving a band down does not mean moving a transistor down.
- $E_C$ is the conduction-band edge; $E_V$ is the valence-band edge. Conduction-band electrons and missing valence-band electrons, called **holes**, can carry current.
- The **Fermi level $E_F$** describes how electron states are occupied. It is not a path followed by electrons or the energy of every electron. In ordinary n-type material it lies nearer $E_C$; in p-type material nearer $E_V$.
- Both NMOS and PMOS diagrams use the **same electron-energy axis**. A peak in $E_C$ is an electron barrier; a dip in $E_V$ is a hole barrier, because hole energy runs in the opposite direction. Raising that dip reduces the hole barrier.

**Optional whiteboard bands:** draw an NMOS $E_C$ hump, then a lower hump after raising the gate. Beside it draw a PMOS $E_V$ dip, then a shallower dip after lowering the gate. Label both vertical axes “electron energy ↑”. Use “lower the carrier barrier” as the shared idea; a bridge going up/down without specifying the carrier is ambiguous. *(Supplementary: Purdue notes, Figs. 3.2–3.4; PMOS worked question 5. The ETH switch abstraction is L2, slides 10–11.)*

#### Why NMOS can have p-type silicon in the middle

| Device | Source / drain | Body beneath the gate before inversion | Gate action that turns it on |
| --- | --- | --- | --- |
| **NMOS** | n-type: electron-rich | p-type | A sufficiently positive gate relative to the source attracts electrons and repels holes, creating a thin **electron inversion channel** at the surface. Its electron-energy bands move down. |
| **PMOS** | p-type: hole-rich | n-type | A sufficiently negative gate relative to the source repels electrons and attracts holes, creating a thin **hole inversion channel**. Its electron-energy bands move up. |

The names describe the channel's carriers when on. The entire body does not change doping. The gate's electric field acts through an insulating oxide: ideally, gate current does not supply the source–drain current. These notes describe conventional enhancement-mode devices; with body tied to source, both are normally off at $V_{GS}=0$.

#### Voltage, band bending, and the Fermi-level confusion

1. **Positive voltage is attractive to electrons.** An electron has negative charge, so increasing local electrical potential lowers its potential energy: $\Delta E=-q\Delta V$, with $q>0$. That is why positive gate bias lowers NMOS channel bands.
2. **Changing a contact voltage and changing a gate voltage are different operations.** Raise a neutral source contact by +1 V: its $E_C$, $E_V$, and $E_F$ all shift down by 1 eV relative to a fixed energy reference. Their separations stay essentially unchanged, so a p-type source remains p-type. Its Fermi level does **not** move up while its bands move down.
3. **Hold source/drain fixed and vary the gate:** the gate field bends the channel bands relative to the contact Fermi levels. A positive gate also lowers the gate electrode's own Fermi level. The gate is separated from silicon by oxide, so its Fermi level need not equal the silicon's under an applied bias.
4. **Equilibrium:** the connected source–channel–drain silicon has one flat $E_F$ when in thermal equilibrium; its bands can still bend. Applying different source and drain voltages takes it out of equilibrium: use contact/quasi-Fermi levels, not a single flat equilibrium line. A biased insulated gate can have a different Fermi level even when source and drain are at the same voltage and there is no net channel current.
5. **Conduction does not require all bands to line up.** The gate must reduce the relevant injection barrier enough to allow substantial carrier flow. For net source–drain current, there must also be a driving bias. With equal source and drain voltages, opposing carrier flows balance: an available channel can be **ON with zero net current**.

**Earlier n→p diode question:** for the smooth, averaged potential of an ordinary equilibrium junction, electrical potential falls from n to p; electron potential energy and the band edges rise. The neutral regions are approximately flat. This describes the built-in junction barrier, not the microscopic binding well of an individual donor: freeing an electron from that donor is a separate ionisation step. Including individual atomic potentials would not give a smooth monotonic curve.

#### The ETH +3 V inverter: why gate = 0 V turns PMOS on

Always compare **gate to source**, not gate to ground. PMOS source is +3 V; NMOS source is 0 V. Assume 3 V exceeds the relevant threshold magnitudes. *(ETH L2, slides 13–16.)*

| Input A = both gate voltages | PMOS: $V_{GS}=V_G-V_S$ | NMOS: $V_{GS}=V_G-V_S$ | What happens to output Y |
| --- | --- | --- | --- |
| **0 V** | $0-3=-3$ V → **ON** | $0-0=0$ V → **OFF** | PMOS charges Y toward +3 V: **pull-up**. |
| **3 V** | $3-3=0$ V → **OFF** | $3-0=+3$ V → **ON** | NMOS discharges Y toward 0 V: **pull-down**. |

- **PMOS bands during charging:** with source fixed at +3 V, lowering the gate from +3 V to 0 V raises the channel bands and reduces the hole barrier. If Y initially sits at 0 V, holes flow from source toward Y. As Y rises, the drain's bands and contact Fermi level move down. At Y = +3 V the source and drain match: the PMOS remains ON, but ideal net current stops.
- **NMOS bands during discharge:** with source fixed at 0 V, raising the gate from 0 V to +3 V lowers the channel bands and electron barrier. If Y initially sits at +3 V, electrons flow from the grounded source toward Y, reducing its positive charge. As Y falls, the drain's bands and contact Fermi level move up. At Y = 0 V the NMOS remains ON, but ideal net current stops. Conventional current flows the opposite way to electrons: **Y → ground**.
- **Reference check:** PMOS with source +3 V and gate 0 V has the same gate–source bias as source 0 V and gate −3 V. To redraw the *whole* circuit with a new voltage zero, shift every terminal by the same amount, including drain and body. PMOS with **source = gate = 0 V** is a different, normally OFF case.

**Why PMOS pulls up and NMOS pulls down:** they connect the output capacitance to different voltage supplies. With PMOS source fixed at +3 V and gate at 0 V, its gate drive remains strong as Y approaches +3 V. With NMOS source fixed at 0 V and gate at +3 V, its drive remains strong as Y approaches ground. “Up/down” refers to **output voltage**, not electron energy or physical orientation. *(ETH L2, slides 13–16.)*

**Why not swap them?** With ordinary 0-to-$V_{DD}$ gate voltages, an NMOS passing a high loses gate drive as its output rises, giving roughly $V_{DD}-V_{Tn}$; a PMOS passing a low gives roughly $|V_{Tp}|$ above ground. Thus NMOS passes a strong 0, PMOS a strong 1. These are approximate threshold limits; different gate-drive arrangements can change them. *(ETH L2, slide 16; supplementary Harris, slide 19.)*

**Band-diagram practice:** [NMOS/PMOS comparison sheets](../shared/sources.md): 1 gate bias; 2 drain bias/current; 3 gate versus silicon Fermi levels; 4 source voltage shift; 5 ETH PMOS charging; 6 ETH NMOS discharge; 7 pull-up/pull-down circuit. Curves are qualitative teaching sketches, not calculated device profiles.

**Supplementary practice sources (not extra ETH slides):** [Lundstrom, *Fundamentals of Nanotransistors*](https://courses.edx.org/asset-v1%3APurdueX%2B69504x%2B1T2021%2Btype%40asset%2Bblock%40LNS_Lecture_Notes_on_Nanotransistors.final.pdf), §§3.2–3.5, Figs. 3.2–3.4 and 6.4; [Lundstrom's Unit 1 worked solutions](https://www.scribd.com/document/458605842/Unit-1-Homework-SOLUTIONS-V2), question 5, pp. 11–14, explicitly covers PMOS; [Harris, *CMOS VLSI Design*, lecture 1](https://pages.hmc.edu/harris/cmosvlsi/4e/lect/lect1.pdf), slides 14 and 19, covers complementary networks and strong/weak logic levels.

### From switches to combinational logic

**Bridge — what combinational logic means (ETH L3, slide 50):** “Combinational logic means the outputs depend only on the current inputs. It has no memory of previous inputs. Examples are an AND gate, a MUX, a decoder, or an adder. Give an adder the same two numbers and it produces the same sum, after a short propagation delay.”

**Combinational-logic whiteboard:** draw two inputs entering an adder box and one sum output; write “current inputs → output; no memory”. Practice examples: L2, slides 77–84 and 92–95; propagation delay: L2, slide 17.

**User-selected topics (2026-10-07):** the transistor, CMOS pull-up/pull-down structure, building simple gates from transistors, sum of products (SOP), canonical form, canonical SOP, decoders with memory/instruction examples, multiplexers for selecting data inputs, tri-state buffers for controllable communication, the basic FPGA/LUT principle, addition using full adders with a worked example, a PLA example demonstrating functional completeness and its cost, and logic simplification using the verified L3 slide 28 example. Keep these topics in the first lesson; condense the wording during the timing edit.

| Required talking point | Whiteboard idea | Practice reference |
| --- | --- | --- |
| **Transistor:** a voltage-controlled switch. Gate voltage relative to the source controls source–drain conduction. | Draw a transistor; label gate, source, and drain. | L2, slides 10–11. |
| **CMOS shape:** PMOS forms the pull-up network toward $V_{DD}$; NMOS forms the pull-down network toward ground. In an inverter, low input turns PMOS on; high input turns NMOS on. | Draw $V_{DD}$ at the top, PMOS, output $Y$, NMOS, then ground. Connect input $A$ to both gates; write $Y=\neg A$. | L2, slides 13–16. |
| **Transistors → gates:** trace which transistor paths conduct for each input combination, then read the output and identify the gate. | Start with NOT; draw NAND with series NMOS and parallel PMOS; add an inverter to obtain AND. | L2, slides 13–16. |
| **SOP form:** OR together AND terms. “Sum” means OR; “product” means AND. Terms may omit inputs. | Write $F(A,B,C)=AB+AC$: two AND terms feeding an OR. | L2, slides 53–55, 60–61. |
| **Canonical form:** a standard representation derived from the truth table. Choosing a canonical scheme and variable order fixes the representation; it need not be the smallest circuit. | Write “truth table → standard expression”; underline “canonical ≠ minimal”. | L2, slides 52, 56, 59–60. |
| **Canonical SOP:** OR the minterms for every output-1 row. A minterm contains every input exactly once, either plain or negated. | Expand the same example: $F=A\neg BC+AB\neg C+ABC$. Mark the rows 101, 110, 111. | L2, slides 55, 57–62. |
| **Decoder:** an input-pattern detector. A basic active-high $n$-to-$2^n$ decoder raises exactly one output for each input code. | Draw a 2-to-4 decoder: input 10 raises output 2. Label its uses: select memory location 2, or recognise an operation code. | L2, slides 77–79. |
| **Multiplexer (MUX):** select bits choose which data input is passed to the output. A 2-to-1 MUX has two data inputs and one select bit: $S=0$ gives $Y=D_0$; $S=1$ gives $Y=D_1$. | Draw two data wires entering a MUX, one output wire, and a select wire. Example: $D_0=0$, $D_1=1$, $S=1$ → $Y=1$. | L2, slides 81–84. |
| **Tri-state buffer:** enables controllable communication: drive the input value when enabled, release the output to $Z$ when disabled. Shared outputs can form a MUX. | Draw one enabled buffer, then add a second sharing its output; label enables $\neg S$ and $S$ to make a 2-to-1 MUX. | L3, slides 17, 20–21; short outline below. |
| **FPGA / LUT:** a field-programmable gate array uses many small lookup tables to implement programmable logic. Each LUT stores truth-table output bits; the input bits select one through a MUX. An FPGA also has storage and programmable connections. | Draw four stored bits 0, 0, 0, 1 feeding a 4-to-1 MUX; inputs $A,B$ select the result of AND. Changing the stored bits changes the function. | L2, slides 88–89; L3, slides 83–84. FPGA qualification: AMD references below. |
| **Addition / full adder:** each bit column adds $A$, $B$, and carry-in, producing a sum bit and carry-out. Connect carries between columns to add whole numbers. | Draw one three-input/two-output full-adder box; link four boxes by their carry wires. Trace $1011_2+1001_2=10100_2$ from right to left. | L2, slides 40, 92–95; worked example on 94. |
| **PLA / any Boolean function:** form AND terms from plain/inverted inputs, then OR the terms for each output. With sufficient hardware, this realises any finite Boolean truth table, though not necessarily efficiently. | Reuse the full adder: draw the AND-term bank feeding separate sum/carry OR gates. Trace 110; show term 111 feeding both outputs. | L2, slides 98–100, 104; L3, slide 6. |
| **Logic simplification:** preserve the function while making its implementation simpler. Balance ease of design/verification with area, speed, and power; gate count alone does not decide the best design. | Write the expression from L3 slide 28, reduce it to $A+B$, then draw one OR gate. Add $AB+A\neg B=A$ to illustrate the uniting theorem. | L3, slides 28–34; Boolean laws in L2, 43–49. |

**Key distinction:** every canonical SOP is an SOP; an SOP is canonical only when each product term is a minterm. For example, $AB+AC$ is SOP but not canonical over inputs $A,B,C$; its three-minterm expansion above is canonical SOP.

**CMOS wording:** “P pulls up; N pulls down” describes the output voltage and supply connections in these static CMOS gates. The top/bottom drawing is a schematic convention, not physical stacking or transistor movement.

### Transistors → simple gates: practice notes

**Method:** choose the input bits → mark conducting transistors → trace a complete path from the output to supply or ground → record the output in a truth table. Series paths need **all** switches on; parallel paths need **at least one** branch on. *(L2, slides 13–16.)*

| Gate | Transistor arrangement to draw | Explain the output |
| --- | --- | --- |
| **NOT (2 transistors)** | One PMOS from supply to output; one NMOS from output to ground. Input $A$ controls both. | $A=0$: PMOS conducts, $Y=1$. $A=1$: NMOS conducts, $Y=0$. Thus $Y=\neg A$. |
| **NAND (4 transistors)** | Two PMOS in parallel above the output; two NMOS in series below it. Each input controls one PMOS and one NMOS. | Both inputs must be 1 to complete the pull-down path. Otherwise, a PMOS pulls up. Thus $Y=\neg(AB)$. |
| **AND (6 transistors in this construction)** | Connect the NAND output to a NOT gate. | Invert NAND's result: $Y=\neg\neg(AB)=AB$. |

**Delivery cue — immediately after drawing the transistor NAND, before turning it into AND:** “This is a basic building block for everything we will build later. NAND is universal: we can combine NAND gates to build any combinational logic, and with feedback we can also build memory.” Point back to the four transistors as you say it. *(NAND circuit: ETH L2, slides 13–16; logical completeness: ETH L3, slide 6; NAND-based storage: L3, slide 56.)*

For the short talk, use NOT as the first example, NAND to explain series/parallel connections, and one NAND → NOT arrow for AND. Analyse settled inputs; switching takes a finite time.

### Decoder: practice notes

A **decoder** turns a binary input code into a selection signal. For a basic active-high 2-to-4 decoder, exactly one of $D_0,D_1,D_2,D_3$ is 1 after the inputs settle; the others are 0. This is called **one-hot** output. *(L2, slides 77–78.)*

| Input $AB$ | Output that is 1 |
| --- | --- |
| 00 | $D_0$ |
| 01 | $D_1$ |
| 10 | $D_2$ |
| 11 | $D_3$ |

- **Connection to canonical SOP:** each output detects one minterm; for example, $D_2=A\neg B$ detects 10. *(L2, 55, 78.)*
- **Memory example:** in a four-location memory, address 10 activates selection line 2. Read/write circuitry accesses that selected location. *(L2, 79; L3, 76–77.)*
- **Instruction example:** the **opcode** is the instruction's operation code. In an invented example, 01 means ADD and 10 means MULTIPLY; decoding activates the corresponding control signal, and arithmetic circuitry performs the operation. Real instruction encodings may require several fields to identify the operation. *(Application: L2, 79; example codes are illustrative.)*

**Whiteboard takeaway:** a bit pattern becomes a specific selection — which memory location, or which operation.

### Tri-state buffer: main points and whiteboard

| What to say | What to draw | L3 slide |
| --- | --- | --- |
| **Enabled:** output follows input. **Disabled:** output is $Z$ (high impedance, no active drive). | A triangle with input $D$, output $Y$, and enable $EN$. Beside it: $EN=1\Rightarrow Y=D$; $EN=0\Rightarrow Y=Z$. | 17 |
| **Purpose: controllable communication.** Enable signals choose who drives a shared wire; at most one driver is enabled at a time. Multiple devices can listen. | Add a second buffer feeding the same output wire; label the enables and circle the active driver. | 20 |
| **This can make a MUX (multiplexer).** Select one input by enabling only its buffer. | Reuse the drawing: inputs $D_0,D_1$; enables $\neg S,S$. Write $S=0\Rightarrow Y=D_0$ and $S=1\Rightarrow Y=D_1$. | 21 |

### FPGA / LUT: basic principle

**Say:** “Much of an FPGA’s programmable logic is built from small lookup tables stored in memory: each table stores a truth table, and its inputs select the answer. By changing those tables and their connections, we can build different logic circuits.” *(ETH L2, 88–89; L3, 83–84.)*

- **Any function — within the available size:** a single-output LUT with $k$ inputs stores $2^k$ output bits and can implement **any Boolean function of those inputs**. Larger or multiple-output functions use several LUTs, subject to the FPGA’s available resources.
- **Example:** for input order 00, 01, 10, 11, store 0, 0, 0, 1 to implement AND; store 0, 1, 1, 0 to implement XOR. Same lookup hardware, different configured function. *(LUT principle: L2, 88–89; L3, 83.)*
- **Connection to the memory-read drawing:** the logic inputs act like an address selecting a stored output bit through a MUX. When a LUT is configured as logic, these table bits normally stay fixed while its inputs change. *(Memory selection: L3, 69–72; LUT: 83.)*
- **FPGA is more than LUTs:** programmable connections join the blocks, and flip-flops hold changing circuit state. Devices also include input/output circuitry and often dedicated memory and arithmetic blocks. LUTs implement combinational functions; state storage enables sequential circuits. See the AMD references below.

**Why useful, but costly — one line:** “FPGAs let us change the hardware without manufacturing a new chip, but that flexibility needs extra memory and switching circuitry, so each device typically costs more than a purpose-built chip at high production volumes.” *(Programmability: ETH L3, 84; cost comparison is supplementary.)*

**Practice clarification:** think **extra transistors and wiring for LUT/configuration memory, multiplexers, and programmable connections**, rather than simply “more NAND gates”. An ASIC is a chip designed for a particular application: it can omit much of that flexibility. FPGAs avoid the large upfront cost of making a custom chip, so they can be cheaper overall for prototypes or smaller production runs. [Area trade-off: Kuon and Rose](https://www.eecg.toronto.edu/~jayar/pubs/kuon/kuontcad06.pdf); [component cost versus total development cost: Intel/Altera](https://cdrdv2-public.intel.com/691452/wp-01199-next-generation-fpgas.pdf). The older study illustrates the trade-off; no historical numerical ratio is being claimed for current devices.

**Whiteboard:** draw four stored bits feeding a 4-to-1 MUX, with A and B as its select inputs; label it “2-input LUT”. Change the stored bits from AND’s truth table to XOR’s. *(ETH L2, 88–89; L3, 83–84.)*

### Addition and full adders: practice notes

1. **Explain the carry:** binary columns have weights 1, 2, 4, 8, … . $1+1=10_2$: write 0 and carry 1 left. *(L2, 92.)*
2. **Draw the full adder:** inputs $A,B,C_{in}$; outputs $S,C_{out}$. Sum is 1 for an odd number of input 1s; carry is 1 for at least two input 1s. For $1+1+1$, both outputs are 1. *(L2, 40, 92–93.)*
3. **Connect the columns:** carry-out feeds the next adder's carry-in; start with carry-in 0. This is a ripple-carry adder. *(L2, 94–95.)*
4. **Trace the example below:** point to the inputs, write the sum bit, and pass the carry left at each step. *(L2, 94.)*

**Equations for practice:** $S=A\oplus B\oplus C_{in}$; $C_{out}=(A\land B)\lor(A\land C_{in})\lor(B\land C_{in})$.

**Worked example: $1011_2+1001_2$ (11 + 9).** Start at the rightmost column with carry-in 0.

```text
   1011
 + 1001
 ------
  10100
```

| Column (right to left) | Input bits + carry-in (arithmetic) | Sum bit | Carry to next column |
| --- | --- | --- | --- |
| 0: ones | 1 + 1 + 0 = 2 | 0 | 1 |
| 1: twos | 1 + 0 + 1 = 2 | 0 | 1 |
| 2: fours | 0 + 0 + 1 = 1 | 1 | 0 |
| 3: eights | 1 + 1 + 0 = 2 | 0 | 1 |

Read the sum bits from left to right: **0100**. Put the final carry **1** in front: **10100₂ = 20**. Retaining that carry gives the full five-bit unsigned result.

**Whiteboard takeaway:** repeat the same one-bit circuit, passing the carry from column to column.

### PLA: practice example and closing idea

*(L2, slides 98–100 and 104; L3, slide 6.)*

A **programmable logic array (PLA)** implements sum-of-products logic: an AND stage forms product terms, then an OR stage combines selected terms for each output. A general PLA can configure both stages' connections.

**Important qualification:** we need both plain and inverted inputs, such as $A$ and $\neg A$; NOT gates provide the inverted versions. **AND, OR, and NOT together** can implement any finite Boolean function. AND and OR alone cannot implement functions such as NOT.

**Example: implement the full adder as a PLA.** Let $C=C_{in}$. Each AND term below detects exactly one input pattern. A 1 in an output column means connect that term to that output's OR gate; 0 means leave it disconnected.

| Input $ABC$ | AND term (minterm) | Connect to sum $S$ | Connect to carry $C_{out}$ |
| --- | --- | --- | --- |
| 000 | $m_0=(\neg A)(\neg B)(\neg C)$ | 0 | 0 |
| 001 | $m_1=(\neg A)(\neg B)C$ | 1 | 0 |
| 010 | $m_2=(\neg A)B(\neg C)$ | 1 | 0 |
| 011 | $m_3=(\neg A)BC$ | 0 | 1 |
| 100 | $m_4=A(\neg B)(\neg C)$ | 1 | 0 |
| 101 | $m_5=A(\neg B)C$ | 0 | 1 |
| 110 | $m_6=AB(\neg C)$ | 0 | 1 |
| 111 | $m_7=ABC$ | 1 | 1 |

$$
S=m_1\lor m_2\lor m_4\lor m_7,\qquad
C_{out}=m_3\lor m_5\lor m_6\lor m_7
$$

- **Trace 110:** only $m_6$ is 1. It feeds the carry OR gate, so $S=0$, $C_{out}=1$: $1+1+0=10_2$.
- **Shared term:** $m_7$ feeds both OR gates; input 111 produces $S=1$, $C_{out}=1$. The unused $m_0$ can be omitted.

**Why this works for any Boolean function:** take its truth table, make an AND term for each output-1 row, then OR those terms. Repeat for each output, sharing terms where useful. A sufficiently large PLA can therefore implement any chosen combinational input/output mapping.

**Why it may be inefficient:** an $n$-input truth table has $2^n$ rows, so the canonical construction can require exponentially many terms and connections. Here, carry uses four three-input minterms, but simplifies to $AB+AC+BC$ (Boolean $+$ means OR); sum can use two XOR gates. PLAs can also simplify and share terms: the construction guarantees the function, not minimum area, delay, or energy.

**Whiteboard sequence:** input literals → AND terms → two OR gates → sum and carry. Mark connections with dots, as in L2 slide 104.

**Closing line:** “Any finite Boolean truth table can become AND–OR logic with inverted inputs available; simplification determines how much hardware we need.”

### Logic simplification: main points and whiteboard

**Talking point:** “One goal of circuit design is to simplify the logic while preserving its behaviour. We want a circuit that is easy to design, implement, and verify; the fewest gates is not the only goal. The design must also meet area, speed, and power requirements.”

**L3 slide 28 — checked and correct:** here $+$ means OR, juxtaposition means AND, and $\neg$ means NOT.

$$
\begin{aligned}
F&=(\neg A)(A+B)+(B+AA)(A+\neg B)\\
 &= (\neg A)B+(A+B)(A+\neg B)\\
 &= (\neg A)B+A+B\neg B\\
 &= (\neg A)B+A\\
 &= A+B.
\end{aligned}
$$

**Check:** original and simplified expressions both give 0, 1, 1, 1 for inputs 00, 01, 10, 11.

**Whiteboard:** write the original expression → $(\neg A)B+A$ → $A+B$; finish with a single two-input OR gate. Briefly demonstrate $AB+A\neg B=A$ beside it.

**Name the main rules briefly:**

| Tool / theorem | Useful rule |
| --- | --- |
| Idempotence, identity, complement | $AA=A$; $A+0=A$; $A\neg A=0$; $A+\neg A=1$. |
| Distributivity / factoring | $A(B+C)=AB+AC$; $(A+B)(A+C)=A+BC$. |
| Absorption | $A+AB=A$; useful related rule: $A+(\neg A)B=A+B$. |
| Uniting theorem | $AB+A\neg B=A$: combine terms differing in just one input. |
| De Morgan's laws | $\neg(AB)=\neg A+\neg B$; $\neg(A+B)=(\neg A)(\neg B)$. |

**Ways to simplify:** rewrite/factor Boolean expressions; use Karnaugh maps to group compatible truth-table cases; exploit irrelevant inputs or specification-permitted don’t-cares; use synthesis tools to automate simplification and map it to available hardware. Check that the truth table is preserved for every required input. *(L2, 43–51; L3, 28–34. K-maps are signposted for self-study.)*

**Priority circuit (one-line example):** Once the highest-priority request is active, lower-priority inputs cannot change the winner, so their redundant truth-table cases can be grouped into one condition. *(L3, slides 31–32.)*

**Arithmetic connection:** these rules simplify the Boolean circuits inside adders and other arithmetic units, preserving the numerical operation. For example, the full-adder carry simplifies from four canonical minterms to $AB+AC+BC$.

Flip-flops and registers (L3, 108–111) now belong to Lesson 2 — Sequential Logic. This preparation bank contains the reference detail; the final delivery outline will target two minutes.

## Lesson 2 — Sequential Logic

**Status:** now discussing **FSM state encoding in ETH L5**. This is the second standup lesson, not ETH Lecture 2. The material below is a preparation bank; the condensed delivery script is in [final_script.md](README.md#historical-script-reference).

**Opening whiteboard — ETH L3, slide 50:** draw this feedback loop first. The arrows below are labelled to explain the roles shown on the slide.

```text
              +-----------------------+
Inputs ------>|  Combinational logic  |------> Outputs
              +-----------------------+
                 ^                 |
                 | stored state    | next state
                 |                 v
                 +----[ Storage ]--+
```

**Say in 15–20 seconds:** “Combinational logic calculates from the current inputs. Add storage, and it can also use information from the past. The logic calculates outputs and what to store next; the stored state feeds back into the logic. Together these form a sequential circuit.” *(ETH L3, slide 50; state terminology: slides 87–88.)*

**Draw in this order:** input → logic → output; storage underneath; logic → storage labelled “next state”; storage → logic labelled “stored state”. Put an outline around logic and storage and label it “sequential circuit”. A clock is introduced with the flip-flop example below; this general diagram does not require every sequential circuit to be clocked.

### First memory: two NOT gates with feedback — ETH L3, slides 52–53

**Say:** “Take two NOT gates and connect each output to the other's input. If one side is 1, the other must be 0, which reinforces the original 1. The opposite arrangement also works. Those two stable states let the circuit remember one bit while powered.” *(L3, slide 52.)*

**Whiteboard:** draw two inverter symbols, label their outputs $Q$ and $\overline Q$, and cross-connect each output to the other input. The same loop can be drawn unfolded:

```text
     +-->[ NOT ]--> Qbar -->[ NOT ]--> Q --+
     |                                     |
     +-------------------------------------+
```

| Stored bit Q | Other node Qbar | Trace around the loop |
| --- | --- | --- |
| 0 | 1 | 0 → NOT → 1 → NOT → 0: self-consistent. |
| 1 | 0 | 1 → NOT → 0 → NOT → 1: also self-consistent. |

- **Why memory appears:** each gate is combinational, but closing the feedback loop makes the overall circuit a storage element. Two inverters in an ordinary open chain just copy their input; they do not remember it. The two complementary nodes hold **one bit**, not two independent bits. *(L3, 50, 52.)*
- **What is missing:** a controlled way to write the desired state. Power-up does not guarantee which bit will be stored. Latches add write controls; the SRAM cell on slide 53 adds access transistors. *(L3, 52–53; R–S latch follows on 55–56.)*
- **Bridge to SRAM:** two CMOS inverters use four transistors; add two access transistors, controlled by a **wordline**, to connect the cell to its two **bitlines**. This gives the conventional **six-transistor (6T) SRAM cell**. For now, just add two switches to the drawing and label wordline “select” and bitlines “read/write data”. *(L3, 53–54; two-transistor inverter: L2, 13.)*

**Practice note on slide 52:** metastability is an unstable analogue condition near intermediate voltage, not a useful third stored value or necessarily a repeated 0/1 oscillation. Leave the timing detail for later. [Supplementary explanation: MIT, bistable storage](https://ocw.mit.edu/courses/6-004-computation-structures-spring-2017/f423c43074131fc9a9dfd98db8969922_z3DEmSG8kPk.pdf).

### Storage overview before the details — ETH L3, slide 54

**RAM = random-access memory:** an address selects a location directly; “random” does not mean random data. The two main RAM cell families here are **SRAM** and **DRAM**. Slide 54 also places them alongside smaller logic storage and larger persistent storage.

| Kind | How it stores information / usual role | Pros | Cons | Practice reference |
| --- | --- | --- | --- | --- |
| **Latches / flip-flops** | Controlled bit-storage circuits; used for state and small registers. A latch is level-sensitive; a flip-flop captures on an edge. | Very fast; many bits can be available in parallel. | High area/cost per bit, so unsuitable for large bulk memories; volatile. Circuit size depends on the design. | L3, 54; details later: 56, 60–61, 103–111. |
| **SRAM — static RAM** | A feedback circuit holds each bit; typically **6 transistors** per cell. Common in caches and small on-chip memories. | Fast access; no periodic refresh while powered. | Larger cells and higher cost per bit than DRAM; still consumes power and loses data when power is removed. | L3, 53–54. |
| **DRAM — dynamic RAM** | Charge on a capacitor; typically **1 transistor + 1 capacitor** per cell. Common for main memory. | Small cells: high capacity and lower cost per bit. | Higher access latency than SRAM; charge leaks, requiring refresh. Reading disturbs the stored charge, so the value must be restored. Volatile; specialised capacitor fabrication and more complex control. | L3, 54; read/refresh clarification below. |
| **Flash / disk / tape — wider context, not the SRAM/DRAM families** | Persistent storage for files and backups; these use different physical mechanisms. | Retain information without power; inexpensive capacity. | Generally much slower access than working memory. Flash has erase/write constraints and finite write endurance; disks have mechanical delays; tape requires sequential positioning. | L3, 54; mechanism details are supplementary. |

**Two distinctions worth saying:**

- **Static ≠ permanent:** SRAM holds its state without periodic refresh **while powered**. Both SRAM and DRAM are volatile.
- **DRAM refresh versus read restoration:** leakage requires periodic refresh even when nobody reads the data. A read also disturbs the cell and is followed by restoration. Both are handled by memory circuitry/control, not an application manually rewriting every value. *(Clarifies L3, 54; [MIT memory notes](https://ocw.mit.edu/courses/6-004-computation-structures-spring-2017/pages/c14/c14s1/), SRAM/DRAM sections.)*

**Say in about 20 seconds:** “Storage trades speed against capacity and cost. Latches and flip-flops hold small amounts of immediately needed state. SRAM is fast but takes more space per bit. DRAM packs more bits into less space, but needs refresh and more time to access. Flash, disks and tape keep data without power, at much slower access speeds.” *(L3, slide 54.)*

**Whiteboard:** write **latches/flip-flops → SRAM → DRAM → persistent storage**; underneath, “generally more capacity / lower cost per bit; higher access latency”. Beside SRAM draw the inverter loop; beside DRAM draw one switch and one capacitor. Circle SRAM and DRAM as the RAM comparison. This is a broad design trade-off, not a precise ranking of every product. *(L3, slides 53–54.)*

### Draw a latch and call it “one-bit memory” — ETH L3, slides 60–61, 67

```text
       +----------------+
D ---->|  1-bit memory  |----> Q
WE --->|    D latch     |
       +----------------+
```

**Call this box “one-bit memory”.** D = data input; WE = write enable; Q = stored-bit output.

**Say — writing and holding:** “To write a bit, put it on D and set WE to 1: Q follows D (**D → Q**). Set WE back to 0 and the latch holds that bit, even if D changes.” *(L3, 60–61; memory symbol: 67.)*

**Quick example:** D = 1, WE = 1 → Q becomes 1; set WE = 0, then change D to 0 → Q stays 1. A latch is open for the whole time WE is high; it is not an edge-triggered flip-flop.

### How to read memory — redraw ETH L3, slide 69

**Draw six of those boxes:** two rows, three bits per row. There are **two addresses**, **three bits per word**, and **six stored bits** in total. One address bit A selects a whole row. *(L3, 67–69.)*

[Whiteboard reconstruction of ETH L3 slide 69: two rows of three memory cells, selected with AND gates and combined with one OR gate per column.](https://safari.ethz.ch/ddca/spring2025/lib/exe/fetch.php?media=onur-ddca-2025-lecture3-sequential-logic-afterlecture.pdf#page=69)

[Scalable diagram for practice](https://safari.ethz.ch/ddca/spring2025/lib/exe/fetch.php?media=onur-ddca-2025-lecture3-sequential-logic-afterlecture.pdf#page=69). Same read-selection structure as slide 69; the stored values and explanatory labels are added examples. Write wiring is omitted, as in the slide.

**Whiteboard drawing order:**

1. Draw **two rows × three memory boxes**. Label the rows address 0 and address 1; columns bit 2, bit 1, bit 0.
2. Put an **AND gate after each Q output**: six AND gates altogether.
3. Draw A = Addr[0] at the left. Use **NOT A** to enable all three AND gates in row 0; use **A** for all three in row 1. These horizontal row-select wires are labelled **wordlines** on the slide.
4. For each column, feed the two AND outputs into **one OR gate**. Label the three read outputs **D[2], D[1], D[0]**, matching the slide. Where wires cross, only a junction dot means they connect. *(L3, 69; decoder labelled on 70, combined MUX function on 71.)*

**Say:** “The address enables one row. The other row's AND gates output zero. Each OR gate therefore passes the selected row's bit. The three columns together give us the selected three-bit word.” *(L3, 69–71.)*

**Trace the example drawn above:**

| Address A | Enabled row | Read output D[2:0] |
| --- | --- | --- |
| 0 | Row 0 stores 101 | 101 |
| 1 | Row 1 stores 011 | 011 |

**One-column check:** $D[k]=(\neg A\land Q_{0,k})\lor(A\land Q_{1,k})$: a **2-to-1 MUX** for each bit, sharing the same address/select signal. *(L3, 69–72.)*

**Keep the roles clear:** hold the latches' **WE = 0** during this read, so they keep their data. The address selects which stored Q values reach the output; it does not write the latches. Also, slide 69's **D[2:0] names the read output**, whereas **D on the one-bit latch names its write input**. Memory write wiring comes later on slides 73–75.

### Later examples — preview until covered

| Talking point | What to draw on the whiteboard | Practice reference |
| --- | --- | --- |
| **State means memory:** stored information summarises the relevant past. A sequential circuit combines storage with combinational logic. | Draw a storage box feeding a logic box, with a return arrow carrying the next state. | L3, slides 50, 87–88. |
| **A clocked example:** a rising-edge D flip-flop stores one bit; at the rising edge it captures D, then holds Q between edges. Several flip-flops form a register. | Draw a register with D, Q, and a clock input; mark one rising edge. | L3, slides 108, 111. |
| **Counter example:** a register remembers the count; an adder calculates count + 1; each rising clock edge stores the new count. | Draw register Q → “+1” → register D, with a clock arrow. Starting from 0, trace 0 → 1 → 2 → 3. | Illustrative example using L3, slides 50, 108, 111; addition from L2, slides 92–95. |

### FSM state encoding — from stored bits to named states

**Practice reference:** ETH L5, slide **61**, as identified in your viewing session. This slide number has not yet been matched to the official 2025 deck.

- **Flip-flop reminder:** one flip-flop stores **one bit**. A rising-edge **D flip-flop** copies D to Q at the rising clock edge, then holds Q between edges. Unlike a latch, it does not follow D throughout the enabled period. *(ETH L3, slides 108, 111.)*
- **Say:** “A finite-state machine, or FSM, remembers which state it is in. Combinational logic uses that state and the inputs to calculate the next state; flip-flops store it at the clock edge. State encoding assigns each named state a bit pattern.”
- **Binary versus one-hot:** binary uses combinations of bits; one-hot dedicates one bit to each state, with exactly one bit set in normal operation.

**Draw this four-state example:**

| State | Binary | One-hot |
| --- | --- | --- |
| A | 00 | 0001 |
| B | 01 | 0010 |
| C | 10 | 0100 |
| D | 11 | 1000 |

- **Say and label:** “Each column of bits needs one flip-flop: binary needs **2**, one-hot needs **4**. The two binary bits together identify one current state.”
- **Why this is the minimum:** $n$ flip-flops provide $2^n$ different patterns. For $S$ states, binary needs $\lceil\log_2 S\rceil$ flip-flops, rounded up. Three flip-flops can represent eight states.
- **Trade-off:** binary minimises state-storage flip-flops; one-hot can simplify the combinational logic for detecting states and choosing the next state. Fewest flip-flops does not necessarily mean the smallest or fastest whole circuit.

**Takeaway:** “Combinational logic calculates; sequential logic remembers as well.”

## Reusable two-minute outline

| Time | Talking point to prepare | Whiteboard / reference to record |
| --- | --- | --- |
| 0:00–0:15 | State the question and central idea. | One title; lecture and slide number. |
| 0:15–0:45 | Explain the mechanism from familiar building blocks. | One diagram; lecture and slide number. |
| 0:45–1:25 | Trace one concrete example. | Annotate the diagram; lecture and slide number. |
| 1:25–1:50 | Connect it to the next abstraction or a design trade-off. | One added arrow/label; lecture and slide number. |
| 1:50–2:00 | End with the single takeaway. | Point back to the diagram. |

## Verified practice sources

- [L2: Combinational Logic — official after-lecture slides](https://safari.ethz.ch/ddca/spring2025/lib/exe/fetch.php?media=onur-ddca-2025-lecture2-combinational-logic-afterlecture.pdf), 21 February 2025. Taught material ends at slide 104; marker on 105.
- [L3: Sequential Logic — official after-lecture slides](https://safari.ethz.ch/ddca/spring2025/lib/exe/fetch.php?media=onur-ddca-2025-lecture3-sequential-logic-afterlecture.pdf), 27 February 2025. Taught material ends at slide 112; marker on 113.
- [ETH course schedule](https://safari.ethz.ch/ddca/spring2025/doku.php?id=schedule). Sources checked 2026-10-07; videos not watched.

- FPGA clarification: AMD 7-series [logic-block overview](https://docs.amd.com/r/en-US/ug474_7Series_CLB/CLB-Overview) and [programmable interconnect](https://docs.amd.com/r/en-US/ug474_7Series_CLB/Interconnect-Resources), checked 2026-10-07. Supplementary explanation, not an additional ETH slide reference.

## Five-minute follow-up: Lectures 6-7 - slide inspiration bank

**Requested:** 2026-10-14. Audience: software engineers and salespeople; retain a concrete, accessible explanation. These are preparation references for a five-minute follow-up, separate from the earlier two-minute Lessons 1 and 2.

**Edition:** ETH DDCA **Spring 2026**, official after-lecture decks. Printed slide numbers match the checked PDF pages. All selected slides were rendered and inspected visually. Images linked below are saved locally.

**User's selected anchors:** L6 **47, 51, 67**; L7 **8, 65, 58**. The table supplies two references for each section of the study recap, plus the blog throughline; repeated references connect related topics.

| Recap section | First slide | Second slide |
| --- | --- | --- |
| 1. Finite-state machines | [L7 slide 65](https://safari.ethz.ch/ddca/spring2026/lib/exe/fetch.php?media=onur-ddca-2026-lecture7-vonneumann-isa-afterlecture.pdf) - FSM inside the machine | [L7 slide 111](https://safari.ethz.ch/ddca/spring2026/lib/exe/fetch.php?media=onur-ddca-2026-lecture7-vonneumann-isa-afterlecture.pdf) - Controller states (supplementary) |
| 2. Timing and delay | [L6 slide 67](https://safari.ethz.ch/ddca/spring2026/lib/exe/fetch.php?media=onur-ddca-2026-lecture6-timing-and-verification-afterlecture.pdf) - Critical path and clock speed | [L7 slide 8](https://safari.ethz.ch/ddca/spring2026/lib/exe/fetch.php?media=onur-ddca-2026-lecture7-vonneumann-isa-afterlecture.pdf) - Timing-design principles |
| 3. Glitches | [L6 slide 47](https://safari.ethz.ch/ddca/spring2026/lib/exe/fetch.php?media=onur-ddca-2026-lecture6-timing-and-verification-afterlecture.pdf) - Unequal paths create a pulse | [L6 slide 51](https://safari.ethz.ch/ddca/spring2026/lib/exe/fetch.php?media=onur-ddca-2026-lecture6-timing-and-verification-afterlecture.pdf) - A redundant path holds the output |
| 4. Verification/testing | [L6b slide 4](https://safari.ethz.ch/ddca/spring2026/lib/exe/fetch.php?media=onur-ddca-2026-lecture6b-verification-and-testing.pdf) - Functional and timing correctness | [L6b slide 9](https://safari.ethz.ch/ddca/spring2026/lib/exe/fetch.php?media=onur-ddca-2026-lecture6b-verification-and-testing.pdf) - Testbench structure |
| 5. Von Neumann model | [L7 slide 58](https://safari.ethz.ch/ddca/spring2026/lib/exe/fetch.php?media=onur-ddca-2026-lecture7-vonneumann-isa-afterlecture.pdf) - Two key properties | [L7 slide 65](https://safari.ethz.ch/ddca/spring2026/lib/exe/fetch.php?media=onur-ddca-2026-lecture7-vonneumann-isa-afterlecture.pdf) - The connected LC-3 machine |
| 6. Memory organisation | [L7 slide 33](https://safari.ethz.ch/ddca/spring2026/lib/exe/fetch.php?media=onur-ddca-2026-lecture7-vonneumann-isa-afterlecture.pdf) - Addresses, bytes, and words | [L7 slide 40](https://safari.ethz.ch/ddca/spring2026/lib/exe/fetch.php?media=onur-ddca-2026-lecture7-vonneumann-isa-afterlecture.pdf) - MAR/MDR: reads and writes |
| 7. ALU, registers, and instructions | [L7 slide 42](https://safari.ethz.ch/ddca/spring2026/lib/exe/fetch.php?media=onur-ddca-2026-lecture7-vonneumann-isa-afterlecture.pdf) - Computation in the ALU | [L7 slide 46](https://safari.ethz.ch/ddca/spring2026/lib/exe/fetch.php?media=onur-ddca-2026-lecture7-vonneumann-isa-afterlecture.pdf) - Register file and fast storage |
| 8. ISA and instruction encoding | [L7 slide 69](https://safari.ethz.ch/ddca/spring2026/lib/exe/fetch.php?media=onur-ddca-2026-lecture7-vonneumann-isa-afterlecture.pdf) - Opcode and operands | [L7 slide 73](https://safari.ethz.ch/ddca/spring2026/lib/exe/fetch.php?media=onur-ddca-2026-lecture7-vonneumann-isa-afterlecture.pdf) - ADD: assembly to instruction bits |
| 9. Instruction processing | [L7 slide 84](https://safari.ethz.ch/ddca/spring2026/lib/exe/fetch.php?media=onur-ddca-2026-lecture7-vonneumann-isa-afterlecture.pdf) - The six conceptual phases | [L7 slide 87](https://safari.ethz.ch/ddca/spring2026/lib/exe/fetch.php?media=onur-ddca-2026-lecture7-vonneumann-isa-afterlecture.pdf) - Fetch through the hardware |
| 10. Worked memory-load example | [L7 slide 79](https://safari.ethz.ch/ddca/spring2026/lib/exe/fetch.php?media=onur-ddca-2026-lecture7-vonneumann-isa-afterlecture.pdf) - Base + offset (use the LC-3 part) | [L7 slide 94](https://safari.ethz.ch/ddca/spring2026/lib/exe/fetch.php?media=onur-ddca-2026-lecture7-vonneumann-isa-afterlecture.pdf) - Address-calculation datapath |
| Blog throughline | [L7 slide 65](https://safari.ethz.ch/ddca/spring2026/lib/exe/fetch.php?media=onur-ddca-2026-lecture7-vonneumann-isa-afterlecture.pdf) - Connect the building blocks | [L7 slide 73](https://safari.ethz.ch/ddca/spring2026/lib/exe/fetch.php?media=onur-ddca-2026-lecture7-vonneumann-isa-afterlecture.pdf) - Make one instruction concrete |

### Proposed five-minute route using the six selected anchors

**Central thread:** circuits must produce usable answers at the right time; memory and control let the same computing hardware follow a stored program.

| Time | Reference | Speaking/drawing cue |
| --- | --- | --- |
| 0:00-0:20 | Recall the earlier adder/register lesson | “We can calculate and remember an answer. Now we need reliable timing and a way to choose the next calculation.” |
| 0:20-0:55 | L6 47 | Trace the fast and slow paths. One input change can briefly make the output wrong. |
| 0:55-1:25 | L6 51 | Point to the added green path: it holds the output steady while the other paths hand over. Explain the mechanism without deriving the K-map. |
| 1:25-2:00 | L6 67 | The slowest path sets how soon the next answer can safely be captured. Data must be ready before the clock edge and remain stable around capture. Keep the equation as background. |
| 2:00-2:20 | L7 8 | Three design ideas: shorten the bottleneck, balance delays, and optimise common cases. |
| 2:20-3:00 | L7 58 | Commands are stored in memory alongside data. PC identifies the instruction address; the simple model processes instructions in sequence, with jumps able to redirect it. |
| 3:00-4:40 | L7 65 | Identify memory, registers/FTS, ALU, control, and I/O. Illustrate ADD: register values 3 and 6 reach the ALU; the result 9 is stored in a register under control signals. Name PC and IR only as needed. |
| 4:40-5:00 | Return to the machine picture | “The program supplies commands; control coordinates the circuits; registers keep the values; timing makes their updates reliable.” |

The twenty-two topic references form an inspiration bank. The route above selects six slides; the detailed ISA/encoding, load, and instruction-cycle examples can support subsequent talks or questions. This is a proposed outline, not a replacement for the user's teaching-script wording.

### Source distinctions for preparation

- L7 **111** is supplementary material after the lecture coverage boundary (marker 107; further-slides marker 109).
- L7 **79** temporarily assumes word-addressable MIPS. Use its LC-3 example here; actual MIPS byte addressing is explained on slide 80.
- L6 **51** adds **not-A AND C**, a direct path independent of changing B with A/C steady. Do not claim every algebraically equivalent implementation is automatically glitch-free.
- L6b **4** groups tool examples under “simulation”, but formal verification is a distinct method. L6b **9** assumes a correct golden design; in practice the checker/reference must also be checked.
- L7 **33** gives a 48-bit x86-64 example; use the notebook's qualification before treating it as a universal limit.
- Slide 65 is detailed: for a short talk, use it as a map and point only to the parts being discussed.

**Official sources:**

- [L6: Timing and Verification](https://safari.ethz.ch/ddca/spring2026/lib/exe/fetch.php?media=onur-ddca-2026-lecture6-timing-and-verification-afterlecture.pdf).
- [L6b: Verification and Testing](https://safari.ethz.ch/ddca/spring2026/lib/exe/fetch.php?media=onur-ddca-2026-lecture6b-verification-and-testing.pdf).
- [L7: Von Neumann Model and Instruction Set Architectures](https://safari.ethz.ch/ddca/spring2026/lib/exe/fetch.php?media=onur-ddca-2026-lecture7-vonneumann-isa-afterlecture.pdf).

