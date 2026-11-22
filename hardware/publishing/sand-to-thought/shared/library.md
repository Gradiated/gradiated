# The chip library

An accessible route through the entire computing stack, with deeper explanations available at every level. The library supports a company developing semiconductor chips across the stack: its explanations should connect physical mechanisms, software, architecture, implementation, and the trade-offs in real products.

## Reading routes

- **Start here:** [How to get an answer out of sand](../articles/sand/script.md), a living introductory journey. Its [working eleven-chapter roadmap](../articles/sand/plan.md#chapter-plan) extends the existing opening towards computers, software, data movement, parallel machines, chip development, complete systems, and an AI response. The current article covers chapters 1–5. The next discussion develops chapter 6; later chapters remain revisable.
- **Browse by subject:** use the [ten-subject map](topics.md#subject-map). Each subject should eventually have an accessible overview and deeper explanations.
- **Follow a question:** future articles can connect several subjects, for example “Why does moving data cost energy?” or “How can a circuit remember?”
- **Study an architecture:** future case studies should identify the particular product or generation, explain the intended workload and mechanisms, and compare benefits and costs under stated conditions.

Subjects describe knowledge; reading routes describe order. Post IDs do not dictate reading order. A linked topic is not necessarily a prerequisite for an overview: deeper treatments state what they assume.

## Agreed reading and navigation model

This is the intended structure, not an implemented website feature:

| Level | Purpose | Link behaviour |
| --- | --- | --- |
| Opening journey | One continuous illustrated article, with short named chapters explaining the connections between levels | A chapter name in its contents list jumps to that chapter on the same page |
| Chapter contents pages | A brief orientation, a link to the overview chapter, and an ordered list of deeper subchapters | The overview link jumps into the opening journey; each deeper subchapter opens its own article |
| Focused articles | Standalone answers to specific questions, with their own examples, illustrations, and deeper links | A contextual link in the opening journey or a subject page opens the relevant article |

The opening journey contains only its overview chapters. Deeper subchapters are separate articles, grouped by chapter contents pages. Give each deeper article one primary chapter and link to it from others when useful. The ten-subject topic map remains the coverage map across the whole stack.

The journey supplies shared introductory reading for several subjects. Subject pages can point to it without duplicating its prose. A subject may later receive a broader overview article when needed. Chapters and subjects do not have a one-to-one relationship. The depth and completeness of the library come from the connected collection; the opening journey should remain understandable on its own.

Heat stays within the arithmetic explanation, in its existing place, with no separate heading, contents entry, or interlude label. A future link from the closing sentence, potentially the words “Heat is a budget”, could lead to a focused article provisionally titled **Why do chips use energy and get hot?** Its title and link wording remain editorial candidates. Add links when their destinations exist.

The first-version article ends with one stored bit, a four-bit register, and storing the adder’s answer. The closing paragraph points towards a computer that follows instructions. LUT/FPGA material is preserved in [a saved draft](../articles/sand/drafts/programmable-logic.md) for later specialisation/configurable-hardware material, potentially chapter 8 or a focused article. The same opening article can expand over time.

## What the library should enable

Readers should eventually be able to trace a computation from software to physical switching; explain where its data lives and how it moves; identify limits on performance and energy efficiency; explain how the hardware is designed, manufactured, and tested; and compare architectures for stated workloads using evidence.

Connect both how a computer works and how engineers create one. Use the AI response as one complete worked destination, alongside future examples involving graphics, scientific computing, networking, signal processing, and embedded control. Revisit correctness, physical limits, reliability, security where relevant, engineering costs, and measurement throughout the library.

## Post register

| ID | Post | Role | Planning and assets |
| --- | --- | --- | --- |
| 001 | [How to get an answer out of sand](../articles/sand/script.md) | Opening overview through a simple computer executing an ADD instruction | [Plan](../articles/sand/plan.md) · [Visuals](../articles/sand/visuals.md) · [Website](../articles/sand/implementation.md) |

Post 001 is a draft integrated into the Gradiated website preview at `/sand-to-thought/`. **Sand to Thought** is the guide’s top navigation destination, immediately after Library. The opening article retains its title and prose, with the dune-to-circuit artwork above it and same-page chapter navigation. Library contains Notes and Methods. Separate chapter guides, chapter renaming, additional chapters, and deeper branch articles remain planned.

## Coverage and gaps

Detailed coverage is owned by the tables in each post's `plan.md`. The summary below is generated by `tools/update_library.py`; edit the plans, then regenerate it. “Introduced” means a first mental model. “Explained” means a mechanism is developed. “Worked” includes a traceable example or derivation. Publication status is independent of these descriptions. There is no blanket “topic complete” checkbox.

<!-- coverage:start -->
| Subject | Topic | Post | Depth | Status |
| --- | --- | --- | --- | --- |
| 1. Physics, materials and devices | [Silicon and doping](topics.md#silicon-and-doping) | [Post 001 — How to get an answer out of sand](../articles/sand/plan.md#topic-coverage) | Introduced | Chapters 1–5 published through merged PR #715. Further work is local on `first-deep-dive`. |
| 1. Physics, materials and devices | [MOSFET](topics.md#mosfet) | [Post 001 — How to get an answer out of sand](../articles/sand/plan.md#topic-coverage) | Introduced | Chapters 1–5 published through merged PR #715. Further work is local on `first-deep-dive`. |
| 2. Circuits and reliable signals | [CMOS logic gates](topics.md#cmos-logic-gates) | [Post 001 — How to get an answer out of sand](../articles/sand/plan.md#topic-coverage) | Introduced | Chapters 1–5 published through merged PR #715. Further work is local on `first-deep-dive`. |
| 3. Information, logic and arithmetic | [NAND and functional completeness](topics.md#nand-and-functional-completeness) | [Post 001 — How to get an answer out of sand](../articles/sand/plan.md#topic-coverage) | Introduced | Chapters 1–5 published through merged PR #715. Further work is local on `first-deep-dive`. |
| 3. Information, logic and arithmetic | [Full adder](topics.md#full-adder) | [Post 001 — How to get an answer out of sand](../articles/sand/plan.md#topic-coverage) | Introduced | Chapters 1–5 published through merged PR #715. Further work is local on `first-deep-dive`. |
| 3. Information, logic and arithmetic | [Ripple-carry addition](topics.md#ripple-carry-addition) | [Post 001 — How to get an answer out of sand](../articles/sand/plan.md#topic-coverage) | Introduced | Chapters 1–5 published through merged PR #715. Further work is local on `first-deep-dive`. |
| 4. State, timing, and memory | [Bistability and feedback](topics.md#bistability-and-feedback) | [Post 001 — How to get an answer out of sand](../articles/sand/plan.md#topic-coverage) | Introduced | Chapters 1–5 published through merged PR #715. Further work is local on `first-deep-dive`. |
| 4. State, timing, and memory | [D latch](topics.md#d-latch) | [Post 001 — How to get an answer out of sand](../articles/sand/plan.md#topic-coverage) | Introduced | Chapters 1–5 published through merged PR #715. Further work is local on `first-deep-dive`. |
| 4. State, timing, and memory | [Registers](topics.md#registers) | [Post 001 — How to get an answer out of sand](../articles/sand/plan.md#topic-coverage) | Introduced | Chapters 1–5 published through merged PR #715. Further work is local on `first-deep-dive`. |
| 3. Information, logic and arithmetic | [Multiplexers](topics.md#multiplexers) | [Post 001 — How to get an answer out of sand](../articles/sand/plan.md#topic-coverage) | Introduced | Chapters 1–5 published through merged PR #715. Further work is local on `first-deep-dive`. |
| 3. Information, logic and arithmetic | [Arithmetic and logic units](topics.md#arithmetic-and-logic-units) | [Post 001 — How to get an answer out of sand](../articles/sand/plan.md#topic-coverage) | Introduced | Chapters 1–5 published through merged PR #715. Further work is local on `first-deep-dive`. |
| 2. Circuits and reliable signals | [Signal propagation and settling](topics.md#signal-propagation-and-settling) | [Post 001 — How to get an answer out of sand](../articles/sand/plan.md#topic-coverage) | Introduced | Chapters 1–5 published through merged PR #715. Further work is local on `first-deep-dive`. |
| 4. State, timing, and memory | [Memory addressing](topics.md#memory-addressing) | [Post 001 — How to get an answer out of sand](../articles/sand/plan.md#topic-coverage) | Introduced | Chapters 1–5 published through merged PR #715. Further work is local on `first-deep-dive`. |
| 5. Processors and the software stack | [Processor organisation](topics.md#processor-organisation) | [Post 001 — How to get an answer out of sand](../articles/sand/plan.md#topic-coverage) | Introduced | Chapters 1–5 published through merged PR #715. Further work is local on `first-deep-dive`. |
| 5. Processors and the software stack | [Stored programs](topics.md#stored-programs) | [Post 001 — How to get an answer out of sand](../articles/sand/plan.md#topic-coverage) | Introduced | Chapters 1–5 published through merged PR #715. Further work is local on `first-deep-dive`. |
| 5. Processors and the software stack | [Instruction processing](topics.md#instruction-processing) | [Post 001 — How to get an answer out of sand](../articles/sand/plan.md#topic-coverage) | Worked | Chapters 1–5 published through merged PR #715. Further work is local on `first-deep-dive`. |
| 6. Performance, parallelism and communication | [Dynamic switching power](topics.md#dynamic-switching-power) | [Post 001 — How to get an answer out of sand](../articles/sand/plan.md#topic-coverage) | Introduced | Chapters 1–5 published through merged PR #715. Further work is local on `first-deep-dive`. |
| 9. Manufacturing, packaging and systems | [Wafer production](topics.md#wafer-production) | [Post 001 — How to get an answer out of sand](../articles/sand/plan.md#topic-coverage) | Introduced | Chapters 1–5 published through merged PR #715. Further work is local on `first-deep-dive`. |
<!-- coverage:end -->

The first draft mainly introduces subjects 1–4, with introductory processor material, switching power and wafer production. Programmable logic remains a saved draft. Subjects 8 and 10 currently have no article coverage; the remaining subjects have substantial gaps too. An introductory mention is not a substitute for a dedicated explanation or technical review.

## Development order

1. Review the implemented chapter 5 and discuss the [chapter 6 outline](../articles/sand/plan.md#chapters-5-and-6-discussion-outline), retaining all eleven chapter names. Establish the brief timing bridge from stored values to coordinated operations.
2. Agree chapter 6's software-to-instruction example. Keep its connection to the machine assembled in chapter 5 clear.
3. Draft approved sections paragraph by paragraph. Keep checking text-aware scene alignment and preserve the first three illustrations.
4. Develop chapter 6's software-to-instruction route and the focused instruction-processing article, using the saved LC-3 encoding and binary load examples. Keep an overview and a deeper treatment distinct. Other branches into devices, reliable bits, arithmetic, energy and memory can develop as useful.
5. Extend later towards data movement, parallelism, design and manufacturing, systems, and an AI workload as the explanations are developed. Publication order can follow the developing understanding.

### Lecture 6–7 planning checkpoint — 2026-10-13

The [saved recap](../../../learning/courses/eth-ddca-lectures-06-07-recap.md) and [main learning notebook](../../../learning/courses/chip-architecture-notebook.md) inform the next work. These notes mainly support chapter 4's timing bridge and chapter 5's computer, with an initial connection to chapter 6. Early mentions of verification and memory organisation are foundations for later revisiting those subjects, not coverage of the whole of chapters 7–11. Lecture numbers and chapter numbers measure different things.

The eleven chapter names are unchanged. Make the three questions explicit when explaining the machine — what parts it contains, what commands software can give it, and how the circuits carry them out. Timing and correctness recur where needed, with fuller engineering treatment in chapter 9. The new chapter outlines are proposals for discussion. This checkpoint changes planning only, leaving the article and website as they are.

Publication order may differ from the final reading order. Preserve a stable home for “How to get an answer out of sand” and use named chapters and a contents map as it grows. Improvements to earlier articles are expected; record significant corrections and keep links useful.

## Architecture case studies

NVIDIA GPUs, Google TPUs, and other chips are a destination for the library, not separate foundations that require duplicate explanations of memory or arithmetic. Candidate families discussed in the learning notes also include AMD GPUs, AWS Trainium, Cerebras, and Groq. This is a research queue, not a ranking or publication commitment.

For each case, explain the workload, organisation of computation and storage, data movement, control and programming model, bottleneck, and trade-off. Distinguish specifications, theoretical peaks, measured results, and inferences. Name the generation and comparison conditions, including precision, workload size, batch size, latency or throughput objective, and measurement boundary where relevant.

Chapter 5 is implemented locally. Timing stays a short propagation-and-capture explanation, with detailed timing and instruction processing planned as deeper articles. All eleven chapter names remain unchanged.
