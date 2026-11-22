# How do we print a transistor onto silicon?

Article plan agreed on 21 October 2026. A first article draft and local animation prototype now exist. The current visual direction is the fixed clean-room map described below. The earlier machine-symbol proposal is retained as planning history. Nothing has been pushed or deployed.

## Purpose and scope

Follow a familiar transistor from a blank wafer to a connected CMOS NOT gate. Explain how patterns and controlled changes to materials produce the physical structures introduced in [Sand to Thought](../sand/script.md). Support Aidan's learning towards chip design and tape-out through a concrete account of what each manufacturing operation achieves.

Use a simplified, documented planar CMOS process. Keep the same cross-section throughout and connect it to a top-view layout and circuit schematic. The central questions are what material changes, what determines where it changes, and what job the resulting feature performs.

Related context is in the [research notebook](../../planning/notes.md#fabricating-a-transistor), [collection purpose and goals](../../README.md#purpose-and-goals) and [shared style guide](../../shared/style-guide.md).

## Agreed decisions

- Keep the example planar, matching the existing overview. No FinFET scene or comparison is required in this article. FinFETs and other geometries can be explored later with scaling.
- Build one transistor closely, then introduce its complementary partner and the connections that complete a NOT gate. Use one consistent CMOS flow for both devices.
- Omit the outer body-contact implants, contact holes and metal branches from the diagrams for simplicity. Retain the substrate and n-well. Briefly state that body contacts hold the surrounding silicon at fixed voltages and are omitted from this teaching view.
- Layer-by-layer construction is the organising visual idea. Include operations that modify silicon within the wafer as well as those that add or remove material above it.
- Explain lithography as defining a temporary resist pattern. Development reveals openings in the resist, and subsequent etching or implantation changes the selected material. Keep these actions visibly distinct.
- Spend most of the article on patterning, transistor formation and electrical connections. Keep wafer production, detailed lithography machinery, packaging and the broader design flow brief.
- Identify the example as simplified planar CMOS. Choose and verify one concrete teaching flow before finalising process order, materials and detailed animation. The outline groups ideas for teaching and is not a complete fabrication recipe.
- Preserve the existing overview. This planning work does not authorise changes to the website, its animations or its published content.
- Follow the wafer between machines and build up a compact collection of reusable machine symbols in the corner, using the building-block language from the overview. Hover shows a short Wikipedia preview and clicking opens the relevant Wikipedia page in a new tab.
- Store video links and study notes only. Do not download, copy or embed video files. Keep this work local until Aidan requests otherwise.

## Article skeleton

### 1 What are we trying to build?

Start with the familiar transistor cross-section. Identify source, drain, gate and gate insulation, briefly recalling their jobs. Show the completed NOT gate as the destination, then return to a blank wafer. Keep a faint outline of the intended structure available when it helps orient the reader.

### 2 How does a drawing specify where things go?

Introduce layout patterns that specify regions and connections. Different operations need different patterns. Pair a top view with a cross-section and mark the cutting line that connects them. Keep design software and mask preparation brief.

### 3 The patterning cycle we will reuse

Explain one complete example slowly. Add a film, coat it with photoresist, expose a pattern, develop the resist, etch the exposed underlying material and remove the remaining resist. Introduce baking where required by the selected resist process. Later sections can reuse this sequence more quickly. Show separately how a patterned protective layer can select implantation regions.

### 4 Prepare regions for neighbouring transistors

Introduce the differently doped body regions needed for n-type and p-type devices and the insulating regions that separate neighbouring devices. Explain every feature through its electrical job. Follow the selected process when determining the order of well formation and isolation.

### 5 Build the gate and its insulation

Form the thin gate insulator, add gate material and pattern it. Explain growing an oxide by reacting with silicon and depositing a material onto a surface. The proposed teaching example uses a polysilicon gate, subject to verification of the chosen flow.

### 6 Create the source and drain

Show implantation introducing dopants into selected regions and subsequent heat treatment repairing damage and activating dopants. Explain how the patterned gate helps define source and drain boundaries in a self-aligned process. Keep any particle motion schematic and the unchanged silicon regions clearly visible.

### 7 Connect a working NOT gate

Add insulation, open contact holes and form connections to the devices. Join the gates as the input, connect the drains as the output and connect the supply rails. Body contacts are omitted from the teaching view. Toggle the input and show the resulting output, linking physical structure, layout and schematic. This is the main payoff.

### 8 Extend the idea to an entire chip

Zoom out to many cells beneath layers of wiring. Introduce insulating layers, vias between wiring layers and planarisation where it is used in the chosen flow. Explain alignment and illustrate how a missed connection or an unwanted connection changes the circuit. Introduce the completed NOT gate as an example of a reusable standard cell. Cleaning, measurement and inspection recur throughout fabrication.

### 9 From a wafer to something we can use

Briefly introduce wafer testing, separating dies, packaging and final testing. Define yield as the proportion meeting the relevant acceptance criteria. End by connecting the physical gate to the larger circuits in the overview and briefly locating the designer and foundry in this process. Detailed packaging and design automation remain future branches.

## Earlier machine journey and reusable symbols

Agreed on 21 October 2026. Use the same wafer as it travels between the machines required by the selected planar process. Each machine receives a stable symbol or small icon, following the compact building-block system used in the overview's Building a computer chapter.

On its first visit, introduce the machine with a small model and a clear name and job. The proposed motion is one gentle rotation before settling. Move it smoothly into a compact block in a reserved corner area. As new machines appear, add their symbols to that collection. Keep symbol sizes and alignment consistent and leave space for labels and the main cross-section.

When an operation needs a familiar machine again, animate its existing symbol out of the corner and expand it into the active machine view. Follow the wafer into the operation and show the resulting material change in the main cross-section. Afterwards, shrink the machine back into its original position. Reuse its identity without adding duplicate symbols. The symbols identify equipment categories in the teaching story, rather than specifying the number of physical tools in a factory.

The detailed equipment model occupies a small area near the main animation while the relevant material change remains central. Keep the collection organised, with a responsive layout, readable names and stable positions. Reverse scrolling should restore the earlier collection and active machine smoothly. Reduced-motion presentation should preserve the same identities and operation sequence.

### Wikipedia preview and link behaviour

- Hover over a machine symbol, or focus it with the keyboard, to open a small preview card near it. Keep the preview inside the viewport and clear of the wafer and essential process labels.
- Show the machine or process name, a short plain-language summary and a clearly labelled Wikipedia source link. This is a compact preview card, with wording checked against the linked article, rather than an embedded full Wikipedia page. Preserve attribution if Wikipedia text or images are reused.
- Clicking the symbol opens the relevant English-language Wikipedia article in a new tab. Preserve the article's current scroll position and fabrication state. Use an accessible link name that makes the new-tab destination clear.
- Let the pointer move from the symbol onto the preview without closing it. Allow Escape to dismiss the card and keep the main narrative usable without opening any preview.
- Support keyboard focus and activation. For touch, provide a separate information control beside the machine link so readers can reveal the preview without accidentally navigating away. Activating the machine link still opens Wikipedia in a new tab.
- Keep the explanation available without a live Wikipedia request. Choose short reviewed preview text during development. Link to the exact machine article when available, otherwise the relevant process article. No video files are needed for this interaction.
- Machine price tags remain an optional detail for the preview. Add a cost only when a particular model or equipment category has a reliable dated source, with currency and scope clear. No prices have been selected or verified.

### Candidate Wikipedia destinations

These pages were checked on 21 October 2026 as possible reading destinations. Select the final machine list and targets after the planar process is chosen. The process pages are optional further reading, not the technical authority for our fabrication sequence.

| Machine or equipment category | Candidate destination |
| --- | --- |
| Lithography exposure system | [Photolithography](https://en.wikipedia.org/wiki/Photolithography) |
| Ion implanter | [Ion implantation](https://en.wikipedia.org/wiki/Ion_implantation) |
| Chemical vapour deposition equipment, if used | [Chemical vapor deposition](https://en.wikipedia.org/wiki/Chemical_vapor_deposition) |
| Reactive-ion etcher, if used | [Reactive-ion etching](https://en.wikipedia.org/wiki/Reactive-ion_etching) |
| Planarisation equipment, if used | [Chemical-mechanical polishing](https://en.wikipedia.org/wiki/Chemical-mechanical_polishing) |

## Current clean-room prototype

Agreed on 21 October 2026 after reviewing the first draft. Replace the moving equipment thumbnails with a simple game-like view. Keep twelve stations in two rows of six on a bird’s-eye clean-room map. Development and resist stripping have separate wet benches. Film deposition and metal deposition have separate stations, as do the oxidation furnace and annealer. The shared etcher represents a tool family, with the active operation labelled as oxide, polysilicon or metal etching. Remove the wafer stand and park the operator in the central aisle when no machine is active. Machine drawings omit the repeated side control panels to keep the map spacious. One bunny-suited operator carries the same wafer between them. Each machine has its own loading point at its chuck, stage, chamber or bath. Loading moves the wafer into that point and smoothly changes its carried ellipse into a flat top-down circle. Retrieval reverses that movement. Machine links and the optional Wikipedia previews remain available.

Below the room, show the whole wafer with gloved hands on the left and the same marked region enlarged on the right. Begin with a plain, continuous wafer. Use the shared dark-grey silicon palette for the whole wafer, carried wafer, enlarged substrate and material key. Oxide colour appears only as oxide grows. Surface patterns appear through processing, while the die-separation grid is reserved for the final testing and dicing section. The enlargement marker selects an area smaller than one die. Two faint solid guides join its corners to the matching corners of the enlarged surface and track the camera and film height. Do not use a dotted leader or terminal dot. The gloved hands appear when the large wafer settles into place. They recede only while a real machine has the wafer loaded, returning on retrieval. Introductory scenes without a machine keep the gloves steady. Loading and retrieval are also shown by the operator and small wafer in the clean-room map. The close-up uses projected 3D geometry with controlled changes between angled, overhead and cutaway views. Large jumps between non-adjacent steps restore the destination material state with a short fade rather than blending all intervening coatings together. Adjacent steps retain continuous material changes. Animation timing follows elapsed visible time so expensive frames do not prolong a transition. A cutaway hides part of the model for viewing and is labelled accordingly. It is distinct from physically etching material.

The first prototype covers the initial patterning cycle. The oxide grows before coating. Exposure changes the positive resist without opening it. Development opens the resist while preserving the oxide. Etching removes exposed oxide while resist remains as protection. Stripping removes the temporary resist and leaves the patterned oxide. Walking, loading, processing and retrieval share one timeline. Keep the cutaway steady through development, etching and stripping so hidden foreground material does not reappear between those steps. Thin films taper to transparency at vanishing thickness, and replay or section changes ease from the currently displayed material and camera state before processing begins. Each step settles for inspection and can be replayed. Reduced motion shows the settled state.

Oxide growth and resist coating have separate scroll sections. Each animated section visits only its own machine and settles there until the reader scrolls or selects the next step. The paragraph wording is unchanged. The same projected 3D model now continues through well formation, field isolation, gate oxide, gate deposition and patterning, source and drain implants, annealing, contact openings and wiring. Doped regions occupy the existing silicon volume. Later insulation is translucent to keep the devices visible, with contact openings reaching their intended terminals. A second wiring level and via illustrate separated conductors above the first level. These have separate scroll steps for insulating-film deposition, polishing, via etching and upper-metal deposition. The deposited insulation has raised areas over existing wires. Polishing only reduces its height and flattens it. Via etching removes insulation down to the intended wire. The next deposition fills that opening and adds the upper connection. No metal or insulating material is added during the polisher visit. A separate polishing visit now follows the first insulation deposition above the transistors, before contact-hole coating. This oxide first follows the device contours, then loses excess material until its surface is flat. Existing article prose is preserved, with only the new scene and its cited explanation added. The opening and working NOT-gate scenes use this same geometry with input controls. The cutaway remains continuous after the first patterning cycle, and the whole-wafer surface reflects later gate and metal patterns.

The local process now has 69 scroll steps and nine explicit photolithography cycles. The first cycle directly defines the n-well implant through a thin screen oxide. Resist is coated, exposed and developed before implantation, retained during implantation and stripped afterwards. Well heating has its own furnace visit. Isolation now follows LOCOS. The cleaned thin oxide is retained beneath a deposited nitride barrier. A positive-photoresist cycle removes nitride around the two transistor sites, then strips the photoresist before field oxidation. Field oxide grows above and into the exposed silicon, with a tapered profile extending slightly beneath the nitride edges. Separate etch visits remove nitride and then the thin pad oxide before fresh gate oxide grows. The pad-oxide etch also thins the field oxide. The example retains the existing thin oxide for simplicity rather than modelling a separate strip, clean and pad-oxide regrowth. Thicknesses, edge profiles, etch selectivity and nitride deformation are illustrative rather than process simulation. Cleaning details, field implants and other refinements remain omitted. Each machine operation still has its own scroll section.

The isolation flow follows [Hollauer, section 1.2](https://iue.tuwien.ac.at/phd/hollauer/node7.html), with the separate nitride and pad-oxide removals checked against [Berkeley’s LOCOS process flow, step 24](https://nanolab.berkeley.edu/public/process/baseline/cmos180/CMOS180_LOCOS.htm). Additional oxide growth consumes silicon using the 0.44 thickness ratio documented in [Radi, section 2.2](https://iue.tuwien.ac.at/diss/radi/node21.html). The nitride uses ochre, distinct from grey oxide and purple photoresist, consistently across the enlarged, whole-wafer and carried-wafer views.

The same coat, expose, develop, operate and strip sequence defines gates, separate n-type and p-type implants, contact holes, first-metal wires, the via opening and upper-metal wires. Each machine visit has its own scroll step. The mask counter and five-stage indicator connect the repeated cycles without repeating the full explanation. The photomask appears only at exposure. The physical resist remains visible until stripping, uses each operation’s actual geometry and has an approximately level coated surface over existing features. Positive-resist openings always correspond to the illuminated pattern. Different patterns can modify the same physical layer.

Oxidation consumes silicon, etching proceeds through exposed material, and polishing only removes material. Deposited metal is initially continuous, then separated into wires while resist protects the retained connections. The whole-wafer patterns and enlarged model use the same mask definitions. The prose now follows these cycles explicitly and distinguishes the photomask, temporary resist and permanent material change. Film recipes, detailed cleaning, additional device refinements and realistic metal filling remain outside the simplified example.

Implementation is in `hardware/publishing/sand-to-thought/articles/fabricating-a-transistor/figures/`. `FabricationJourney.tsx` owns scrolling and replay. `process.ts` links machine visits and material changes. `FabricationLab.tsx` draws the room, operator and whole wafer. `PatterningModel.tsx` draws the layered structure throughout the article. Styles remain scoped to the fabrication article. The article remains a draft visible locally and in Vercel previews, excluded from the public production build.

The opening now introduces the views in separate scroll sections. The working inverter symbol, circuit and physical model fade away before a large blank wafer appears centrally. The wafer moves into the lower-left gloves as an empty room fades in. A temporary door on the right opens for an empty-handed operator, who walks to the centre. A shrinking copy links the large wafer to the operator’s hand. The red region marker then extends into guides for the enlarged view. Machines appear with the layout explanation before processing begins. Each view is introduced in the corresponding prose. Moving past an introductory section immediately settles its movement, so rapid scrolling never leaves the wafer floating in the centre during later sections. The same wafer, floor and observation panels remain mounted across these transitions, and reduced motion shows their settled states.

## Proposed animations

1. **Finished structure to blank wafer.** Show the target NOT gate, isolate one transistor and unwind its construction. Then build forwards. Keep orientation and scale stable during each operation.
2. **Linked views.** Keep a large cross-section with a smaller layout view and a marked cutting line. Selecting a feature highlights its corresponding region in both. Bring in the schematic once terminals and connections become meaningful.
3. **One complete pattern-transfer cycle.** Pause at the film, coated resist, exposure, developed openings, etched material and stripped surface. Use stable before-and-after states. A short repeat of this sequence later recalls the mechanism without repeating all the explanation.
4. **Growing versus depositing.** Contrast an oxide forming through a reaction that consumes some silicon with a film added onto the surface. Source the relative boundaries and avoid implying that oxidation simply paints a layer on top.
5. **Selective doping and self-alignment.** Show protection over regions that should remain unchanged, then illustrate implantation and heat treatment. Highlight the gate's role in defining the source and drain boundaries. Distinguish temporary masks, permanent materials and dopant changes.
6. **A contact makes a circuit.** Open a contact hole and add a conductor, tracing which terminal it reaches. Assemble the NOT gate connections one by one. Use the existing yellow wire highlight for electrical paths when demonstrating operation, rather than for arbitrary process activity.
7. **Multiple wiring levels.** Raise the view to reveal an insulating layer separating crossing conductors. Cut through a via to show the deliberate vertical connection. Keep any planarisation step tied to the selected process.
8. **Manufactured gate to familiar symbol.** Toggle the completed gate's input, show its output, then smoothly simplify it into the NOT symbol from the overview. Zoom out to a few connected cells before the brief wafer and packaging ending.

Use the established restrained line art, cream background and fonts. Give materials a consistent, labelled visual identity. Do not rely on colour alone. Reserve live electrical highlights for the operational explanation. Prefer editable SVG or code-native geometry, with stable inspection states, reversible progress and a reduced-motion alternative. Exact interaction design and implementation technology remain open.

## Video references and study progress

- [Branch Education — How are Microchips Made? CPU Manufacturing Process Steps](https://www.youtube.com/watch?v=dX9CGRZwD-w). Aidan explicitly reported watching this on 20 October 2026 and found the manufacturing explanation extremely useful. Use it as orientation for the overall process.
- [Branch Education — How do Transistors Build into a CPU? How do Transistors Work?](https://www.youtube.com/watch?v=_Pqfjer8-O4). Aidan highlighted this as another excellent reference on 20 October 2026. Use it as a companion when developing the connection between physical devices, logic gates and standard cells.

Aidan noted the FinFET examples in the video discussion and chose planar construction for our article. The links are references, not downloaded media or assets to reuse. Watching a source does not by itself establish mastery of every topic it covers.

## Technical sources for development

- [NPTEL CMOS fabrication sequence](https://archive.nptel.ac.in/content/storage2/courses/117101058/Slides/12.7.htm) covers a planar nMOS example through gate formation, self-aligned doping, contacts and wiring.
- [NPTEL CMOS inverter connections](https://archive.nptel.ac.in/content/storage2/courses/117103066/chap3/slides/slide209.htm) connects the physical devices into an inverter.
- [MIT 6.152J Fall 2005 lecture notes](https://ocw.mit.edu/courses/6-152j-micro-nano-processing-technology-fall-2005/pages/lecture-notes/) provide routes into implantation, deposition and etching. Some listed lectures have no attached handout.
- [ASML manufacturing overview](https://www.asml.com/en/company/stories/2021/semiconductor-manufacturing-process-steps) provides broad process and packaging context. Keep resist development distinct from etching the underlying film.
- [Lam Research pattern-transfer example](https://newsroom.lamresearch.com/everything-you-need-to-know-about-aether) distinguishes exposure, development and transfer etch. Its advanced dry-resist example does not specify the planar flow we will illustrate.
- [Applied Materials on planarisation](https://www.appliedmaterials.com/il/en/semiconductor/semiconductor-technologies/cmp.html) explains material removal and surface flattening.

These sources informed the outline. Recheck the exact passages and chosen process before writing detailed claims or drawing dimensions and process sequences.

## Next development step

Review the clean-room map, gloved wafer and first patterning cycle together with Aidan. Refine their clarity before extending the projected 3D structure through device formation, contacts and interconnect. Keep the existing article text and later diagrams available until their replacements are agreed. Keep work local until Aidan requests a commit and push.
