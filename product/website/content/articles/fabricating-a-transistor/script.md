# How do we print a transistor onto silicon?

A microchip is built on a small piece of silicon cut from a wafer. Transistors are formed just below and on its surface. Many are grouped into reusable building blocks called standard cells, such as NOT gates, NAND gates and flip-flops. These cells combine into larger circuits that calculate, remember and control. Layers of metal wires above the transistors connect nearby cells and distant parts of the chip.

Here, we will follow a silicon wafer through the main steps of building the two transistors of a NOT gate, also called an inverter. We use a simplified planar design, where the conducting channel runs along a flat silicon surface beneath each transistor’s gate electrode, between its source and drain connections. The structures are simplified and exaggerated to make operation clear and changes visible.

<!-- scene: destination -->

## Printing a NOT gate with two transistors and metal wire

Our target structure is a NOT gate, a circuit whose output voltage is the opposite of its input. Inside it, two transistors each have a gate electrode connected to the same input. One transistor is n-type and the other p-type. Together, they connect the output to the high voltage supply (+1 V) when the input is low (0 V), or to the low supply (0 V) when the input is high (+1 V).

One transistor is made of the narrow gate electrode, the source and drain on either side of it, and the conducting channel between them flowing from doped regions of the wafer. We will form these features in or on the same piece of silicon, then connect them to each other and other parts of the chip. {{please improve this paragraph, make it sound clearer and nicer}}

<!-- scene: wafer -->

## Begin with a silicon wafer

Let's begin with a polished silicon wafer, a thin slice out of a large, single crystal {{mention that it is an element and mention atomic number and please polish this section}}. For now, {{apart from some sparse dopants to make it slightly conductive}}, it is a continuous crystal {{use a better word than crystal here to avoid repetition}} with no transistors or wires.

<!-- scene: clean-room --> {{I think the clean room figure should be white everywhere inside it, to make it look clean}}

Let's go inside Gradiated's clean room, where filtered air and protective clothing help keep particles off the wafer, which can spoil the structures we are trying to make.

<!-- scene: operator -->

Normally all steps in a clean room are performed entirely by robots, guided by rails on the ceiling. However in this case, our intern is undergoing initiations and enters wearing a Gradiated merch protective coverall.

<!-- scene: hand-off -->

The intern is handed our wafer.

<!-- scene: magnify -->

Let's zoom into one small chunk of the wafer. Here we will watch the two transistors take shape. {{This next bit need to fit better with the previous 2 sentences, it is a bit abrupt. Please make it clearer - it is important to introduce what n type and p type means, please explain how they work and examples of dopants}} Doping means adding small quantities of selected elements, called dopants, to control how silicon conducts electricity. In n-type silicon, current is carried mainly by electrons. In p-type silicon, it is carried mainly by holes, missing electrons that behave as mobile positive charges. Our starting wafer is lightly doped p-type.

<!-- scene: layout -->

## The machines

