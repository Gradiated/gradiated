# How do we print a transistor onto silicon?

A microchip is built on a small piece of silicon cut from a wafer. Transistors are formed at the silicon surface, with doped regions extending beneath it. Layers of metal wiring connect the transistors into logic gates, such as NOT and NAND, and larger circuits that calculate, remember and control.

Here, we will follow a silicon wafer through the main steps of building and connecting the two transistors of a NOT gate, also called an inverter. We use a simplified planar design[@cmos-fabrication], where the conducting channel runs along a flat silicon surface beneath each transistor’s gate electrode, between its source and drain connections. We simplify the manufacturing sequence and exaggerate dimensions to make each step clear.

<!-- scene: destination -->

## The NOT gate we will build

Our target structure is a NOT gate, a circuit whose output voltage is inverted from its input. Inside it, two transistors each have a gate electrode connected to the same input. One transistor is n-type and the other p-type. Together, they connect the output to the high voltage supply (`+1 V`) when the input is low (`0 V`), or to the low supply (`0 V`) when the input is high (`+1 V`).

Each transistor has two doped regions called the source and drain, with a gate electrode above the silicon between them. The gate voltage controls whether a conducting channel forms between source and drain. We will make these features in and on the same wafer, then add the connections that turn them into a circuit.

<!-- scene: wafer -->

## Begin with a silicon wafer

Let's begin with a polished silicon wafer, a thin slice cut from a large single crystal[@silicon-element]. Apart from a small, sparse quantity of dopant atoms, which we will explain shortly, our wafer is a continuous piece of silicon with no transistors or wires.

<!-- scene: clean-room -->

Let’s go inside Gradiated’s imaginary clean room, where filtered air and protective clothing help keep particles off the wafer. Even nanometer-scale debris can disrupt the tiny circuit patterns, so the air is continually recirculated through fine filters.[@cleanroom-filtration]

<!-- scene: operator -->

In many modern chip factories, or fabs, automated systems carry wafers between machines, often using overhead rails.[@fab-cleanroom] Here, our intern is undergoing initiations and will carry ours, wearing a Gradiated-merch protective coverall.

<!-- scene: hand-off -->

The intern is handed our wafer.

<!-- scene: magnify -->

Let's zoom into one small chunk of the wafer, where we will watch the two transistors take shape. Before we begin, we need a way to control how silicon conducts electricity.

Doping means adding small quantities of selected elements, called dopants. Phosphorus supplies extra electrons that can move through silicon and carry electric current. Electrons have negative charge, so we call this n-type silicon, with n meaning negative. Boron creates gaps where electrons are missing, called holes. As neighbouring electrons move to fill these gaps, the holes effectively move in the opposite direction and behave as positive charges. This is p-type silicon, with p meaning positive. These names describe how current is carried, not the overall charge of the silicon. Our starting wafer is lightly doped p-type.[@silicon-doping]

<!-- scene: layout -->

## The machines

A fab contains machines that add, remove and alter materials on a wafer. Large fabs can contain more than a thousand manufacturing tools. Our clean room groups their jobs into twelve stations so we can follow the process.

Our intern will visit `47` processing machines (even in our simplified example) before we have a working NOT gate, returning to the same machines with new patterns and materials.

<!-- scene: grow-oxide -->

## Prepare the silicon

For our NOT gate, we need an n-type and a p-type transistor side by side. Adding small amounts of phosphorus to silicon produces n-type silicon, where electric current is carried mainly by negatively charged electrons. Adding boron produces p-type silicon, where current is carried mainly by positively charged holes, the gaps left by missing electrons. The letters n and p stand for negative and positive.

In an n-type transistor, the gate controls a conducting channel between two n-doped regions called the source and drain. These sit within a p-type body, the surrounding silicon. In a p-type transistor, the channel connects two p-doped regions in an n-type body. Each transistor therefore contains both types of silicon.

