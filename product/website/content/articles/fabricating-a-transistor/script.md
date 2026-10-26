# How do we print a transistor onto silicon?

A microchip is built on a small piece of silicon cut from a wafer. Transistors are formed at the silicon surface, with doped regions extending beneath it. Many are grouped into reusable building blocks called standard cells, such as NOT gates, NAND gates and flip-flops. These cells combine into larger circuits that calculate, remember and control. Layers of metal wires above the transistors connect nearby cells and distant parts of the chip.

Here, we will follow a silicon wafer through the main steps of building the two transistors of a NOT gate, also called an inverter. We use a simplified planar design, where the conducting channel runs along a flat silicon surface beneath each transistor’s gate electrode, between its source and drain connections. The structures are simplified and exaggerated to make operation clear and changes visible.

<!-- scene: destination -->

## Printing a NOT gate with two transistors and metal wire

Our target structure is a NOT gate, a circuit whose output voltage is the opposite of its input. Inside it, two transistors each have a gate electrode connected to the same input. One transistor is n-type and the other p-type. Together, they connect the output to the high voltage supply (`+1 V`) when the input is low (`0 V`), or to the low supply (`0 V`) when the input is high (`+1 V`).

Each transistor has two doped regions called the source and drain, with a gate electrode above the silicon between them. The gate voltage controls whether a conducting channel forms between source and drain. We will make these features in and on the same wafer, then add the connections that turn them into a circuit.

<!-- scene: wafer -->

## Begin with a silicon wafer

Let's begin with a polished silicon wafer, a thin slice cut from a large single crystal. Silicon is a chemical element with atomic number `14`, meaning each atom has `14` protons.[@silicon-element] Apart from a small quantity of dopant atoms, which we will explain shortly, our wafer is a continuous piece of silicon with no transistors or wires.

<!-- scene: clean-room -->

Let’s go inside Gradiated’s clean room, where filtered air and protective clothing help keep particles off the wafer. Even tiny particles can spoil the structures we are trying to make.

<!-- scene: operator -->

In many modern chip factories, or fabs, automated systems carry wafers between machines, often using overhead rails.[@fab-cleanroom] Here, our intern has drawn the short straw and will carry ours, wearing a Gradiated-branded protective coverall.

<!-- scene: hand-off -->

The intern is handed our wafer.

<!-- scene: magnify -->

Let's zoom into one small chunk of the wafer, where we will watch the two transistors take shape. Before we begin, we need a way to control how silicon conducts electricity.

Doping adds small quantities of selected elements, called dopants. Phosphorus, for example, supplies extra mobile electrons, producing n-type silicon. Boron produces p-type silicon, where missing electrons, called holes, behave as mobile positive charges. These electrons or holes carry current when a voltage is applied. Our starting wafer is lightly doped p-type.[@silicon-doping]

<!-- scene: layout -->

## The machines

A fab contains machines that add, remove and alter materials on a wafer. Large fabs can contain more than a thousand manufacturing tools.[@fab-cleanroom] Our clean room groups their jobs into twelve stations so we can follow the process.

Our intern will make `44` processing visits before we have a working NOT gate, returning to the same machines with new patterns and materials.

<!-- scene: grow-oxide -->

## Two different environments for two adjacent transistors

We need an n-type and a p-type transistor side by side for our NOT gate. The n-type transistor forms an electron-carrying channel between two n-doped pockets in a p-type silicon body. Its p-type partner forms a hole-carrying channel between p-doped pockets in an n-type body. Our p-type wafer already provides the body for the n-type transistor. To build its p-type partner alongside it, we first create a deeper n-type region called an n-well.

We do this by ion implantation, accelerating electrically charged n-type dopant atoms, such as phosphorus, into the silicon. First, we grow a thin silicon dioxide film by heating the wafer in oxygen. Some silicon is consumed as the oxide grows.

