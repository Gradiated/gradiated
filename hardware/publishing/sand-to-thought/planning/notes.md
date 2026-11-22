# Sand to Thought — Deep-dive notebook

Created: 2026-10-19. Last updated: 2026-10-21.

Purpose: study notes for accessible, scientifically accurate deep-dive articles across the whole guide. Physics and manufacturing are the first topics; this file is not restricted to them. ETH lecture notes remain in [the separate lecture notebook](../../../learning/courses/chip-architecture-notebook.md).

## Contents

- [Study order and prerequisites](#study-order-and-prerequisites)
- [Why does adding an impurity make silicon useful?](#silicon-and-doping)
- [How does a voltage control a transistor?](#voltage-and-transistor-control)
- [Why does switching take time and energy?](#switching-time-and-energy)
- [How do we print a transistor onto silicon?](#fabricating-a-transistor)
- [Why can’t we keep shrinking transistors?](#scaling-limits)
- [Sources and how to use them](#sources-and-how-to-use-them)
- [Continuing this notebook](#continuing-this-notebook)

## Study order and prerequisites

**Current focus, chosen by Aidan on 2026-10-19: question 4 — how do we print a transistor?** Start with fabrication and introduce device physics as needed.

**Original suggested order, retained for reference: foundations → question 3 → question 1 → question 2 → question 4 → question 5.** This is a proposed learning route, not a record of topics already mastered.

| Stage | What to understand | Why here |
| --- | --- | --- |
| Foundations | Charge, electric field, voltage, current, resistance, capacitance and energy | Gives meaning to the language used throughout |
| 3. Silicon and doping | Bonds, bands, mobile electrons and holes, donors and acceptors | Explains what charges a gate can rearrange |
| 1. Transistor control | MOS capacitor → accumulation/depletion/inversion → source, drain and gate | Connects an applied voltage to a controllable conducting path |
| 2. Switching | Charging a circuit node through a finite current; delay, energy and leakage | Explains why a transistor is not an instantaneous, free switch |
| 4. Fabrication | Repeated patterning and material changes that build the device and its connections | We can ask what physical purpose each step serves |
| 5. Scaling | What changes when dimensions shrink, and which approximations fail | Brings together device physics, circuits, manufacturing and heat |

A brief fabrication cross-section can accompany transistor study; the detailed process sequence comes later. Article publication order can differ from study order.

### Prerequisites to build as needed

- **Physics:** positive/negative charge; forces and electric fields; potential difference versus potential energy; current as charge flow; energy conservation. Learn drift and diffusion before detailed junction or MOS explanations.
- **Circuits:** distinguish a node voltage from a voltage difference; understand a closed current path, resistance and charge storage. Then introduce elementary current/voltage conservation.
- **Materials:** atoms, valence electrons, covalent bonds and a crystal lattice. Introduce allowed electron energies and bands qualitatively before detailed band diagrams.
- **Mathematics:** powers of ten, units, rearranging simple equations and reading graphs. Exponentials/logarithms become useful for charging, carrier populations and leakage. Calculus can follow when we need rates and accumulated charge; it is not an entry requirement for our first explanations.

These are tutoring prerequisites, not a claim about MIT’s formal entry requirements. We do not need to complete an entire electromagnetism or quantum mechanics course before beginning.

### First foundation: voltage is energy per charge

For a charge moving between two points, **ΔU = qΔV**. An electron has charge **q = −e**, so raising electric potential lowers that electron’s electrostatic potential energy. A voltage of one volt represents one joule per coulomb. [F1]

**Worked example:** between points at 0 V and +1 V, an electron’s electrostatic potential energy is 1 eV lower at +1 V. This is an energy comparison, not a claim that every electron in a solid immediately travels there: fields, scattering, available states and barriers matter.

**Accuracy reminder:** if a drawing uses hills that electrons roll down, its height must represent electron potential energy, not voltage. A semiconductor band diagram also needs clearly labelled axes; it is not a drawing of physical surface height.

**Understanding check — not yet answered:** if an electron goes from 0 V to +1 V, does its electrostatic potential energy rise or fall? Why?

<a id="silicon-and-doping"></a>
## Why does adding an impurity make silicon useful?

**Overview connection:** chapter 1, *From sand to a switch*. Primary subject: Physics, materials and devices.

### Study notes

- Start with silicon’s bonding picture, then connect it to valence and conduction bands. A mobile electron and a hole are two ways charge transport appears in the material. [F2]
- Suitable dopants change carrier populations: donors can supply mobile electrons; acceptors can leave mobile holes. This gives engineers control over electrical behaviour. Pure silicon is already a semiconductor; doping makes particular device structures possible and controllable. [F2]
- Study temperature, ionisation and carrier concentration before treating any simple electron-counting picture as a quantitative model.

### Questions, corrections and unresolved points

- What exactly moves when a hole moves? How does that differ from an empty physical cavity?
- **Correction to avoid:** n-type does not mean the entire material has a large net negative charge. Mobile carriers and ionised dopants must be accounted for together.
- How do isolated atomic energy levels become bands? How far into quantum mechanics does this article need to go?
- Later worked example: relate dopant concentration to average dopant spacing, with explicit assumptions.

### Article and animation ideas

Move between a bond cartoon, a carrier picture and an energy diagram of the same material. Label each as a different model. Show the fixed ionised dopant separately from the mobile carrier.

**Sources / next reading:** [F2]; MIT 6.012 Spring 2009 lecture 2 [M1].

### Starting material — 2026-10-19

**Main reading:** [MIT 6.012 Spring 2009, Lecture 2 — Semiconductor Physics I](https://ocw.mit.edu/courses/6-012-microelectronic-devices-and-circuits-spring-2009/resources/mit6_012s09_lec02/), an 18-page slide PDF. Suggested passes, using the printed slide numbers:

1. **2–6:** silicon atoms, crystal bonds, electrons and holes.
2. **7–8:** generation/recombination and intrinsic silicon.
3. **9–14:** donors, acceptors and majority/minority carriers.
4. **15–17:** charge neutrality and summary. Return to the concentration algebra after the physical picture is clear.

**Optional band-picture companion:** [OpenStax 9.5, Band Theory of Solids](https://openstax.org/books/university-physics-volume-3/pages/9-5-band-theory-of-solids). Focus on Figure 9.15 (many atomic energy levels becoming bands) and Figure 9.17 (conductors, semiconductors and insulators). The wavefunction details can wait.

**Reading accuracy note:** OpenStax 9.6, linked in [F2], currently contains an erroneous sentence identifying electrons as the majority carriers in p-type material. The correct assignment is holes as majority carriers and electrons as minority carriers; MIT slide 14 states this correctly. This does not change the earlier recommendation of its introductory hole diagrams, but use MIT for the carrier classification.

**First discussion target:** explain how an electron can move through a crystal while its atoms remain in place, and why a mobile hole is an electronic vacancy rather than a missing atom. The bond cartoon is a useful first model, not a literal picture of electrons as localised balls.

### YouTube starting route — 2026-10-19

User requested high-quality videos as an alternative starting format. Recommended, not yet recorded as watched:

- **Quick orientation:** [MIT OpenCourseWare — Tutorial: Doping](https://www.youtube.com/watch?v=k12GMjtN8aA), Joe Sullivan. A demonstration comparing intrinsic and doped silicon connects added impurities to electrical conductivity. This introduces the practical question before longer theory lectures.
- **Main lesson 1:** [MIT 3.091, Fall 2018 — 15. Semiconductors](https://www.youtube.com/watch?v=CxAkraYlBuE), Jeffrey C. Grossman. Study the band picture and semiconductor behaviour. [Official MIT page](https://ocw.mit.edu/courses/3-091-introduction-to-solid-state-chemistry-fall-2018/resources/lecture-15/).
- **Main lesson 2:** [MIT 3.091, Fall 2018 — 16. Doping](https://www.youtube.com/watch?v=Ep7mkm_T0Po), Jeffrey C. Grossman. Continue with how impurities change carriers and conductivity. [Official MIT page](https://ocw.mit.edu/courses/3-091-introduction-to-solid-state-chemistry-fall-2018/resources/lecture-16/).

The two full lectures belong to a chemistry course and assume some earlier bonding concepts; introduce those as needed. Their YouTube IDs were verified against the embeds on MIT’s own pages. They are companions to the 6.012 slide deck, not recordings of that same lecture or course. Watch for the distinction between a band gap and the much smaller energy needed to release a carrier from a shallow dopant.

<a id="voltage-and-transistor-control"></a>
## How does a voltage control a transistor?

**Overview connection:** chapter 1, *From sand to a switch*; leads into chapter 2, *From switches to logic*.

### Study notes

- Begin with a MOS capacitor: a gate, an insulating layer and semiconductor. Use it to study how an applied voltage rearranges charge without requiring conduction through the insulator as the control mechanism.
- Learning sequence: charge rearrangement → accumulation/depletion/inversion → MOSFET source-to-drain transport. Explain the channel picture and the carrier-barrier picture together.
- Keep gate-to-source voltage explicit when discussing switching. Body and drain voltages also influence real device behaviour; an absolute gate voltage alone is insufficient.

These are the mechanisms to work through using MIT’s MOS lectures, rather than a completed device derivation. [M1]

### Questions, corrections and unresolved points

- Where do channel carriers come from, and how does the gate’s field reach the semiconductor?
- **Correction to avoid:** the gate does not inject the operating channel current through an ideal insulating layer. Changing gate voltage still requires charging, and real insulators can leak.
- How does lowering an electron energy barrier differ from mechanically opening a switch?
- Separate an illustrative planar, long-channel nMOS from later FinFET/gate-all-around structures. Threshold and dimensions require an identified device/process.

### Article and animation ideas

Show one labelled cross-section alongside an electron-energy diagram. Vary gate-to-source voltage and display charge rearrangement; add drain bias separately so control and transport are distinguishable.

**Sources / next reading:** MIT 6.012 Spring 2009 lectures 6–9 [M1].

<a id="switching-time-and-energy"></a>
## Why does switching take time and energy?

**Overview connection:** chapters 2–4, especially chapter 3’s heat discussion and chapter 4’s timing bridge; later connection to power and cooling in chapter 10.

### Study notes

- Begin with charge storage: **Q = CΔV** for a constant capacitance. A voltage change requires charge to move; finite available current means that takes time. Capacitance belongs to wires and device structures, not only separately drawn capacitor components. [F3]
- Introduce a resistor–capacitor charging model and its time constant **RC**, then explain where a transistor departs from a fixed resistor model.
- Keep stored capacitor energy, energy drawn from the supply, and heat dissipated during an operation distinct. The stored energy is **½C(ΔV)²** for a linear capacitor. [F3]
- Study propagation delay, loading, switching power, short-circuit current during transitions, and leakage. The digital-circuit lectures supply the next level of analysis. [M1, M2]

### Questions, corrections and unresolved points

- Why does a larger load take longer to drive? What determines when the receiving gate recognises the new value?
- **Correction to avoid:** stored energy of ½CV² is not automatically the total supply energy per complete logic cycle. Specify the circuit and which transitions are counted before quoting a switching-energy formula.
- How much energy is used while no useful logic transition occurs? Separate leakage from other background activity.
- Later worked example: charge a stated capacitance through a stated resistance, then account for energy over charging and discharging.

### Article and animation ideas

Show a CMOS inverter charging the next gate and wire capacitance. Synchronise output voltage, current and energy graphs. Distinguish energy temporarily stored in the electric field from heat.

**Sources / next reading:** [F3]; MIT 6.012 Spring 2009 lecture 13 [M1], with Fall 2009 lectures 14–16 and supplementary delay/power notes [M2].

<a id="fabricating-a-transistor"></a>
## How do we print a transistor onto silicon?

**Overview connection:** chapter 1’s wafer introduction and chapter 9, *How a design becomes a chip*. Primary subject: Manufacturing, packaging and systems.

### Study notes

- Treat “printing” as the question to unpack: lithography defines patterns; oxidation, deposition, etching, doping and thermal treatments create or modify the physical structure.
- Follow a single illustrative planar MOSFET through a specified process sequence. At every step ask: what material changed, where, and why does the finished device need that change?
- Include isolation, gate insulation, source/drain regions, contacts and wiring. Drawing a transistor shape is not enough to connect a working circuit.

### Questions, corrections and unresolved points

- What is the difference between growing an oxide and depositing a film?
- What does photoresist do, and how does its pattern transfer into another material?
- How do implantation and annealing differ? Why can process order and later heating affect earlier structures?
- **Correction to avoid:** light does not directly print a complete transistor in one exposure. The finished structure results from multiple coordinated steps.
- No universal fabrication recipe is assumed. Select and source a concrete teaching flow before drawing a full sequence; distinguish it from a contemporary production process.

### Article and animation ideas

Keep the same cross-section throughout a layer-by-layer animation, with a persistent material legend. Distinguish a patterning step from the subsequent material change and mark simplified or omitted steps.

**Sources / next reading:** MIT 6.152J Fall 2005 syllabus and lecture index [P1, P2]. The index lists oxidation, lithography and CMOS lectures without attached notes; these gaps need supplementary authoritative material before detailed teaching.

### Fabrication first: starting videos — 2026-10-19

Aidan chose to begin here instead of silicon/doping. These were recommendations on 19 October. The update below records later viewing progress and the agreed article direction.

- **Start with [Branch Education — How are Microchips Made? CPU Manufacturing Process Steps](https://www.youtube.com/watch?v=dX9CGRZwD-w), 27:48.** A visual overview to establish the manufacturing sequence. Title, duration and video identity were checked against [the creator’s site](https://branch.education/videos). Use it for orientation; detailed process claims should be checked against technical sources.
- **Optional shorter overview: [Intel — From Sand to Silicon: The Making of a Microchip](https://www.youtube.com/watch?v=_VMYPLXnd7E), published 2020.** Manufacturer animation, linked from [Intel’s own introduction](https://www.intel.com/content/www/us/en/newsroom/news/billions-transistors-make-processor-new-video-shows-how-they-made.html). Its device/process illustrations are examples, not a universal fabrication recipe.
- **Written companion:** [ASML — Six crucial steps in semiconductor manufacturing](https://www.asml.com/en/company/stories/2021/semiconductor-manufacturing-process-steps), updated 2023. Useful terminology and overview; we will distinguish resist development from etching the underlying material when teaching the detailed steps.

### First physical picture: make a pattern, then change the material

An illustrative pattern-transfer loop:

1. Have a material layer on a silicon wafer.
2. Coat it with light-sensitive **photoresist**.
3. Expose a pattern and **develop** the resist, leaving selected areas open.
4. For an etching step, remove exposed parts of the underlying material while protected parts remain.
5. Strip the remaining resist and continue with the next operation.

This is one building block of fabrication, not the complete transistor sequence. Other operations add films, grow oxide, introduce dopants or apply thermal treatments. Repeated, aligned steps create the device and its connections. Light patterns the resist; subsequent operations change the structure. [ASML companion above; P1–P2]

**Viewing questions:** What material is being added, removed or changed? What selects where it happens? Which part of the finished transistor or wiring does that operation create?

### Planar fabrication article agreed on 21 October 2026

The first deep dive will follow a simplified planar transistor through fabrication and connect a complementary pair into the familiar CMOS NOT gate. Keep the same cross-section throughout. Explain material added above the wafer, selected material removed, and doping changes within the silicon. The layer-by-layer manufacturing story remains valid for planar devices. No FinFET scene or comparison is needed here. The planar decision supersedes the earlier suggestion to add a FinFET transition at the end.

The [dedicated article plan](../articles/fabricating-a-transistor/plan.md) saves the nine-part skeleton, scope decisions, linked schematic/layout/cross-section idea, proposed animations and technical sources. Its next step is to choose one documented planar CMOS flow and storyboard a complete patterning cycle before developing the rest.

Aidan reported watching [Branch Education's manufacturing video](https://www.youtube.com/watch?v=dX9CGRZwD-w) and found it extremely useful. He also highlighted [Branch Education's transistor and CPU video](https://www.youtube.com/watch?v=_Pqfjer8-O4) as an excellent companion. Both links are saved in the plan. Store references only, with no video downloads or copied media.

The outline and planar scope are agreed. On 21 October, Aidan also agreed a wafer journey between machines, with small reusable machine-symbol blocks collecting in the corner as in Building a computer. Revisiting equipment brings its existing symbol out into the active view and returns it afterwards. Hover shows a compact Wikipedia preview and clicking opens the relevant article in a new tab. The [machine interaction specification](../articles/fabricating-a-transistor/plan.md#machine-journey-and-reusable-symbols) records this behaviour, keyboard and touch access, proposed motion and candidate Wikipedia targets. Optional price details require a dated source before inclusion.

Detailed storyboards remain proposals. No website prose or runtime changes are authorised by this notes update. Keep the work local.

<a id="scaling-limits"></a>
## Why can’t we keep shrinking transistors?

**Overview connection:** chapters 1–3 and 9–10; links device limits to manufacturing, energy and systems.

### Study notes and investigation plan

- First derive the attraction of scaling under explicit ideal assumptions. Then examine which assumptions fail.
- Device questions: loss of gate control over a short channel, subthreshold leakage, tunnelling and variability.
- Circuit/system questions: interconnect resistance and capacitance, power density and heat removal. Separate these mechanisms instead of attributing every limit to “quantum effects”.
- Manufacturing questions: pattern fidelity, alignment, defects, variation, yield and cost. Smaller dimensions alone do not establish a better complete product.

### Questions, corrections and unresolved points

- **Framing correction:** there is no single universal size at which all progress stops. Ask which dimension, mechanism and performance target we mean.
- Why does reducing supply voltage help switching energy but complicate speed and leakage trade-offs?
- How do improved gate geometries change electrostatic control? Which problems do they leave unresolved?
- Verify any claim about current production nodes or device dimensions against dated, process-specific primary sources. Do not use a node name as a literal gate-length measurement.

### Article and animation ideas

Shrink an idealised device with assumptions visible. Then introduce gate-control loss, leakage, wire delay and heat separately. Show these as interacting constraints, not one magic wall.

**Sources / next reading:** MIT 6.012 Fall 2009 lectures 12 and 16 [M2] for foundations. Contemporary process claims remain to be researched; the historical course is not evidence for current manufacturing specifications.

## Sources and how to use them

Sources checked on 2026-10-19. The course indexes establish the reading route; individual lecture documents and figures should be examined before using a detailed derivation or making a slide-specific attribution.

- **[M1] [MIT 6.012, Spring 2009 — lecture notes](https://ocw.mit.edu/courses/6-012-microelectronic-devices-and-circuits-spring-2009/pages/lecture-notes/).** Main device-physics route: 2–3 for carriers/transport, 4–5 for junction electrostatics, 6–9 for MOS structures, 11–13 for digital circuits. Use selected material rather than requiring the entire analogue-circuits course.
- **[M2] [MIT 6.012, Fall 2009 — lecture notes](https://ocw.mit.edu/courses/6-012-microelectronic-devices-and-circuits-fall-2009/pages/lecture-notes/).** Complementary route: 9–12 for MOS and subthreshold operation; 14–16 for CMOS, delay, power and scaling. Lecture numbers differ from Spring 2009; always retain the edition.
- **[P1] [MIT 6.152J, Fall 2005 — syllabus](https://ocw.mit.edu/courses/6-152j-micro-nano-processing-technology-fall-2005/pages/syllabus/).** Processing course covering fabrication methods and their interaction; its labs include a MOS capacitor, rather than a complete contemporary processor process.
- **[P2] [MIT 6.152J, Fall 2005 — lecture notes](https://ocw.mit.edu/courses/6-152j-micro-nano-processing-technology-fall-2005/pages/lecture-notes/).** Processing references, including diffusion/implantation, deposition and etching. Some listed sessions have no linked handout.
- **[F1] [OpenStax — Energy stored in capacitors](https://openstax.org/books/college-physics-2e/pages/19-7-energy-stored-in-capacitors).** Includes the distinction between potential difference and potential-energy change, ΔU = qΔV.
- **[F2] OpenStax, University Physics Vol. 3 — [Band theory](https://openstax.org/books/university-physics-volume-3/pages/9-5-band-theory-of-solids) and [Semiconductors and doping](https://openstax.org/books/university-physics-volume-3/pages/9-6-semiconductors-and-doping).** Introductory bridge into material/carrier models.
- **[F3] OpenStax, University Physics Vol. 2 — [Capacitance](https://openstax.org/books/university-physics-volume-2/pages/8-1-capacitors-and-capacitance) and [Stored energy](https://openstax.org/books/university-physics-volume-2/pages/8-3-energy-stored-in-a-capacitor).** Basic charge–voltage and energy relationships.

Established mechanisms can be studied using these historical teaching resources. Particular materials, geometries, temperatures, voltages, dimensions and fabrication sequences require their own stated assumptions and sources. Keep current industrial claims separate from idealised teaching models.

## Continuing this notebook

- Add future deep dives by central question or potential article, linking them in the contents. Include relevant overview chapter, study notes, questions, corrections, sources, unresolved points and article/animation ideas.
- Record what has actually been discussed and distinguish it from planned investigation. Mark understanding checks unanswered until answered; do not infer mastery from inclusion here.
- Read the latest file before each edit. Preserve existing notes and user wording; explain technical corrections rather than silently rewriting unrelated passages.
- When a topic becomes unwieldy, propose moving its notes to a dedicated file. Preserve the material and retain a summary and link here as the index.
- Initial checkpoint, 2026-10-19: notebook created; route and prerequisites proposed; five topic outlines established. Voltage/energy check remains unanswered.
- Latest direction, 2026-10-19: Aidan chose fabrication as the starting topic. Next: use the manufacturing overview to study patterning and material changes; return to the saved silicon/doping resources as needed.

- Latest direction, 2026-10-21: the planar fabrication article skeleton, two Branch Education video references and animation proposals are saved in [the dedicated plan](../articles/fabricating-a-transistor/plan.md). Begin development by verifying one consistent process and storyboarding the pattern-transfer cycle.