Our starting wafer is already p-type, so it provides the body for the n-type transistor. Beside it, we first create a large, deep n-type region called an n-well. This will provide the body for the p-type transistor. We will form both transistors’ source and drain pockets later.

We do this by ion implantation, accelerating electrically charged n-type dopant atoms, such as phosphorus, into the silicon. First, we grow a thin silicon dioxide film by heating the wafer in oxygen. Some silicon is consumed as the oxide grows.

This oxide helps protect the silicon from contamination during implantation. As the electrically charged ions are moving very quickly, they punch through the oxide and into the silicon.[@implant-screen-oxide] The thicker photoresist we apply next will stop them where we want to keep the original doping.

<!-- scene: coat -->

The intern now goes to the coater, where the wafer spins as we spread liquid photoresist into a thin film. Gentle heating removes solvent and leaves a solid coating. This temporary film will protect the silicon that should remain p-type. Next, we will define an opening in it so ions can reach the future n-well.

<!-- scene: expose -->

We use a light-sensitive coating called "positive" photoresist. At the lithography machine, a patterned template called a photomask controls where ultraviolet light reaches it. The light triggers chemical reactions that make the exposed photoresist easier to dissolve and wash away using a chemical solution called developer. Here, the photomask exposes only the area where we want to form the n-well. “Positive” means that these light-exposed regions will be removed.

<details>
<summary>How does light make the photoresist easier to dissolve?</summary>

One common type of positive photoresist is made up of polymer molecules with chemical protecting groups attached, which make them difficult to dissolve in the water-based, alkaline developer.[@chemical-amplification] The coating also contains an ingredient called a photoacid generator. Extreme ultraviolet light, or EUV, can knock electrons out of molecules in the coating, including the polymer. These electrons can release further electrons through collisions and trigger reactions involving the photoacid generator, producing acid in the exposed regions.[@euv-electrons]

The acid catalyses reactions that remove protecting groups, helped by a controlled bake after exposure. This reveals acidic sites on the polymer. The acid is regenerated as it acts, so it can remove many protecting groups. This repeated action is called chemical amplification.[@chemical-amplification]

Some acid can spread beyond the illuminated area and blur the pattern. The photoresist’s chemistry, carefully controlled bake time and temperature, and acid-neutralising additives called quenchers limit this spread.[@acid-spread; @euv-electrons]

The alkaline developer then makes the polymer's revealed acidic sites electrically charged. Once enough sites on a polymer chain are charged, the chain can dissolve in the solution and wash away. The unexposed photoresist keeps its protecting groups and dissolves much more slowly.[@resist-dissolution]

</details>

<!-- scene: develop -->

Our intern now uses developer to wash away the exposed photoresist, opening the region for our n-well. The remaining photoresist forms a protective pattern, while the thin oxide beneath it remains intact.

<!-- scene: well -->

Next we create the n-well. The implanter accelerates ions of an n-type dopant, such as phosphorus, towards the wafer. They pass through the gaps in the photoresist and thin oxide into the silicon. The photoresist blocks them elsewhere. Inside the opening, the added atoms will make the silicon n-type after heat treatment.

<!-- scene: strip -->

Only after implantation do we strip the remaining photoresist and clean the wafer. Its job is finished, but the dopants remain in the silicon. Later operations will need fresh photoresist and different photomask patterns.

<!-- scene: well-anneal -->

Annealing heats the wafer so silicon and dopant atoms are “shaken” back into ordered positions after implantation damage, allowing it to be electrically conductive. The n-well now provides the body of the p-type transistor.

<!-- scene: isolation -->

## Foundations of the NOT gate

We need thicker insulation around the two transistor sites to help prevent unwanted conduction between neighbouring transistors. We will grow this *field oxide* only where it is needed, using local oxidation of silicon, or LOCOS.[@device-isolation] First, the deposition machine adds silicon nitride, a temporary barrier to oxidation. We keep the existing thin oxide between this film and the silicon.

<!-- scene: isolation-coat -->

Our intern returns to the coater for fresh photoresist. This time, we will pattern the nitride rather than implant dopants.