This oxide helps protect the silicon from contamination during implantation. As the electrically charged ions are moving very quickly, they punch through the oxide and into the silicon.[@implant-screen-oxide] The thicker photoresist we apply next will stop them where we want to keep the original doping.

<!-- scene: coat -->

The intern now goes to the coater, where the wafer spins as we spread liquid photoresist into a thin film. A gentle heating step, called a soft bake, removes solvent and leaves a solid coating. This temporary film will protect the silicon that should remain p-type. Next, we will define an opening in it so ions can reach the future n-well.

<!-- scene: expose -->

We use a light-sensitive polymer called "positive" photoresist. At the lithography machine, a patterned template called a photomask controls where ultraviolet light reaches it. The light triggers chemical reactions that make the exposed photoresist easier to dissolve and wash away using a chemical solution called developer. Here, the photomask exposes only the area where we want to form the n-well. “Positive” means that these light-exposed regions will be removed.

<details>
<summary>How does light make the photoresist easier to dissolve?</summary>

One common approach uses a chemically amplified positive photoresist. Its polymer molecules have chemical protecting groups attached, which make them resist dissolution in the water-based, alkaline developer. The coating also contains a photoacid generator, an ingredient that produces acid after exposure.[@chemical-amplification]

With extreme ultraviolet light, or EUV, each absorbed photon has enough energy to knock an electron out of a photoresist molecule. Collisions release further electrons, which trigger reactions that generate acid in the exposed regions.[@euv-electrons]

The acid catalyses reactions that remove protecting groups, helped by a controlled bake after exposure. This reveals acidic sites on the polymer. The acid is regenerated as it acts, so it can remove many protecting groups. This repeated action is the chemical amplification.[@chemical-amplification]

Some acid can spread beyond the illuminated area and blur the pattern. The photoresist’s chemistry, carefully controlled bake time and temperature, and acid-neutralising additives called quenchers limit this spread.[@acid-spread; @euv-electrons]

The alkaline developer then makes the revealed sites electrically charged. Once enough sites on a polymer chain are charged, the chain can dissolve in the solution and wash away. The unexposed photoresist keeps its protecting groups and dissolves much more slowly.[@resist-dissolution]

</details>

<!-- scene: develop -->

Our intern now uses developer to wash away the exposed photoresist, opening the region for our n-well. The remaining photoresist forms a protective pattern, while the thin oxide beneath it remains intact.

<!-- scene: well -->

Next we create the n-well. The implanter accelerates ions of an n-type dopant (usually phosphorus, antimony or arsenic) towards the wafer. They pass through the photoresist opening and thin oxide into the silicon. The photoresist blocks them elsewhere. Inside the opening, the added atoms will make the silicon n-type after heat treatment.

<!-- scene: strip -->

Only after implantation do we strip the remaining photoresist and clean the wafer. Its job is finished, but the dopants remain in the silicon. Later operations will need fresh photoresist and different photomask patterns.

<!-- scene: well-anneal -->

Annealing heats the wafer so atoms can move back into ordered positions after implantation damage. It also helps dopants occupy silicon lattice sites where they can supply electrons or holes. The n-well now provides the body of the p-type transistor.

<!-- scene: isolation -->

## Foundations of the NOT gate

We now grow a thicker silicon dioxide layer in the furnace. This field oxide will help keep neighbouring devices electrically separate. We will remove it from the two sites where we want our transistors, leaving insulation around them.

<!-- scene: isolation-coat -->

Our intern returns to the coater for a fresh photoresist film. This time, we are going to remove oxide rather than implant dopants.

<!-- scene: isolation-expose -->

A different photomask exposes a new pattern of two sites for two transistors. The pattern must line up with the n-well we have already made.

<details>
<summary>How do successive patterns line up?</summary>

Special reference patterns called alignment marks are formed on the wafer alongside the circuit patterns. Before a new exposure, optical sensors locate these marks. The machine adjusts the wafer’s position and rotation so the new pattern lines up with features made using the same references, including our n-well.[@lithography-alignment]

