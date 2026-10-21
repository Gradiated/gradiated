# How do we print a transistor onto silicon?

A transistor is a carefully arranged pattern of materials. Silicon provides a path for current, an insulator separates the gate from that path, and conductors connect the device to the rest of a circuit. How can we put all of these features in the right places?

Let’s follow a wafer through a simplified planar process and build the two transistors of a NOT gate. Each gate will sit above a channel along the silicon surface. The drawings exaggerate thicknesses and simplify shapes so we can follow the material changes. This is a teaching example rather than a complete manufacturing recipe.

<!-- scene: destination -->

## Start with a working circuit

Our destination is the NOT gate. Its input controls two transistors, one n-type and one p-type. Together, they connect the output to the high supply when the input is low, or to the low supply when the input is high.

Notice the gate above each transistor, the thin insulation beneath it and the two doped regions called source and drain. We will form these features in or on the same piece of silicon, then connect them. Body contacts hold the surrounding silicon at fixed voltages, but we omit these connections from the diagrams for simplicity.

<!-- scene: wafer -->

## Give each operation a pattern

We begin with a polished silicon wafer, a thin slice of a single crystal. Our starting silicon is lightly doped p-type. Many copies of our circuit will be made across its surface together. The red square marks a tiny part of one future chip, enlarged on the right.

<!-- scene: layout -->

A layout specifies the shapes of the regions and connections we want. These shapes become patterns on photomasks, which control where light reaches a sensitive coating on the wafer.

We need different patterns for different operations. Several can modify the same silicon, so a photomask does not necessarily correspond to a new material layer. We will keep returning to the same machines with new patterns.

<!-- scene: grow-oxide -->

## Make the first implant pattern

Our p-type wafer can provide the body of an n-type transistor. Its p-type partner needs an n-type body region, a deeper pocket called an n-well. First, we grow a thin silicon dioxide film by heating the wafer in an oxidising environment. Some silicon is consumed as the oxide grows.

This thin film can remain during implantation. With suitable energy, dopant ions pass through it and enter the silicon. The thicker photoresist we apply next will block the ions elsewhere. Being an electrical insulator does not make oxide impenetrable to accelerated atoms.

<!-- scene: coat -->

At the coater, the wafer spins while liquid photoresist spreads across it. A bake prepares the film. This temporary coating will protect the silicon that should remain p-type during the well implant.

<!-- scene: expose -->

At the lithography machine, a photomask controls where ultraviolet light reaches the resist. We use positive resist, so exposure makes the illuminated region easier to dissolve. Nothing has been removed yet. The photomask belongs to the exposure equipment and does not travel to the implanter.

<!-- scene: develop -->

Developer dissolves the exposed resist, opening the region for our n-well. The remaining resist stays on the wafer. We have made a physical protective pattern, while the thin oxide beneath it remains intact.

<!-- scene: well -->

The implanter directs n-type dopant ions towards the wafer. They pass through the resist opening and thin oxide into the silicon. The resist blocks them elsewhere. The selected silicon becomes an n-well within the original wafer, rather than a new slab added on top.

<!-- scene: strip -->

Only after implantation do we strip the remaining resist and clean the wafer. Its job is finished, but the dopants remain in the silicon. Later operations will need fresh resist and different photomask patterns.

<!-- scene: well-anneal -->

Heat treatment repairs implantation damage, activates dopants and helps establish their depth distribution. The n-well will provide the body of the p-type transistor. Implantation and heating are separate operations.

<!-- scene: isolation -->

## Open the device sites

Neighbouring devices also need insulation around them. In this simplified flow, we first grow thicker field oxide across the surface, then remove it where we want to build the devices. Growing the oxide consumes more silicon. Etching it later will not restore that silicon.

<!-- scene: isolation-coat -->

We return to the coater for a fresh resist film. This time, we are preparing to remove oxide rather than implant dopants.

<!-- scene: isolation-expose -->

A different photomask exposes the two device sites. The pattern must line up with the n-well we have already made.

<!-- scene: isolation-develop -->

Development opens the resist above those sites. Resist remains over the field oxide we want to keep.

<!-- scene: prepare-isolation -->

The etcher removes oxide through the resist openings, stopping at the silicon. The remaining resist protects the surrounding oxide. We now have openings in the permanent insulating film, not just in the resist.

<!-- scene: isolation-strip -->

We strip the resist after etching. The oxide pattern remains, surrounding the exposed device sites. Our repeated cycle is coat, expose, develop, change the selected material, then strip. The pattern and the material-changing operation depend on the feature we need.

<!-- scene: oxide -->

## Form the gates

We prepare the exposed silicon and grow a thin, high-quality gate oxide. A voltage on the gate will affect charge in the silicon through its electric field, while this insulation limits direct current through the gate.