{{we no longer need the dotted line mask region in this section's figure}}

A semiconductor fab clean room {{Is that the best way of calling it?}} contains often {{hundreds? thousands?}} of machines to preform various tasks on the surface of the silicon. Here we have simplified the clean room to the twelve main processes we will need to supply the best possible intuition for building transistors and gates.

In order to make our NOT gate, our intern will have to perform {{is it 43 steps to the firt NOT gate?}} steps by visiting {{43?}} machines, altering layer after layer of the chip.

<!-- scene: grow-oxide -->

## Two different environments for two adjacent transistors

We need an n-type and a p-type transistor side-by-side for our NOT gate. The n-type transistor forms a conductive electron-carrying channel between two small n-doped pockets in a p-type silicon background "body", while its p-type partner forms a hole-carrying channel between p-doped pockets in an n-type body. Since our wafer is already p-type, we automatically have the correct body for an n-type transistor. However since we need a p-type transistor next to our n-type, we must first create a deeper n-type "n-well". {{I changed this last part alot - can you make it sound more fluid/eloquent? dont change it too much please.}}

We do this by ion implantation, accelerating electrically charged n-type dopant atoms (such as phosphorus) into the silicon. First, we grow a thin silicon dioxide film by heating the wafer in oxygen. Some silicon is consumed as the oxide grows.

This oxide helps protect the silicon from contamination during implantation. As the electrically charged ions are moving very quickly, they punch through the oxide and into the silicon. The thicker photoresist we apply next will stop them where we want to keep the original doping.

{{after the oxide is finished, can you add a label and a dotted line saying something like "target n-well region"}}

<!-- scene: coat -->

The intern now goes to the coater, where the wafer spins as we spread liquid photoresist into a thin film. This temporary film will protect the silicon that should remain p-type during the n-well implantion.

<!-- scene: expose -->

Next, we will imprint the pattern of the n-well. At the lithography machine, a photomask controls where ultraviolet light reaches the resist. We use positive resist, so exposure makes the illuminated region easier to dissolve. Nothing has been removed yet. The photomask belongs to the exposure equipment and does not travel to the implanter.

<!-- scene: develop -->

Developer, a chemical solution, dissolves the exposed resist, opening the region for our n-well. The remaining resist stays on the wafer. We have made a physical protective pattern, while the thin oxide beneath it remains intact.

<!-- scene: well -->

The implanter directs ions of an n-type dopant towards the wafer. They pass through the resist opening and thin oxide into the silicon. The resist blocks them elsewhere. Inside the opening, the added atoms will make the silicon n-type after heat treatment. We are changing the existing crystal.

<!-- scene: strip -->

Only after implantation do we strip the remaining resist and clean the wafer. Its job is finished, but the dopants remain in the silicon. Later operations will need fresh resist and different photomask patterns.

<!-- scene: well-anneal -->

Annealing heats the wafer to repair damage from implantation and move dopant atoms into positions in the crystal where they can provide the mobile electrons or holes that carry current. This makes the dopants electrically active. Heating also spreads the dopants through the silicon, helping establish the n-well’s depth. The well now provides the body of the p-type transistor.

<!-- scene: isolation -->

## Open the device sites

Thicker insulation around the device sites helps keep neighbouring circuits electrically separate. This is called field oxide. In our simplified flow, we grow it across the surface, then remove it where we want to build the devices. Growing the oxide consumes more silicon. Etching it later will not restore that silicon.

<!-- scene: isolation-coat -->

We return to the coater for a fresh resist film. This time, we are preparing to remove oxide rather than implant dopants.

<!-- scene: isolation-expose -->

A different photomask exposes the two device sites. The pattern must line up with the n-well we have already made.

<!-- scene: isolation-develop -->

Development opens the resist above those sites. Resist remains over the field oxide we want to keep.

<!-- scene: prepare-isolation -->

Etching removes exposed material using chemical reactions, sometimes assisted by energetic particles. Here, we choose conditions that remove oxide much faster than silicon, allowing us to stop at the silicon surface. The resist protects the surrounding oxide. We now have openings in the permanent insulating film, not just in the resist.

<!-- scene: isolation-strip -->

We strip the resist after etching. The oxide pattern remains, surrounding the exposed device sites. Our repeated cycle is coat, expose, develop, change the selected material, then strip. The pattern and the material-changing operation depend on the feature we need.

<!-- scene: oxide -->

## Form the gates

We prepare the exposed silicon and grow a thin, high-quality gate oxide. Its thinness lets the gate’s electric field strongly influence charge just beneath it. Changing the voltage between gate and source will control whether a conducting channel forms between source and drain. The oxide keeps the gate electrically insulated from the silicon.

<!-- scene: poly -->

A deposition machine adds a film of polysilicon, silicon made up of many small crystals. We use doped polysilicon so that the film conducts electricity and can serve as the gate electrode.

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

We apply another resist film for an n-type implant. The two transistor types need different dopants, so we will use separate masking cycles to form their source and drain regions.

<!-- scene: n-expose -->

The n-type implant photomask exposes the region around the n-type transistor. Resist above the p-type transistor remains unexposed.

<!-- scene: n-develop -->

Development opens those regions. The p-type transistor remains covered by resist, while the n-type transistor’s gate is visible inside its opening.

<!-- scene: implant -->

Ions of an n-type dopant enter the silicon through the thin oxide. The gate blocks implantation into the channel region immediately beneath it, while resist protects the other device. This places a high concentration of dopants in the shallow source and drain regions beside the gate, labelled `n+`. The `+` means heavily doped, not electrically positive.

The gate’s edges define where these implants begin, so we do not need to align a separate pattern to each channel edge. This is called a self-aligned process.

<!-- scene: n-strip -->

We strip the resist after the n-type implant. The dopants stay in the silicon, ready for the heat treatment after both implants.

<!-- scene: p-coat -->

A fresh resist film covers both devices again. This time it will protect the n-type transistor while we open the region around its p-type partner.

<!-- scene: p-expose -->

The p-type implant photomask exposes the region around the p-type transistor.

<!-- scene: p-develop -->

Development opens the resist around the p-type transistor while leaving the n-type transistor covered.

<!-- scene: implant-p -->

Ions of a p-type dopant enter the source and drain regions, labelled `p+`. The `+` again means heavily doped. The gate protects the channel region beneath it, and the resist shields the n-type transistor.

<!-- scene: p-strip -->

We remove the remaining resist. Both implant patterns have now served their purpose. The new source and drain regions lie within the existing silicon.

<!-- scene: anneal -->

We anneal the wafer to repair crystal damage and make the newly implanted dopants electrically active. Heating can also spread dopants beyond their initial positions, so we control its temperature and duration to preserve the intended source and drain boundaries.

We now have the essential device structures. Their terminals still need electrical connections.

<!-- scene: contact-insulation -->

## Turn the devices into a circuit

We deposit insulation over the devices to keep unrelated conductors apart. We still need to reach each terminal, an electrical connection point at the source, drain or gate. Another photomask will define holes through the insulation at those points.

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

We coat the metal with fresh resist. The next photomask will define wire routes across the surface, while the previous contact pattern defined holes through the insulation.

<!-- scene: metal-expose -->

The first-metal photomask exposes resist between the intended wires. Resist above the wires remains unexposed.

<!-- scene: metal-develop -->

Development leaves protective resist above the future connections and exposes the metal we want to remove.

<!-- scene: metal-pattern -->

The etcher removes that exposed metal, separating the remaining film into wires. The resist protects the wires until the etch is complete.

<!-- scene: metal-strip -->

We strip the resist to reveal the connections. The two gate electrodes join as the input, and the drains join as the output. The n-type transistor’s source connects to the low supply, while the p-type transistor’s source connects to the high supply.

Body contacts also hold the surrounding silicon at fixed voltages. We omit these connections from the diagrams for simplicity.

<!-- scene: inverter -->

Use the `0` and `1` buttons to change the input. In this example, logic `0` corresponds to `0 V` and logic `1` to `+1 V`.

When the input is `0`, the p-type transistor connects the output to the high supply while the n-type transistor is off. When the input is `1`, the n-type transistor connects the output to the low supply while the p-type transistor is off. The output settles to the opposite logic value.

This complementary pairing is called complementary metal–oxide–semiconductor, or CMOS. The historical name also covers processes with polysilicon gate electrodes. Our physical structure now implements the NOT gate we began with.

A gate like this can be developed into a standard cell, a reusable circuit building block with a defined layout and known electrical behaviour. Designers can combine cells to build larger circuits.

<!-- scene: interconnect -->

## Build above the transistors

Larger circuits need many connections, often on several levels. We deposit another insulating film over the first wires. Its surface follows some of the height differences below.

<!-- scene: planarise -->

Chemical-mechanical planarisation combines chemical action and polishing to remove raised material and flatten the surface. A flatter surface makes it easier to apply the next resist coating evenly and accurately focus its exposure pattern.

<!-- scene: via-coat -->

We coat this surface with fresh resist to define a via, a metal connection between wiring levels. First we need an opening through the insulation, landing on the intended wire below.

<!-- scene: via-expose -->

The via photomask exposes resist above the lower wire at the point where the two wiring levels should connect.

<!-- scene: via-develop -->

Development opens the resist at that point, ready for the etcher to remove the insulation below.

<!-- scene: via -->

The etcher removes insulation through the opening, stopping at the lower wire. Resist protects the surrounding surface.

<!-- scene: via-strip -->

We strip the resist. The opening now reaches the first wiring level, but needs metal before it can connect that level to the next.

<!-- scene: upper-metal -->

Metal fills the via and covers the insulating surface. As before, this is initially a continuous film that must be patterned into a wire.

<!-- scene: upper-coat -->

Fresh resist covers the new metal. The upper-wire pattern will define its route across the surface, including where it meets the filled via.

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

Zoom out and our gate becomes one small part of a die, an individual chip on the wafer. Electrical tests help identify which dies meet the required criteria. The fraction that passes is the yield for those criteria. Dies are separated and packaged to protect them and provide connections to other parts of a system, then tested further.

Designers specify circuits and layouts for a chosen manufacturing process. A foundry is a company that manufactures chips for other companies. Its process design kit supplies device models and layout rules that help designers create circuits suitable for that process. We will explore that relationship in another deep dive.

Our two transistors and their connections emerged through repeated, aligned changes to materials. Light selected resist patterns, machines added or removed material, dopants changed the silicon, and conductors connected the result. Those same kinds of operations can build the many gates that make a computer.
