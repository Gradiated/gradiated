# Post 001 — How to get an answer out of sand

**Status:** Chapters 1–5 published through merged PR #715. Further work is local on `first-deep-dive`.

> Current checkpoint, 20 October 2026. The dated entries below are retained history and may describe superseded publication boundaries, branches or two-copy workflows. See the [collection guide](../../README.md) for the current source and editing workflow.

**Historical status:** PR #470 is merged and published. Continued memory and chapter 5 work is on `feat/sand-to-thought-next`. Chapter 5 is approved for public release, with the website publication boundary set to its final computer scene. The latest prose and publication settings are saved in `ee4261e24`. Latest main (`74a2c4e00`) was merged without conflicts and pushed as `52deeca47`, with all 69 website tests and preview/public build checks passing. Recovery branch `backup/sand-to-thought-before-main-2026-10-20` retains `ee4261e24`. No new PR or production merge has been made.

Memory Read/Write and width-expansion animations now resume from their current position after a visibility pause. Three regression tests failed before the fix and pass afterwards. All 72 website tests, typecheck and the public build pass. Saved in `d147215cb` on the same feature branch. The portable animation copy is synchronised.

**Role:** Opening overview and growing guided journey through the library.

**Audience:** Curious newcomers, with routes into deeper explanations for every major subject.

**Current purpose:** Show how physical devices combine into circuits that calculate, remember and follow a stored instruction.

**Next milestone:** Review the new fetching and sequencing scenes, then choose the next instruction example. Detailed branch conditions, the wider instruction set and lower-level controller states remain later work.

**Long-term purpose:** Connect the whole stack, ending with a worked explanation of a computing system generating an AI response.

**Files:** [Script](./script.md) · [Visual direction](visuals.md) · [Website notes](implementation.md) · [Topic map](../../shared/topics.md) · [Library](../../shared/library.md)

## Controller example — current behaviour, 2026-10-20

Inside the controller follows a complete simplified ADD cycle with four states. Request instruction → wait for memory → copy MDR to IR → execute ADD → request the next instruction. Exactly one state remains active throughout. Decode and Execute ADD are merged here, because this example always follows ADD rather than selecting between instructions. The text explains that the full controller also uses instruction bits to choose between different operations. Earlier whole-computer fetching and decoding explanations remain unchanged.

The animation repeats naturally over fifteen seconds. A clock edge at 3 seconds enters waiting, and the edge at 6 seconds captures the same waiting state. READY rises at 8 seconds. The edge at 9 seconds enters copying and enables MDR send and IR load. The edge at 12 seconds captures the instruction in IR and enters execution. The edge at 15 seconds completes execution and requests the next instruction. Slower or absent memory readiness extends waiting in the timing model. This is an illustrative sequence rather than the real LC-3 microstate schedule.

The two-bit state register and both bus-width markers match codes 00 through 11. The four states sit in a balanced loop above the register and logic box. The faint, spaced circuit contains eleven gates implementing the state decoder, readiness wait and two next-state bits. Its truth table is tested for all four states with both READY levels. The zoom into the CU controller and back, shared yellow highlights, offscreen pause and reduced-motion support are preserved. No bold emphasis appears in this section's prose. Chapter 5 remains public. The canonical script, authoring symlink and portable runtime are coordinated. Keep the batch local until Aidan requests a push.

## Stored instructions before control — 2026-10-19

Chapter 5 now explains the instruction fields, then shows the stored-program memory table before introducing the CU’s control signals. PC and instruction fetching follow the CU example. The memory block expands into the table and returns to its corner before the PU unfolds for control. Afterwards the PU shrinks and memory unfolds into the MAR interface for fetching. The Fetching and executing subheading begins with PC. Chapter 5 remains preview-only.

## Current source workflow — 2026-10-18

The company `hardware/publishing/sand-to-thought/articles/sand/script.md` is now the single article source. This folder’s `script.md` is a symbolic link to `hardware/publishing/sand-to-thought/articles/sand/script.md`, so there is no second prose copy to maintain. Edit the canonical path and save. Both local previews read that file, with the standalone builder following the link. This supersedes older instructions to synchronise two scripts or run the authoring-to-company draft sync. Branch changes in the company checkout also change the linked source.

All 43 private Visual cue blocks are preserved verbatim in [visual-cues.md](visual-cues.md). Continue keeping detailed direction in visuals.md. The website content and publication boundary are unchanged. Animation runtimes remain separate and still require coordinated changes. The generated standalone HTML remains portable, while rebuilding elsewhere requires recreating the source link. Commit and push website changes from the company repository when a Vercel preview is wanted.

## Instruction binary fields — 2026-10-16

The instruction scene now explains the full sixteen-bit encoding of ADD R0, R0, R3 as `0001 000 000 0 00 011` (0x1003). Four opcode bits and three bits per register are distinguished from the register values. The middle 0 selects a register operand and the next 00 bits are unused in this form. This is checked against Patt and Patel's [LC-3 ISA Appendix A, ADD, printed page 526](https://www.cs.colostate.edu/~cs270/.Fall20/resources/PattPatelAppA.pdf). Other operations can use the remaining fields differently, so NOT is an opcode alternative rather than a claim that the complete ADD format also encodes NOT. No footnotes are added.

The figure has no commas. Matching curly braces above and below each binary group align the instruction names with operation, destination, inputs and format bits. AND/NOT and alternate register names fade with height above the selected fields. These annotations disappear before the existing instruction-to-CU movement. The CU figure refinements are saved and pushed in `7d7592cd5`. Desktop and 390px layouts, the source-input phase, ADD phase, enabled destination write, normal playback, static introduction and earlier register heading were checked in the in-app browser. All 58 website tests, 11 authoring checks, preview build and DevEx pass. Temporary verification overrides are removed. The introductory fields are now static. The following CU figure repeats the full encoding faintly above the readable instruction and ties field highlights to input selection, calculation and the enabled destination write. Its write-control path enters the top of the register bank, the storage caption sits underneath, the ADD control label sits beside its port and write R0 is removed. The public boundary and all other scenes are unchanged. Both scripts and portable runtime are synchronised. Saved and pushed in `49f7cbd0d`. All 58 website tests and 11 authoring checks pass. The preview build passes. Desktop and 390px layouts, fading into control, the retained write animation and browser console were checked. Temporary scene pinning is removed, and rendered public article HTML is unchanged.

## Chapter 5 instruction and control building blocks — 2026-10-16

Verified in the Codex in-app browser with settled and intermediate scenes pinned, normal playback, reverse scrolling and a 390-pixel viewport. R0 retains 9 before write enable, saves 11 while WE is 1 and holds 11 afterwards. Existing accumulating ALU playback and manual memory behaviour are preserved. All 58 website tests and 11 authoring checks pass, as do full preview/public builds and DevEx. Public article HTML is byte-identical to the previous version, and both scripts render identically. Temporary verification parameters and timing diagnostics are removed.

Three scenes follow alu and precede addressed-memory, in this order processing-block, instruction and instruction-control. The existing ALU keeps accumulating and finishes its current transfer when leaving. Its registers, MUXes, ALU and return path gain a faint red frame. Staged shrink, rise and slide movements avoid the green memory miniature. The red PU sits above memory and remains as an overview while its detailed view unfolds for control.

Instruction fields show ADD, destination R0 and source registers R0/R3. The simple CU has no IR, PC, FSM or clock. It selects the two inputs, ADD and the destination. A fixed 9 + 2 = 11 demonstration returns the result before enabling the write. R0 remains 9 at 6.6 seconds, changes to 11 at 7.4 while WE is 1, and holds 11 after WE returns to 0. Other registers are unchanged. The MUX selection ports and R labels sit above the MUXes consistently in the adder, ALU and control figures. Thin dashed muted-red control paths enter those top ports and are distinct from thick data buses and the shared yellow transfer highlights. The overview labels stay readable rather than shrinking with the circuit.

The register paragraph recalls the memory array's read-selection and write-enable principle without claiming identical port arrangements. Each input selects a source independently and the write selects a destination. Existing later fetching prose and diagrams remain drafts for the next discussion. Publication still ends at memory-buses. Both scripts, scene manifests and portable runtime must remain coordinated, including private visual cues.

## Chapter 5 processing unit — 2026-10-16

Latest behaviour uses six-second ALU transfers, starting with 3 + 6 = 9 and repeatedly adding R3 = 2 to R0. R0 updates when the flying result arrives and remains visible between transfers. A continuous timeline supports arbitrary repetitions, with results modulo 65,536. Active-scene changes restart the example without changing the standalone adder loop. Input and output numbers are aligned to accommodate five digits. Both scripts replace BIDMAS with this running-total example, and both runtimes match. Browser checks cover saved values 9, 11, 13, 1009, 65535 and wrap to 1, large-value spacing, real playback and scroll-away/re-entry reset. All 58 website tests and 11 authoring checks pass. Temporary verification parameters are removed.

Reader-facing figures and chapter 5 text now call the R0–R7 collection fast storage registers, in the plural. The technical description of LC-3’s eight general-purpose registers remains. Stable scene names such as working-registers are unchanged. Both authoring copies match, 38 article tests pass and the longer caption fits the first register and compact ALU figures in the in-app browser.

