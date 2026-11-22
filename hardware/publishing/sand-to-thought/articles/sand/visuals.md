# Visual direction — How to get an answer out of sand

## Chapter 5 memory interface — 2026-10-16

The four-row array widens from four to eight bits, then becomes four compact row blocks with separate MAR and MDR registers. Sixteen-bit contents appear as two groups of eight, with bus markers changing from 8 to 16. MAR widens independently from 2 to 16, and the array becomes a window onto locations 0, 1, …, 65535. The first interface deliberately omits the clock. Clocked capture will be explained alongside processor control, while WE remains the separate memory-write control. Each row stays in place during the scroll transition: internal wiring fades first, latch boxes compress towards the stored number, and a row outline expands around them before MAR/MDR and their buses appear. Reversing scroll reverses this collapse. Data feeds run in the gaps between latches and enable rails above them. The address decoder is a compact block on the left. The interface labels its address column “Address”, retains the name “memory”, and places MDR lower with separated D/Q buses and width markers.

Read/Write buttons use the existing memory-control styling. Address and data copies enter the interface registers before the access. Yellow paths and a faint selected-row fill identify the active connection. The flying word follows the corresponding data bus between the selected row and MDR. Read initially returns 6. Write stores 9 at location 1, and subsequent Read returns 9. Accesses finish and hold. Buttons disable during a transfer, remain keyboard accessible, and announce completion through the existing live region. Earlier memory controls and the timing figure retain their behaviour.


[Script](./script.md) · [Plan](plan.md) · [Shared style guide](../../shared/style-guide.md) · [Original handover](../../archive/before-reorganisation/HANDOVER.md)

This records the original nineteen scenes and the chapter 5 extension and provides a place for future direction. It does not implement the planned chapter names or change the artwork. Short cues stay beside the prose in `script.md`; detailed sequence, prompts, alternatives, and technical notes belong here.

## Chapter 5 opening — 2026-10-16

The chapter begins with `computer-overview`, a still block diagram matching the later building-block colours. A red processing unit and blue control unit sit inside the CPU, with green memory below and orange I/O above. Simple register and ALU shapes preview processing, with PC and IR inside control. Two-way links show the main connections. Labels stay minimal and there is no bottom caption. It then looks inside the working registers. The existing `select-values` loop follows the registers, immediately before the ALU, with its selected output visibly connected to an adder. The text recalls memory’s read-selection multiplexer instead of introducing the concept again. The register bank and its caption fade during this selector view and return for the ALU. The compact memory block fades at `computer-overview`. Timing remains after heat and before Memory. Public builds still end at `memory-buses`; Vercel previews retain chapter 5.

## Memory typography — 2026-10-16

Signal names and numbers now follow the shared typography rules in STYLE_GUIDE.md. `D`, `Q`, `WE` and `ADDR` use one code font at medium weight, with bold tabular digits for values, stored words and row addresses. Bus widths and the adder equation use the code font too. Descriptions such as Memory, Decoder and 4-bit register retain Barlow. Small port labels stay small inside repeated latch boxes. The compact memory block has D and Q just inside its boundaries, centred descriptive text and no yellow overlays or read caption. Write prose names the AND gate and the number at D; read prose identifies the chosen word at Q. Animation logic and the timing figure are unchanged.

## Adder replay and wire alignment — 2026-10-15

This supersedes the earlier one-time adder hold. Each entry into `stored-answer`, from either direction, restarts a short sequence. Write `1001` to row `01`, turn WE off, then fly copies of that row’s digits down to Q to read the answer. Finish holding that read result, without looping while the reader stays in this section. The compact bus view retains the completed answer. Earlier manual array choices and contents remain independent and persist. The adder’s four output wires use the same base stroke as the memory wires, with no separate width override. Its result digits shift twelve drawing units right, and flying write copies start from those shifted digits. No prose or timing changes.

## Address notation — 2026-10-15

Use `ADDR` for address references throughout the guide, with inline code styling in prose and the existing code font for diagram input labels. Keep the term word-addressable. This changes notation only, with no animation or memory behaviour changes.

## Established direction

Thin, restrained line art on warm cream. A sticky illustration accompanies prose and transforms as the reader scrolls. Physical objects become cross-sections, circuit symbols, and larger logical blocks. Preserve this continuity. Use Barlow for diagram labels and JetBrains Mono for bit values and the hollow-boron / filled-phosphorus convention.

Scenes **0, 1, and 2 are fixed** unless Aidan explicitly asks to change them. Their timing, geometry, motion, and shadows are part of that protected artwork. Discuss creative or structural approaches before implementation; a specifically requested small fix can proceed. When asked to audit, inspect and report without editing.

## Scene directory

Scene keys match the script's editorial markers and `data-scene` in the HTML. Indices match the current JavaScript; chapter numbers are separate.