<!-- scene: poly -->

A deposition machine adds polysilicon, silicon containing many small crystals. With appropriate doping, it can conduct and serve as the gate material. Here we show it as a conducting film.

Deposition adds material. Oxidation instead reacts with silicon already present. Neither operation defines our narrow gates yet.

<!-- scene: gate-coat -->

Fresh photoresist covers the polysilicon. We will keep resist above the gate strips so they survive the etch.

<!-- scene: gate-expose -->

The gate photomask exposes the resist around those strips. Because we use positive resist, these exposed areas will be removed during development.

<!-- scene: gate-develop -->

Development removes the exposed resist, leaving protective strips above the intended gates. The polysilicon is still a continuous film underneath.

<!-- scene: pattern-gate -->

The etcher removes unprotected polysilicon and stops at the oxide. Two narrow gates remain beneath the resist. Their position will help determine the source and drain boundaries.

<!-- scene: gate-strip -->

We strip the resist, leaving the polysilicon gates and their thin insulation. We have finished shaping the gate film, but still need to form the more heavily doped source and drain regions.

<!-- scene: n-coat -->

## Make the source and drain

We apply another resist film for an n-type implant. The two transistor types need different dopants, so we will use two separate masking cycles. No single implant should change both devices in the same way.

<!-- scene: n-expose -->

The n-type implant photomask exposes the region around the n-type transistor. Resist above the p-type transistor remains unexposed.

<!-- scene: n-develop -->

Development opens those regions. The p-type transistor remains covered by resist, while the n-type transistor’s gate is visible inside its opening.

<!-- scene: implant -->

N-type ions enter exposed silicon through the thin oxide. The gate blocks implantation into the channel immediately beneath it, while resist protects the other device. This forms heavily doped source and drain regions beside the gate, labelled `n+`.

The gate itself helps define the source and drain boundaries. This is why the process is called self-aligned.

<!-- scene: n-strip -->

We strip the n-type implant resist. The implanted regions stay in the silicon. Before introducing the opposite dopant type, we must prepare a different protective pattern.

<!-- scene: p-coat -->

A fresh resist film covers both devices again. This film will protect the regions made by the previous implant.

<!-- scene: p-expose -->

The p-type implant photomask exposes the region around the p-type transistor.

<!-- scene: p-develop -->

Development opens these regions while leaving the n-type transistor covered. We have changed the selection pattern, not the positions of the existing devices.

<!-- scene: implant-p -->

P-type ions form the p-type transistor’s source and drain, labelled `p+`. Its gate protects the channel beneath it. The resist shields the n-type transistor.

<!-- scene: p-strip -->

We remove the remaining resist. Both implant patterns have now served their purpose. The source and drain regions are changes within the silicon, not separate material blocks sitting on it.

<!-- scene: anneal -->

Controlled heating repairs crystal damage and makes the implanted dopants electrically active. This is annealing. Heating also moves dopants, so its temperature, duration and place in the sequence matter.

We now have the essential device structures. Their terminals still need electrical connections.

<!-- scene: contact-insulation -->

## Turn the devices into a circuit

We deposit insulation over the devices. This will keep unrelated conductors apart. To reach the source, drain and gate terminals, we need holes through it, defined by another photomask.

<!-- scene: contact-coat -->

Fresh resist covers the insulating film. It will protect the insulation everywhere except at the intended contact holes.

<!-- scene: contact-expose -->

The contact photomask exposes small regions above the terminals. Alignment matters, because each hole must reach the right feature below.

<!-- scene: contact-develop -->

Development opens these small regions in the resist. The insulation still covers the terminals underneath.

<!-- scene: contacts -->

The etcher removes insulation through those openings. Each hole stops at its intended terminal, either silicon or a gate conductor. The drawing exaggerates the holes so we can follow their destinations.

<!-- scene: contact-strip -->

We strip the resist after etching. The contact holes remain in the insulation, ready to receive conducting material.

<!-- scene: metal -->

Metal fills the contacts and forms a film across the surface. The drawing idealises this filling operation. We use a simplified aluminium wiring flow, in which unwanted metal is etched away after deposition. Other materials and manufacturing flows use different sequences.

The blanket film is not yet our circuit. We must separate it into individual connections.

<!-- scene: metal-coat -->

We coat the metal with fresh resist. This mask has a different job from the contact mask. It will define the wires across the surface rather than the holes through the insulation.

<!-- scene: metal-expose -->

The first-metal photomask exposes resist between the intended wires. Resist above the wires remains unexposed.

<!-- scene: metal-develop -->

Development leaves protective resist above the future connections and exposes the metal we want to remove.

