# Writing, graphics, and website style

Working conventions saved on 2026-10-12 for the chip library. They preserve the established visual direction and the collaboration decisions made with Aidan. New accessibility and publishing goals below are guidance for future work, not claims that the current prototype already implements them.

## Audience and purpose

Write the main path for a curious newcomer. Every major subject should have a high-level explanation, with links into as much technical depth as the subject needs. Demonstrate understanding of the semiconductor stack through clear mechanisms, worked examples, evidence, and honest trade-offs.

The library belongs to a company pursuing full-stack chip development. Keep explanations useful in their own right. Separate an architectural explanation from a product claim, company comparison, or marketing statement.

## Voice and teaching

- Avoid semicolons in prose. Use full stops or rephrase the sentence instead.
- Use British spelling and familiar language. Define technical terms at first use; avoid unexplained acronyms.
- Begin with a concrete question or capability. Explain why the next building block is needed.
- Develop intuition, show the mechanism, trace a small example, and explain the limits of the model. Link to derivations when they help rather than putting every prerequisite in the introductory article.
- Make transitions between levels explicit: what is being grouped into a new block, what behaviour it preserves, and what detail is now hidden.
- Keep analogies consistent with the physics. Identify the quantity represented by height, colour, position, or motion. Do not depend on a distant footnote to reverse a central explanation.
- Explain changes over time with a sequence or signal trace when relevant. State what is held fixed and what is allowed to vary.
- Use concrete trade-offs: what improves, what it costs, and under which conditions. Distinguish an example implementation from a universal claim.
- Preserve Aidan's authored passages. Discuss substantive editorial or structural approaches before implementing them; specific requested fixes can proceed. An audit request means inspect and report without editing.
- When restructuring, move retained passages verbatim unless Aidan explicitly requests wording changes. Permission to move or remove material does not imply permission to rewrite it.

## Scientific conventions

- Distinguish voltage from energy, conventional current from electron motion, and logic values from their physical voltage representation.
- Define terminal voltages and reference points. For a transistor explanation, avoid suggesting an absolute gate voltage alone determines its state in every circuit.
- State assumptions behind ideal switches, Boolean gates, timing models, and energy formulae. Keep a consistent notation within an article.
- Give quantities units, and define subscripts and indices. Worked calculations must agree with the diagram.
- Clearly distinguish combinational behaviour, stored state, configuration data, and instructions. Do not imply all storage uses the same cell or all real circuits are made exclusively from NAND gates.
- Verify technical claims against primary sources where needed. Follow the citation guidance below when choosing references for readers.
- Keep unresolved questions in the post plan. The first post's current prose is preserved for editing and is not a verified technical reference.

## Citations and source selection

Apply this guidance to the overview, deep dives and future articles, including reference audits.

- Prioritise references that readers can understand and learn from, provided they are accurate, relevant and of good quality. Wikipedia, lecture slides and course notes, clear technical websites and books are all appropriate choices.
- Also consider fundamental, influential research papers and substantial reviews. Include older landmark papers where they help explain an idea's origins or development, connecting today's semiconductor stack to its scientific and engineering history. Keep historical references relevant to the claim and distinguish the original result from current practice.
- Readability and rigour should work together. Use an accessible explanation for the reader and consult primary evidence to verify precise or disputed claims. Cite the primary source alongside the explanation when it adds useful evidence or context.
- Where relevant, also cite concrete process recipes, materials or “ingredient lists”, machine settings and measured results. These make the building process tangible and demonstrate practical understanding of the semiconductor stack from the ground up. Pair terse recipe tables with a clear explanation of what the materials and settings achieve.
- Check that every citation supports the nearby claim. Record the verified page, slide or section and the relevant edition, course year or device generation.
- Usually link directly to and highlight the relevant passage, so the reader can immediately find the evidence being discussed. Prefer a verified text-fragment link when supported. When highlighting is unavailable, link to the closest page, slide or section and identify the passage clearly.

## Scripts and visual direction

The company website’s `script.md` is the single source of article prose. Post 001’s local `script.md` links to that file, so do not maintain or synchronise a second prose copy. Keep short private **Visual cue** blocks in `visual-cues.md` and detailed prompts, timing instructions, alternatives and implementation decisions in `visuals.md`, under matching scene names. Neither notes file is imported into the published article.

Use stable scene keys to connect prose and visuals. A reader should be able to read the script comfortably without understanding code. Chapter plans and future ideas belong in `plan.md`; do not insert them into the public prose until that edit is agreed.

## Visual identity

The current direction is restrained line art on warm cream, generous space, and a continuous sense of construction as one level becomes the next. Prefer editable SVG or code-native diagrams for circuits and precise technical structures. Use raster illustrations where appropriate, preserving their source and prompts.

Current Post 001 colours, recorded from its CSS:

| Role | Value |
| --- | --- |
| Paper | `#f7f3ec` |
| Ink | `#17161a` |
| Muted prose | `#8d8781` |
| Floor shadows | `#e3ddd2` |
| Diagram captions | `#4a4540` |

Black line art is the baseline. The prototype already uses a restrained yellow bulb glow and red heat marks; do not describe the existing page as strictly monochrome. Use colour for a defined teaching purpose and never as the only distinction between states.

Active wire routes share one yellow stroke throughout the guide. The company stylesheet `hardware/publishing/sand-to-thought/articles/sand/figures/journey.css` defines `--signal-stroke` (`#c49b3c`), `--signal-width` (`3px`) and `--signal-glow` together. Logic connections, memory routes, computer paths and timing pulses use that common rule. The authoring equivalent is [web/style.css](../articles/sand/figures/journey.css). Highlights follow the exact wire geometry and appear above the base wires. Keep dots at genuine branching connections. Yellow identifies the selected or changing route rather than a binary value of 1. Timing keeps its travelling pulse and other routes retain their established animations.