| Index | Key | Existing drawing / purpose | Detail |
| --- | --- | --- | --- |
| 0 | quartz | Rotating 3D quartz cluster; begin with material | Fixed |
| 1 | ingot | Growing silicon ingot | Fixed; wafer is hidden during this state |
| 2 | wafer | Slice, turn edge-on, and move towards a cross-section | Fixed; preserve the hand-off into scene 3 |
| 3 | boron | Wafer cross-section seeded with hollow boron circles | Deterministic scatter |
| 4 | implant | Filled phosphorus dots enter two doped pockets | No trapezium guns; preserve dopant convention |
| 5 | wires | Two contacts and insulated gate arrive | Label only what the prose introduces |
| 6 | voltages | 0 V left, 1 V right and electron-energy slope | Curve remains inside silicon as an energy analogy, labelled below the slab |
| 7 | blocked | Gate at 0 V; dots meet the energy hill | Original curve placement and particle paths retained at Aidan’s request |
| 8 | flowing | Gate at 1 V lowers the hill; dots flow and bulb illuminates | Electron direction and energy convention now match the prose |
| 9 | symbol | Transistor symbol at left; ON/OFF wire equivalents at right | Separate control gate; continuous path at 1 V, visible gap at 0 V |
| 10 | switch-types | N-type and p-type symbols with open/closed path comparisons | Opposite responses at gate inputs 0 V and 1 V |
| 11 | not | Complementary transistors form an inverter | Raised A/Ā labels, values below; two-state yellow supply-connection loop |
| 12 | nor | Two series p-type switches above two parallel n-type switches | Four cases; output 1 only for 00; yellow complete conducting routes |
| 13 | nand | Two parallel p-type switches above two series n-type switches | Four cases; output 0 only for 11; truth tables in prose |
| 14 | nand-symbol | Four transistor symbols shrink as the NAND outline draws around them | Connecting wires and their labels fade early; bubble and terminal stubs appear smoothly |
| 15 | adder | Three-input, two-output full-adder block | Keep bold current digits, carry labels, and the idle NAND-tiling sequence |
| 16 | chain | Four ripple-carry blocks | Worked example 0011 + 0110 = 1001 |
| 17 | heat | Adder, heat marks, and P ∝ C V² f | Preserve the proportionality sign; red heat accent is existing artwork |
| 18 | timing | Existing abstract wire grid and travelling pulse | Paragraph and drawing unchanged |
| 19 | latch | Gated D-latch circuit with drawn feedback wires | Inputs D and WE, output Q |
| 20 | register | Original latch shrinks into a one-bit block; four aligned copies share WE | Preserve the zoom-out and stacking continuity; loop enabled copying and disabled holding |
| 21 | memory-two | Add a second four-bit row with address-selected reading and writing | One address bit; read AND/OR selection; writing gated by WE |
| 22 | memory-array | Extend the same wiring to four four-bit rows | Two-bit decoder; address width differs from word width |
| 23 | stored-answer | Four adders feed the sixteen-latch memory array | Fixed 0011 + 0110 = 1001; write row 01, read row 01, then hold; replay on entry |
| 24 | memory-buses | Array contracts into a memory block; parallel data wires converge into a bus | Slash 4 means four wires; slash 2 on address; WE is one wire |
| 25 | computer-overview | CPU, unified memory and I/O | Chapter 5 opening |
| 26 | working-registers | Eight sixteen-bit LC-3 working registers | Existing chapter 5 draft |
| 27 | select-values | Four-bit multiplexer feeding an adder | Reused after working registers |
| 28 | alu | ALU connected to registers | Existing chapter 5 draft |
| 29 | addressed-memory | Address-selected memory | Existing chapter 5 draft; MAR to discuss next |
| 30 | program | Instructions, PC and IR | Existing chapter 5 draft |
| 31 | control | Decoding and control | Existing chapter 5 draft |
| 32 | execute | ADD R0, R1, R2 | Existing chapter 5 draft |
| 33 | computer | CPU, memory and I/O | Existing chapter 5 draft |


## Switches and gates — expanded teaching sequence

The symbol scene shows the same n-type MOSFET as a circuit symbol and as two ideal-wire equivalents. The gate remains electrically separate from the path. An on path is continuous, while an off path has two blunt ends with a visible gap. Joined ideal wires share a voltage once settled. Do not relabel voltage as electron potential energy or reuse a hill/valley encoding with the sign reversed.

The new `switch-types` scene compares n-type and p-type before Logic begins. The two symbols then move into the NOT circuit. NOR adds one of each type with series p-type and parallel n-type connections. NAND rearranges the same four symbols with parallel p-type and series n-type connections. Input controls stay separate from the output wiring. A wire crossing without a junction uses a small bridge.

NOT loops over 0 and 1. NOR and NAND loop over 00, 01, 10 and 11, holding each case for 2.4 seconds before a smooth change. Yellow marks only direct conducting routes from a supply rail to the output, including both routes when both parallel switches conduct. Leave segments leading into unused branches black. In NAND with A = 1 and B = 0, the highlight joins the right-hand p-type switch directly to the output and stops before the central junction on its left. Apply the same rule to the right-hand n-type route in NOR. Input-control wires remain black. Old wiring and labels fade before the next set appears while the transistor symbols move. Loops pause during scroll transitions and reset only when hidden. Reduced motion keeps a stable first case, and the prose truth tables include all cases.

The NAND-symbol scene includes a small reference row below its caption. NOT has two equivalent variants, a standalone inversion circle and a triangle with an inversion circle. AND, OR and NOR follow. Each NOT variant has one input; the others have two. The row fades in after the NAND symbol and fades away before the adder is assembled.

The changing input and output digits use 16 SVG units and weight 600. Captions retain the approved 13.5-unit typography. The prose tables fit the text column on both desktop and mobile.