<!-- scene: isolation-expose -->

A different photomask exposes the photoresist around the two future transistor sites. The photoresist over those sites stays unexposed. The pattern must line up with the n-well we have already made.

<details>
<summary>How do successive patterns line up?</summary>

Special reference patterns called alignment marks are formed on the wafer alongside the circuit patterns. Before a new exposure, optical sensors locate these marks. The machine adjusts the wafer’s position and rotation so the new pattern lines up with features made using the same references, including our n-well.[@lithography-alignment]

Small positioning errors remain. Manufacturers measure how closely successive patterns line up, called overlay, and feed those measurements back to improve alignment in later exposures.[@lithography-overlay]

</details>

<!-- scene: isolation-develop -->

Developer removes the exposed photoresist. The remaining photoresist covers the two transistor sites, protecting the nitride beneath it.

<!-- scene: prepare-isolation -->

Etching removes material from the wafer. Our etcher uses plasma, an electrically energised gas containing free electrons, ions and reactive particles. Reactive particles combine with surface atoms to form gases that can be evacuated. Energetic ions striking the surface help these reactions take place.[@plasma-etching]

Here, we choose gases and settings that remove nitride much faster than oxide, clearing the exposed nitride while leaving the thin oxide largely intact.[@nitride-over-oxide; @nitride-etch-recipe] Photoresist protects the nitride over the two transistor sites.

<!-- scene: isolation-strip -->

We strip away the photoresist before returning to the hot furnace. The patterned nitride remains over the two transistor sites. It will protect them during oxidation.

<!-- scene: field-oxide -->

In the furnace, field oxide grows where the nitride has been removed. It consumes silicon as it grows, extending below the original surface as well as above it. Some oxide also spreads a short distance beneath the nitride edges. The protected transistor sites retain their thin oxide.[@device-isolation]

<!-- scene: nitride-strip -->

The nitride has done its job. We remove it with another etch that leaves the oxide largely intact, exposing the thin oxide over our transistor sites.

<!-- scene: pad-oxide-strip -->

A separate oxide etch clears that thin film, ready for fresh *gate oxide*. It also thins the field oxide, which remains around the transistor sites.[@locos-process] We have now used photoresist to define both an implant and a permanent material pattern. We will repeat coating, exposure, development, material processing and stripping as we build the transistors and lay down their wiring.

<!-- scene: oxide -->

## Lay down the gates

<figure class="fab-inline-circuit">
<img src="/assets/fabrication/inverter-gates.svg" alt="CMOS inverter circuit with the gate electrode of each transistor labelled. Both gates connect to the input.">
</figure>

Next we will build the two gate electrodes connected to the input in this diagram. Modern processes often use metal gates. In this example we will use an simpler, older process with gates made from polysilicon, silicon made up of many small crystals. These gates can withstand the high temperatures still needed before metal wires are laid down in later steps. Some modern processes use temporary polysilicon gates during these hot steps, then replace them with metal.[@gate-materials; @metal-gate-process]

We prepare the exposed silicon by growing a thin gate oxide. Both oxides are silicon dioxide, but the thick field oxide isolates neighbouring transistors, while the thin gate oxide separates each gate electrode from the silicon beneath it. Through this thin insulation, the gate’s electric field controls whether a conducting channel forms between source and drain as we change the input voltage relative to the source.

<!-- scene: poly -->

A deposition machine adds the polysilicon film. Inside the chamber, gases supply silicon to build the film and dopant atoms to make it conduct electricity.[@polysilicon-doping] We will shape this conducting film into the gate electrodes later.

<details>
<summary>Which gases supply the silicon and dopant?</summary>

For example, silane gas supplies silicon while a small amount of phosphine gas supplies phosphorus. The phosphorus atoms become part of the film as it grows.[@polysilicon-doping]

</details>

<!-- scene: gate-coat -->

Fresh photoresist covers the polysilicon. We will keep photoresist above the gate strips so they survive the etch.

<!-- scene: gate-expose -->

