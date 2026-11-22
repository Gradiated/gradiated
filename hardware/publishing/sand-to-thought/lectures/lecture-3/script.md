# Lecture 3 — How do we manufacture a transistor?

> **Presentation website:** [Open the Lecture 3 animations](http://127.0.0.1:5182/lectures/lecture-3/). Use this diagram-only website alongside these speaking notes when giving Lecture 3 again.
>
> **For future sessions:** when Aidan asks to give Lecture 3, open this website. Check whether the local server is running; if needed, restart it using the [saved website instructions](../../../../../product/website/lectures/README.md). The presentation source is saved in the repository, so it can be reopened for later talks.


**Today, we’ll follow how a silicon wafer becomes a working circuit, by adding, shaping and modifying materials one layer at a time.**


## What are we trying to get across?

- **An extremely long process:** a chip can require hundreds to over a thousand processing steps, taking months. Our NOT gate illustrates the principles behind that much longer sequence. we have skipped loads of steps, ignored cleaning, inspection, and bundled many of the steps you will see into 1, and we still have 64 steps. 
- **A small toolbox, reused many times:** we can group the work into six jobs: **pattern, add material, remove material, modify material, clean, and inspect/measure**. Different patterns, ingredients and settings turn these recurring jobs into hundreds of individual steps. 
- **A carefully discovered and tuned route:** THIS WHOLE THING IS BASICALLY AN EXTREMELY COMPLEX RECIPE FIGURED THROUGH TRIAL AND ERROR. Temperatures, times, chemical recipes and implant energies must stay within suitable ranges — a “Goldilocks zone”. Took decades to find the best path and is still improving.
- **Reliability at scale:** the sequence must work repeatedly across a wafer and across batches. 


**Slide:** start on the title and cover card.

**Opening:** “We have seen how transistors make logic gates. How do we actually build those transistors and connect them?” 

## What are we trying to build? 

**Slide:** [The NOT gate we will build](http://127.0.0.1:5182/lectures/lecture-3/#fab-destination) — 

DRAW SIMPLE NOT GATE 

A NOT gate is one of the simplest building blocks of a computer: a tiny electronic circuit that turns a 1 into a 0, or a 0 into a 1, and works with other circuits to perform more complex tasks.

DRAW CIRCUIT DIAGRAM

explain how the not gate works by connecting to rails

important to know difference between p and n type transistor
p type n type, means materials have been switched around

Note that this is a large array of not gates, the process can be done simultaneously everywhere. 

point at physical transistor on slide. 

## Begin with a silicon wafer

**Slides:** [Begin with a silicon wafer](http://127.0.0.1:5182/lectures/lecture-3/#fab-wafer). Advance through the clean-room introduction to the enlarged wafer region.

- **The starting point:** a polished silicon wafer. We will add material, remove material and change how selected regions conduct electricity.

processing happens over whole wafer at same time, we dont have to make each transistor one by one

## Why silicon?

A chip needs more than a semiconductor that carries current well. We also need insulation, electrical contacts and hundreds of manufacturing steps that work together reliably.

WHAT RUST IS TO IRON SAND IS TO SILICON
- SAND: **Silicon gives us a particularly good insulator:** heat silicon in oxygen and we can grow silicon dioxide on its surface. This oxide stops unwanted current while allowing the gate's electric field to control the transistor. The boundary between silicon and its oxide can be made with relatively few defects, helping the transistor behave predictably. Producing equally good insulating boundaries on other semiconductors has often been harder. This was a major historical advantage.
- 1960 was turning point from germanium to silicon
- **We can manufacture many working chips together:** silicon is abundant, and we have learned to purify it and grow large single crystals with very few defects. A wafer provides space for many circuits to go through the same processing operations. Large wafers and low defect rates help reduce the cost per working chip; producing them still takes considerable effort. 
- **That early advantage has grown over decades:** engineers have refined the tools, chemicals and recipes around silicon. The process now has an enormous base of equipment, suppliers and experience. A replacement material must offer enough benefit to justify developing and integrating a different process. 

**CMOS is not unique to silicon.** Other semiconductors can make complementary transistors too. The advantage is how well silicon, its insulation and its manufacturing process work together.

**The point:** “Silicon became dominant because we could make reliable transistors with good insulation, then manufacture huge numbers of them at a practical cost. Decades of improvement strengthened that lead.”

## The machines and our small toolbox

**Slide:** [The machines](http://127.0.0.1:5182/lectures/lecture-3/#fab-layout) — point to the room map and the process circle below the contents.

- **Six broad jobs:** pattern, add, remove, modify, clean and inspect. The highlighted segment tells us which kind of work is happening now. Ive skipped cleaning and inspection
- **Keep watching the circle:** the same jobs return with new patterns and materials. Hundreds of steps come from reusing this small toolbox. 


## First, prepare the silicon


We need to make sure that we can lay both an n type and a p type transistor next to each other side by side, but because they are opposites this means one has to exist in silicon that is n doped and one has to exist in silicon that is p doped. 

n type transistor can be made already because they actually are built in a p-doped background, which we already have, the wafer is lightly doped with boron.

So we need to make something called an n-well. this is basically just a large region where we have filled it, doped it with phosphorus atoms, and we will build one of our transistors, the p-type transistor, in this pit. 


FIRST WE PREPARE THE BASE SILICON:

**Slide:** [Prepare the silicon](http://127.0.0.1:5182/lectures/lecture-3/#fab-grow-oxide) — begin with the thin screen oxide, then advance into the first resist cycle.

now the first cycle starts:

**Coat → expose → develop → process the material → strip. Repeat with a new pattern.**

- **Coat:** cover the surface with photoresist, a temporary light-sensitive film.
- **Expose:** a photomask defines where light reaches the resist. With our **positive resist**, exposure makes those areas easier to dissolve. USE WORD BURN
- **Develop — dissolve selected resist:** developer washes away the exposed resist. Openings appear; resist still protects the other areas.
- **Process through the openings:** in this first cycle, implant dopants into the silicon. Later cycles use an etcher to remove exposed oxide, polysilicon or metal; the remaining resist protects the material we want to keep.
- **Strip — remove the remaining resist:** its job is finished. The lasting pattern remains in the material underneath.

**Development opens the temporary coating. Etching changes the underlying material. Stripping clears away the coating that remains.**

- **Heat treatment:** annealing repairs implantation damage and makes dopants electrically active.

## Foundations of the NOT gate

**Slides:** [Heat the implanted well](http://127.0.0.1:5182/lectures/lecture-3/#fab-well-anneal), then [Foundations of the NOT gate](http://127.0.0.1:5182/lectures/lecture-3/#fab-isolation). Advance through the barrier pattern, oxide growth and removal of the temporary barrier.

- **Isolation:** thicker oxide helps separate neighbouring transistor sites. We use a patterned nitride barrier to control where this oxide grows, then remove that barrier.
  
- **Same toolbox:** deposition and oxide growth add material; etching removes it. The patterns determine which places change.

Now we have these sand banks between the transistors to separate them so they cant leak current and electrons between them, we want to be able to control that so we do it in the wires we will build above it later. 

## Build the gates, source and drain

**Slides:** [Lay down the gates](http://127.0.0.1:5182/lectures/lecture-3/#fab-oxide) — show the thin insulation, polysilicon deposition and full gate-patterning cycle. Continue to [Make the source and drain](http://127.0.0.1:5182/lectures/lecture-3/#fab-n-coat) for the two implant patterns and annealing.

- **Gate insulation:** grow a thin oxide over the transistor sites. It separates the gate electrode from the silicon while allowing its electric field to control the channel.
- **Gate material:** deposit conducting polysilicon. Repeat **coat → expose → develop → etch → strip**, leaving the narrow gate electrodes. This is the etching version of the cycle we first used for implantation.
- **Source and drain:** use separate resist patterns to implant the n-type and p-type regions. Protect the other transistor each time; strip the resist afterwards and anneal.
- **Self-alignment:** the gate itself blocks implantation beneath it, defining the source and drain edges beside the channel. Dopants can still spread during heating.

FIRST STEP OF MAKING SOURCE AND DRAIN IS SENDING IN THE CORRECT DOPANT TYPE, SO WE DO THIS ONE AT A TIME.

SAY SAND INSTEAD OF SILICON OXIDE.

## Connect the transistors: two more cycles

**Slides:** [Connect the transistors](http://127.0.0.1:5182/lectures/lecture-3/#fab-contact-insulation) — insulation and polishing, contact-hole cycle, then metal deposition and wire-patterning cycle. Stop at [A working NOT gate](http://127.0.0.1:5182/lectures/lecture-3/#fab-inverter) and toggle its input.

- **Cover with insulation:** deposit oxide over the devices, then polish it flat. We need electrical connections through it at selected places.
- **Contact-hole cycle:** coat → expose → develop → **etch holes through the oxide** → strip. The holes expose the terminals; they still need conducting material.
- **Add metal:** in our simplified example, metal fills the contacts and covers the surface as a continuous film.
- **Wire cycle:** coat → expose → develop → **etch away unwanted metal** → strip. Separate wires remain.
- **Complete the NOT gate:** join the gates as the input and the drains as the output. Connect the n-channel source to the low supply and the p-channel source to the high supply. Body connections hold the surrounding silicon at the appropriate supply voltages.

## Repeat upwards and across the wafer

Here we want to connect our output of our not gate to the rest of the circuit

**Slides:** [Building above the transistors](http://127.0.0.1:5182/lectures/lecture-3/#fab-interconnect) — follow the insulation, polishing, via and upper-wire cycles. Finish at [From one gate to a chip](http://127.0.0.1:5182/lectures/lecture-3/#fab-finish) with the stack of connections.

- **More wiring:** add insulation, open holes between wiring levels called vias, add metal and pattern more wires. Polish surfaces flat where needed.
- **Precision matters:** patterns must line up. An unwanted metal bridge can join two wires; a misplaced contact can miss its terminal. Cleaning, measurement and inspection recur throughout.
- **Manufacturing at scale:** we followed two transistors, but many operations treat the wafer broadly, and lithography repeats patterned exposures across it.

**Closing:** “We keep changing the pattern and the material, but reuse the same idea: protect selected places, make a controlled change, remove the temporary protection and repeat. Those changes turn silicon into a circuit.”


## Backup: what the animation skips or simplifies

- **Cleaning:** repeated wafer cleans, rinsing and drying are not animated separately. Resist stripping is shown as material removal; it does not replace all the other cleaning operations.
- **Inspection and measurement:** the room map includes an inspection station, but the sequence does not visit it. Real fabrication repeatedly checks film thickness, pattern dimensions, alignment and defects, then uses those measurements to adjust the process.
- **Supporting steps:** resist baking, detailed surface preparation and many process refinements are not separate animation steps. Chemical recipes, temperatures, treatment times and implant doses are simplified.
- **Before and after:** we begin with a prepared wafer. Crystal growth and wafer preparation, the final protective coating, electrical testing, cutting the wafer into chips and packaging are not animated.

**Reading the process circle:** coat, expose and develop are grouped as **patterning**; deposition and oxide growth as **adding**; etching, stripping and polishing as **removing**; implantation and annealing as **modifying**. These categories can overlap — oxide growth also consumes silicon. Cleaning and inspection remain faded on the circle as reminders of real fab work omitted from the animation. Introductory and finished-circuit views show **Overview**.

## Questions that may come up

1. Why do we use silicon? What makes it suitable for building transistors?
2. How can adding a tiny amount of another element change how silicon conducts electricity?
3. What is the difference between the photomask and the photoresist? Which one stays on the wafer?
4. What exactly does the light do? Does it cut the material or only change the photoresist?
5. Why are development, etching and stripping separate steps? What does each remove?
6. How does the etcher remove one material without destroying the material underneath?
7. How do successive patterns line up accurately enough? What happens if they miss?
8. Why does forming the gate first help position the source and drain? What does “self-aligned” mean?
9. Why cover the transistors with insulation, then make holes through it? How do the metal wires reach the right terminals?
10. Are we building one transistor at a time? How does this process scale to billions of transistors?

---

## Talk metadata and references

- **Created:** 29 October 2026. **Status:** working delivery notes.
- **Audience:** software engineers and salespeople; no assumed physics or advanced mathematics.
- **Our numbering:** teaching lecture 3, following [Lecture 2](../lecture-2/script.md). This is a fabrication talk, not ETH DDCA Lecture 3.
- **Based on:** [the first deep-dive article](../../articles/fabricating-a-transistor/script.md) and its [plan](../../articles/fabricating-a-transistor/plan.md).
- **Main point:** repeated patterning cycles; distinguish development, material processing and resist stripping. Implantation replaces etching in some cycles.
- **Presentation:** use the dedicated [Lecture 3 animation website](http://127.0.0.1:5182/lectures/lecture-3/). The script follows its chapter order and links to exact animation steps. **Adapted to the presentation:** 30 October 2026. References checked on 29 October 2026. Dimensions, recipes and realistic metal filling are simplified.

| Reference | Useful material |
| --- | --- |
| [Branch Education — How are Microchips Made?](https://www.youtube.com/watch?v=dX9CGRZwD-w) | The six equipment categories shown in Aidan’s screenshot. The video uses an 80-layer cake and 940 recipe steps as an analogy, then clarifies that its 80 “layers” are photomask patterns, not 80 metal wiring levels. These are example figures, not universal counts. Wording checked using a [transcript copy](https://pickscribe.com/v/dX9CGRZwD-w). |
| [TRUMPF — semiconductor manufacturing](https://www.trumpf.com/en_US/solutions/industries/semiconductor-manufacturing/) | “How is a microchip manufactured?” supports the general scale: several hundred, sometimes over a thousand steps, taking months. The count depends on the process and how steps are counted. |
| [Washington University — Fabrication of MOSFETs](https://classes.engineering.wustl.edu/cse463/Chapter_2_CSE463.pdf#page=8) | PDF page 8: one transistor; pages 9–10: CMOS process and mask patterns. Page 6 shows a patterning cycle using **negative** resist, so its exposed resist stays rather than dissolves. This talk uses positive resist. |
| [MIT 6.152J, Fall 2005 — Lecture 18: CMOS](https://ocw.mit.edu/courses/6-152j-micro-nano-processing-technology-fall-2005/57460d7d1e3ffe8e245f4f2eb3d8f845_lecture18.pdf) | Slides 10–11: transistor fabrication; 13–16: inverter and CMOS structure; 26–27: LOCOS isolation. |
| [NPTEL — fabrication sequence](https://archive.nptel.ac.in/content/storage2/courses/117101058/Slides/12.7.htm) | Written explanation of gate formation, self-alignment, contacts and wiring. |
| [UTEP Nanofabrication Facility — Oxidation Basics](https://www.utep.edu/engineering/nanomil/processes/oxidation_basics.html) | Why silicon: stable, readily grown silicon dioxide with a low-defect interface; gate insulation, isolation and surface protection. Checked 1 November 2026. |
| [Shin-Etsu — Silicon Wafers](https://www.shinetsu.co.jp/en/products/semiconductor-silicon-business/silicon-wafers/) | Why silicon: purification, large single-crystal ingots and wafers with low contamination and defect levels. Checked 1 November 2026. |
| [Royal Society of Chemistry — Silicon](https://periodic-table.rsc.org/element/14/silicon) | Silicon's natural abundance. Abundant raw material does not make semiconductor-grade purification or fabrication easy. Checked 1 November 2026. |

Detailed chemistry and comparisons with advanced processes stay in the [deep-dive notes](../../planning/notes.md).