Small positioning errors remain. Manufacturers measure how closely successive patterns line up, called overlay, and feed those measurements back to improve alignment in later exposures.[@lithography-overlay]

</details>

<!-- scene: isolation-develop -->

Development clears out the photoresist above those sites. Photoresist remains over the field oxide we want to keep.

<!-- scene: prepare-isolation -->

Etching removes exposed material through chemical reactions, sometimes assisted by energetic particles. In our plasma etcher, reactive gases turn material at the surface into gaseous products that can be pumped away.[@plasma-etching] Here, we choose conditions that remove oxide much faster than silicon, allowing us to stop at the silicon surface. The photoresist protects the surrounding oxide. We now have openings in the permanent insulating film, not just in the photoresist.

<!-- scene: isolation-strip -->

We strip away the photoresist after etching with another wash. The oxide pattern remains, surrounding the exposed device sites. We have now completed two cycles of coating, exposure, development, material processing and stripping. We will repeat this sequence with different patterns as we build the transistors and their wiring.

<!-- scene: oxide -->

## Lay down the gates

<figure class="fab-inline-circuit">
<img src="/assets/fabrication/inverter-gates.svg" alt="CMOS inverter circuit with the gate electrode of each transistor labelled. Both gates connect to the input.">
</figure>

Next we will build the two gate electrodes connected to the input in this diagram. Modern processes often use metal gates. We use an older process with gates of polysilicon, silicon made up of many small crystals. These gates can withstand the high temperatures needed to activate the source and drain dopants later. Our metal wires are added after that heating. Some modern processes use temporary polysilicon gates during these hot steps, then replace them with metal.[@gate-materials; @metal-gate-process]

We prepare the exposed silicon by growing a thin *gate oxide*. Both oxides are silicon dioxide, but the thick *field oxide* isolates neighbouring devices, while the thin gate oxide separates each gate electrode from the silicon beneath it. Through this thin insulation, the gate’s electric field controls whether a conducting channel forms between source and drain as we change the input voltage relative to the source.

<!-- scene: poly -->

A deposition machine adds the polysilicon film. Inside the chamber, gases such as silane and a small amount of phosphine supply silicon and phosphorus, incorporating dopant atoms into the growing film so it conducts electricity.[@polysilicon-doping] We will shape this conducting film into the gate electrodes later.

<!-- scene: gate-coat -->

Fresh photoresist covers the polysilicon. We will keep photoresist above the gate strips so they survive the etch.

<!-- scene: gate-expose -->

The gate's photomask exposes the photoresist around those strips. Because we use positive photoresist, these exposed areas will be removed during development.

<!-- scene: gate-develop -->

Development washes away the exposed photoresist, leaving protective strips above the intended gates. Next we can cut away the unprotected polysilicon.

<!-- scene: pattern-gate -->

The etcher removes unprotected polysilicon and stops at the oxide. Two narrow gates remain beneath the photoresist. Their edges will block the later source and drain implants, aligning those regions with the channel beneath each gate. This avoids a separate alignment step that could leave gaps or excessive overlap between the gate and the doped regions.[@cmos-fabrication]

<!-- scene: gate-strip -->

We strip the photoresist, leaving the polysilicon gates and their thin insulation. We have finished shaping the gates, but still need to form the more heavily doped source and drain regions.

<!-- scene: n-coat -->

## Make the source and drain

We now form the n-type transistor’s source and drain, two n-doped regions in its p-type body. Fresh photoresist will protect the p-type transistor on the right during implantation. Its source and drain need different dopants, so we will form them in a separate patterning cycle.

<!-- scene: n-expose -->

The n-type implant photomask exposes the region around the n-type transistor.

<!-- scene: n-develop -->

Those regions are cleared out after a visit to the developer. The p-type transistor remains covered by photoresist, while the n-type transistor’s gate is visible inside its opening.