The ALU text now contains a table of ADD, AND, NOT and PASSA, distinguishing the three operate instructions from the internal pass-through mode. The operation list above the first ALU is removed; ADD inside the block still identifies the active mode. Both scripts and runtimes match. Checked against Patt and Patel’s [LC-3 microarchitecture, Table C.1](https://people.cs.georgetown.edu/~squier/Teaching/HardwareFundamentals/LC3-trunk/docs/LC3-uArch-PPappendC.pdf) and [UT Austin’s ALUK explanation](https://users.ece.utexas.edu/~patt/19f.306/Exams/OldExams/f19_ee306_exam2_sol.pdf), which confirm ADD, AND, NOT and PASSA. Sources stay in planning rather than article footnotes. Desktop/mobile browser checks and the website/authoring tests pass.

The running sum is centred at x349, y143 above the first ALU, closer above the ALU outline. The operation list still names available capabilities, while ADD inside the ALU identifies the active operation. Browser-checked with the ALU scene pinned.

Caption cleanup removes the bottom status line from both input-selection and ALU figures and removes “choose two register values” above the adder. The register-size caption remains in working-registers only and fades before selection. The ALU calculation, input labels and all transfer animations remain. Browser checks and the 38 article tests pass.

The input-selection scene now produces a 9 beneath the adder after 3 and 6 arrive. The result moves smoothly down from the output, holds, and fades with the existing loop reset. It belongs to the adder group and fades out when the ALU replaces it. The portable runtime and visual cue match; browser verification and all 38 focused article tests pass.

Latest visual refinement removes the sixteen small squares and their caption beneath the first working-register figure. The first ALU now has two sloping sides, with input wires and their highlights meeting the outline, and the selection paragraph explicitly names MUX. Both script and runtime copies are synchronised. Saved and pushed in `0b295d45f`. All 58 website tests and 11 authoring checks pass, and the affected figures were verified with scenes pinned in the in-app browser. The latest Vercel deployment has not yet been checked.

The first working-register figure now adds a faint right-hand column with the same values as full sixteen-bit binary numbers grouped in fours. It fades out before the input-selection scene, whose compact layout and animations are preserved. The requested processing-unit wording is applied in both scripts. Saved and pushed in `a5495df20`; all 58 website tests and 11 authoring checks pass, with desktop/mobile and neighbouring-scene checks in the in-app browser.

Saved and pushed in `f7ae586d1`. All 58 website tests, 11 authoring checks, DevEx, diff checks and the full preview build pass. The published article HTML is unchanged, both scripts render identically, and earlier text plus later control-unit prose are unchanged. In-app browser checks covered registers, selection, writes of 9 then 11, intermediate transfer frames, normal/reverse scrolling and a 390px mobile viewport. Temporary pinning is removed. Only the company script, scoped diagram CSS and computer scene runtime changed. No PR or production deployment.

The three approved scenes now form one visual sequence. A sixteen-bit working register expands into eight registers, R0 to R7, alongside the persistent green memory miniature. R1 starts at 3, R2 at 6, and R3 at 2. Two selection paths recall the memory multiplexer, with sixteen-bit buses feeding an adder. The adder becomes an ALU supporting ADD, AND and NOT. A repeating example saves 3 + 6 = 9 in R0, then reads that intermediate result and R3 to save 9 + 2 = 11 in R0. Copies of the numbers travel along yellow paths and R0 updates on arrival; completed transfers fade before the next operation. The example resets softly between repetitions. Existing later computer/control scenes are retained without developing them further, and chapter 5 remains preview-only.

Registers use the familiar bit-storage principle without renaming the earlier D latches as flip-flops. The text connects their quick access to a small collection directly connected to calculation circuits, rather than claiming size has no cost. Eight sixteen-bit registers and LC-3's ADD/AND/NOT operations were checked against the [LC-3 ISA reference, Appendix A](https://www.cs.colostate.edu/~cs270/.Fall20/resources/PattPatelAppA.pdf). BIDMAS motivates retaining intermediate results. Both authoring and company scripts carry this version; no footnotes are added.

## Chapter 5 memory building block — 2026-10-16

After the Read/Write demonstration, a short memory-block transition retains the same memory interface and draws a faint green frame around it. Scrolling into working registers shrinks that framed module to the upper left, fades its detailed labels and values into a simple array outline, and adds a small MEMORY label. This miniature remains visible throughout the rest of chapter 5. Later combined machine diagrams leave space for it. Existing memory controls, timing, and the publication boundary are preserved.

## Chapter 5 memory interface — 2026-10-16

Latest refinement, saved in `3ac77e39d`: the eight-bit latch rows now compress in place into the first eight-bit memory block, with staged fades for internal wiring and the added MAR/MDR registers. Data wires run between latch boxes, the decoder is smaller, MDR sits lower, and “Address” labels the address column. Keep the array named memory, since MAR/MDR are registers and the array contains many locations. The clock diagram and introductory clock paragraph are deferred to control circuits; manual Read/Write behaviour, timing, earlier memory scenes and publication boundary are preserved. Both scripts and portable runtime are synchronised. All 58 website tests, 11 authoring checks and the full preview build pass. Desktop/mobile spacing, continuous forward/reverse morph and read-before/write/read-after behaviour were verified in the in-app browser. Clock capture remains an internal transaction step; only its introductory diagram/prose are deferred.

Implemented and pushed through `3ac77e39d`. There are 39 development/preview scenes; publication still ends at memory-buses, with 25 scenes. All 58 website tests, 11 standalone authoring checks, DevEx, formatting and diff checks pass. Both public and preview build modes pass. Browser verification covers widening, interface and address-range scenes, Read before Write (6), Write then Read (9), existing two-row memory controls, forward/reverse reading, integrated CPU layout and 390px mobile layout without overflow. Temporary pinning is removed. Generated public article HTML is unchanged. Both scripts, manifests, portable runtime and visual notes are coordinated. No production deployment or new PR.

After the unchanged von Neumann introduction, return to the four-location array and widen each location from four to eight bits. Collapse storage cells into four row blocks, then add MAR and MDR as distinct registers on the address and data connections. Keep the initial interface free of clock wiring. Keep WE as the simple memory-write control throughout the overview; MEM.EN and R.W are reserved for deeper treatment. The reader-facing promise to return to control-circuit timing is removed. Widen data/MDR to sixteen bits, introduce a two-byte LC-3 word, then widen MAR from two to sixteen bits to explain the full 65,536-location address range. Address width, bits per location and total capacity remain separate concepts. A processor’s 16/32-bit label does not automatically give its address width.

Aidan chose separate Read and Write buttons. Both use location 1. Initially it contains 6. Write captures address 1 and data 9, then copies MDR into the selected location under WE. Read captures the selected contents into MDR after the response. Other locations remain unchanged, writes persist across button presses, and the example holds after each access. Clock pulses mark register captures. The simplified array omits dense read-gate wiring already explained in chapter 4. No footnotes are added. The timing section and chapter 4 interactions are preserved.

The new scene order is computer-overview → memory-width → memory-interface → memory-word → memory-address-space → memory-access → memory-block → working-registers → select-values → alu → addressed-memory → program → control → execute → computer. Chapter 5 stays preview-only. The later combined machine includes MAR/MDR on its memory connection. Do not describe the array as one CPU register, relabel WE as a clock, or equate a sixteen-bit-wide row with a sixteen-bit address.

References retained in planning, not as article footnotes: [LC-3 ISA memory organisation](https://www.cs.colostate.edu/~cs270/.Fall20/resources/PattPatelAppA.pdf), [LC-3 datapath with MAR/MDR and separate load controls](https://www.cs.utexas.edu/~fussell/courses/cs352h/assignments/project.pdf), [clocked LC-3 control](https://www.unm.edu/~zbaker/ece238/slides/LC3-control.pdf), and [Arm register-width terminology](https://developer.arm.com/community/arm-community-blogs/b/architectures-and-processors-blog/posts/arm-architecture-reference-manual-for-armv8-a-64-bit-publicly-released). The saved study notebook’s MAR/MDR explanation and addressability notes remain the learning reference.

## Chapter 5 opening — current decision, 2026-10-16

The Harvard comparison was withdrawn at Aidan’s request. The opening retains his manual wording about a list of instructions and “unified” memory. The source note is removed from the page, and the article should have no footnotes. Source attribution is retained here instead.

The LC-3 example and the organisation of our computer diagram follow ETH Zürich’s [Digital Design and Computer Architecture course](https://safari.ethz.ch/ddca/spring2026/), particularly lecture 7 and its LC-3 diagram on slide 65. The illustration is simplified to introduce the parts one step at a time.

Harvard comparison reference: [Microchip architectural overview](https://onlinedocs.microchip.com/oxy/GUID-74578654-4F5F-4B29-9F3C-6C3B1F1DF670-en-US-2/GUID-AA5CC158-9A54-4C01-A3E3-47AABEEF987C.html).

The opening now emphasises stored-program flexibility without claiming to solve any finite problem. The program/PC scene briefly introduces sequential execution, jumps, conditional choices and repetition. After the ADD trace, a short paragraph connects one calculation to larger programs. The final computer scene introduces the cost of control and data movement, with memory systems, parallel processors and specialised chips saved for later chapters. GPU, dataflow and TPU comparisons remain deferred. These are prose changes within the existing scenes, with no new animation or scene order changes.

Chapter 5 opens with the whole computer and the von Neumann idea of one memory storing instructions and data. Working registers follow, then the existing multiplexer animation recalls memory’s read-selection circuit while choosing an input for an adder. The ALU and remaining computer scenes follow. The memory explanation already introduces multiplexing adequately and is unchanged. The first mention of a word is in the LC-3 register paragraph, where it means sixteen bits. Chapter 5 stays excluded from the public build and included in local and Vercel previews. Timing remains after heat and before Memory, and the concise memory ending is preserved.

## Resume here — current work and todo

**Active checkout — 2026-10-16:** `feat/sand-to-thought-next` in `the company checkout`, at commit `dac7c95cf` (published-main integration is `06d53025d`). PR #470 was merged into main at `ca3ad93f1` and is published. That main commit has now been merged into this development branch. The original memory work remains preserved at `65040e5d2`. This branch is local only, with no new PR or push.

**Latest local update:** `dac7c95cf` standardises memory typography across the first latch, register, addressed arrays, adder and compact bus figure. Signal names and numbers use JetBrains Mono with consistent role-based sizes and weights; descriptions retain Barlow. Shared style rules and authoring copies are coordinated. All 53 website tests, DevEx and diff checks pass. Pinned desktop scenes and a 390px-wide array were visually checked, with no horizontal overflow; normal scrolling and a write action work with no browser errors. Previous local refinements place D/Q inside the compact block, centre its text, remove its yellow highlights/read caption, and clarify the AND gate, D write input and Q read output in prose. Animation behaviour and timing remain unchanged. No push or deployment.

**Previous adder update:** `a10e0eaa9` — The adder output wires now share the memory wire thickness, and its result digits sit clear to the right. The adder writes `1001` to address `01`, turns WE off, then reads `01` with flying digit copies. Entering the section from either scroll direction restarts this sequence. It finishes on the read result instead of looping. The bus view holds the completed result. The two manual arrays keep their choices and contents. No prose, timing or earlier latch/register changes. Authoring runtime and visual notes coordinated. All 53 website tests, DevEx, diff checks and the local build pass. In-app browser checks verified re-entry from both directions, write and read transfers, settled output, and pinned mobile layout without overflow. Temporary pinning removed. Three company website files changed. Local only, no push or deployment.

**Previous manual controls update:** `538efe519` replaces the two-row (8-bit total) and four-row (16-bit total) memory loops with native Read and Write buttons for every binary address. The selected action and yellow paths remain in place. Four copies of D travel to the selected row when writing; copies of stored digits travel to Q when reading. Stored values and Q update on arrival, reads preserve memory, and each diagram retains its choices and contents when revisited. Clicking the selected button replays that transfer. Buttons briefly wait for the transfer to finish before accepting another action. Expansion carries earlier writes forward. The adder writes 1001 once to the second row, address 01, then disables WE and holds; the compact bus view retains that result. Its paragraph now uses 01. The single latch and first-register loops, other prose and timing are unchanged. Controls fade into reserved space, support keyboard input and accessible result announcements, and fit a 390-pixel viewport with 44-pixel touch targets. Controls, listeners and their size observer are removed on unmount. Authoring files, script and generated HTML are coordinated. All 52 website tests, DevEx, diff checks and the local build pass. In-app browser checks covered every read/write address, digit transfers, persistence, the adder hold, mobile sizing, keyboard operation and route cleanup. Temporary scene pinning was removed. Local only, no push or deployment.

The eight company files included in this update are all under `product/website/`:

- `content/articles/sand/script.md`
- `scripts/sand-memory-model.test.mjs`
- `src/components/articles/sand/journey.css`
- `src/components/articles/sand/runtime/main.js`
- `src/components/articles/sand/runtime/memory-controls.js`
- `src/components/articles/sand/runtime/memory-model.js`
- `src/components/articles/sand/runtime/memory-scenes.js`
- `src/components/articles/sand/runtime/scenes2d.js`

**Previous highlight update:** `b9ae6b6a7` completes missing memory gate input highlights. The selected row now lights the short selection inputs at every read AND gate and at its write AND gate, even when WE is 0. WE lights all its input branches while enabled, while only the selected row’s write output and data routes light. Decoder output-to-row segments are continuous through both memory layouts. The same fix applies to the array and adder views. Prose, circuit geometry and timing remain unchanged. Authoring runtime coordinated. Pinned browser checks covered every address, read and write states, followed by normal playback. All 51 website checks, DevEx, diff checks and the local build pass. Verification hooks removed. One company website runtime file changed. Local only, no push or deployment.

**Previous alignment update:** `0690f9a9c` centres the address decoder around its row outputs and adds more clearance below its caption. Each address digit sits above its own wire, including the single-bit case. WE labels and values share a centre in the first latch, first register and memory arrays. The two-row prose now introduces address decoding on its first appearance, explains one active selection signal per row, and connects the NOT/direct-wire implementation to the address values. The four-row prose refers back to that same decoder. Authoring Markdown, generated HTML and runtime are coordinated. All 51 website checks and the local build pass. The one-bit and two-bit address layouts and register WE alignment were checked with scenes pinned in the in-app browser. Temporary verification code was removed. Only three company website files changed. No push or deployment.

**Earlier wire cleanup:** `43d965f64` simplifies the memory wiring after the register. Columns and rows have more clearance, write AND outputs run straight across their rows, and read lanes descend directly into balanced OR inputs. Junction dots mark real branches. Memory highlights sit consistently above base wires, and later computer paths use the same ordering. One scoped CSS rule and shared colour, width and glow tokens now cover logic, memory, computer paths and timing pulses. The register-to-array landing and adder carry links were adjusted to the new spacing. Prose, read/write behaviour and timing choreography are unchanged. The authoring runtime and style guide are coordinated. All 51 website checks and the production build pass. In-app browser checks covered pinned read/write states, expansion and bus transitions, normal reading and reverse navigation, and the 390-pixel mobile layout without overflow. Temporary verification hooks were removed. Only four company files changed, all under `hardware/publishing/sand-to-thought/articles/sand/figures/`. No push or deployment.

**Previous local update:** `62386474b` adds flying input copies to the first D latch and replaces its persistent D/Q backgrounds with a short green flash on D only when D changes. WE keeps its yellow background while 1. Q stays plain and holds when disabled. The register independently flashes only changed D bits, and its duplicate internal stored digits are hidden until the second memory row appears. The register's existing yellow-enable and flying-copy loop remains in `77cda2822`. The single-latch loop preserves its seeded inputs and slow enable cycle, settles transfers before WE closes, and carries its held output across repeats. The authoring runtime, styles and visual notes are coordinated. All 51 website checks and the production build pass. Pinned states verified enabled copying, disabled input flashes without copying, no flash for unchanged data, selective register flashes, and empty first-register boxes in the in-app browser. Temporary verification hooks were removed. Only five company files changed, all under `product/website/`. No push or deployment.

**Integration verified:** All 42 website tests and the production build pass. The single stylesheet conflict was resolved by preserving both the memory diagram styles and the published theme fixes. Compared with the integrated main, only the eight original memory-work files differ, all under `product/website/`. The memory script, manifest and drawing files match the saved memory commit. Published renderer/component refactors, navigation scoping, Library filter correction and animation behavior are retained. The 33-scene development preview was checked in the in-app browser with the memory array active and no console errors.

**Preview and next action:** Review the expanded memory chapter at [localhost:5173/sand-to-thought/#sand-memory-array](http://localhost:5173/sand-to-thought/#sand-memory-array). Port 5174 remains the older publication-review snapshot. Continue with memory diagram clarity, read/write loops, transitions and bus notation before chapter 5 and MAR. Timing remains unchanged. Production is unaffected by these local changes.

**Draft separation:** This folder’s `script.md`, visual notes and standalone website retain the newer memory work. The company checkout now contains that work plus the published code fixes. No draft-sync watcher is running. Keep review fixes in the company runtime intact when coordinating future illustration changes between the two copies.

The dated publication and review records below describe earlier states. This checkpoint takes precedence.

**PR review cleanup — 2026-10-15:** Commit `a39d8d644` is pushed to `feat/hardware-library` on PR #470. The six human review comments are addressed and their threads resolved. The Markdown renderer has named parsing, validation, publication and footnote steps; the guide uses a stable JSX stage and focused hooks; the obsolete tuning panel and unused Library animated-cover variant are removed; the deterministic cover has separate particle, canvas and lifecycle modules; navigation safeguards are limited to the guide-enabled bar and Library writing list. Public and preview article HTML and canvas drawing commands are unchanged. Thirty-five tests, both builds and in-app desktop/mobile checks pass. Chapter 5 remains preview-only. The PR is unmerged. The saved memory branch at `65040e5d2` is unchanged and does not yet include this cleanup, so integrate the review fixes before resuming it. Keep draft sync stopped.

**Final publication check — 2026-10-15:** The PR branch includes current main in merge commit `258db8646`, preserving its docs/API changes and resolving the generated homepage-image conflicts against the proper Git baseline. Additional fixes preserve single-action hero markup, scope the portalled guide link styling, and make the guide and diagram captions readable in the site’s dark theme while leaving the default cream appearance unchanged. The existing website `pnpm test` command now runs all 35 checks, including publication boundaries, rather than relying on manual commands. Production still has 22 scenes ending at timing; chapter 5 remains preview-only. The production-style preview at port 5174 is refreshed from this work. At Aidan’s request, the new reduced-motion rendering and demonstration changes in `c5ffef535` were reverted in `feb7ca7ae`. The runtime files match their version before that addition; preserve the existing instructional animations. Offscreen visibility pausing and other review fixes remain intact. Latest pushed head is `f1fccce79`, including automated website screenshots and excluding unrelated console captures. All 35 tests and the public build pass, with the restored page checked in the in-app browser. Remote checks are rerunning after the push. No PR merge or production deployment has occurred. The saved memory branch and authoring draft remain unchanged.

**Saved memory work:** The original commit `65040e5d2` is preserved in the active `feat/sand-to-thought-next` branch, now at `06d53025d` after merging published main. The memory chapter now develops one latch → a four-bit register → two addressed rows → four addressed rows → an adder writing into the array → a compact memory block and buses. The two supplied references are lecture 3 slides **116 and 118**; no slide 117 was attached. Four bits per row retain the existing arithmetic example. Reading selects a word without changing it. Writing requires both row selection and `WE = 1`. The loop retains stored data across repetitions. Address width and word width are separate, and this example is word-addressable. The timing prose and figure remain unchanged.

**Publication boundary:** `publishedThrough` remains `timing`. The expanded local production build has 25 scenes, while development has 33 including the chapter 5 draft. No work on this branch has been pushed or added to PR #470. The earlier manual von Neumann wording is preserved in the saved commit `65040e5d2`. PR #470 contains the earlier version and remains unmerged; its recorded checks and bot conversation were resolved before starting this branch.

**Next chapter 5 decision:** Introduce MAR as the register holding the selected memory address, and distinguish it from MDR, which carries the word being transferred. LC-3 is word-addressable with sixteen-bit words. The current chapter 5 prose/figures have not been changed by the memory expansion.

**2026-10-14 — Current review point:** the switch-to-gates explanation has been expanded at Aidan's request. Review the symbol and ideal-wire explanation, the new n/p switch comparison, then NOT → NOR → NAND. The gate animations cycle through every input case and highlight only complete conducting connections to a supply. NOR is 1 when neither input is 1. NAND is 1 when the inputs are not both 1 simultaneously. Two truth tables follow the NAND explanation. Keep voltage distinct from the earlier electron-potential-energy hill. After this review, resume chapter 5 and the chapter 6 discussion below. The first three drawings and all later article prose remain unchanged.

Verification for this update covers all ten pinned gate cases, intermediate construction states, normal forward/reverse reading into the NAND symbol and full adder, a static presentation fixture and 390-pixel mobile layouts. The two truth tables fit without horizontal overflow. Seven builder checks, four portable scroll-mapping checks and the company preview build pass. Temporary verification code is removed. The existing local von Neumann wording edit is preserved separately from the committed gate update.

Company website integration is implemented locally, with [draft PR #470](https://github.com/Gradiated/gradiated/pull/470) available for review, on `feat/hardware-library` in `the company checkout`. Review [Sand to Thought](http://localhost:5173/sand-to-thought/), the new top navigation destination immediately after Library. Its dune-to-circuit artwork is followed directly by the approved article text and illustrations. The docs-style sidebar jumps to Introduction, Sand and metal, Logic, Arithmetic and Memory, with a compact contents control on mobile. These links are generated from the script’s existing headings. The former article address redirects to this page. Library now contains Notes and Methods. The guide is prepared to publish chapters 1–4. Chapter 5 remains available only locally and in the protected Vercel preview. The PR remains a draft and has not been merged. The original script is still the working draft, with a running sync exporting public prose to the monorepo preview. Separate chapter guides and deeper subchapters remain future pages. The chapter 5 update replaces the later uniform scroll mapping with text-aware holds and transitions in the gaps. Verification is recorded in the latest chapter 5 checkpoint below.

Checkpoint updated on 2026-10-13 after the lecture 6–7 planning discussion. Read this section and the latest `script.md` before continuing. The script is the current website copy; approved-copy entries below record the editorial decisions. This checkpoint takes precedence over older planning statements about what still needs discussion.

**Next action:** Review the expanded memory chapter on `feat/sand-to-thought-next`, then revisit chapter 5 and MAR. The eleven chapter names and simple timing treatment remain unchanged.

The current manifest has 34 scenes. The added binary-place-value figure and its paragraph have been removed at Aidan's request. Historical scene numbers in earlier records below refer to earlier versions. Scene keys identify the current drawings. Chapter 5 ends with R0 holding 9, while R1 and R2 retain 3 and 6. The earlier stored-answer scene still shows only 0011 + 0110 = 1001.

### Completed and on the local website

- [x] **2026-10-13 — Sand to Thought:** moved the company guide out of Library to `/sand-to-thought/`, added the top navigation link after Library, retained the animated sand artwork above the unchanged article, added generated same-page contents using the docs styling and mobile control, and corrected the Library dropdown’s card count. Publication status and illustration geometry remain unchanged.
- [x] Folder structure, topic map, style guide, and Markdown-to-website publishing workflow.
- [x] Title changed to **How to get an answer out of sand**.
- [x] Approved introduction applied.
- [x] Scenes 0–2, quartz, ingot, and wafer, have their approved revised text. Their illustrations are unchanged.
- [x] Scene 3, boron, now defines doping and says boron was mixed into the melt before crystal growth.
- [x] Scene 4, implantation, now explains phosphorus, holes, and shaping current flow. The exact approved paragraph is in `script.md` and recorded below.
- [x] Each of these text edits was built and inspected in the browser with the relevant scene pinned. Adjacent forward/reverse navigation was checked; no browser warnings or errors were reported. Temporary verification pages were removed.

### Remaining editorial and implementation work

- [x] **2026-10-13 — Lecture 6–7 planning:** saved Aidan's pasted recap unchanged, retained all eleven chapter names, clarified the timing/control/software boundaries and added proposed chapter 5 and 6 outlines. No article or website files changed.
- [x] Chapter 5 authorised and implemented, with the abstract visual timing explanation. The additional place-value scene is removed.
- [ ] Review chapter 5, then agree chapter 6's example and software-to-instruction route before implementing it.
- [x] **Scene 5 — wires:** approved wording applied, retaining “wire” and introducing the insulating layer. Built and checked with scene 5 pinned, plus forward/reverse reading navigation. No browser warnings or errors reported.
- [x] **Scenes 6–8 — voltages, blocked, flowing:** approved copy applied, 0 V left / 1 V right, electron-potential-energy label, and obsolete footnote removed. At Aidan’s request, retain the original curve inside the silicon and particles meeting/following it as an energy analogy. Verified pinned states and forward/reverse transitions, including the hand-off to scene 9. All seven build tests pass and browser console is clean.
- [x] **Scene 9 — symbol:** approved transition applied, retaining Aidan’s “calculate, remember and think” wording and introducing the layer-by-layer progression.
- [x] **Scene 10 — NOT:** approved three-paragraph introduction to bits, gates, and the two-transistor inverter applied. Built and verified pinned at scene 10 with no console errors.
- [x] **Scroll alignment:** the chapter 5 update holds later scenes through their associated text and transitions in the gaps. The original opening artwork retains centre-to-centre choreography. A regression check covers long passages and reverse mapping, with browser checks recorded in the latest checkpoint.
- [x] **Scene 11 — NAND:** approved two-input explanation applied.
- [x] **Scene 12 — NAND symbol:** approved symbol and universal-building-block explanation applied.
- [x] **Scene 13 — full adder:** approved binary-addition and three-input explanation applied.
- [x] **Scene 14 — chained adders:** approved worked-example paragraph applied.
- [x] **Scene 15 — heat:** approved two-paragraph explanation applied, with “voltage flips”, “expending energy”, and f described as clock speed. Keep heat inline within arithmetic. Built and checked with scene 15 pinned, with no browser warnings or errors.
- [x] **Scene 16 — latch:** approved two-paragraph explanation applied, retaining “How does a loop create memory?” and explaining reinforcing feedback. Built and inspected with scene 16 pinned. No browser warnings or errors.
- [x] **Scene 17 — register:** approved paragraph and zoom-out/stacking animation applied. The original latch shrinks into the first block; three copies spread into a row before the shared write-enable wire draws. Verified pinned settled and intermediate states forward and reverse, normal reading navigation, and the preserved LUT/FPGA scenes. Seven builder tests pass and the final browser log is clean.
- [x] **Scene 18 - stored answer:** approved paragraph and illustration applied. The four register blocks copy and retain 1001. At Aidan’s request the original 0011 + 0110 = 1001 sum stays fixed throughout, with current values beside D and Q and the WE value beside its label. The demonstration plays once per visit, pauses during scroll transitions, and resets only when hidden. Pinned copy/hold/new-calculation phases and normal playback verified; all seven build tests pass.
- [x] **First-version ending:** moved LUT/FPGA prose and animation into the linked saved draft, removed their live scenes, and applied the agreed closing paragraph. Keep the stored-answer illustration visible at the end.
- [ ] Apply the agreed chapter names to article headings as a separate coordinated edit. The generated contents navigation already works with the original headings.
- [ ] Choose and develop deeper articles after the opening is coherent. Subject pages and contextual links are planned, not built.

### Memory handoff after compaction

- The latch, register, stored-answer demonstration, and closing paragraph are applied. The first-version content now ends here and can be extended over time.
- Preserve D, WE, and Q so the text follows the illustration. While WE is 1, Q follows D. When WE becomes 0, feedback retains the last value.
- The one-bit-to-register expansion is implemented. The stored-answer demonstration is now applied, showing changed inputs while the saved answer remains. New scenes require discussion first.
- LUT/FPGA prose and the exact animation fragment are preserved under `drafts/` for later reuse; they are no longer live coverage.
- After each approved prose update, automatically propose the next paragraph. Memory is complete for the current version. Resume with the chapter 5 and 6 planning discussion, without applying new public prose automatically.
- The later scroll mapping now follows actual text bounds. Keep normal-reading checks alongside pinned scene checks when changing paragraph lengths.

### Decisions and working rules to retain

- The library serves curious newcomers, with deep branches across the full semiconductor stack for a company pursuing full-stack chip development. It should eventually explain and compare GPUs, TPUs, and other architectures with evidence.
- One continuous opening journey, subject reading-guide pages, and separate focused articles. Subject pages can link directly to relevant introductory chapters. Contents links stay within the opening article; deeper links open other articles.
- The eleven-chapter roadmap below is a working destination, with all chapter names retained on 2026-10-13. The first four chapters are represented in the current article. Keep the bridge from memory into chapter 5 high-level, explaining that signals need time to settle. Develop clocked updates and the distinction between latches and edge-triggered storage in the deeper timing article. Chapter 5 explains the computer and one instruction executing; chapter 6 follows software into those instructions. New prose and visuals require discussion.
- Heat remains within arithmetic. The future link from its closing sentence may lead to an energy-and-heat article. Do not create an interlude.
- Keep main-path explanations concise. Seed pulling and container details were deliberately omitted from the ingot paragraph. Explain deeper mechanisms in branches when useful.
- Aidan requested no semicolons or colons in the recent prose revision. Follow that preference in new proposed copy without automatically rewriting earlier approved sentences.
- Preserve Aidan's wording once agreed. Draft original prose and verify technical facts against primary sources; do not copy source prose verbatim.
- Discuss substantive changes before applying them. Apply approved wording to `script.md` when authorised; do not claim it is on the website if it exists only in chat or notes. Audit/discussion-only requests mean no website edits.
- Scenes 0–2 artwork remains protected. All animation must be smooth. Follow the pinned-scene and transition checks in [visuals.md](visuals.md).
- Preview is [localhost:8080](http://localhost:8080/). `./preview.sh` from the project root starts it if needed; `./preview.sh --build` builds once. Saving `script.md` updates the running preview automatically. Do not edit generated `web/index.html` directly.

## Chapter plan

Working roadmap revised after discussion on 2026-10-12, with coverage boundaries clarified on 2026-10-13. The eleven chapters below replace the earlier nine-chapter roadmap by giving data movement and chip development explicit homes. All eleven names are unchanged. The current article covers chapters 1–5, with same-page contents navigation. The first four retain their shorter website headings and chapter 5 uses Building a computer. Chapter 6 is the next planned continuation. Later chapters remain revisable. The 2026-10-13 lecture-note update changes planning only.

| Chapter | Name | Reader outcome | Current material / remaining work |
| --- | --- | --- | --- |
| 1 | **From sand to a switch** | Understand how silicon, doping, and an insulated gate give control over current | Scenes 0–9 reviewed and revised |
| 2 | **From switches to logic** | Understand how voltages represent bits and transistors implement gates | Scenes 10–12 show NOT and NAND; the bridge to reliable digital levels needs development |
| 3 | **From logic to calculation** | See how circuits represent and add numbers, and why switching has an energy cost | The existing binary-addition and carry-in explanation leads directly into the four-bit adder. The extra place-value scene is removed. Keep heat within this chapter. |
| 4 | **How circuits remember** | Follow one stored bit into a register that retains an arithmetic result, introducing controlled updates | Latch, register and stored answer lead into the abstract timing grid, then the transition into building a computer. The stored sum remains 0011 + 0110 = 1001. |
| 5 | **Building a computer** | Combine arithmetic, registers, memory, and control into a machine that follows instructions | Implemented through looping selection, working registers, ALU, addressed memory, program, control, ADD execution and the complete computer. Timing precedes the chapter. |
| 6 | **How code becomes action** | Trace a program into instructions and execution, with a map of compilers and supporting system software | Proposed outline below connects source code, assembly, ISA, an LC-3 encoding example and loading a program into chapter 5's machine. Detailed instruction processing branches into its own article. |
| 7 | **Keeping computation fed** | Explain where instructions and data live, how they move, and why waiting for them can limit computation | Planned; memory hierarchy, locality, bandwidth, and communication |
| 8 | **Doing more at once** | Understand pipelining, parallelism, specialisation, and the relationship between workloads and machines | Planned; CPUs, GPUs, tensor accelerators, and other approaches; a possible home for reused FPGA material |
| 9 | **How a design becomes a chip** | Follow requirements through design, verification, layout, fabrication, and testing | Planned; revisit physical fabrication after its brief introduction in chapter 1 |
| 10 | **From chips to systems** | See packages, memory, links, boards, power, and cooling working together | Planned |
| 11 | **How a machine generates an answer** | Follow an AI request through software, numerical work, memory, and hardware | Planned; connect the whole journey through one worked example; other library articles will trace other workloads |

### Heat within arithmetic

Keep scene 15 and the heat discussion at their current point after addition, inside chapter 3. Do not add a separate heading, contents item, or interlude label. A future contextual link from the closing sentence “Heat is a budget we will keep encountering as the counts climb.” could lead to a focused article provisionally titled **Why do chips use energy and get hot?** The precise linked words and destination title remain candidates; neither the link nor the article exists yet.

### Memory ending and future programmable logic material

Replace the planned memory conclusion with **one stored bit → a register → storing the adder's answer**. Show a result being stored, then change the adder inputs while that stored result remains. This creates the question for chapter 5: how do we choose operations, inputs, and destinations?

The LUT/FPGA explanation has been moved out of the opening conclusion and saved in [the programmable-logic draft](drafts/programmable-logic.md), with its matching animation fragment. Reuse it for later specialisation/configurable-hardware material, potentially chapter 8, or a focused article. A processor does not require an FPGA as an intermediate layer. The first version ends with storing an answer and the closing paragraph below.

### How the article grows

Keep one stable home for “How to get an answer out of sand”. Publish a satisfying opening when ready, then add chapters and a visible contents map. Chapter names in that contents list will jump to sections on this same page. Contextual links will open focused deeper articles. Subject pages will offer short orientations and reading routes, using the relevant chapters as introductory reading; broader subject overviews can be added when needed. See [the library navigation model](../../shared/library.md#agreed-reading-and-navigation-model).

Short scenes explain connections between levels; detailed derivations belong in linked articles. Show available chapters and working links as material is published. Reading order and publication order can differ. The ten library subjects and eleven working chapters serve different purposes and need not map one-to-one.

### Latch

Approved and applied on 2026-10-12. Retain Aidan’s question and explain stable feedback concisely. The illustration is unchanged.

> We can now calculate an answer, but how do we remember it? Let’s zoom back in and connect a few NAND gates so that their outputs feed back into their inputs. This circuit is called a latch. It has a data input D, a write-enable input WE, and an output Q. While WE is 1, Q follows D. When WE becomes 0, Q holds its last value, even if D changes.

> How does a loop create memory? The two gates on the right feed their outputs into each other, each reinforcing the other’s state. With writing disabled, this feedback holds Q at its last value for as long as power is supplied. We have added memory to our toolset.

### Register

Approved and applied on 2026-10-12. Preserve the recurring sense of zooming out and stacking recognisable components. Four level-sensitive latches share write-enable; do not draw an edge-triggered clock symbol.

> Let’s zoom out again and place four latches side by side, each holding one bit. Together, they form a four-bit register that can remember an entire binary number. By sharing a write-enable signal, all four latches can copy their inputs together, then hold the number while those inputs change.

### Stored answer

Approved and applied on 2026-10-12. Keep the same four register cells as the adder enters above them. Copy before disabling write-enable, then hold the answer. The original sum remains fixed, per Aidan’s later simplification request.

> We can now connect our register to the four-bit adder. With write-enable at 1, the register copies the answer, 1001. Set write-enable to 0 and that answer is held. The adder can calculate something new while the register remembers the previous result. We can now both calculate and keep the answer.

### First-version closing paragraph

Approved and applied on 2026-10-12. This closes the first version while leaving the same article open to future chapters. No public deployment has been made.

> We now have circuits that calculate and circuits that remember. Our next step is to combine them into a machine that follows instructions, choosing which values to use, what to calculate, and where to store each result.

## Approved copy applied to the local website

### Introduction

Approved by Aidan in the scene-by-scene discussion and applied to `script.md` and the local website at his request on 2026-10-12.

> How do we get from the silicon atoms in a grain of sand to a machine that answers a question? Here we will follow the journey one step at a time: making a switch, combining switches into circuits that calculate and remember, and assembling those circuits into a computer that performs progressively more complex tasks. We will highlight examples of each successive structure and what it can accomplish.

### Quartz

Aidan's replacement paragraph was applied verbatim to `script.md` and the local website on 2026-10-12. The quartz illustration is unchanged.

> We start with quartz, the main ingredient in sand. Quartz is silicon dioxide: one silicon atom for every two oxygen atoms, arranged in a repeating crystal structure. Our first task is to separate the silicon from the oxygen.

### Silicon ingot

Aidan approved the concise version below, which was applied to `script.md` and the local website on 2026-10-12. The ingot illustration is unchanged. Seed pulling and the quartz container are reserved for a deeper manufacturing explanation.

> We heat the quartz with carbon to extract silicon, then purify it. We melt the purified silicon and grow it into one large crystal, called an ingot.

### Wafer

Approved by Aidan and applied to `script.md` and the local website on 2026-10-12. The wafer illustration is unchanged.

> We then slice the ingot into thin wafers: the blank canvases for our chips.

### Boron and doping

Approved by Aidan and applied to `script.md` and the local website on 2026-10-12. The cross-section illustration is unchanged. The boron/phosphorus distinction is introduced in the approved implantation paragraph below.

> We can change how silicon conducts electricity by adding small amounts of other elements. This is called doping. Here is a cross-section of our wafer, lightly doped with boron mixed into the melt before crystal growth.

### Phosphorus implantation

Approved by Aidan and applied verbatim to `script.md` and the local website on 2026-10-12. The implantation illustration is unchanged. The approved wording uses no colons or semicolons.

> We can also implant dopants into selected parts of the wafer using what is essentially an atom gun. Here we create two islands of phosphorus-doped silicon within the boron-doped silicon. Phosphorus supplies extra mobile electrons, while boron creates gaps called holes that carry current in a different way. By arranging these two types of silicon, we can shape how current flows.

### Wires and insulated gate

Approved by Aidan and applied to `script.md` and the local website on 2026-10-12. The illustration is unchanged.

> We can now build our first transistor. We add a wire to each of the two islands and place a third wire, called the gate, above the silicon between them. A thin insulating layer separates the gate from the silicon, allowing it to control the current without making direct electrical contact.

### Voltage and the energy barrier

Approved and applied on 2026-10-12. Keep 1 volt without a threshold clarification and keep “n-type MOSFET” in the main text. The old corrective footnote is removed. The left wire is 0 V and the right wire is 1 V. Increasing gate voltage lowers the electron energy barrier. Aidan prefers the curve in its original position inside the silicon, with dots visibly meeting the hill, rather than a separate graph below it. Its label identifies electron potential energy. This is an energy-landscape analogy, not a literal spatial trajectory.

#### Setting the voltages

> A voltage difference can drive electrons through a circuit. Let us hold the left wire at 0 volts and the right wire at 1 volt. Electrons would then flow from left to right if there were a conducting path between them. Imagine the electrons moving through an energy landscape, where a hill represents a barrier to their flow.

#### The switch is off

> With the gate also at 0 volts, this barrier is high and electrons struggle to flow between the two islands.

#### The switch is on

> Raising the gate to 1 volt lowers this barrier, opening a conducting path between the islands. Electrons can now flow through the transistor and around a connected circuit, perhaps lighting a bulb. This is the basic picture of an n-type MOSFET, an electrically controlled switch with no moving parts.

### From transistor to symbol

Approved by Aidan and applied on 2026-10-12. The illustration is unchanged.

> We now have a switch that we can control with an electrical signal. To make larger circuits easier to draw, we will represent each transistor with a simple symbol. The next step is to connect these switches so that, together, they can calculate, remember and think. We will build towards these abilities one layer at a time, showing how each new structure makes more complex tasks possible.

### Bits and the NOT gate

Approved and applied on 2026-10-12. Preserve the recurring zoom-out framing as we combine smaller elements into larger structures. Keep the p-type MOSFET description in the original style and avoid the pulling terminology.

> To calculate with electrical signals, we first need a way to represent information. We use a low voltage to represent 0 and a high voltage to represent 1. Each of these binary digits is called a bit.

> By connecting transistors, we can build circuits called logic gates that turn input bits into output bits according to a simple rule. The simplest example is the NOT gate, which flips its input. A 0 becomes a 1, and a 1 becomes a 0.

> Let’s zoom out one step and connect two transistors to make our first logic gate. The lower one is our n-type switch. The upper one, drawn with a small circle on its gate, is its mirror image, a p-type MOSFET made with the dopants swapped. In this circuit, it turns on when the input is 0, while the n-type turns on when the input is 1. Together, they make the output the opposite of the input. This is a NOT gate.

### NAND gate

Approved and applied on 2026-10-12.

> Add two more transistors and we can build a NAND gate. It takes two input bits, A and B, and produces a 1 unless both inputs are 1, in which case it produces a 0.

### NAND symbol and universality

Approved and applied on 2026-10-12.

> Let’s zoom out again and give this four-transistor circuit a symbol. The two inputs enter on the flat side, and the output leaves through the small circle, which indicates inversion. It can be shown that NAND gates alone can be combined to implement any function that maps a finite set of input bits to output bits. This makes them universal building blocks. From this one simple circuit, we can build the logic for everything from a calculator to a computer running an AI model.

### Full adder

Approved and applied on 2026-10-12.

> Let’s zoom out further and combine NAND gates into a circuit that adds. In binary, we have only two digits, 0 and 1, so adding 1 and 1 gives 10. We write down 0 and carry 1 into the next column, just as we carry digits in ordinary addition.

> Our circuit handles one column at a time. It adds two input bits, aᵢ and bᵢ, along with any carry from the previous column, cᵢ. It produces the answer bit sᵢ and a carry for the next column, cᵢ₊₁. This three-input, two-output circuit is called a full adder.

### Chained adders

Approved and applied on 2026-10-12.

> Connect several full adders in a row, passing each carry cᵢ₊₁ into the next column, and we can add entire binary numbers. Here, four adders calculate 0011 + 0110 = 1001, or 3 + 6 = 9. More columns let us work with larger numbers. With addition as a building block, it is a short step to circuits that subtract and multiply, and our toolset has grown.

### Heat

Approved and applied on 2026-10-12. The illustration and P ∝ C V² f remain unchanged. The proportional scaling assumes comparable switching activity. The fuller switching-power model is αCV²f, as discussed with Aidan. Clock speed receives a brief introduction here, with coordination explained later.

> We have combined small groups of transistors into a circuit that adds numbers, but each calculation has a physical cost. Every calculation involves voltage flips as some of the transistors switch. These flips charge or discharge the tiny capacitances of the transistors and wires, expending energy that is dissipated as heat.

> The faster we switch, the more heat we produce each second. This switching power scales with C V² f, where C is the capacitance being switched, V is the voltage swing, and f is the clock speed, which sets the pace of computation. Smaller capacitances and lower voltages reduce the energy needed, while switching less often reduces the rate at which we generate heat. Heat is a budget we will keep encountering as the counts climb.

## First four chapters: discussion outline

The direction above is agreed; the outline below is a proposal for the next discussion, not approved replacement prose or a fixed scene implementation. Existing scene indices are references, not assignments for new drawings.

| Chapter | Promise and boundary | Proposed sequence | Deeper branches / later material |
| --- | --- | --- | --- |
| 1. From sand to a switch | Begin with a silicon-bearing material; end with one electrical signal controlling conduction, represented by a transistor symbol | Quartz → purification and crystal growth → wafer → doping → contacts and insulated gate → blocked/conducting states → symbol (existing scenes 0–9). Clarify the gate's electric-field control and use a consistent voltage/energy explanation. Give only enough fabrication context to make the device tangible. | Crystal and carrier physics, junctions, device equations, detailed fabrication. First three illustrations stay fixed. |
| 2. From switches to logic | Begin by assigning meaning to voltage ranges; end with gates we can combine into larger logical functions | Reliable 0 and 1 → complementary switches and NOT → NAND → gate symbol and composition (existing scenes 10–12, with the missing digital-signal bridge). Explain the abstraction without suggesting all real hardware consists only of NAND gates. | Noise margins, transistor sizing, full gate derivations, Boolean proofs and other gate families. |
| 3. From logic to calculation | Begin with bits representing numbers; end with a multi-bit addition and its physical cost | Binary place value → one-bit addition with incoming and outgoing carry → chained adders and a worked example → heat in the existing paragraph/scene (13–15). Distinguish energy from power and explain switching rate before using it in a formula. | Arithmetic implementations, number formats, multiplication, detailed switching energy and leakage. |
| 4. How circuits remember | Begin with an answer that would otherwise change when its inputs change; end with that answer deliberately stored | Stable feedback → latch follows/holds → several stored bits form a register → capture the adder result → change inputs while the saved answer remains. Existing scene 16 is the starting point; additional scenes and controlled-update/clock treatment remain to discuss. | Detailed timing, edge-triggered storage, metastability, SRAM/DRAM and large addressable memories; introduce addressing as chapter 5 needs it. |

Proposed connecting questions:

- **1 → 2:** How can we use voltage-controlled switches to implement a rule about bits?
- **2 → 3:** If groups of bits represent numbers, how can these rules perform arithmetic?
- **3 → 4:** How can we keep an answer after the inputs to our calculation change?
- **4 → 5:** How do we choose what to calculate, which values to use, and where to store the result?

The current prose review and stored-answer ending are applied. Chapter 5 now introduces the simple timing bridge, and text-aware scroll alignment is implemented. Do not equate a write-enable latch with an edge-triggered register.

## Chapters 5 and 6 discussion outline

Saved on 2026-10-13. Chapter 5 was subsequently authorised and implemented with the simpler visual timing explanation described below. Chapter 6 remains a proposal for discussion. The current script is the source for applied public prose.

### Study notes and scope

- The [pasted lecture 6–7 recap](../../../../learning/courses/eth-ddca-lectures-06-07-recap.md) is saved unchanged. The [Chip Architecture Notebook](../../../../learning/courses/chip-architecture-notebook.md) remains the main learning record, with detailed notes and local reference slides.
- These notes mainly develop the transition from chapter 4 into chapter 5. ISA and assembly provide an initial bridge into chapter 6. Early mentions of verification and memory organisation seed later treatment rather than completing chapters 7–11. Course lecture numbers and journey chapter numbers are independent.
- Separate the computer model, the ISA's programmer-visible commands and behaviour, and the microarchitecture that implements them. Introduce terms alongside the question they answer.
- Introduce timing and correctness when they become necessary. Setup/hold, glitches, skew and detailed analysis can branch into focused articles. Chapter 9 later revisits verification within the full design-to-chip process.

### 5. Building a computer

**Promise** — understand how the familiar arithmetic and storage circuits become a machine that follows a stored program.

**Entry** — we can calculate 3 + 6 and retain 9. Briefly introduce the von Neumann model and shared instruction/data memory before the multiplexer. **Exit** — readers can follow a simple instruction through a computer and understand how it proceeds to another instruction.

| Step | Explanation | Visual direction |
| --- | --- | --- |
| 1. Choose values | A multiplexer chooses which value travels along a path, using a selection signal shown at the bottom. | Loop smoothly between 0 passing 3 and 1 passing 6. Return to the same state before repeating. |
| 2. Organise working registers | Expand working storage to eight LC-3 registers, holding sixteen bits each. | Fade the multiplexer into the growing register bank, keeping the values 3 and 6. |
| 3. Group operations into an ALU | Combine addition and logical operations, selected by control signals. | Connect the existing registers to the ALU and its result path. |
| 4. Address memory | Distinguish the selected location's address from the bits stored there. | Select addressed rows with contents 3 and 6. |
| 5. Store instructions | Introduce command bits, a stored program, PC holding an instruction address and IR holding the fetched instruction. | Add instruction locations and show one instruction arriving in IR. |
| 6. Control the work | Selection and write signals coordinate the datapath. A small state machine remembers which step comes next. | Highlight the selected route and capture point with the controller beside them. |
| 7. Execute | Trace one ADD using 3 and 6, saving 9 and advancing PC. | Follow the paths through the same machine. |
| 8. Zoom out to the computer | Group the datapath and control into a CPU with memory and I/O around it. | Retain familiar blocks in the complete computer overview. |

**Depth boundary** — readers should understand the jobs and one trace. Full control tables, every internal register, all instruction formats and timing inequalities belong in deeper explanations. One instruction can require multiple clock cycles. Conceptual phases are not a fixed cycle count.

**Worked machine** — use the saved LC-3 examples for concrete encoding and execution. Discuss how much LC-3 detail belongs in the overview. Explicitly explain the widening from the existing four-bit example to sixteen-bit structures. Slide 65 is a reference for the machine's organisation, to be explained gradually through our own illustration.

### 6. How code becomes action

**Promise** — connect a program written by a person to the stored instruction bits that chapter 5's machine executes.

**Entry** — the machine already follows instructions. **Exit** — readers can trace a small piece of code into instructions, memory and physical execution, and distinguish ISA from implementation.

| Step | Explanation | Visual direction |
| --- | --- | --- |
| 1. Express a task | Begin with the familiar addition written as a small program. | Place a short code example beside the machine readers already know. |
| 2. Translate it | Explain a simple source → compiler → assembly → assembler → machine-code route. Identify this as one route, with other execution models available later. | Transform the same task through successive representations. |
| 3. Define the commands | The ISA specifies instructions, registers, encodings and observable behaviour. Assembly gives those commands readable names. | Connect ADD and its named source/destination registers to the existing diagram. |
| 4. Inspect one encoding | Reuse LC-3 ADD R0, R1, R2. Distinguish the register IDs inside the instruction from the values stored in those registers. | Group the sixteen instruction bits by operation and operand fields, with the complete field table available in the deeper treatment. |
| 5. Put the program in memory | Explain that loading places the encoded program in memory and execution begins at a chosen instruction address. | Follow instruction bits into addressed locations and return to chapter 5's fetch loop. |
| 6. Follow a short sequence | Introduce a few commands and a brief example of changing the next instruction address for choices or repetition. | Keep the same machine visible while its instruction address and stored values advance. |
| 7. Place supporting software | Give a short orientation to libraries, runtimes, operating systems, firmware and drivers as relevant to the example. | Zoom out to a software-to-hardware map, then lead into chapter 7's need to supply instructions and data. |

**Depth boundary** — complete compiler construction, calling conventions, virtual memory and operating-system internals belong in branches. Establish one coherent software route before comparing others. The opening journey gives enough detail to connect the levels.

### Focused instruction-processing article

Instruction processing has its own planned deeper article, linked from chapters 5 and 6. Its question is how stored instruction bits cause a particular machine's circuits to act.

- Preserve the LC-3 ADD encoding from the notebook, `0001 | 000 | 001 | 0 | 00 | 010`, and the familiar 3 + 6 = 9 example.
- Preserve the binary load walkthrough, LDR R3, R0, #2, with R0 holding 100 and memory location 102 holding 30. Explain the address calculation separately from the data read, retaining R0 and updating R3. These are independent starting states from the ADD example.
- Build up the machine diagram gradually, then trace the relevant paths, control signals and PC/IR/MAR/MDR values. Use the saved slide 65 as a reference. Detailed fetch/decode and instruction-specific phases belong here.
- Keep LC-3's word addressing explicit. MIPS comparisons should explain a purposeful contrast in a later treatment.
- Candidate titles and exact article placement remain open. No new article folder or public page has been created.

**Next discussion** — settle chapter 5's opening transition, timing bridge and visual sequence first. Then review chapter 6's example and how much encoding to keep in the opening journey.

## Latest chapter 5 checkpoint — 2026-10-14

Aidan authorised the chapter 5 implementation after reviewing the detailed proposal, then requested an even simpler timing treatment and removal of the extra binary explanation. Applied public copy is in `script.md`. The timing scene now follows the stored answer and immediately precedes the paragraph beginning “We now have circuits that calculate and circuits that remember.” Eight chapter 5 scenes follow. Looping selection, register organisation, ALU, addressed memory, PC/IR, control and one ADD trace build into the final computer. The original memory example is unchanged.

Timing uses an abstract grid of wires and twenty scattered bit values. Faint green highlights mean 1 and faint red highlights mean 0. A yellow pulse starts at the top-left input and branches through the grid at differing speeds. Fifteen digits crossfade to the opposite value and colour as the pulse passes, while five remain unchanged. The pulses fade and the final values remain still. All figure headings, captions and the input label are removed at Aidan's request. The paragraph is Aidan's supplied 2026-10-14 version about timing challenges, stale data and glitches. The transition paragraph follows it within the same timing scene. This is a conceptual signal map, not a literal circuit simulation. Clocked capture, hazard remedies, setup/hold inequalities, clock skew and verification belong in **How do circuits keep time?**, a planned deeper article. No public deeper-article page has been created.

The LC-3 trace uses the saved ADD encoding and 3 + 6 = 9. It begins with R0 = 0, R1 = 3 and R2 = 6. Fetch uses the old PC address before incrementing PC. The trace writes 9 to R0 and retains R1/R2. The diagram omits detailed internal transfers and status flags at overview level. Its complete bit-field treatment and the saved binary LDR walkthrough remain available for the focused article.

Browser pinning used temporary local verification code, which is removed from the finished website. Protected opening scenes, every new settled scene, fractional transitions and reverse states were inspected. The ADD trace was checked before and after capture. Desktop and mobile layouts and the long NOT passage at a 655px test width were checked during normal reading. A temporary reduced-motion fixture exposed a zero-duration scrolling issue, which was corrected and rechecked with settled capture. Eleven writing-preview tests and four portable scroll-mapping tests pass. Preview and production builds pass, with the draft still excluded from production. Screenshots are temporary verification files rather than published assets.

## Topic coverage

This table describes only the current website, through chapter 5 and its one ADD trace. LUT/FPGA remain saved for later and excluded from current coverage. Chapters 6–11 and deeper articles remain planned. The treatment is introductory; none is marked as a completed deep explanation or technical review.

<!-- coverage:start -->
| Subject | Topic | Depth | Current scenes |
| --- | --- | --- | --- |
| 1. Physics, materials and devices | [Silicon and doping](../../shared/topics.md#silicon-and-doping) | Introduced | quartz, boron, implant |
| 1. Physics, materials and devices | [MOSFET](../../shared/topics.md#mosfet) | Introduced | wires, voltages, blocked, flowing, symbol |
| 2. Circuits and reliable signals | [CMOS logic gates](../../shared/topics.md#cmos-logic-gates) | Introduced | not, nand |
| 3. Information, logic and arithmetic | [NAND and functional completeness](../../shared/topics.md#nand-and-functional-completeness) | Introduced | nand, nand-symbol |
| 3. Information, logic and arithmetic | [Full adder](../../shared/topics.md#full-adder) | Introduced | adder |
| 3. Information, logic and arithmetic | [Ripple-carry addition](../../shared/topics.md#ripple-carry-addition) | Introduced | chain |
| 4. State, timing, and memory | [Bistability and feedback](../../shared/topics.md#bistability-and-feedback) | Introduced | latch |
| 4. State, timing, and memory | [D latch](../../shared/topics.md#d-latch) | Introduced | latch |
| 4. State, timing, and memory | [Registers](../../shared/topics.md#registers) | Introduced | register, stored-answer |
| 3. Information, logic and arithmetic | [Multiplexers](../../shared/topics.md#multiplexers) | Introduced | select-values |
| 3. Information, logic and arithmetic | [Arithmetic and logic units](../../shared/topics.md#arithmetic-and-logic-units) | Introduced | alu |
| 2. Circuits and reliable signals | [Signal propagation and settling](../../shared/topics.md#signal-propagation-and-settling) | Introduced | timing |
| 4. State, timing, and memory | [Memory addressing](../../shared/topics.md#memory-addressing) | Introduced | memory-two, memory-array, memory-buses, addressed-memory |
| 5. Processors and the software stack | [Processor organisation](../../shared/topics.md#processor-organisation) | Introduced | working-registers, alu, control, computer |
| 5. Processors and the software stack | [Stored programs](../../shared/topics.md#stored-programs) | Introduced | program |
| 5. Processors and the software stack | [Instruction processing](../../shared/topics.md#instruction-processing) | Worked | execute |
| 6. Performance, parallelism and communication | [Dynamic switching power](../../shared/topics.md#dynamic-switching-power) | Introduced | heat |
| 9. Manufacturing, packaging and systems | [Wafer production](../../shared/topics.md#wafer-production) | Introduced | ingot, wafer |
<!-- coverage:end -->

## Candidate deeper branches

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

## Current script and publishing state

`script.md` was extracted from the current `web/index.html` on 2026-10-12. Its article wording, existing headings, and footnote were preserved; short visual cues and scene markers were added as editorial notes. It now drives the website automatically: saving the script while `preview.sh` runs rebuilds the HTML and refreshes the browser. Edit article text in the script; `web/index.html` is generated. See [website notes](implementation.md) for the format and validation rules.

The two earlier text drafts and handover are preserved in the [pre-reorganisation snapshot](../../archive/before-reorganisation). They are reference material, not automatically approved replacements for the current article.

## Open editorial and scientific questions

These remain pending for the agreed scene-by-scene review; this planning update applies none of them to the live script:

- Voltage, electron direction, and energy-barrier explanation were reconciled on 2026-10-12. Keep the curve inside the silicon as an explicitly labelled energy analogy, per Aidan’s preference.
- Explicitly introduce the full adder's incoming carry in its first paragraph. The alternative draft includes that wording; the live paragraph does not.
- Explain the transition from physical voltages to logical bits, including the limitations of treating 0 and 1 as exact universal voltages.
- Clarify the scope of NAND completeness and distinguish an explanatory construction from actual chip implementation.
- Clarify switching energy versus average power, the activity and rate assumptions behind the heat formula, and the introduction of clocks. Keep heat within arithmetic.
- Explain stable feedback rather than implying arbitrary loops produce memory; develop the agreed stored-answer ending and discuss the minimum timing explanation.
- Review the LUT wording “3-to-1 function”, and avoid implying that all FPGA storage is implemented by the illustrated gated D latch.
- Review the scope of the FPGA description, including state and resource limits, when developing the deeper branch.
- Review the proposed wording changes around crystal growth and “any ideating” in context rather than importing a whole older draft.

Current live ending is the stored-answer demonstration and the approved closing paragraph. Programmable logic is saved under `drafts/` for later reuse.

## Sources and research notes

- [ETH DDCA, Spring 2025](https://safari.ethz.ch/ddca/spring2025/doku.php?id=schedule) informed earlier study. The learning notebook records the move to Spring 2026 and its lecture 6–7 deck references. Preserve each edition's labels and verify slide-specific references before publication.
- [Saved lecture 6–7 recap](../../../../learning/courses/eth-ddca-lectures-06-07-recap.md), supplied and saved unchanged on 2026-10-13. It is study material rather than an independently audited transcript or public article. The notebook remains the detailed source record.
- [Learning notebook](../../../../learning/courses/chip-architecture-notebook.md) and [standup notes](../../lectures/standup_lectures.md) contain prior explanations and references. Treat them as working notes; check the underlying source for publication.
- [Mark Lundstrom, Fundamentals of Nanotransistors, chapter 3](https://courses.edx.org/asset-v1%3APurdueX%2B69504x%2B1T2021%2Btype%40asset%2Bblock%40LNS_Lecture_Notes_on_Nanotransistors.final.pdf): source consulted for the barrier-controlled transistor model. Link and paraphrase appropriately; do not copy or redistribute the source document into the site.
- [MIT 6.004, The Digital Abstraction](https://ocw.mit.edu/courses/6-004-computation-structures-spring-2017/pages/c2/): reference for the planned bridge from voltages to bits.
- [Broader curriculum references](../../shared/topics.md#curriculum-references) guide the future map, not a claim that all the current article's statements have been verified.

## Revision record

- **2026-10-14:** applied the supplied multiplexer paragraph and smooth repeating selection. Applied the supplied timing paragraph and moved the timing scene before the transition into building a computer. Scene keys remain stable; timing is now index 19 and selection index 20. The von Neumann model is introduced directly under the chapter heading, before the multiplexer. The multiplexer paragraph ends with Aidan's sentence establishing selection as a recurring idea.

- **2026-10-13:** simplified timing to the approved wire grid, travelling yellow pulse and high-level paragraph. Removed the additional binary figure and place-value paragraph, with topic coverage updated to signal settling.

- **2026-10-13:** implemented the authorised chapter 5, a binary-place-value bridge, simple light-propagation timing and one ADD trace. Retained chapter names and the original memory calculation. Updated both local previews and the topic coverage.

- **2026-10-13:** saved the pasted lecture 6–7 recap unchanged, retained all eleven chapter names, clarified the timing/control/software boundaries, updated the resume checkpoint and added chapter 5 and 6 outlines for discussion. No script, website or animation files changed.

- **2026-10-12:** saved the agreed folder and chapter plans; extracted current live prose into Markdown; archived previous material; relocated the existing website without changing its content or animation source.

- **2026-10-12:** connected the script to the website with automatic local rebuilding and refresh; preserved article wording, layout, and all nineteen scene connections.

- **2026-10-12:** updated planning notes after discussion: recorded the working eleven-chapter roadmap and library navigation, kept heat within arithmetic, planned the stored-answer memory ending and later reuse of LUT/FPGA material, and added a first-four-chapter outline for discussion. No script, website, or animation files changed.

- [MIT 6.701, Introduction to Nanoelectronics, Figure 5.29](https://ocw.mit.edu/courses/6-701-introduction-to-nanoelectronics-spring-2010/6a95133986a8698a55448d60c7834d15_MIT6_701S10_textbook.pdf#page=161): checked for the gate-controlled electron injection barrier and energy convention during the scenes 6–8 revision.

## Latest memory visual decision - 2026-10-12

Keep the final example simple. The equation stays 0011 + 0110 = 1001 throughout, and the second calculation is removed. Each register cell shows its current input next to D and its output next to Q. The output appears as the answer is copied and stays at 1001 when WE becomes 0. WE and its value share a baseline, before the shared wire. This supersedes older descriptions of changing the adder inputs in the animation. The prose still explains that the adder can perform a later calculation. Preserve Aidan’s direct script edits, including the register wording about copying inputs at D simultaneously.

## Stored instructions and fetching — 2026-10-17

Aidan approved replacing all of the earlier ending after instruction-control. The coordinated tail is addressed-memory → program → instruction-fetch → execute → control → computer. The public boundary remains memory-buses. Earlier prose and illustrations, including the existing memory interactions and accumulating ALU, are unchanged.

Use ADD R0, R0, R3 consistently. Display the same encoded instruction at decimal addresses 12288 and 12289, with data 6 shown at 16384. Introduce PC before IR, copying PC into MAR, then reading into MDR and copying into IR. PC advances during fetch while MAR retains the address being read. Start the calculation example from R0 = 9 and R3 = 2. The first instruction saves 11 and the second saves 13. In the combined example, the result is never silently cleared between instructions. New demonstrations replay on entry and hold after completion. Fetch/decode/execute are explanatory groups rather than literal LC-3 microstates. Clock pulses are regular and result captures occur while writing is enabled. The final CPU boundary includes the red PU and blue CU, with PC and IR inside CU. The green memory boundary groups the array with MAR/MDR outside CPU.

Sources checked for instruction fields, PC behaviour and fetch sequencing, retained here without article footnotes: [Patt and Patel LC-3 ISA Appendix A](https://www.cs.colostate.edu/~cs270/.Fall20/resources/PattPatelAppA.pdf) and [LC-3 microarchitecture Appendix C](https://people.cs.georgetown.edu/~squier/Teaching/HardwareFundamentals/LC3-trunk/docs/LC3-uArch-PPappendC.pdf). The SVG is a deliberately simplified teaching layout, not a complete LC-3 datapath or cycle-accurate trace.

Verification for `ee12bbcd8` passed all 63 website tests and 11 authoring checks, DevEx and the final preview build. Public article HTML is unchanged, both scripts render identically, and the portable scripts load together without duplicate declarations. In-app browser checks covered the staged fetch, unchanged MAR after PC advances, enabled result capture, continuation from 11 to 13, reverse entry, the earlier simple CU, a 390px layout without overflow and the reduced-motion settled state. Temporary verification overrides were removed. All nine committed files are confined to product/website. The Vercel Preview deployment completed successfully at https://gradiated-aj1b8tzgo-gradiated.vercel.app/sand-to-thought/#sand-addressed-memory.


## Control and memory grouping correction — 2026-10-17

Aidan requested the blue CU to include PC and IR alongside the controller, and the green memory group to include MAR and MDR. The blue outline now expands from the register band into an L-shaped boundary around the controller, excluding the red PU. The green outline groups the memory interface and array while excluding I/O. CPU groups the red PU and blue CU. Controller is the name of the smaller internal box. Transfer routes are aligned to the adjusted boundaries, with the existing timing, values, write captures and publication boundary preserved. Both scripts and the portable runtime are coordinated.


## Simplified, spaced computer layout — 2026-10-17

Aidan requested more room and fewer lines. This supersedes the L-shaped group outlines. Keep the stored-program table only in addressed-memory, then collapse it into a compact rectangular green memory group containing MAR and MDR. Keep the red PU as a small outline and silhouette in the upper-left corner during program and instruction-fetch. Before execute, slide it down while small, then expand below the CU. Its internal wires inherit the same transform as its registers and ALU, and the red control links appear near the end of the expansion. The blue CU is a simple rectangle at the top right, with PC and IR above the controller. CPU groups this CU with the expanded PU. Omit the individual I/O boxes and the drawn PC increment feedback loop from this simplified combined view. The prose still explains incrementing PC.

Use larger twelve-unit binary text and omit field spaces in IR/MDR and their moving copies, retaining all sixteen bits. The initial memory table retains the spaced encoding. Route PC to MAR around the PU miniature. Keep a clear gap between the red control route and the outer data route. Red control paths retain a faint baseline with stronger active emphasis. No model timings, values, source prose, scene order or publication boundary change. The browser check includes the expansion midway, the settled desktop view and a 390px layout without horizontal overflow.

Saved and pushed the spacing revision in `4cdd49ee6`. The two committed files are `hardware/publishing/sand-to-thought/articles/sand/figures/runtime/instruction-cycle-scenes.js` and `hardware/publishing/sand-to-thought/articles/sand/figures/journey.css`. All nine focused instruction/publication tests, DevEx, diff checks and the preview build pass. The public article is unchanged, both authoring scripts render identically and the portable scripts load together. The temporary scene override and viewport override are removed. Browser checks cover the persistent PU miniature, its contained expansion, clear final grouping, normal playback and mobile width without overflow.


## ISA and I/O introduction — 2026-10-17

Name instruction set architecture (ISA) beside the instruction encoding. Explain that it defines supported instructions, encodings and effects, rather than equating it only with field positions. Add a brief keyboard/screen explanation of input and output beside the PU wrap-up. Show a small faint orange I/O building block, shelved through instruction and fetching scenes, then bring it above and outside the final CPU outline. Use a quiet two-way overview connection, with no yellow transfer or implied I/O operation during ADD. Keep actual LC-3 device access for later. The overview connection is deliberately abstract, not the physical LC-3 datapath. No scene-order or public-boundary changes.

Checked against [LC-3 ISA Appendix A](https://www.cs.colostate.edu/~cs270/.Fall20/resources/PattPatelAppA.pdf), which defines instruction fields and operations and specifies memory-mapped device registers for actual I/O access.

Saved the four intended website files in `0f57cbcd7`. DevEx, all nine focused instruction/publication tests and the preview build passed. Public HTML is unchanged and both scripts render identically. In-app browser checks covered the I/O introduction, its shelved position clear of the fetch wires and the final external two-way connection.


### I/O overlap correction

Keep I/O in a compact left-hand shelf below the PU and memory miniatures during instruction and the first control explanation. Move it beside the later CU during fetching and execution, clear of the address bus. Fade its inner contents during the short diagram rearrangements so neither the moving block nor the growing PU can cross visible I/O. Keep its original introduction and final position above CPU. This supersedes the earlier upper-right position during instruction-control.

The I/O overlap fix is saved in `ff30e7c26`, confined to the website computer-scenes runtime. All nine focused tests, DevEx and copy/parsing checks pass. In-app checks confirmed the clear instruction/control shelf, the fetch shelf and invisible I/O at the midpoint of PU expansion. Temporary verification code and query were removed.


### Animated PU and memory handoff

Make I/O 56 by 26 SVG units with an unscaled label, centred at x=51.6 under the early shelved blocks and x=52 beside the later CU. Keep it small above CPU in the final view. On the instruction-control to addressed-memory transition, shrink the full PU around its centre, move it into the upper-left corner and exchange its simplified silhouette with the persistent miniature. Then expand the green memory block from the shelf into the stored-program table. Match both green frame bounds exactly during the contents crossfade, fade the old memory silhouette and name, and keep later signal highlights hidden until the handoff completes. All phases follow scroll position and reverse when scrolling back. No public prose or scene-order changes.

Saved the two animation runtime files in `b2f044491`. The preview build, DevEx and all nine focused tests passed. Both script copies render identically and the portable runtime is synchronised. In-app checks covered intermediate shrinking/expansion, matching green outlines, the smaller aligned I/O block, normal fetching afterwards and the reverse transition. Temporary scene pinning was removed.

## Controller circuitry — 2026-10-19

Added controller between control and computer, after the existing fetch/decode/execute walkthrough. Keep this as a simple example of one transfer. The added readiness AND gate and external ready-input wire were removed at Aidan’s request because they made the close-up unnecessarily complex. Show the memory wait in the preceding whole-computer sequence, which explicitly labels the wait before MDR receives the instruction. Its memory-ready state remains false during the wait, including a clock pulse, and the MDR-to-IR transfer follows completion of the read. The close-up begins after MDR is ready.

The close-up contains a two-bit clocked state register, an OR and NOT calculating the next state, and NOT/AND gates recognising state 01. The illustrative sequence is 00 MDR ready → 01 copy to IR → 10 next step and hold. Next-state bits are D1 = S1 OR S0 and D0 = NOT D1. At 2 seconds the state register captures 01, enabling MDR to drive the bus and IR to capture the instruction at the next clock edge, at 6 seconds. State 10 disables the transfer and holds through the later clock pulse at 10 seconds. The example loops after 12 seconds. These are explanatory state assignments, not the actual LC-3 encoding or full controller. The text explains that a complete controller also uses readiness and instruction inputs to decide when and where to advance.

The labels next state, current state and control signals share a header line. The register has evenly spaced S1 and S0 rows, with matching label/digit typography. Its clock is centred above it. The left-hand NOT output enters the lower register input horizontally, and the OR output enters the upper input horizontally. Feedback routes run around the outside, and the outgoing control labels sit clear of the vertical branch. The close-up frame is 416 by 308 SVG units. Its zoom centre and scaling match the adjusted frame, preserving the expansion from and return to the controller inside the CU.

Aidan requested external components off-screen. No MAR, MDR or IR boxes appear in this close-up. Only labelled outgoing control wires lead towards MDR and IR. The reset input is omitted. Yellow wires indicate asserted signals. Brief yellow register fills mark captures at the same clock edges as the value updates. The fetch sequence flashes PC and MAR at 1.6 seconds, MDR at 3.2, IR at 4.8 and R0 at 10.4 in each instruction. The close-up flashes its state register at 2 and 6 seconds. Each fill fades over 0.45 seconds. Clock pulses use a brighter yellow and a soft glow. Reduced motion shows the copy state without playback or capture flashes. Re-entry restarts the example, and the following section restores the existing whole-computer view. Publication still ends at memory-buses. The script link, both scene manifests and portable runtime remain coordinated. Private visual cues remain intact.

References checked visually in the saved ETH Spring 2026 decks. Lecture 4a slides 68–69 show state-register, next-state and output gate circuits for a traffic-light controller. Lecture 7 slide 111 and lecture 8 slide 14 show the abbreviated LC-3 instruction-cycle FSM. These support the mechanism, not a claim that our illustrative gates reproduce the complete LC-3 controller.

### Controller close-up transition

The controller close-up now expands from the controller box inside the preceding CU. Its frame grows from that box while the circuit details scale uniformly into view and the surrounding computer fades away. On leaving, the same frame and circuit shrink back into the controller box as the full computer returns. The return target follows the existing final computer transform, so both frames align. Reverse scrolling follows the same geometry. Removed a duplicate wire segment before the right-hand NOT gate so the standard yellow highlight stays above its wire.

### Controller gate pin alignment

The OR input wires now meet its curved outline at their actual intersection points. The final AND gate spans both incoming wire heights, allowing the NOT output and S0 wire to enter horizontally without short bends. Its output and value label follow the new centre. The reset pin, pulse and caption are removed. Circuit behaviour and zoom transitions are unchanged.