Primary checks for the mechanism are [MIT 6.004 CMOS annotated slides](https://ocw.mit.edu/courses/6-004-computation-structures-spring-2017/pages/c3/c3s1/) for complementary switches and supply connections, and [Michigan's circuit introduction](https://www.eecs.umich.edu/courses/eng100/circuit_intro/index.html) for equipotential ideal wire nodes. The article wording and geometry are original.

The first D-latch retains its seeded input sequence and slow WE cycle. WE has a soft yellow background only while it is 1. D briefly flashes green for about 0.65 seconds whenever its value actually changes, in either direction, even while WE is 0. Q has no coloured background. When an enabled change updates Q, a copy of D flies in a small arc above the circuit to Q, then the output digit updates. Unchanged values do not fly. The presentation settles before writing closes and holds the stored value through the repeat boundary. The first four-bit register uses the same brief flash independently for each changed D input. Its latch boxes contain only port labels, with input digits above and output digits below. Internal stored digits reappear smoothly when the second memory row is introduced.

## Memory array — current sequence

The latch’s NAND feedback circuit shrinks into the first D-latch block. Three copies form a four-bit register. The same first row remains as a second row appears, then two more rows. Per-row write AND gates combine selection with WE. Per-bit read AND gates feed a column OR gate, so inactive rows do not short their Q outputs together. A NOT/direct selector for two locations grows into a two-bit, four-output decoder. The prose introduces the decoder at the two-row stage, explaining that it turns the address into a separate selection signal for each row, with only one active. Its enclosure is centred around the two or four output rows, with a clear caption gap. Address digits sit individually above their wires, and WE labels and values share the same horizontal centre. Reading uses the address even when writing is disabled.

The original adder sum remains 0011 + 0110 = 1001. Four full-adder blocks connect to the four data wires above the same array. The loop reads row 00, reads 01, selects 10, writes 1001 with WE = 1, holds with WE = 0, then reads row 11. Stored data survives repeats. The two-row demonstration writes row 1 instead. Values carry into the larger array when rows are added. Yellow indicates selected read/write routes, not logic 1. Digits stay visible and change directly, without flashing. Phase labels identify Read, Write and Hold.

At the end, the array shrinks into a memory block. The four parallel adder-to-memory wires converge onto a thick bus. The diagonal slash and number 4 indicate four separate wires, not a physical cut. Address uses two wires and WE one. The same read/write loop continues in the compact view. Reduced motion shows a static held answer. Demonstrations pause when their scene or the page is inactive and are killed on navigation. Timing geometry and choreography are unchanged.

The latch swaps the lower-left NAND inputs to avoid the unnecessary WE crossing. Its feedback keeps one compact crossover, marked with a bridge, at Aidan’s request. The register’s shared WE wire sits below its output digits. The register title, array headings, status captions and decoder labels have extra clearance. In the array, write gates sit below the row-selection wire. Read lanes descend directly from the row AND gates to balanced OR-gate inputs, without the earlier horizontal detours near the bottom. Columns have more space for the separate lanes, and rows have more clearance between selection and write-enable rails. The write AND output runs straight across its row. Small dots mark actual branch junctions. The two-row collector has two symmetric inputs and the four-row collector has four evenly spaced inputs. All selected memory routes occupy one overlay above the base wires, including during expansion. Later computer paths use the same layering so the multiplexer’s unselected base wire cannot cover the selected output. The shared yellow stroke, width and glow are recorded in the style guide and implemented in one CSS rule. Output labels fit within the stage, including the adder view. The model and article wording are unchanged.

`web/memory-model.js` defines the repeatable read/write behaviour. `web/memory-scenes.js` draws the array and bus transitions. The company runtime uses the same model and drawing code as ES modules. The supplied references are ETH lecture 3 slides 116 and 118, using three bits per word; our original artwork uses four for continuity with the adder. The earlier LUT/FPGA material remains saved under `drafts/`.

Verification covers all read/write/hold phases and the repeat boundary, preservation of existing rows while expanding, forward and reverse reading, the four-wire-to-bus transition, mobile layouts without horizontal overflow, and a static reduced-motion view. The temporary pinning helper is removed. The production build retains the expanded memory chapter and ends at timing; chapter 5 remains excluded.

## Adding visual ideas

For a proposed change or a new scene, use a matching heading here and record:

1. **Teaching purpose:** what the reader should understand.
2. **Starting state and ending state:** what remains recognisable between them.
3. **Action:** what moves, changes, appears, or is selected, and why.
4. **Labels and encodings:** text, symbols, units, colour meaning, and correspondence with the prose.
5. **Direction or prompt:** a plain-language drawing brief; put generation prompts here when needed.
6. **Open decisions and verification:** alternatives, approval context where required, and the states/transitions to inspect.

Prefer editable geometry for circuit diagrams. Do not regenerate the first three scenes as illustrations. Keep candidate assets separate from selected assets within `assets/` when those assets exist.

## Animation rules

- Nothing pops on or off. Use a fade, draw, or continuous transformation.
- Lines that join must visibly meet; no partial drawing followed by a sudden complete path.
- Diagram captions are at most 13.5 SVG units. The current digit in bit strings is weight 600.
- Check both forward and reverse scrolling, settled states, idle loops, and the transitions around a changed scene.
- For reduced-motion and static reading improvements, agree on the approach first; the prototype's existing support has not been comprehensively audited.

## Implementation notes

`web/main.js` contains the 3D renderer and scroll mapping. `web/scenes2d.js` builds the paused GSAP timeline for the physical-device and logic scenes, including the register and stored-answer illustrations. `web/computer-scenes.js` supplies the timing and chapter 5 scenes. `web/style.css` contains diagram and page styles. The preview now builds article HTML from `script.md` using `tools/build_post.cjs`; the animation files remain separate from the prose builder. `web/scenes.json` records the required scene order. Updating that manifest alone does not implement or retime an animation.

The page exposes `window.__demo` with `state`, `ctl`, `parts`, and `d2`. The SVG uses a 440 × 440 viewBox; 2D captions sit at y=380. `ctl.hold` defaults to 0.18, and the responsive breakpoint is 640px.

The first three drawings retain their original choreography. Later progress mapping holds each drawing through its associated text and transitions in the gaps. Check actual layout after text edits, especially the long NAND section with its tables.

Use the existing `draw()` helper for progressive paths. `stroke-dasharray` drawing can break under non-scaling strokes. Tween plain objects and apply geometry through `afterRender`; avoid positioning from `onUpdate` inside the scrubbed timeline. Preserve `prime(tl)`, which prevents a flash of all diagrams on initial load. The original handover contains the full helper reference.

## Verification recipe

Run the site, then use the page console or an authorised browser-development interface to detach scrolling and pin the affected scene. A viewport resize can recreate ScrollTrigger, so detach it again after resizing.

```js
ScrollTrigger.getAll().forEach(st => {
  gsap.killTweensOf(st.animation);
  st.kill();
});
__demo.state.progress = 14; // integer: settled scene; 13.5: transition
gsap.ticker.tick();
```

For real-time idle loops, use `gsap.ticker.lagSmoothing(0)` and tick/wait/tick. Inspect screenshots and the visible labels; use SVG bounds and computed opacity where needed. Check the console. Reload afterwards to restore normal scrolling. Do not claim a pinned-scene audit when only normal scrolling was checked.

Optional PNG capture support remains in `serve.js`: start with `SNAP_DIR` pointing to an existing capture directory, then send a PNG to `POST /snap?name=...`. See the archived handover for SVG/font serialisation details. Verification screenshots should normally go in a temporary directory rather than the published asset folder.

## Handover corrections

The original file is retained unchanged as historical reference. Since it was written:

- JavaScript filenames were restored from `.js.txt` to `.js`.
- The source prose file supplied was `From_sand_to_blog.txt`, not `From_sand_to.txt`.
- The live heading already reads “Programmable logic”.
- The live prose uses “islands”; the scene 7 caption was also corrected to “islands” at Aidan's request.
- The separate prose draft names the carry-in earlier, while the live page still uses its original wording.
- The current folder has no `.claude/launch.json`; that is unnecessary for the local preview.
- The Markdown publisher uses a bundled, MIT-licensed copy of Marked; no package installation is required. Runtime animation scripts and fonts still load from CDNs. It uses small existing colour accents as well as monochrome line art.

The original folder reorganisation preserved all five runtime files byte-for-byte. The later Markdown integration generates `index.html` from `script.md` and updates `serve.js`; `main.js` and `style.css` remain unchanged. The subsequent approved scenes 6–8 revision updates voltage labels and the energy explanation in `scenes2d.js`.

## Scenes 6–8 decision — 2026-10-12

Keep the energy curve in its original position inside the silicon so the dots visibly meet the barrier. Do not move it to a separate graph. Label it “Electron potential energy” below the slab. The animated path is an energy analogy. Keep 0 V on the left wire and 1 V on the right wire, and gate 0 V off / 1 V on. Keep the original dot paths, smooth curve morph, fades, and bulb loop. The obsolete electron-direction footnote is removed. Pinned settled states and fractional transitions were checked in both directions, including entry from wires and exit to the symbol.

## Scene 17 — register, 2026-10-12

Aidan approved the paragraph and asked to preserve zooming out and stacking. Keep the existing latch visible while it shrinks around SVG origin 220,250 into the first block centred at 100,246. Draw a box around it, then fade the internal circuit into the D/Q/one-bit abstraction. Three copies emerge from that block into centres 180, 260, and 340. Their shared WE wire draws last, joining each block at a separate lower input. D enters above and Q leaves below. No clock-edge triangle is used. The four blocks form a level-sensitive register, not an edge-triggered register.

The prose and diagram introduce grouping and shared write-enable. Scene 17 introduces the grouping; scene 18 adds the demonstration with the answer 1001. The original scene-16 latch drawing is preserved, and reverse scrubbing restores it exactly.

Verification completed with settled scenes 16–19, fractional points through the latch/register transition in both directions, the revised register exit, and normal navigation between latch and register. No warnings or errors in the final browser run. Builder checks pass. `main.js`, `style.css`, and scene code before scene 16 are unchanged. The previously recorded wider scroll-alignment issue remains pending.

## Scene 18 - storing an answer, 2026-10-12

Keep the scene-17 register group and shift it down by 32 SVG units, fading the one-bit abstraction labels as current values enter beside D and Q. Bring four full-adder blocks into view above it, preserving plus signs and right-to-left carry direction. Draw four individual answer wires into the same D inputs.

A one-shot timeline starts once scene 18 settles. It copies 1001 from 0011 + 0110 with WE=1, then fades WE to 0. The equation and input digits stay at the original 0011 + 0110 = 1001 throughout, following Aidan’s simplification request. Output digits stay at 1001 after copying. All changing labels fade. The final comparison stays visible. Scrubbing away pauses the demonstration; it resets only once its overlay is fully hidden, avoiding a visible reset during reverse scrolling. The storeDemo timeline is exposed with the other demo objects for pinned verification.

The four register cells are level-sensitive latches, not edge-triggered flip-flops. Travel dots illustrate propagation of an answer, not electron trajectories or an extra clock. The original arithmetic drawing is unchanged.

Verified the pinned copy, hold, and changed-calculation states, both directions of the register transition, the retained LUT/FPGA scenes, and automatic playback and replay through normal article navigation. The final browser log is clean and all seven builder tests pass. The wider scroll-alignment issue already recorded in the plan remains pending.

## First-version ending

On 2026-10-12 Aidan approved ending the opening at the stored-answer demonstration, followed by the agreed closing paragraph. The exact LUT/FPGA animation fragment is saved under `drafts/programmable-logic-scenes.js`. The main diagram timeline has an explicit endpoint at 18 so the final demonstration still runs after those later scenes are removed. It resets only when scrolling back before its entrance.

Ending verification passed with scene 18 pinned and in normal scrolling. The final automatic demonstration reaches WE=0, new answer 0111, and saved answer 1001, and remains visible beside the closing paragraph. Reverse navigation restores the register. Browser warnings/errors are empty, all seven builder tests pass, and the saved prose/animation match the removed material exactly.

## Caption style and NAND zoom-out labels, 2026-10-12

Aidan selected the “4-bit register” typography as the reference for diagram captions. All captions now use that same unoutlined rendering. The heavier appearance came from the muted drawing rule adding a stroke to letters; text and text descendants are now excluded from that effect. Intentional size differences for terminal labels and bold current digits remain. The large NAND symbol keeps A/B/out in scene 12, then fades those labels away during the first 35% of the transition into the full adder. Reverse scrubbing restores them. Verified pinned scenes 12, 12.3, 13 and 17, including reverse navigation; computed caption styles match and the browser console is clean. Article prose is unchanged.

## Simplified final memory display - 2026-10-12

Aidan requested no changing calculation. Keep only 0011 + 0110 = 1001. The one-shot demonstration copies the answer, changes WE from 1 to 0, then holds. Current input digits sit beside D and output digits beside Q, aligned on the same baselines. The WE label shifts slightly left as the diagram expands so its value fits on the same baseline before the shared wire. All labels restore when scrolling backwards. This supersedes the earlier changed-input demonstration.

Final display refinements: show 0011 and 0110 bit-by-bit above their respective adder input wires, retaining the full sum at the top. D and Q sit beside their current values. After Aidan’s alignment adjustment, their local baselines are 229 and 270 (one SVG unit above the original), while the numbers remain at 262 and 303 in the overlay. WE and its 0/1 value are inline. Verified pinned copy and hold states, the unchanged sum and input mapping, normal playback, and restoration of register labels. Browser console is clean.

Aidan requested removal of the bottom copy/hold captions from the final scene. Only the inline WE label and changing 1/0 remain. Verified with scene 18 pinned, with no browser errors.

## Chapter 5 implementation — 2026-10-13

The current manifest contains 28 scenes after Aidan requested removal of the binary-place-value figure and paragraph. The original chain, heat, latch, register and stored-answer use indices 14–18. Their geometry is retained. Timing is index 19 and closes memory before the transition paragraph. Chapter 5 occupies indices 20–27 through select-values, working-registers, alu, addressed-memory, program, control, execute and computer.

`web/computer-scenes.js` builds the new editable SVG diagrams using the existing helpers. The selector loops between selection 0 passing 3 and selection 1 passing 6. Digits and routes fade smoothly during changes. It redraws the upper route on returning to 3, then holds an identical state on both sides of the repeat boundary. It pauses away from its scene and shows a still selection of 3 with reduced motion. Timing now uses an abstract wire grid with twenty bit values. Green highlights mark 1 and red highlights mark 0. Yellow pulses branch from the top-left input, travelling with different delays. Fifteen digits and their colours crossfade as the pulses pass; five retain their values. The pulses fade and the final values remain still. The figure contains no headings, captions or input label. The grid has no gate outlines, register or clock waveform. The register demonstration widens the represented value to sixteen bits, followed by eight LC-3 working registers. The ALU and addressed memory join that arrangement. PC/IR and a controller lead into the one-shot ADD trace and the complete CPU/memory/I/O view. Glows use translucent fills so labels remain readable. Fetch paths stay clear of the inactive I/O devices. The source values remain 3 and 6 and R0 captures 9.

The abstract timing illustration and Aidan's supplied timing paragraph are the approved overview treatment. The section now sits immediately before the transition paragraph beginning “We now have circuits that calculate and circuits that remember.” The stored-answer drawing fades before the grid appears, and the grid fades before the multiplexer appears. This is a conceptual picture of propagation, not a literal netlist or logic simulation. Clocked capture, latch-pair construction, glitches, setup/hold, skew and verification methods are reserved for the deeper article. The earlier write-enable latch diagrams remain unchanged. Original memory sum 0011 + 0110 = 1001 remains fixed.

`web/scroll-progress.js` maps the reading line to the actual content bounds. Later diagrams hold while their prose is being read and transition through the spaces between passages. The protected opening retains centre-to-centre choreography. Forward/reverse and long-text behaviour are checked by `tools/scroll-progress.test.cjs`, in addition to browser verification.

The multiplexer repeats while its scene is active. The other new demonstrations play once per visit. They pause during scene transitions and reset when fully hidden. The final computer retains the ADD result. Reduced-motion code selects settled demonstration states. Company-page cleanup kills their timelines on navigation. The protected geometry and first three scenes remain unchanged.

The timing revision was checked with its scene pinned at the start, during propagation and after settling. The incoming and outgoing transitions were inspected in both directions, together with the restored direct full-adder-to-chain transition. The grid fits at 1280px, 938px and 390px widths; mobile has no horizontal overflow. A temporary reduced-motion fixture confirms final digits and no pulses. All temporary browser helpers were removed. The existing eleven writing checks and four portable scroll checks pass.

2026-10-14 verification checked both multiplexer selections, matching states immediately before and after the repeat boundary, and the second cycle. Timing was checked at its new index 19, with the stored-answer drawing hidden. The two incoming/outgoing transitions and mobile layouts were inspected. A temporary reduced-motion fixture shows selection 0 and output 3 without a loop. All temporary pinning and fixture files are removed.


## First four-bit register write loop — 2026-10-15

The `register` scene has its own repeating eighteen-second demonstration. WE starts at 0. Inputs change while outputs retain 0011, then WE becomes 1 and the full shared enable wire, including all four branches, fades yellow using the established signal style. Copies of changed input digits curve around the latch blocks to the output digits. Unchanged bits stay still. A second input change while WE remains 1 repeats the transfer. When WE is 0, changed inputs do not update the stored word. Later enabled writes return the register to 0011 before the loop restarts, so repetition never silently clears the memory. The current stored word carries into the next two-row diagram. Original input digits remain visible throughout. Moving copies fade gently in and out. Playback pauses during scroll transitions and offscreen, using the existing lifecycle. The first single-bit latch, subsequent memory demonstrations, prose and timing figure are unchanged.

### Complete memory gate input highlights — 2026-10-15

The selected row’s yellow read route includes each short selection branch into its read AND gates and the selection input of its write AND gate. These stay lit during reading even when WE is 0. All WE input branches light while WE is 1, but only the selected row’s write output, latch enable branches and data path light. Decoder output segments join the row rail without a gap. Highlights retain the shared signal style and foreground layer. This applies to the two-row, four-row and adder views, without changing circuit geometry, prose or timing.

### Manual memory reads and writes — 2026-10-15

This supersedes the earlier loops in `memory-two`, `memory-array`, `stored-answer` and `memory-buses`. The first single latch and four-bit register continue looping.

The two-row and four-row diagrams start with a static Read of address 0 or 00. Beneath each figure, one row of Read buttons and one row of Write buttons offer every address. Use native buttons with the brand code font, thin outlines, a soft yellow selected background, visible keyboard focus, and a minimum 44-pixel height. All four input bits stay visible above the array. Selecting Write sends copies of 1001 into the chosen latch row. Selecting Read sends copies of that row’s four stored bits to the Q outputs. Original digits remain visible, copies fade in and out, and destinations update on arrival. Only the chosen word is written. Reads retain all stored contents. Selection stays highlighted and the action stays still after its one-time transfer. Clicking again replays it. During the short transfer, buttons wait until it finishes before accepting another action. Each figure keeps its own choices and words when revisited, and expansion seeds new rows without erasing prior writes. A transfer in progress completes when leaving its diagram so a write is retained on expansion.

The adder example automatically writes 0011 + 0110 = 1001 to the second row, address 01, once. It then sets WE to 0 and holds. It has no buttons or repeating address cycle. The bus view carries the same held result. Yellow routes keep the shared style and semantics. Controls fade and the illustration moves smoothly to make space beneath it. Mobile sizing leaves room for all eight buttons without horizontal overflow. The timing figure and paragraph are unchanged.


## Processing unit, instruction and simple control

The existing PU gains a faint red frame. It shrinks to the right, rises while green memory moves down, then slides into the upper-left slot above memory. The reverse scroll follows the same route. The detail view unfolds by moving right, descending clear of memory, then growing below the corner overview. Keep both miniature labels readable. Fade detailed numbers into the PU silhouette, with no overlapping building blocks.

ADD R0, R0, R3 separates operation, destination and two inputs. The simple CU sends thin dashed muted-red control signals into the top MUX selection ports, ADD, destination and WE. The earlier adder and ALU use the same top ports and R labels. Selected data routes retain the shared yellow highlight. The controlled example reads 9 and 2, returns 11, holds R0 at 9 until writing is enabled, then saves 11 and holds it with WE off. The explanatory sequence is not a clock-cycle diagram. Its loop pauses outside the scene and restarts on entry. IR, PC, FSM and clock are deferred.


## Instruction encoding refinement — 2026-10-16

Show ADD R0 R0 R3 without commas in the figure. Beneath it, align the exact LC-3 bits 0001 / 000 / 000 / 0 00 / 011 with the names. Upper and lower curly braces frame each group, with small role labels below. The format group is accounted for in the prose without developing immediate arithmetic. AND and NOT sit above ADD, R7/R6 above R0 and R2/R1 above R3, with decreasing opacity upwards. These alternatives are possibilities, not changing operands during the example. Fade annotations before the selected names move to the CU. Preserve all existing control and write-enable behaviour.


## Control-path refinement

In instruction-control, the CU write-control path enters the horizontal centre of the top of the register bank. Omit its WE label, numeric value and label tint. The control-path emphasis and enabled save still occur at the same times. The fast storage registers caption moves beneath the bank, while earlier register figures retain their existing caption placement. ADD sits just above its right-hand ALU control input. Remove write R0. A faint full sixteen-bit instruction is centred above the readable ADD R0 R0 R3.

The standalone instruction introduction has no pulsing fields. In the control demonstration, the two source fields glow during selection and input transfer, ADD during calculation, and the destination only while writing is enabled. R0 still holds 9 after the returning result arrives and changes to 11 during the enabled write. This is a staged explanation, not a clock-cycle trace.


## Stored program, fetching and sequencing — 2026-10-17

Supersedes the older addressed-memory/program/control/execute/computer draft. Keep the approved simple CU intact. Its following scenes rebuild the machine progressively rather than dropping in the complete datapath. Fade the old miniature memory and PU views as memory becomes a table. Store ADD R0 R0 R3 at decimal addresses 12288 and 12289 and show data 6 separately at 16384. All memory locations retain their bits throughout fetching.

Introduce PC then MAR, animate the selected address, then introduce the +1 connection, MDR and IR. Address and instruction copies travel along the shared thick data paths, with the established yellow wire overlay exactly on the base route. MAR holds the current address while PC advances. Pause on the fetched instruction. For execution, add a compact red PU showing only R0 and R3, with other registers and selectors hidden inside its boundary, beside a simple CU. Copy both inputs towards the ALU, then return the result to R0 during the enabled capture. No WE label or numeric annotation is added to the control lines.

The combined sequence replays the full example from 9, fetches both instructions, and holds at 13 with PC pointing to 12290. The CU highlights fetch/decode/execute groups and a regular clock pulse accompanies enabled register captures. These groups summarise many real microsteps. They do not assert an exact LC-3 cycle count. All new demonstrations pause offscreen and replay when their passage is revisited. Reduced motion displays the completed state. The final frame groups the red PU with the blue CU as CPU. The CU boundary contains PC, IR and the controller. The green memory boundary contains the memory array and its MAR/MDR interface. Input and output remain outside these coloured groups. Preserve earlier memory, latch and ALU animations and the public publication boundary.


## Control and memory grouping correction — 2026-10-17

Aidan requested the blue CU to include PC and IR alongside the controller, and the green memory group to include MAR and MDR. The blue outline now expands from the register band into an L-shaped boundary around the controller, excluding the red PU. The green outline groups the memory interface and array while excluding I/O. CPU groups the red PU and blue CU. Controller is the name of the smaller internal box. Transfer routes are aligned to the adjusted boundaries, with the existing timing, values, write captures and publication boundary preserved. Both scripts and the portable runtime are coordinated.


## Simplified, spaced computer layout — 2026-10-17

Aidan requested more room and fewer lines. This supersedes the L-shaped group outlines. Keep the stored-program table only in addressed-memory, then collapse it into a compact rectangular green memory group containing MAR and MDR. Keep the red PU as a small outline and silhouette in the upper-left corner during program and instruction-fetch. Before execute, slide it down while small, then expand below the CU. Its internal wires inherit the same transform as its registers and ALU, and the red control links appear near the end of the expansion. The blue CU is a simple rectangle at the top right, with PC and IR above the controller. CPU groups this CU with the expanded PU. Omit the individual I/O boxes and the drawn PC increment feedback loop from this simplified combined view. The prose still explains incrementing PC.

Use larger twelve-unit binary text and omit field spaces in IR/MDR and their moving copies, retaining all sixteen bits. The initial memory table retains the spaced encoding. Route PC to MAR around the PU miniature. Keep a clear gap between the red control route and the outer data route. Red control paths retain a faint baseline with stronger active emphasis. No model timings, values, source prose, scene order or publication boundary change. The browser check includes the expansion midway, the settled desktop view and a 390px layout without horizontal overflow.


### Orange I/O block

Introduce the small orange input/output block alongside the completed PU, hold it aside through instruction and fetching, then place it above and outside the final CPU boundary with a two-way overview link. Reuse the restrained building-block treatment. This link does not animate during ADD and does not depict the detailed LC-3 I/O interface.

## MUX inputs clarified — 2026-10-20

The register-selection, ALU and simple CU figures now show all eight register data inputs to each MUX. Unselected sixteen-bit buses are faint, and the selected pair retains the shared yellow overlay above the base wires. Both MUXes have more input spacing. One incoming bus per MUX and both outgoing buses have a slash marked 16. The control wires still enter the top selection ports. The R1/R2 and subsequent R0/R3 selections and existing transfers are preserved. The prose briefly defines multiplexing again at the point of use. This local revision supersedes earlier cues that show only the example’s input connections. No scene order or publication changes.


## Controller close-up simplified — 2026-10-20

Supersedes the earlier detailed next-state gate drawing. Focus on two steps, waiting for memory and copying MDR to IR. Show only these two named state cards. Hide the next-state Boolean network inside a small next-step gates block, with two-bit input and feedback buses connected to the state register. Retain the simple NOT/AND output gates and two external control wires, with MDR and IR offscreen. READY still arrives from outside. Preserve the actual timing model, including a clock edge that retains state 00 while memory is busy, READY rising before the transition to 01, and IR capture at the following edge. After capture, the controls turn off, a stable note says that the controller continues, and the example stops until Replay. Do not suggest a direct loop back to waiting. Preserve the zoom from and back into the CU, shared highlights, clock flashes, reduced-motion behaviour, existing scene order and public publication boundary. The prose no longer traces individual Boolean gates or develops a third hold state.


### Controller loop and quieter CU inputs

The controller close-up now repeats its sixteen-second demonstration automatically, pausing offscreen. It holds the completed transfer briefly, then labels the final three seconds as a demonstration restart before returning to waiting. The actual controller model still advances beyond the copy state, rather than looping immediately back to waiting. Remove Replay and its extra figure offset. Reduced motion retains a settled completed view. Show a faint miniature OR/NOT/AND network inside the next-step gates box, keeping the external connections and labels clear.

The second enlarged PU in instruction-control shows only the selected R0 and R3 buses into the MUXes. Fade the unused inputs out during expansion into that scene. Earlier selection and ALU scenes retain all eight faint inputs per MUX. Incoming sixteen-bit slash markers follow the selected ports, so removing unused buses leaves no floating wire-width markers.


### Connected next-step gates and direct control paths

Replace the faint disconnected circuit inset with a full-strength OR, NOT and AND circuit inside the next-step box. Both state outputs feed back to the OR inputs. OR prepares the upper next-state bit, and its inverse combined with READY prepares the lower bit. Each output connects to its matching state-register input, with values showing what is prepared before capture. Keep the simpler prose and sixteen-second demonstration loop. A single real READY/feedback crossing has a bridge. Increase the close-up frame height to 340 and update its zoom centre to preserve alignment. Clock enters the top of the state register and its caption sits above its input.

In the earlier CU figure, use a straight control connection to the first MUX, a single bend to the second, and a single bend from the CU side into the register bank. Remove obsolete control-line hops. Keep the ALU control path on the outer right and all control endpoints unchanged. No other prose, scene order or publication changes.


### Controller label spacing and top arrows

READY and its changing value share one label and font just below the incoming wire, clear of the box border and AND gate. The two yellow step highlights are compact 112 by 35 unit rectangles. Shift the external transfer-control branch left of the load IR label. The two step cards are joined by gently curved forward and return arrows. The return arrow is faint and has no label. Circuit behaviour and timing are unchanged.

The final output AND gate uses the same compact 48-unit height and rounded proportions as the next-step AND gate. Short input bends bring the state signals to its two pins, and its output remains on the existing transfer-control rail.


## Complete illustrative controller cycle — 2026-10-20

Supersedes the partial two-step close-up and its detailed next-state gate network. Show a complete simplified ADD cycle with five states and exactly one highlighted at all times. Request instruction, wait for memory, copy MDR to IR, decode, execute ADD, then request the next instruction. A wait self-loop stays active while READY is low. The register captures the same waiting state on a clock edge, prepares the copy state when READY rises, and advances only at the following edge. Copy controls remain enabled before IR captures, then turn off as decoding begins. The return from execution is part of the instruction cycle, with no demonstration-reset label.

Use illustrative three-bit codes, a compact state register and a single logic-gates block with feedback and outgoing controls. Avoid implying that these are the real LC-3 microstate codes or its full set of states. Preserve the zoom into the controller within the CU and back, the shared yellow wire overlay, offscreen external components and reduced-motion support. Only the controller scene and its prose change. Publication remains public through chapter 5.


The five-state controller uses matching open arrowheads, drawn separately from highlighted shafts so the wait loop keeps a crisp tip. Its execution-to-request arrow returns upward through the space under the request card, avoiding the left frame edge. Loop and next-state-feedback bends are rounded. Preserve the state positions and timing.


### Controller bus widths and circuit backdrop

The current-state and next-state feedback buses have the established thick-bus treatment, a diagonal slash and a 3 marking their three state bits. READY, clock, request-memory, send-MDR and load-IR controls remain individual signals. The logic box contains a faint connected gate network below its labels. Its shared gate netlist decodes states 000 through 100, holds waiting when READY is low and generates the next three state bits and control outputs. A truth-table test checks every valid state with both READY values. The drawing is an illustrative ADD controller rather than the full LC-3 controller. Preserve the existing sequence and animation timing.


Spread the faint controller circuit across the full logic-box height in four evenly separated columns. Space inverted inputs, state-decoding gates and output/next-state gates vertically, with wider signal-rail gaps and a straight copy-state fanout. Preserve the gate netlist, opacity, foreground labels, external ports and timing.


## Four-state controller with merged execution

Supersedes the five-state cycle above. Merge Decode and Execute ADD into a single Execute ADD state. Use a balanced two-by-two layout and clockwise Request instruction → Wait for memory → Copy MDR to IR → Execute ADD → Request instruction loop. Codes 00, 01, 10 and 11 require two state bits, so update both register displays, prepared bits and bus markers to 2. The fifteen-second loop retains the existing memory wait and IR capture timing, then executes from 12 to 15 seconds before returning to request.

The faint circuit has eleven gates. Decode the four state codes, retain the READY hold/advance gates, prepare D0 = request OR hold OR copy and D1 = advance OR copy, and drive PU control directly from the execute-state detector. Remove the old decode-state detector, third state bit and extra processing OR gate. Preserve the spacious faint layout, foreground labels, external ports and smooth zoom. The prose stays unbolded and identifies this as an illustrative ADD controller. The full controller's instruction-dependent choices and the earlier whole-computer decode explanation remain outside this small example.


Centre the three-line Logic gates / control signals / + next step label group at the logic box centre (235, 303). READY and its live value sit above the incoming wire and slightly further right, at (196, 208). This supersedes the earlier below-wire READY placement.


READY uses one shared port for the visible wire and the faint circuit. Convert that port through the miniature circuit transform rather than approximating it independently. Continue the faded input down inside the box before routing left, keeping it distinct from the box border.