<!-- scene: metal-pattern -->

The etcher removes that exposed metal, separating the remaining film into wires. The resist protects the wires until the etch is complete.

<!-- scene: metal-strip -->

We strip the resist to reveal the connections. The two gates join as input `A`, the drains join as output `Q`, and the sources connect to the low and high supplies.

<!-- scene: inverter -->

Try changing input `A`. When it is `0`, the p-type transistor connects the output to the high supply while the n-type transistor is off. When `A` is `1`, the n-type transistor connects the output to the low supply while the p-type transistor is off.

The output settles to the opposite logic value. This pairing is called complementary metal–oxide–semiconductor, or CMOS. Our physical structure now implements the NOT gate we began with. A reusable layout for a gate like this can become a standard cell in a larger design.

<!-- scene: interconnect -->

## Build above the transistors

Larger circuits need many connections, often on several levels. We deposit another insulating film over the first wires. Its surface follows some of the height differences below.

<!-- scene: planarise -->

Chemical-mechanical planarisation combines chemical action and polishing to remove excess material and flatten the surface. The polisher removes material. It does not add a new film.

<!-- scene: via-coat -->

We coat this surface with fresh resist to define a via, a connection between wiring levels. Its opening must land on the intended wire below.

<!-- scene: via-expose -->

The via photomask exposes resist above that wire. This pattern selects the vertical connection, not the route of the upper wire.

<!-- scene: via-develop -->

Development opens the resist at the via location. The insulating film below is still intact.

<!-- scene: via -->

The etcher removes insulation through the opening, stopping at the lower wire. Resist protects the surrounding surface.

<!-- scene: via-strip -->

We strip the resist. The opening now reaches the first wiring level, but needs metal before it can connect that level to the next.

<!-- scene: upper-metal -->

Metal fills the via and covers the insulating surface. As before, this is initially a continuous film that must be patterned into a wire.

<!-- scene: upper-coat -->

Fresh resist covers the new metal. We now need the upper-wire pattern, separate from the via pattern we just used.

<!-- scene: upper-expose -->

The upper-metal photomask exposes resist around the intended connection. The future wire remains protected.

<!-- scene: upper-develop -->

Development reveals the unwanted metal while leaving resist along the wire’s route.

<!-- scene: upper-metal-pattern -->

The etcher removes exposed metal, leaving the upper connection beneath the resist. The insulating film keeps it separate from unrelated wires below.

<!-- scene: upper-strip -->

We strip the resist to reveal the upper wire. Two wires can cross in a top view while remaining separate at different heights. They connect only where a via deliberately joins them.

We have repeated the same patterning cycle with different patterns and materials. Cleaning, alignment checks and inspection recur throughout real fabrication. Detailed cleaning, film recipes and additional device refinements are outside this simplified example.

<!-- scene: finish -->

## From the wafer to the outside world

Zoom out and our gate becomes one small part of a die, an individual chip on the wafer. Electrical tests help identify which dies meet the required criteria. The fraction that passes is the yield for those criteria. Dies are separated and packaged so that their connections can reach other parts of a system, then tested further.

Designers specify circuits and layouts for a chosen manufacturing process. The foundry carries out the physical operations. A process design kit supplies models and rules that help designers make suitable layouts. We will explore that relationship in another deep dive.

Our transistor emerged through repeated, aligned changes to materials. Light selected resist patterns, machines added or removed material, dopants changed the silicon, and conductors connected the result. Those same kinds of operations can build the many gates that make a computer.

<details>
<summary>Sources and further reading</summary>

- [NPTEL planar MOS fabrication sequence](https://archive.nptel.ac.in/content/storage2/courses/117101058/Slides/12.7.htm) and [CMOS inverter connections](https://archive.nptel.ac.in/content/storage2/courses/117103066/chap3/slides/slide209.htm).
- [NPTEL on lithography and selective processing](https://archive.nptel.ac.in/content/storage2/courses/117103066/chap3/slides/slide174.htm).
- [MIT Micro/Nano Processing Technology](https://ocw.mit.edu/courses/6-152j-micro-nano-processing-technology-fall-2005/pages/lecture-notes/) covers implantation, deposition and etching.
- [Applied Materials on planarisation](https://www.appliedmaterials.com/il/en/semiconductor/semiconductor-technologies/cmp.html) and [ASML on manufacturing](https://www.asml.com/en/technology/all-about-microchips/how-microchips-are-made).
- Branch Education's [manufacturing video](https://www.youtube.com/watch?v=dX9CGRZwD-w) and [transistor and CPU video](https://www.youtube.com/watch?v=_Pqfjer8-O4) provide further visual orientation. Their device examples differ from the planar process followed here.

</details>
