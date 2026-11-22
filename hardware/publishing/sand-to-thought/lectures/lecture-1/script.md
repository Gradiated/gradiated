# Final script — Lectures 1 and 2 in five minutes (lectures at the bottom)

Prepared 8 October 2026. These are **your two standup lessons**, drawing mainly on ETH L2 and L3.

**Preparation reminder:** We need a **HILL analogy for voltage** near the beginning, before introducing transistors. Keep voltage height distinct from electron-energy height. 

**Delivery target: 4:10, with 50 seconds spare within the five-minute limit.** Speak the **Talk** bullets; the **Draw** and **Reference** bullets are practice instructions. Move on at the printed times. Use three board areas: gates/arithmetic on the left, logic/memory in the middle, LUTs/FPGA on the right. 

## Lecture 1 — Combinational logic · 0:00–2:15

**Spoken meaning:** 

### 0:00–0:15 · Forward signals, no feedback loops

“Combinational: the output depends only on the current inputs, and at no point does a signal from any output flow back into the input. Once we start forming these loops we get an effect we call memory, and we call that sequential logic, which I will talk about later.”

- **Draw:** Write **inputs → logic → output; no feedback loops** above the left board area. 
- **Reference:** ETH L3, slide **50**. When introducing the latch below, mention that feedback inside it enables storage; **52** provides the internal diagram for questions.

### 0:15–0:50 · Transistors lower barriers; capacitors store charge

"Everything in this black box is made up of transistors, so what is a transistor? Well it is basically three metal wires lying on the surface of a plate of silicon, the silicon is full of boron atoms which snatch up electrons and so leaves this area depleted of electrons, and someone has come in and fired phosphorus atoms into the regions beneath these to metal wires to make them electron rich. Now these wires with external batteries or circuits can have their voltages altered. and what I mean by voltage is essentially you can imagine that across all the wires there are these hills where the electrons sit on, and the voltage determines the height of that hill, and electrons always want to flow down a hill like a ball, so they want to go from a high +1 voltage hill to a low 0 Volt hill. So if I set this wire on left to +1 V, and the one on the right to 0V, then electrons want to flow from left to right but cant becuase this little transistor is designed such that there is a voltgae hill right here when this middle wire is set to zero. but, when this middle wire is set to 1, the hill drops and suddenly electrons are happy to flow along this valley from left to right."

- **Reference:** Supplementary band explanation in the [preparation notes](../standup_lectures.md), using Lundstrom’s Fig. **3.3** and PMOS worked question **5**. ETH’s switch model: L2, **10–11**; capacitor-based memory: L3, **54**.

### 0:50–1:50 · Four transistors make a NAND gate, also power line

"So it is basically a switch that has no moving parts, you can control current flow by just changing the voltage here, and that turns out to be incredibly useful. In a circuit diagram we can draw these three wires like this, which means these three wires. And I will just very high level describe it but it turns out if you combine 4 of these in this way (show diagram below) you basically have a system where if the voltage inputs are both 00, you get a single 1 on the output, and for any other combination of inputs A and B you get a zero volt output. This is called a NAND gate, and its part of boolean logic where just like in coding if you have A and B true, then its 1 if both A and B are 1, and if you have A or B, then its a 1 if either A or B is one but is a zero if theyre both zero etc. And it turns out there exists some combination of loads and loads of NAND gates that can be used to create any logic function, and therefore basically any arithmetic or function from inputs to outputs that you like. "

- **Reference:** Gate symbols: ETH L2, **19**; CMOS NAND: L2, **13–16**; power: L2, **18**; NAND completeness: L3, **6**.