## Typography and diagrams

- Follow the [Gradiated style reference](https://www.gradiated.com/style/). Use Instrument Sans at weight 500 for the article title and section headings. Use Barlow at weight 400 for prose and weight 500 for diagram labels and captions. Navigation and uppercase labels use the shared site typography. Use the website’s `--font-title`, `--font-body` and `--font-code` tokens so future brand updates carry through.
- Use normal prose text for component and architecture names and abbreviations, including MOSFET, MUX, ALU, PU, CU, CPU, I/O, ISA and FSM. Use Markdown inline code for signal names, register identifiers (including MAR, MDR, PC and IR), instruction mnemonics, logic values, bit strings, mathematical symbols and equations in article prose. Spell out ordinary counts in prose rather than styling them as code; use inline code for literal numeric examples and quoted bit-width designations such as `16-bit`. Use a subtle ink-tinted background and JetBrains Mono at 0.9em. Preserve superscripts, subscripts and leading zeros, and allow equations to wrap naturally on small screens.
- Approved caption reference is the “4-bit register” label. Use Barlow, weight 500, 13.5 SVG units for captions, with no text stroke. Muted drawing styles must not add outlines to text or its subscripts.
- For Post 001, diagram labels are 13 SVG units, small labels 10, and captions 13.5 or less. These sizes scale with the SVG; check actual readability at the intended viewport sizes.
- Use JetBrains Mono for diagram equations, bit strings and changing logic values. Disable ligatures on these diagram values and use tabular digits. Keep the current digit in worked bit strings at weight 600. Preserve real subscripts and clear mathematical notation.
- Memory diagrams use JetBrains Mono at weight 500 for signal names (`D`, `Q`, `WE`, `ADDR`), indexed ports and bus widths. Values and binary addresses use the same font at weight 600. Use 10 SVG units for array/bus labels, 13 for array values and focused latch labels, 16 for the focused latch values, and 6 only for miniature port labels inside latch boxes. Keep descriptive titles and captions in Barlow at weight 500 and 13.5 units. Size changes follow the zoom level and density; keep matching roles consistent within each view.
- Chapter 5 uses faint green framing for the memory building block and faint red for the processing unit. Their miniature labels remain readable. Thin dashed muted-red connections distinguish control signals from thick data buses. The established yellow highlights still show data transfers. A write-enable value and brief glow identify when a register may save its result.

- Use consistent line weights, clean joins, adequate spacing, and labels that do not overlap wires or symbols.
- Distinguish physical cross-sections, circuit symbols, logical blocks, and system diagrams. Show the transition rather than quietly changing what a drawing means.
- Label only terminals the explanation introduces. State axes, units, and the meaning of visual encodings when present.
- In the first post, preserve hollow circles for boron and filled dots for phosphorus. The heat formula retains `∝`.

## Animation and interaction

- Every appearance and disappearance should fade, draw, or transform smoothly. No abrupt popping, half-drawn paths that snap complete, or wires that finish disconnected.
- Animate a mechanism or meaningful relationship. Idle motion should not obscure the explanation.
- Give the reader stable states to inspect. Support scrolling backwards as carefully as forwards.
- Preserve visual identity across levels where helpful: the same object should visibly become the next abstraction.
- Do not require animation to carry essential facts alone. Future improvements should support readable static and reduced-motion presentations, keyboard use, and small screens.
- Test prose and diagrams together. Long paragraphs can affect the alignment of a scroll-driven scene; do not assume a text-only edit is visually neutral.

## Navigation and growth

The library should offer a clear start, subjects, selected question-led routes, and eventually search and a glossary when useful. Each article should indicate what it assumes, where it sits, and where to go deeper. Use stable links and a visible contents map as “How to get an answer out of sand” expands.

The agreed navigation model is one continuous opening journey, subject pages that organise reading, and focused explanatory articles. Contents links jump to chapters within the opening article; contextual links lead to deeper articles. Subject pages may use the relevant chapter as their introductory reading, with a short orientation and ordered onward links. Keep one source for each explanation and introduce broader subject overviews when useful. Show links to available material; navigation and subject pages are still planned.

For Post 001, keep heat within the arithmetic explanation at its current point. Give it no separate heading, contents entry, or “interlude” label. A future contextual link in its closing sentence can lead to an energy-and-heat article. Plan the memory ending around retaining the adder's answer; reserve LUT/FPGA explanations for later specialisation material and deeper articles. These are planning decisions, not permission to edit the live script or animations.

A recent-post feed can supplement the library, but the learning path should remain useful regardless of publication date. Revisit earlier articles as understanding improves. Give substantial factual corrections a brief revision note.

## Evidence for comparisons

Name the chip and generation, intended workload, numerical precision, relevant sizes or batch conditions, and what is being measured. Separate theoretical capability from demonstrated performance. State the boundary of power, cost, and throughput comparisons. Explain both gains and costs, and distinguish a claim, observation, and inference.

## Post-specific rules

Post-specific exceptions and fixed scenes belong in its `visuals.md`. For Post 001, scenes 0, 1, and 2 are fixed unless Aidan explicitly asks to change them. The original handover's scene-pinning verification recipe is preserved in that file and in the archive. The website's content and animation source were not changed during the folder setup.

## Verification before delivering a website edit

Reload the page, pin the affected scene using the post's documented recipe, inspect its settled state and relevant transitions in both directions, and check the browser console. Verify long labels and captions fit. Always check figure changes in both a wide landscape layout and a narrow portrait layout, including the settled views and their transitions; do not rely on one orientation. Check reduced-motion behaviour when affected. Report the checks actually performed; a startup smoke check is not a complete animation or accessibility audit.