<!-- scene: implant -->

Ions of an n-type dopant enter the silicon through the thin oxide. The gate blocks implantation into the channel region immediately beneath it, while photoresist protects the other device. This places a high concentration of dopants in the shallow source and drain regions beside the gate, labelled n-doped.

Because the gate itself sets the implant boundaries, this is called a self-aligned process.

<!-- scene: n-strip -->

We strip the photoresist after the n-type implant. The dopants stay in the silicon, ready for the heat treatment after implantation.

<!-- scene: p-coat -->

A fresh photoresist film covers both devices again. This time it will protect the n-type transistor on the left while we open the region around its p-type partner on the right.

<!-- scene: p-expose -->

The p-type implant photomask exposes the region around the p-type transistor.

<!-- scene: p-develop -->

Development opens the photoresist around the p-type transistor while leaving the n-type transistor covered.

<!-- scene: implant-p -->

Ions of a p-type dopant enter the source and drain regions, labelled p-doped. The gate protects the channel region beneath it, preserving the n-type silicon beneath the gate, where its channel will form.

<!-- scene: p-strip -->

We remove the remaining photoresist. Both implant patterns have now served their purpose. The new source and drain regions lie buried within the existing silicon.

<!-- scene: anneal -->

We anneal the wafer to repair crystal damage and make the newly implanted dopants electrically active. Dopants can also spread during heating, so we control the temperature and duration to preserve the intended source and drain boundaries.

We now have the essential device structures. Their terminals still need electrical connections.

<!-- scene: contact-insulation -->

## Turn the devices into a circuit

<figure class="fab-inline-circuit">
<img src="/assets/fabrication/inverter-contacts.svg" alt="CMOS inverter circuit. The two sources connect to the supply rails and the two drains join at the output. The gates share the input.">
</figure>

We now need metal connections to the source, drain and gate of each transistor. First, our intern deposits silicon dioxide insulation over the devices. This fills the gaps, supports the wiring we will build above, and prevents unwanted electrical connections. Another photomask defines where we will etch contact holes through the insulation. We then fill these holes with metal to connect to the terminals below. The insulator is mostly transparent in the following diagrams to make visualisation easier.

<!-- scene: contact-planarise -->

The deposited oxide follows the raised shapes beneath it. Before applying photoresist, our intern visits the polisher. Chemical action and polishing remove excess oxide, leaving a flat insulating surface above the devices.[@dielectric-polishing]

<!-- scene: contact-coat -->

Fresh photoresist covers the insulating oxide film. It will protect the insulation everywhere except at the intended contact holes.

<!-- scene: contact-expose -->

The contact photomask exposes small regions above the terminals. Each hole must reach the right feature below, so the machine uses the alignment marks introduced earlier to position this pattern.[@lithography-alignment]

<!-- scene: contact-develop -->

Development opens up these small regions in the photoresist. The insulator still covers the terminals underneath.

<!-- scene: contacts -->

The etcher removes insulating oxide through those openings. Each hole stops at its intended terminal, either doped silicon or the polysilicon gate. The drawing exaggerates the holes so we can follow their destinations.

<!-- scene: contact-strip -->

We strip the photoresist after etching. The contact holes remain in the insulation, ready to be filled with conducting material.

<!-- scene: metal -->

Metal deposition fills the contacts and forms a film across the surface. The blanket film is not yet our circuit. We must separate and cut it into individual connections.

<!-- scene: metal-coat -->

We coat the metal with fresh photoresist. The next photomask will define wire routes across the surface.

<!-- scene: metal-expose -->

The first-metal photomask exposes photoresist between the intended wires. Photoresist above the wires remains unexposed.

<!-- scene: metal-develop -->

Development leaves protective photoresist above the future wires and exposes the metal we want to remove.

<!-- scene: metal-pattern -->

The etcher removes that exposed metal, separating the remaining film into wires. The photoresist protects the wires until the etch is complete.