[ETH L2 slide 13: CMOS NOT, NAND and AND gates, with truth tables and transistor circuits.](https://safari.ethz.ch/ddca/spring2025/lib/exe/fetch.php?media=onur-ddca-2025-lecture2-combinational-logic-afterlecture.pdf#page=13)

*ETH L2, slide 13 — use the centre column for the NAND gate. [Original slide](https://safari.ethz.ch/ddca/spring2025/lib/exe/fetch.php?media=onur-ddca-2025-lecture2-combinational-logic-afterlecture.pdf#page=13).*

### 1:50–2:15 · Logic can do arithmetic - i hope its not a drastic conceptual leap

"So skipping a bit, you can imagine that a box ful of these all combines in all sorts of ways (show diagram below) can basically have the effect after some careful design that you have 3 inputs ai bi ci and 2 outputs si ci+1, and what this black box does is Si is just the 1 bit sum of ai and bi, where i is the first digit of the number we want to add together. and Just like in promamy school maths, when you do addition, if both ai and bi are 1, then you need to carry over the 1 to the nex digit and you get Si is zero, but the carry over number c is 1. Then we can plug this carry over term into the next addition black box, with the next digits ai+1 and bi+1, to continue the sum. And if you stack these boxes along you can basically form this massive addition block made up of NAND gates, which are themselves made up of 4 transistors each, and if you can add any 2 arbitrary numbers together, you can then expand that to subtraction and multiplication pretty easily and you see where you start to get arbitrary arithmetic."

- **Draw:** One **full adder** box: inputs A, B, carry-in; outputs sum, carry-out. Beside it, write **1 + 1 + 0 = 10₂**, labelling **sum = 0, carry = 1**.
- **Reference:** ETH L2, **92–95**; simplification: L3, **28–34**. L3 slide 26 too!!!!

[ETH L3 slide 26: a full adder built from logic gates in sum-of-products form, alongside its truth table.](https://safari.ethz.ch/ddca/spring2025/lib/exe/fetch.php?media=onur-ddca-2025-lecture3-sequential-logic-afterlecture.pdf#page=26)

*ETH L3, slide 26 — the logic gates inside the full-adder box. [Original slide](https://safari.ethz.ch/ddca/spring2025/lib/exe/fetch.php?media=onur-ddca-2025-lecture3-sequential-logic-afterlecture.pdf#page=26).*

## Lecture 2 — Sequential logic · 2:15–4:10

**Spoken meaning:** “Sequential: the circuit remembers, so past inputs matter too.”

### 2:15–2:35 · Add state

“Sequential logic also uses stored state: information from the past. Logic computes outputs and what to store next; storage feeds that information back. This is possible once you start having some subset of outputs loop into inputs again, and allows for many more possibilities for generating functions and programs.”

- **Draw:** **inputs → logic → outputs**, with a **storage** box underneath. Add **logic → storage** labelled “next state”, and **storage → logic** labelled “stored state”. Keep both boxes small; leave space below.
- **Reference:** ETH L3, **50**.

### 2:35–3:15 · One latch stores one bit JUST BY INTRODUCING A LOOP - latches very expensive, so many transistors, 

"So I wont go into too many details but with this combination of NAND gates here, we have a very basic 1 bit storage system where by pulsing this write enable slot on and off, we basically shift whatever is at D, so a 1 or a zero, to Q, and it stays at Q as long as power is on."

- **Draw:** One box labelled **D latch / one-bit memory**, with **D (data)** and **WE (write enable)** entering and **Q (stored bit)** leaving.
- **Note:** This D latch stores one volatile bit using static feedback, like SRAM; DRAM instead stores capacitor charge that needs refreshing.
- **Reference:** ETH L3, **60–61, 67** for D, WE and Q; **52** explains the internal feedback if asked.

[ETH L3 slide 60: the gated D latch, showing data D, write enable, and outputs Q and Q-prime.](https://safari.ethz.ch/ddca/spring2025/lib/exe/fetch.php?media=onur-ddca-2025-lecture3-sequential-logic-afterlecture.pdf#page=60)

*ETH L3, slide 60 — the circuit inside the D latch box. [Original slide](https://safari.ethz.ch/ddca/spring2025/lib/exe/fetch.php?media=onur-ddca-2025-lecture3-sequential-logic-afterlecture.pdf#page=60).*

### 3:15–3:45 · Memory families: speed, size and cost

"That was called latched memory, which is super fast... read below"

- **Latches / flip-flops:** very fast, costly; often tens of transistors/bit.
- **SRAM:** typically **6 transistors/bit**; fast, larger and costlier; no refresh.
- **DRAM:** **1 transistor + 1 capacitor/bit**; slower, denser and cheaper; needs refresh.
- **All three:** lose data without power.
- **Flash / disk / tape:** cheap bulk storage; much slower access; retain data without power.
- **Reference:** ETH L3, **53–54**.

### 3:45–4:10 · Memory can implement logic: LUTs and FPGAs

"FPGAs contain lots of small programmable lookup tables, which are again just large blocks of NAND gates but with slightly configurable combinations due to some SRAM in them. A three-input LUT takes three bits and maps it with some function we have programmed onto it into one output bit. We program the answer for each of the eight possible input combinations, so it can implement any three-input Boolean function. Connecting many LUTs through programmable wiring lets us build much larger functions."

- **Reference:** ETH L3, **83–85**; L2, **88–89**. FPGA cost is supplementary context from the preparation notes. Configuration memory: [AMD configuration guide](https://docs.amd.com/r/en-US/ug570-ultrascale-configuration/Overview).

[ETH L3 slide 85: a three-input, one-output LUT using eight configuration bits and a multiplexer to implement majority logic.](https://safari.ethz.ch/ddca/spring2025/lib/exe/fetch.php?media=onur-ddca-2025-lecture3-sequential-logic-afterlecture.pdf#page=85)

*ETH L3, slide 85 — a programmable LUT example: output 1 when at least two input bits are 1. [Original slide](https://safari.ethz.ch/ddca/spring2025/lib/exe/fetch.php?media=onur-ddca-2025-lecture3-sequential-logic-afterlecture.pdf#page=85).*

**4:10–5:00: spare time for drawing and transitions. End after the FPGA point.**

## Practice references

- [ETH L2 — Combinational Logic, after-lecture slides](https://safari.ethz.ch/ddca/spring2025/lib/exe/fetch.php?media=onur-ddca-2025-lecture2-combinational-logic-afterlecture.pdf).
- [ETH L3 — Sequential Logic, after-lecture slides](https://safari.ethz.ch/ddca/spring2025/lib/exe/fetch.php?media=onur-ddca-2025-lecture3-sequential-logic-afterlecture.pdf).
- [Full preparation notes](../standup_lectures.md) retain the band physics, SOP/PLA derivations, tri-state circuits, detailed memory wiring, and further examples for questions after the talk.

## Lecture videos (YouTube)

- [ETH L2 — Combinational Logic (21 February 2025)](https://www.youtube.com/watch?v=U-4jmbm8inw)
- [ETH L3 — Sequential Logic (27 February 2025)](https://www.youtube.com/watch?v=smHJ1W7S-2Q)