The gate's photomask exposes the photoresist around those strips. Because we use positive photoresist, these exposed areas will be removed during development.

<!-- scene: gate-develop -->

Development washes away the exposed photoresist, leaving protective strips above the intended gates. Next we can cut away the unprotected polysilicon.

<!-- scene: pattern-gate -->

The etcher removes unprotected polysilicon and stops at the oxide. Two narrow gates remain beneath the photoresist. They will also help position the source and drain regions we form next.

<!-- scene: gate-strip -->

We strip the photoresist, leaving the polysilicon gates and their thin insulation. We have finished shaping the gates, but still need to form the more heavily doped source and drain regions.

<!-- scene: n-coat -->

## Make the source and drain

We now form the (left) n-type transistor’s source and drain, two n-doped regions in its p-type body. Fresh photoresist will protect the p-type transistor on the right during implantation. Its source and drain need different dopants, so we will form them in a separate patterning cycle.

<!-- scene: n-expose -->

The n-type implant photomask exposes the region around the n-type transistor.

<!-- scene: n-develop -->

Those regions are cleared out after a visit to the developer. The p-type transistor remains covered by photoresist, while the n-type transistor’s gate is visible inside its opening.

<!-- scene: implant -->

Ions of an n-type dopant enter the silicon through the thin oxide. The gate blocks implantation into the channel region immediately beneath it, while photoresist protects the other transistor. This places a high concentration of dopants in the shallow source and drain regions beside the gate, labelled n-doped.

This is called a self-aligned process[@self-aligned-gate] because the gate itself sets the source and drain boundaries beside the channel, so they are perfectly positioned without another photomask. The gate must therefore be in place before implantation and survive the hot annealing step afterwards to repair the damage caused by implantation. We use polysilicon because aluminium gates would melt during that heating. The metal wiring is added later.

<!-- scene: n-strip -->

We strip the photoresist after the n-type implant. The dopants stay in the silicon, ready for the heat treatment after implantation.

<!-- scene: p-coat -->

A fresh photoresist film covers both transistors again. This time it will protect the n-type transistor on the left while we open the region around its p-type partner on the right.

<!-- scene: p-expose -->

The p-type implant photomask exposes the region around the p-type transistor.

<!-- scene: p-develop -->

Development opens the photoresist around the p-type transistor while leaving the n-type transistor covered.

<!-- scene: implant-p -->

Ions of a p-type dopant (usually boron) enter the source and drain regions, labelled p-doped. The gate protects the channel region beneath it, preserving the n-type silicon beneath the gate, where its channel will form.

<!-- scene: p-strip -->

We remove the remaining photoresist. Both implant patterns have now served their purpose. The source and drain regions are now formed within the silicon, extending down from its surface.

<!-- scene: anneal -->

We anneal the wafer to repair damage to the crystal and make the newly implanted dopants electrically active. Dopants can also spread during heating, so we control the temperature and duration to preserve the intended source and drain boundaries.

We now have the essential transistor structures. Their terminals still need electrical connections.

<!-- scene: contact-insulation -->

## Connect the transistors

<figure class="fab-inline-circuit">
<img src="/assets/fabrication/inverter-contacts.svg" alt="CMOS inverter circuit. The two sources connect to the supply rails and the two drains join at the output. The gates share the input.">
</figure>

We now need metal connections to the source, drain and gate of each transistor. First, our intern deposits silicon dioxide insulation to cover the transistors. This fills the gaps, supports the wiring we will build above, and prevents unwanted electrical connections. We show the insulation as transparent so the transistors beneath it remain visible.

<!-- scene: contact-planarise -->

The deposited oxide follows the raised shapes beneath it. Before applying photoresist, our intern visits the polisher. Chemical reactions and polishing remove excess oxide, leaving a flat insulating surface above the transistors.[@dielectric-polishing]

<!-- scene: contact-coat -->

To reach the terminals below, we will etch contact holes through the insulation. Fresh photoresist covers the oxide so we can define where those holes will go.