<!-- scene: metal-strip -->

We strip away the photoresist to reveal the connections. The two gate electrodes join as the input, and the drains join as the output. The n-type transistor’s source connects to the rail on the left, which we will connect to the low `0 V` supply, while the p-type transistor’s source connects to the high `+1 V` supply rail.

Body contacts are additional connections that hold the p-type body at the low supply and the n-well at the high supply. We omit them from the diagrams for simplicity.[@cmos-fabrication]

<!-- scene: inverter -->

Use the `0` and `1` buttons to change the input. In this example, logic `0` corresponds to `0 V` and logic `1` to `+1 V`.

When the input is `0`, the p-type transistor connects the output to the high supply while the n-type transistor is off. When the input is `1`, the n-type transistor connects the output to the low supply while the p-type transistor is off. The output settles to the opposite logic value.

This complementary pairing is called complementary metal–oxide–semiconductor, or CMOS.[@cmos-origin; @cmos-fabrication] Our physical structure now implements the NOT gate we began with.

The same techniques can build other logic gates. Connecting these gates into larger circuits requires more wiring above the transistors.

<!-- scene: interconnect -->

## Building above the transistors

Our intern now begins the next wiring level by depositing another insulating oxide film over the first wires.

<!-- scene: planarise -->

Chemical-mechanical planarisation combines chemical action and polishing to remove raised material and flatten the surface. A flatter surface makes it easier to apply the next photoresist coating evenly and accurately focus its exposure pattern.

<!-- scene: via-coat -->

We coat this surface with fresh photoresist to define a via, a metal connection between wiring levels. First we need an opening through the insulation, landing on the intended wire below.

<!-- scene: via-expose -->

The via photomask exposes photoresist above the lower wire at the point where the two wiring levels should connect.

<!-- scene: via-develop -->

Development opens the photoresist at that point, ready for the etcher to remove the insulation below.

<!-- scene: via -->

The etcher digs a hole through the exposed insulation until it reaches the lower metal wire. Photoresist protects the surrounding surface. This recipe removes oxide much faster than metal, so the wire can form the bottom of the hole.[@etch-selectivity]

<!-- scene: via-strip -->

We strip the photoresist. The opening now reaches the first wiring level, but needs metal before it can connect that level to the next.

<!-- scene: upper-metal -->

Metal fills the via and covers the insulating surface. As before, this is initially a continuous film that must be patterned into a wire.

<!-- scene: upper-coat -->

Fresh photoresist covers the new metal.

<!-- scene: upper-expose -->

The upper-metal photomask exposes photoresist around the intended connection. The future wire remains protected.

<!-- scene: upper-develop -->

Development reveals the unwanted metal while leaving photoresist along the wire’s route.

<!-- scene: upper-metal-pattern -->

The etcher removes exposed metal, leaving the upper connection beneath the photoresist. Here we use a metal-etching recipe that largely preserves the oxide beneath it.[@etch-selectivity] The insulating film keeps the new wire separate from unrelated wires below.

<!-- scene: upper-strip -->

We strip the photoresist to reveal the upper wire, which can act as a connection to the greater circuit.

We have repeated the same patterning cycle with different patterns and materials. Real fabrication also needs frequent cleaning and measurements of film thickness, pattern size and alignment. We have left out detailed chemical recipes and refinements such as extra implants and insulating spacers beside the gates, which help control the transistors’ behaviour.[@cmos-fabrication; @chipmaking-overview]

<!-- scene: finish -->

## Zooming out

Our NOT gate is one tiny part of a chip. Repeating the insulation, patterning and connection steps builds more wiring levels above it. Lower wires join nearby transistors, while larger wires higher up carry signals and power between distant parts of the chip. Vias connect the levels.[@interconnect-layers]

The transistors stay near the silicon surface. Above them, layers of insulated metal turn many small circuits into one connected machine.
