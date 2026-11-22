# Deep-dive ideas

This backlog collects the questions already saved in the overview plan. It is open-ended, with no required chapter assignment or publication order. Keep detailed research in the [notebook](notes.md) or a future article folder. The original dated discussion remains in the [overview plan](../articles/sand/plan.md#candidate-deeper-branches).


Current focus, agreed on 21 October 2026, is [How do we print a transistor onto silicon?](../articles/fabricating-a-transistor/plan.md). The planar fabrication outline is saved for development. Earlier suggested starting points below are retained as discussion history.

These are ideas, not created posts or assigned publication slots:

- How does a gate control current? Develop the potential-energy barrier model and its limits.
- How can imperfect voltages represent reliable bits? Explain the digital abstraction.
- How does a full adder work? Trace all three inputs, derive its outputs, then connect stages.
- How can a circuit remember? Explain stable feedback and a latch with an input/output trace.
- Why do chips use energy and get hot? Candidate destination for the contextual heat link; introduce switching energy, power, leakage, data movement, and thermal constraints, with narrower branches such as “Why does switching use energy?”
- How can hardware be programmable? Reuse LUT/FPGA material later; develop selection, configuration, state, and routing. This is no longer the proposed conclusion of the opening memory section.
- How do circuits keep time? Develop clocked storage, propagation delay, setup/hold, skew and the physical limits on coordinated updates.
- How does a stored instruction make a computer do something? Develop the planned LC-3 instruction-processing article, reusing the saved encoding and binary load example.
- How do we know a chip will work before we manufacture it? Verification deep dive requested by Aidan on 2026-10-19. Follow a small design from its specification through a testbench, simulation, assertions, formal verification and equivalence checking. Distinguish functional correctness from timing and physical sign-off, including design-rule and layout-versus-schematic checks, and distinguish pre-silicon verification from testing manufactured chips. Explain assumptions and coverage limits rather than implying that passing checks guarantees a working chip. Suggested interactive example lets the reader introduce a bug, see ordinary tests miss it, then expose it with a targeted test or property. Connect to the timing deep dive and chapter 9, How a design becomes a chip.

### Physics-led deep-dive shortlist — 2026-10-19

Saved at Aidan's request. These five candidates expand the device and energy ideas above and add semiconductor and manufacturing branches. They are planning notes, not commissioned articles or a fixed publication order.

| Candidate article | Central question and scope | Visual idea |
| --- | --- | --- |
| How does a voltage control a transistor? | How can an electric field change conduction through silicon without the gate touching the conducting channel? Explain how charge rearranges and how the gate controls conduction. | A transistor cross-section showing charge rearranging as the gate voltage changes. |
| Why does switching take time and energy? | What must physically happen when a wire changes from `0` to `1`? Connect resistance and capacitance to charging, delay and energy consumption. | Charge accumulating on capacitances, with adjustable resistance, capacitance and voltage. |
| Why does adding an impurity make silicon useful? | How do silicon's electronic structure and dopants produce mobile electrons and holes? | Move from atomic bonds to a simple energy-band picture. |
| How do we print a transistor onto silicon? | How do patterns become actual structures through lithography, deposition, etching and doping? | Build one simplified transistor layer by layer. |
| Why can't we keep shrinking transistors? | How do leakage, tunnelling, variability and heat complicate scaling? | Compare devices as their dimensions shrink. |

Suggested starting point from the discussion is **Why does switching take time and energy?**, since it develops the overview's existing timing and heating explanations. Device physics, switching physics and one transistor's manufacturing journey form a possible first group. The publication order remains open.