<!-- scene: contact-expose -->

The contact photomask exposes small regions above the terminals. Each hole must reach the right feature below, so the machine uses the alignment marks introduced earlier to position this pattern.[@lithography-alignment]

<!-- scene: contact-develop -->

Development opens up these small regions in the photoresist. The insulator still covers the terminals underneath.

<!-- scene: contacts -->

The etcher removes oxide through the openings to expose doped silicon or a polysilicon gate. We control the etch conditions and duration to clear the oxide while limiting damage to these terminals.[@plasma-etching] The drawing exaggerates the holes so we can follow their destinations. Some processes place a thin silicon nitride layer beneath the oxide to protect the terminals during oxide etching. A subsequent etch opens this protective layer where contacts are needed. We omit this extra layer here.[@nitride-etch-stop]

<!-- scene: contact-strip -->

We strip the photoresist after etching. The contact holes remain in the insulation, ready to be filled with conducting material.

<!-- scene: metal -->

Metal deposition fills the contacts and forms a film across the surface. This continuous film is not yet our circuit. We must separate and cut it into individual connections.

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

In order to connect different parts of the circuit, our intern now begins the next wiring level by depositing another insulating oxide film over the first wires.

<!-- scene: planarise -->

We polish the oxide flat again. A flatter surface makes it easier to apply the next photoresist coating evenly and accurately focus its exposure pattern.

<!-- scene: via-coat -->

We coat this surface with fresh photoresist to define a via, a metal connection between wiring levels. First we need an opening through the insulation, landing on the intended wire below.

<!-- scene: via-expose -->

The via photomask exposes photoresist above the lower wire at the point where the two wiring levels should connect.

<!-- scene: via-develop -->

Development opens the photoresist at that point, ready for the etcher to remove the insulation below.

<!-- scene: via -->

The etcher digs a hole through the exposed insulation until it reaches the lower metal wire. Photoresist protects the surrounding surface. The recipe for etching used in this step removes oxide much faster than metal, so the wire can form the bottom of the hole.[@etch-selectivity; @oxide-over-aluminium]

<!-- scene: via-strip -->

We strip the photoresist. The opening now reaches the first wiring level, but needs metal before it can connect that level to the next.

<!-- scene: upper-metal -->

Metal fills the via and covers the insulating surface. As before, this is initially a continuous film that must be patterned into a wire.

<!-- scene: upper-coat -->

Fresh photoresist covers the new metal.

<!-- scene: upper-expose -->

The upper-metal photomask exposes photoresist around the intended connection. The future wire remains protected.

<!-- scene: upper-develop -->

Development washes away light-exposed photoresist to reveal the unwanted metal.

<!-- scene: upper-metal-pattern -->

The etcher removes exposed metal, leaving the upper connection beneath the photoresist. Here we use a metal-etching recipe that largely preserves the oxide beneath it.[@etch-selectivity; @oxide-over-aluminium] The insulating oxide film fills in gaps and keeps the new wire separate from unrelated wires below.

<!-- scene: upper-strip -->

We strip the photoresist to reveal the upper wire, which can act as a connection to the greater circuit.

We have repeated the same patterning cycle with different patterns and materials. Real fabrication also needs frequent cleaning and measurements of film thickness, pattern size and alignment.[@locos-process; @process-metrology] In order to simplify our depiction of fabrication we have also left out detailed chemical recipes and refinements.[@cmos-fabrication]

<!-- scene: finish -->

## From one gate to a chip

Our NOT gate is one tiny part of a chip. Repeating the insulation, patterning and connection steps builds more wiring levels above it. Lower wires join nearby transistors, while larger wires higher up carry signals and power between distant parts of the chip. Vias connect the levels.[@interconnect-layers]

A finished chip also receives a protective coating, often combining oxide and silicon nitride, to keep moisture and contaminants out.[@chip-passivation]

The transistors stay on the silicon surface. Above them, a jungle of insulated metal layers turn many small circuits into one connected machine.
