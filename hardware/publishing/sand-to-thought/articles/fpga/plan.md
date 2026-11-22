# FPGA deep dive

## Original scope — 29 October 2026

Local interactive first draft, implemented on 29 October 2026 after Aidan authorised the article build and regular self-audits. The existing prose and references remain canonical. The page, interactive figures and grey library card are connected locally. No hardware experiment, compiled HDL implementation or performance measurement has been performed for this article.

- [Canonical prose](./script.md)
- [Article references](./script.references.json)
- [Shared writing and visual conventions](../../shared/style-guide.md)
- [Purpose and goals](../../README.md#purpose-and-goals)

The title is **Inside our FPGA**, with the subtitle **A chip you can reconfigure.** Local route is `/sand-to-thought/fpga/`, linked from the collection library. The registered page wrapper is marked `draft`, so it is available locally and on preview builds but excluded from production, including its library link. Keep all work local until Aidan requests otherwise.

Work is on `FPGA-deep-dive`, created from `first-deep-dive`. Fabrication PR [#844](https://github.com/Gradiated/gradiated/pull/844) was still open when checked on 29 October 2026. Do not merge, rebase, commit, push or deploy as part of drafting. Preserve the existing fabrication edits and untracked collection notes. Update, 30 October 2026: #844 has merged and this branch has been fast-forwarded to that merged main; subsequent FPGA work remains local. Preserve the earlier dated status as history.

The goal is to understand the mechanism, then connect it to engineering practice and the wider field. The audience can write software but need not know electronics. No fictional projects. On 30 October 2026, Aidan selected a real FPGA inference build as the article’s practical thread. The [LED pulse generator walkthrough](led-pulse-generator.md) is saved for a future practical guide. The main article explains the build process through the transformer itself.

## Inference progress record

### 20 November 2026 — measurement introduction

The measurement introduction shows a plain routing grid without a resource callout. Resource highlights and labels begin with the first experiment.

### 20 November 2026 — chip comparisons after the measured results

The article shows the four outlines in a compact grid with the chip name beneath each one. The opening paragraph identifies them by row and distinguishes measured FPGA inference from illustrative estimates. The detailed lecture view retains its captions and spoke labels.

The final measured profile and the four smaller hardware profiles use the article’s figure and prose columns, with figures on the left and reading text on the right. Both figures fill the same centred column up to 30rem wide, including when the text moves below them. The columns follow the same responsive breakpoints as the experiment chapter. The KV260 fabric and its Cortex-A53 share the same external memory. The NVIDIA H100 SXM and Google TPU v5e use their per-chip specifications. All four diagrams share the five spokes and scales of the measured KV260 profile. Grey dashed outlines combine specification-based capacity and bandwidth with illustrative, unmeasured latency, decode and energy values. The article shows the operation counts, assumed effective rates, overheads and power for the frozen three-prompt workload. GPU and TPU share the same uncalibrated accelerator scenario. The estimates live in the article figure, outside the experimental run records. The prose retains the four architectures’ strengths and trade-offs. Tokens/s, first-token time and tokens/J remain specific to the measured KV260 workload.

### 20 November 2026 — original and final KV260 profiles

The opening profile shows the [experiment 24 candidate](../../../../research/inference/results/attention-clock-20261120T004416Z-a9d9d2/run.json) alone. The smaller closing profile compares it with the CPU-controlled arm of [the first board comparison](../../../../research/inference/results/autonomous-prefill-decode-20261115T210134Z-97efcb/run.json) and includes the electricity estimate and methods. Both use the existing article graph's mixed-prompt timing and energy data. Module tokens per joule and tokens per dollar of module electricity describe the same energy measurement. The latter assumes 24.51p/kWh and $1.3431/£ for Q2 2026. The closing chart explains its scales and electricity estimate in its disclosure and links to the measurement chapter for the shared test method.

The five spokes share fixed scales across profiles. TTFT runs from 1,000 to 0.1 ms, decode from 1 to 20,000 tokens/s, module efficiency from 1 to 10,000 tokens/J, external bandwidth from 1 GB/s to 25 TB/s and 16-bit weight capacity from one million to six trillion weights. These scales are logarithmic. Board specifications, calculated ceilings and measurements are identified in the reader's disclosure. Use matched model, prompts, concurrency, timing and power boundaries for future chip overlays. Lecture 4 retains its illustrative profiles.

### 19 November 2026 — neutral read-ahead comparison

Experiment 5 restores a compact Before/After comparison. Before, “Multiply + add” leads to “Read next pair” with an arrow. After, the two jobs align vertically beside “Same cycle”. All four boxes share the same neutral style. Clock headings, pair numbers and footnotes remain absent. The chip map now marks both CLB logic and DSPs: the controller coordinates the read-ahead schedule while the existing DSP arithmetic calculates with the current pair. This matches the [final-scoring pipeline change](../../../../research/inference/results/logits-pipeline-20261116T143416Z-2592fd/run.json); the measured DSP count is unchanged. The accessible description distinguishes the old schedule from the overlap. Prose, measurements, the transformer overview and other experiment details are unchanged. Checked at 1280 × 720, 390 × 844 and 844 × 390: labels fit their boxes, all four jobs have identical neutral fills and borders, and there is no text overlap, clipping or horizontal overflow. CLB/DSP labels fit beside the chip. Forward and reverse navigation through adjacent experiments works on desktop and phone. TypeScript, all 27 FPGA tests and DevEx passed, with no browser console errors. The static comparison retains the existing entrance and reduced-motion rules.

### 19 November 2026 — simpler read-ahead figure

Experiment 5 replaces the three-clock timeline with two aligned boxes: a neutral “Read next pair” and a gold “Multiply + add”. One caption, “Same clock cycle”, explains the overlap. The clock headings, Before/After rows, pair numbers and two explanatory footnotes are removed. The larger shared diagram type replaces the timeline-specific small text. The accessible description retains the distinction between reading the next pair and calculating with the current pair. The transformer overview, chip map, prose, measurements and other experiment details are unchanged. Checked at 1280 × 720, 390 × 844 and 844 × 390: labels fit their boxes with no text overlap, clipping or horizontal overflow. Forward and reverse navigation through adjacent experiments works on desktop and phone. TypeScript, all 27 FPGA tests and DevEx passed, with no browser console errors. The static detail keeps the existing entrance and reduced-motion rules.

### 19 November 2026 — simpler transformer overview

The shared token-generation figure now uses text and block widths about ten per cent smaller. Normalisation blocks are shallower, leaving equal thirteen-unit gaps between the ordinary stage blocks. Attention is a single block except in experiment 13, where it expands smoothly to reveal two heads and highlights Head 1. Other rows and their connecting arrows move together during that expansion, and the head detail fades in or out. The existing reduced-motion rule disables these transitions. Final normalisation, scores and next-token labels, CPU/FPGA selection and the experiment highlights remain. The screen-reader description identifies the head detail only when expanded. Prose, measurements and right-hand experiment figures are unchanged. Checked the compact baseline and all ordinary experiment states, plus the expanded experiment 13 state, at 1280 × 720, 390 × 844 and 844 × 390. Visible labels fit their blocks without overlap, clipping or horizontal overflow. Attention expands and collapses correctly on desktop and phone, retaining the relevant stage/head/cache and CPU/FPGA highlights. TypeScript, all 27 FPGA tests and DevEx passed, with no browser console errors. The scoped transition properties and the existing reduced-motion override were inspected.

### 19 November 2026 — clearer token-generation figure

The shared experiment panel is titled “Generating a token”. Labelled scores travel from the scoring layer into token selection, and a labelled next-token return path points back to embedding. Small downward arrows identify the main processing order. The unexplained left bracket is removed, and final normalisation is shown before scoring, matching `normfinal` in [the model implementation](../../../../research/inference/implementations/kv260/rtl/transformer.sv). The CPU selects tokens in the baseline and the FPGA does so thereafter. Existing stage/head/cache highlights are retained, including highlighting both displayed normalisation stages in scalar-arithmetic experiments. A screen-reader description follows the same flow. This remains a simplified overview, omitting residual connections and the separate normalisation before the feed-forward stage. Article prose, measurements and right-hand experiment figures are unchanged. Checked the baseline and all fourteen experiment states at 1280 × 720, 390 × 844 and 844 × 390. Labels fit their boxes, no text overlaps or clips, and there is no horizontal overflow. Reverse scene navigation also passed on desktop and phone, including the CPU/FPGA selection labels and stage/head/cache highlights. TypeScript, all 27 FPGA tests and DevEx passed, with no browser console errors. Existing animation and reduced-motion rules are unchanged.

### 19 November 2026 — scoring read-ahead timeline

Experiment 5’s FPGA panel is titled “Read while calculating”. Its three-clock Before/After timeline includes the initial read, then shows calculation of one input–weight pair overlapping the read of the next. Gold identifies multiplication and addition in both schedules, while reads stay neutral. Two short captions explain the calculation and pair numbers. The accessible description follows the same sequence. The centred chip map, article prose, measured results and other experiments’ detail diagrams are unchanged. This is a schematic of the initial read and steady calculation loop, omitting end-of-score rounding and output handling. Checked at 1280 × 720, 390 × 844 and 844 × 390: all timeline text fits, labels stay inside their boxes and there is no text overlap or horizontal overflow. Forward and reverse navigation through adjacent scenes works on desktop and phone. TypeScript, all 27 FPGA tests and DevEx passed, with no browser console errors. The static timeline retains the existing entrance and reduced-motion rules.

### 19 November 2026 — centred experiment chip maps

The FPGA chip outline is horizontally centred in every experiment's top-right panel using the shared map transform. Resource leaders are slightly shorter, and multiword resource labels use two lines so they fit beside the centred chip throughout scene changes. The lower experiment details, prose and measurements are unchanged. Checked all five resource-label layouts at 1280 × 720, 390 × 844 and 844 × 390. The chip outline has zero horizontal offset from the panel centre, labels stay inside the drawing area and there is no horizontal overflow. Forward and reverse scene changes, TypeScript, all 27 FPGA tests and DevEx passed, with no browser console errors. Existing animation and reduced-motion rules are unchanged.

### 19 November 2026 — scoring-layer explanation and label

Experiment 5 now explains the final scoring layer after normalisation, the original alternating read/calculate schedule and the overlapping schedule. Its resource increase is explicitly scoped to the final-scoring change, and it points forward to reuse in experiments 9 and 10. The transformer diagram's shared final-stage label reads “Scoring layer” for every experiment. The measured results and circuit schedules are unchanged. Verified the five-paragraph passage in the preview and the label at 1280 × 720, 390 × 844 and 844 × 390, with no clipping or horizontal overflow. Phone scrolling from experiment 5 into 6a and back retains the correct figures. Desktop scene navigation also retains the shared label. All 27 FPGA tests and DevEx passed, with no browser console errors.

### 19 November 2026 — simple arithmetic comparisons

Experiments 3 and 4 share a compact Before/After comparison beneath the chip map. The rows show bits per clock and calculation steps: multiplication changes from 1 to 4 bits and 64 to 16 steps, while division changes from 1 to 2 bits and 64 to 32 steps. Before values are muted and improved values are gold, without surrounding boxes. The chip maps and resource callouts remain. Accessible descriptions match the comparisons and retain division's final finishing cycle. Prose and measured results are unchanged. Checked both comparisons at 1280 × 720, 390 × 844 and 844 × 390, with no text overlaps, clipped labels or horizontal overflow. Scene changes work in both directions on desktop and phone. TypeScript, all 27 FPGA tests and DevEx passed, with no browser console errors. The existing entrance fade and reduced-motion rules are unchanged.

### 19 November 2026 — division inputs and saved progress

Experiment 4 now matches the multiplication figure's visual language. Two labelled inputs show the next two bits of the 64-bit number and the number to divide by. A Divide block feeds saved progress labelled “Answer + remainder”, with a clock input and feedback loop. The caption distinguishes two answer bits per clock from the 32 calculation steps. The accessible description retains the additional finish cycle. The schematic follows the [measured two-bit divider](../../../../research/inference/results/scalar-div-20261116T105755Z-3c2ae0/run.json), abstracting shifts, quotient selection and final sign/range handling. It remains labelled CLB Logic. Prose and measurements are unchanged. Checked at 1280 × 720, 390 × 844 and 844 × 390, with all labels inside their boxes and no text overlaps or horizontal overflow. Adjacent scene changes work in both directions on desktop and phone. TypeScript, all 27 FPGA tests and DevEx passed, with no browser console errors. The new diagram is static and retains the existing reduced-motion entrance handling.

### 19 November 2026 — removing the experiment guide stroke

The short, unlabelled vertical guide beneath the chip map is removed from the shared experiment figure. This applies to every experiment and leaves the labelled circuit connections unchanged.

### 19 November 2026 — multiplication inputs and saved progress

Experiment 3’s detail now shows a full 64-bit input and the next four bits of the other input feeding multiplication, followed by addition into saved progress. A feedback arrow returns that progress to the addition, with a separate clock input showing when it updates. The chip map marks CLB and DSP resources and labels them “CLBs + DSPs”. The simplified drawing follows the [measured scalar-multiplier variant](../../../../research/inference/results/scalar-mul-20261116T001133Z-268099/run.json), retaining sixteen calculation steps. The caption reads “64 → 16 calculation steps” to show the improvement directly. Arithmetic state, shifts and sign/error handling remain abstracted. The prose, measured values and other experiment details are unchanged. The input and saved-progress boxes, arithmetic circles and their labels are slightly smaller, leaving more space between the blocks. Connecting arrows and the clocked feedback loop meet the resized shapes.

Checked the settled figure at 1280 × 720, 390 × 844 and 844 × 390, plus forward and reverse scene changes on desktop and phone. TypeScript, all 27 FPGA tests and DevEx passed. The existing reduced-motion rule covers the additional map-focus fade, and the new mechanism itself is static. The smaller blocks and labels were rechecked at the same three viewport sizes, with forward and reverse scene changes on desktop and phone. TypeScript and all 27 FPGA tests passed again, with no console errors or overlapping labels in the resized mechanism.

### 19 November 2026 — score-label clarification

Experiment 2’s figure now says “Score only the last token onwards” to clarify that scoring continues during generation. This changes the label only.

### 19 November 2026 — one FPGA editing and publication source

Aidan designated the reconciled article in `/Users/aidanmcconnell/dev/gradiated`, on `FPGA-deep-dive`, as the only FPGA article intended to go online. All article prose, figure, reference and results-selection edits belong in that checkout. The local preview is `/sand-to-thought/fpga/` on port 5173. The `gradiated-hardware-wip` article is superseded recovery material, not a parallel draft. Publishing instructions in both checkouts record this rule. No deployment is authorised by this source decision.

### 19 November 2026 — reconciling the edited article

The `FPGA-deep-dive` checkout in `/Users/aidanmcconnell/dev/gradiated` serves the local article. The manually edited prose and approved figure changes from `gradiated-hardware-wip` have been reconciled into that source. The edited wording through the transformer explanation is preserved, including the SRAM left/right explanation, MUX example, hardwired-chip comparison, one-DSP comparison, KV-cache detail and shorter fixed-point explanation. The projection dropdown and its `fpga-projection` target are restored. The newer design-tool/timing paragraph, model context, neuron/carry explanations and token-selection motivation remain as additions. The current board walkthrough and complete measured-inference chapter, including all thirteen experiments, chart data and source records, are preserved. Older statements that the physical test and measurements were still pending are superseded by those measured results.

The routing-input and IP-block prose scenes and IP animation are removed. Configuration settings arrive continuously, the clock has a darker light-theme signal and a pulse, and the three small filled DSP arrows share their wire highlights. The I/O highlight has light-theme contrast without duplicate darker base wires. Both transformer bypasses have directional arrows. The surrounding transformer remains visible for the first 250 ms of the 900 ms zoom, with immediate/reduced-motion views retaining their existing behaviour. The opening output pin follows the same selection as the rest of its path. New board/measurement transitions and token-flow direction are retained.


### 18 November 2026 — resources alongside each measured circuit

The baseline and fourteen measured variants share one resource chart. Counts are for the full placed and routed design. Each percentage uses the available K26 count for that resource. Occupied CLBs include the reported LUTs and registers. BRAM is in 36-kilobit tile equivalents. The [figure data](figures/measurementData.ts) follows the order of the [selected physical runs](results.json). Each run’s resource evidence identifies its control and candidate implementation reports. Occupied CLBs and UltraRAM were checked in the archived routed utilisation reports. Resource changes in the prose use the actual paired control, including experiment 5 for 6b and experiment 11 for 13.

Each resource label and its pointer move with the circle on the chip map. Experiment 12 marks both placements on the chip map. The close-up moves one illustrative weight pattern from BRAM in the earlier build to LUTs inside a CLB in the new build. The scalar multiplier and score lanes use one DSP marker, with the lane count shown in the close-up.

### 18 November 2026 — KV260 chip label

The Zynq label sits on the chip outline. The CPU and programmable logic are inside that outline, with the FPGA logic label directly above the fabric drawing. The board overview and request animation share this placement. Both omit the prospective FPGA-to-DDR4 route. The article distinguishes the BRAM baseline, the measured move of one weight set into LUT memory and the planned DDR4 experiment.

### 18 November 2026 — token prediction layout

The two-prediction figure puts the CPU on the left and the FPGA on the right, matching the following KV260 board view. The scores travel left to the CPU, and the selected token travels right to the FPGA. The prompt and output paths meet the CPU on the left.

### 18 November 2026 — measured inference on the KV260

The closing chapter follows the CPU-controlled circuit and all thirteen completed physical experiments with the frozen text-input model at 50 MHz. Experiment 6 has two points because both lane counts were measured against one lane. Experiments 12 and 13 each use Experiment 11 as their control. [Selected physical runs and checksums](results.json). The [chart data](figures/measurementData.ts) identifies the run and paired control for each point. Each experiment tick shows three workload values. TTFT is the mean of all 18 admission-to-first-byte intervals. Decode TPS divides 1,878 output tokens after the first by the sum of all first-to-last-byte intervals. There are six replies each of 90, 122 and 104 useful bytes for Hello, the six-byte prompt and the 48-byte prompt respectively. Both calculations were checked against the per-request samples in the pinned records and the original board timestamps. Gross module joules per useful output byte use three mixed-prompt power blocks. The chart does not measure wall energy. Experiment 10 retains its peripheral caveat, with more detailed observations in Experiments 11 and 13.

The reusable stage pairs a simplified transformer with a schematic fabric map and an expanding history of absolute measurements. The three series share an experiment axis, with separate linear scales for first-token milliseconds, decode tokens per second and module joules per output token. At the chapter boundary, the FPGA logic on the KV260 board moves into the measurement panel as the board surroundings fade. Scrolling back returns it to the board. Reduced motion shows the settled views directly. Each experiment detail is centred beneath the map at a uniform scale in both dimensions. The map labels the configurable logic as CLB Logic. The token feedback path shows where the CPU handover disappears. Experiments 5, 9 and 10 share a clock diagram showing a read moving into the same tick as the addition. The paired exponential diagram follows two scores inside one head. The stage follows the measured builds in both scroll directions. Physical acceptance supersedes the earlier pending board test. The opening profile and Lecture 4 illustrations retain their separate illustrative status.

Engineering detail for the transformer walkthrough is recorded in the [KV-cache interface](../../../../research/inference/implementations/kv260/hardware.md#kv-cache-measured-result-and-interface), the [selected model and tokenisation record](../../../../research/inference/implementations/kv260/model/conditioned.md) and its [configuration](../../../../research/inference/implementations/kv260/model/conditioned.json). The [server record](../../../../research/inference/implementations/kv260/history/server-record.md) preserves the timing diagnostics and resource counts. The [board acceptance record](../../../../research/inference/results/physical-acceptance-20261114T232418Z-c39918/run.json) records the score and reply checks.

### 16 November 2026 — choosing a chip for inference

The chip comparison table and orbit close “Measuring inference on the KV260.” Their examples connect the four chips to model arithmetic, token selection and request volume. The LED timer, standalone CPU–FPGA diagram and general pipelining paragraph were removed from the article’s closing sequence. Lecture 4 keeps its chip comparison slide and contents link. The comparison describes design trade-offs and uses no new hardware measurements.

Checked the table, chip selection and scroll transition in a local preview across desktop, phone portrait and phone landscape. TypeScript, FPGA tests, citation tests and DevEx checks passed.

### 16 November 2026 — opening circuit and trade-offs

The opening figure now keeps AND selected while its inputs go from `11` to `10`, then keeps `10` fixed while switching the rule to OR. The later LUT close-up explains the same change by rewriting rows `01` and `10`. The routing section explains the energy cost of extra programmable connections, and the bitstream section introduces fitting, routing and timing checks with the earlier missed `100 MHz` target as an example. These are teaching and editorial changes.

### 14 November 2026 — hardware consolidation

The article script, references, figures and this progress record now live together under `hardware/publishing/sand-to-thought/articles/fpga/`. Lecture 4 lives under `../../lectures/lecture-4/`. The website retains its route wrappers and imports these sources. This move preserves the existing prose, scene design and chart values.

The [inference project](../../../../research/inference/README.md) combines the Mac model work with recovered Linux circuit and host tools. The original transformer has physical-board correctness evidence. The newer text-input model has software and RTL evidence, with its board test pending. No new model training, board test or performance/energy measurement was performed during consolidation. The opening charts remain illustrative and the closing measurements remain planned. Local artifact recovery and pending shared backup are recorded in the [storage register](../../../../research/inference/storage.json).

### 14 November 2026 — interactive chip comparison

Choosing a chip reuses the four processor symbols from Lecture 4. The selected chip moves to the centre of the orbit with its strength and trade-off above and below. The full cited comparison remains available in the article. The figure compares design choices without adding benchmark data.

### 13 November 2026 — reusable IP on the routing map

The article introduces IP blocks at the end of Choosing the connections. The original chip map retains the selected path from CLB 4 through the routing MUX to CLB 5. Four highlighted CLBs illustrate how a reusable processor design can occupy part of the configurable logic. This is a teaching diagram with illustrative placement.

### 13 November 2026 — article performance chapter removed

The article now moves from the KV260 walkthrough to Choosing a chip. The comparison table keeps the distinction between latency and throughput. The measurement plan explains why DSPs need a steady supply of weights. The original adder, pipeline and energy figure plans are kept below for future teaching.

### 13 November 2026 — Lecture 4 inference resources

[Slide 2](../../lectures/lecture-4/script.md#02-how-would-we-compare-this-chip) pairs the illustrative profile with the KV260’s inference resources. DDR4 peak bandwidth is derived from AMD’s published 64-bit, 2,400 Mb/s interface. The demo’s raw parameter storage is derived from 26,720 parameters at 16 bits each. The fixed-weight example illustrates what can be built into a circuit. The [article’s verification record](./script.md#running-a-tiny-transformer) describes the existing block-RAM implementation and its software, RTL and board evidence.

### 13 November 2026 — Lecture 4 closing benchmarks

[Slide 58](../../lectures/lecture-4/script.md#58-how-far-can-we-push-this-fpga) sets out a model capacity test and fixed small and larger model benchmarks for speed and energy. Five named chips have compact, unlabelled spider charts with placeholder scores and the same spokes as the opening chart. The [article’s verification record](./script.md#running-a-tiny-transformer) records the existing software, RTL and physical board evidence.

### 13 November 2026 — Lecture 4 inference experiments

[Slide 57](../../lectures/lecture-4/script.md#57-experiments-with-inference-on-our-fpga) uses a [dual-axis chart](../../lectures/lecture-4/assets/illustrative-throughput.svg) to show hypothetical throughput and cost across four experiments. The third moves the model weights and KV cache to distributed RAM. The fourth runs more multiply-adds in parallel. The speaking notes list the four planned measures. The curves are illustrative. The [article’s verification record](./script.md#running-a-tiny-transformer) distinguishes existing software and RTL checks from the original physical board run.

### 13 November 2026 — Lecture 4 chip comparison

[Slide 56](../../lectures/lecture-4/script.md#56-choose-the-chip-for-the-job) compares the FPGA, CPU, GPU and ASIC. The FPGA row gives more space to sustained throughput on large streams, predictable timing, custom interfaces and arithmetic, reconfiguration, and their practical limits. It draws on the [article’s chip comparison](./script.md#choosing-a-chip). The slide describes design trade-offs without introducing benchmark data.

### 13 November 2026 — continuous request animation in Lecture 4

[Slide 55](../../lectures/lecture-4/script.md#55-follow-a-request-through-the-board) shows the prompt travelling from the laptop through Ethernet and the controllers to Arm. After each score transfer, Arm sends the chosen token back to the FPGA for the next calculation and through the network to the laptop. The laptop adds the character when the update arrives. The lecture uses a narrower laptop drawing with a smaller prompt. On opening the slide or pressing Replay, it first shows the KV260 boot firmware coming from QSPI flash, then Linux loading from microSD into DDR4 for Arm to run. The request loop begins after that introduction. The boot sequence follows [AMD’s KV260 boot guide](https://docs.amd.com/r/en-US/ug1089-kv260-starter-kit/Boot-Devices-and-Firmware-Overview). The figure illustrates the route described in the [FPGA article](./script.md#running-a-tiny-transformer), using the existing software example. Checked the route joins, live marker movement in the browser, TypeScript and 14 FPGA tests.

The article’s board request figure now shares Slide 55’s compact laptop, boot introduction, and continuous prompt, score and token paths. It runs at the article’s usual speed, with the lecture retaining its slower pace. Startup plays on entry, and subsequent requests loop from the prompt. The article prose describes the illustrated boot and reply paths alongside the existing software and board evidence.

### 12 November 2026 — Lecture 4 closing slides

The [closing slides](../../../../../product/website/lectures/README.md#lecture-4--inside-our-fpga) pair the existing illustrative throughput curve with first-token latency, output rate, whole-board joules per output token and estimated cost per million output tokens. The labels now describe possible experiments in token selection, weight placement and cache placement. The [speaking notes](../../lectures/lecture-4/script.md#measuring-inference-on-the-kv260) state the cost assumptions and connect AI-assisted circuit changes and checks to repeated board experiments. The graph still uses example values. Existing software, RTL and physical board evidence is recorded separately in the [FPGA article](./script.md#running-a-tiny-transformer).

Both slides were checked at 1440 × 900, 390 × 844 and 844 × 390. TypeScript and DevEx passed.

### 12 November 2026 — Lecture 4 presentation

The [local slide deck](../../../../../product/website/lectures/README.md#lecture-4--inside-our-fpga) reuses all 64 article scenes and adds four slides for the cover, inference profile, SRAM write illustration and illustrative throughput graph. The [speaking script](../../lectures/lecture-4/script.md) links each slide to two or three bullets. It distinguishes the software token trace, RTL checks and original KV260 board run. The newer text-input model’s board test remains pending.

Checked all 68 slides at 1440 × 900, 390 × 844 and 844 × 390, plus direct slide links, replay, chapter jumps and keyboard controls. TypeScript, 26 FPGA tests, seven citation tests and DevEx passed.

### 12 November 2026 — inference benefits and limitations

Added a six-row semantic table within “Choosing a chip”, pairing latency, throughput, storage/data movement, energy, edge processing and reconfiguration with their constraints. The existing FPGA map stays alongside it. Scoped styles stack each benefit above its limitation on phone portrait while preserving table semantics. NPU context and engineering/IP costs remain in the surrounding prose. A separate supplier-migration note distinguishes retargeting a design from portable bitstreams or guaranteed availability.

Sources checked: Microsoft Project Brainwave and its 2018 ISCA paper, sections I–III (architecture, on-chip memory and configurable arithmetic), hls4ml’s FAQ (parallelism, resource fit and precision), Altera’s sensor-processing overview, and Efinity Software User Guide v16.1, June 2025, pp. 27–28 (device migration). Efinix’s supplied shortage campaign is attributed as a vendor proposal, not current stock evidence. Its form lists 2023–24 dates. No historical performance result is presented as a KV260 measurement or a general ranking against current CPUs, GPUs or NPUs.

This is a reusable teaching comparison, not new model, RTL-simulation or physical-board evidence. The engineering source remains the separate inference checkout’s `research/fpga-inference/README.md` and `model/conditioned.md`. The original model’s board run and the newer text-input model’s pending board test are unchanged. Checked desktop 1440 × 900, phone portrait 390 × 844 and phone landscape 844 × 390, including forward/reverse transitions. TypeScript, seven citation tests, three scroll tests, DevEx and whitespace checks pass. Work remains local.

Use this section to keep the article and lecture work reproducible across chats. Add a short dated entry when a model, circuit, measurement or reusable teaching figure changes. Record what changed, why, what was checked, and where to find the source or evidence. Keep failed attempts when they inform the next build. The separate `codex/fpga-inference` worktree holds the underlying model and engineering records in `research/fpga-inference/`. Start with its `README.md`, `model/README.md`, `model/conditioned.md` and `history.md` for the relevant model and experiment history.

### 13 November 2026 — slide 57 API callout

The [illustrative chart](../../lectures/lecture-4/assets/illustrative-throughput.svg) uses a gold callout above the chart, to the right of the lecture bullets, to point to the final output-rate point as a candidate for the API. The plotted values remain hypothetical. The separate inference checkout’s `research/fpga-inference/model/conditioned.md` remains the engineering record.

### 12 November 2026 — connected KV260 board view

The board view keeps the same FPGA map within the Zynq chip and connects the CPU, DDR4, boot flash and carrier microSD through a simplified processing-system interface. Power enters at the carrier edge. A following `board-request` scene emphasises the laptop and highlights the prompt, token, score and returned-text paths. The two scenes share the same component and camera so scrolling between them changes emphasis without replacing the board. These are functional connections, not physical trace routing or a floor plan. Memory and storage access are grouped for readability, and the request arrows do not imply separate physical cables.

AMD’s UG1089 primary and secondary boot-device sections distinguish module boot firmware from Linux and application files on the carrier’s microSD. The existing separate inference checkout’s `research/fpga-inference/model/conditioned.md` remains the source for token feedback. No model, circuit or measured result changed. This is a reusable teaching-figure update, with no new software, RTL-simulation or physical-board evidence. The newer text-input model’s board test remains pending.

Checked 1440 × 900 desktop, 390 × 844 portrait and 844 × 390 landscape, including forward and reverse scrolling and both neighbouring scenes. Enlarged phone labels and removed the inherited entrance delay between board views. TypeScript, three scroll tests, seven citation tests, the preview client build, DevEx and diff whitespace checks passed. Work remains local.

Factual audit, 12 November: checked AMD DS986 product details, DS987 processing-system and peripheral-controller sections, and UG1089 primary/secondary boot and power sections. The starter-kit module omits the production module’s eMMC, so the figure correctly shows microSD instead. The article now briefly explains each label, identifies “Memory + I/O” as grouped controllers, distinguishes external DDR4 from internal BRAM, and states that the CPU–FPGA transfer is on-chip. Power regulation is explained without adding circuitry to the functional drawing. The text-input flow is explicitly a design description, checked against `research/fpga-inference/hardware.md` and `model/conditioned.md`, not a claim that the pending board test has happened. Hardware.md contains superseded sampler proposals, so the highest-score choice follows the current conditioned model record. No engineering evidence or board-test status changed. The seven citation tests and diff check pass. Rechecked the explanation list and scene boundary at all three target viewport sizes. No figure code changed in this audit.

Lecture diagram follow-up, 12 November: the FPGA logic now has a dashed path to the Controllers box for access to off-chip DDR4. The request view shows the laptop’s prompt and reply going through the carrier’s Ethernet interface and on-chip controllers. The CPU’s tokens and the FPGA’s scores travel within the Zynq chip. The text distinguishes the existing BRAM weight load at startup from the proposed DDR4 weight fetch during inference. Sources: [AMD’s starter-kit block diagram](https://docs.amd.com/r/en-US/ug1089-kv260-starter-kit/Summary), [connector table](https://docs.amd.com/r/en-US/ug1089-kv260-starter-kit/Interfaces), [K26 interface table](https://docs.amd.com/r/en-US/ds987-k26-som/Functional-Interfaces) and [Zynq AXI interface table](https://docs.amd.com/r/3.4-English/pg201-zynq-ultrascale-plus-processing-system/Slave-Interface?contentId=a27dSHbpSWjx9dexkTB1Ug). Ethernet is the illustrated board interface. The records do not establish the laptop’s physical network setup. No hardware measurements or new board runs accompany the figure.

Lecture exports: [board connections](../../lectures/assets/kv260-board-connections.png) and [request flow](../../lectures/assets/kv260-request-flow.png). Checked both views on desktop, phone portrait and phone landscape.

The board request view loops the example prompt “We need more chips.” and pairs it with the wafer fab joke, an exact reply recorded for a different prompt in the fixed-point software evaluation (J15, run `20261109T190531255188`). The first two tokens follow the CPU-to-FPGA, FPGA-to-CPU and Ethernet paths in turn, then the remainder plays at a faster pace. The earlier token walkthrough uses an edited reply for the recorded `a` request. The figure expands “Resist” to “Photoresist” and animates the first two displayed letters, P and h. The replies appear in the figures without a final full stop. The saved fixture retains the original text and scores. The lecture PNGs above show the static wiring and request path.

### 12 November 2026 — choosing a chip

The published chapter now opens with `built-in-timers`, followed by `chip-choices`, `ip-blocks` and `cpu-and-fpga`. Repeated definitions are condensed into practical choices, IP blocks remain explicit, and the soft-processor explanation stays optional. Video recommendations move to the article’s end. The existing map’s labels now read “Reusable IP block” and “Scores / chosen token”. The CPU/FPGA drawing remains a conceptual division of work, not a physical floor plan. These are teaching and editorial changes, with no new software-model, RTL-simulation or physical-board evidence.

Checked desktop landscape, phone portrait and phone landscape, including the reordered scenes, reverse scrolling and the optional IP disclosure. TypeScript, seven citation tests and three scroll tests pass. Browser console has no errors. Changes remain local.

### 12 November 2026 — performance and energy figures

Shortened the chapter to four main paragraphs: parallel arithmetic, overlapping inputs in a pipeline, waiting for data, and energy for the same completed task. The `PerformanceFigures.tsx` (historical figure, subsequently removed) retain the existing FPGA map. A logic-region close-up compares one reused adder with three adders, then adds registers without changing the arithmetic layout. Sets A, B and C produce 10, 14 and 18 on consecutive edges after the two-cycle fill. The map then shows the BRAM-to-DSP supply path and zooms out to a KV260 system drawing with a meter at the board power input. Equal-scale power/time areas show the hypothetical 2 J and 3 J comparison.

These are browser teaching figures using the existing [arithmetic model](./figures/model.ts), not a new RTL implementation or measured KV260 pipeline. The power values remain hypothetical. No inference model, engineering evidence or board-test status changed. The separate inference checkout's `research/fpga-inference/README.md` and `model/conditioned.md` remain the engineering source, with the newer text-input model's physical test pending.

Checked desktop landscape (1440 × 900), phone portrait (390 × 844) and phone landscape (844 × 390), including controls, forward/backward transitions and the neighbouring board and chip-choice scenes. Removed the inherited blank entrance interval between the arithmetic views and enlarged phone labels. TypeScript, 26 FPGA tests, seven citation tests, the preview client build, DevEx and diff whitespace checks passed. No browser console errors were observed. Work remains local.

### 12 November 2026 — KV cache and token feedback

The [transformer chapter](./script.md#running-a-tiny-transformer) now follows the first neuron. The same chip zooms out from its DSP, highlights block RAM and opens the cache. A teaching animation shows two existing entries, writes for the third and fourth tokens and attention reading all four pairs. It shows the order of the operations without assigning board timings. The [token feedback figure](./figures/TransformerFigures.tsx) uses the existing integer software record of `a` → `R` → `Re` to show the FPGA sending scores to Arm and the selected token returning. The earlier projection and cache datasets remain available for numerical tests. Projection arithmetic, cache addressing and reset behaviour remain in expandable article notes.

The cache close-up uses the four signed key and value rows from the pinned integer export of the same request. Each entry is drawn as two four-by-four groups. The first attention head reads the four keys in turn and mixes the corresponding values using its recorded attention weights. Red and green show the sign of each stored number. Gold traces the reads and writes and highlights all four value paths equally. The query and result grids use the first sixteen numbers from the rotated query and context vectors of the fourth token. The query and selected key highlight together. The completed result stays visible for inspection. The timing and routes are illustrative.

The write source sits at the cache’s upper left. The overview’s three generic wires on each side fade out in the close-up. Each pair travels down outside the BRAM outline, then enters the active row from the left. During each write, small red and green squares fall in centred lanes from above the source, pass behind it and fade beside the write path. The squares pause with the figure and are hidden in reduced motion. The centred cache uses the chip map’s green BRAM styling. Violet FPGA logic sits directly on the two surrounding rails, with the key comparison on the upper rail and value mixing on the lower rail. The comparison weights travel to the mixing block before the four value paths light up together. The result flows left along the lower rail back into the FPGA logic.

The token feedback figure now comes before the KV260 board drawing. It starts with the prompt `a` entering the CPU and an empty output box. It then illustrates the first two choices and types an edited reply based on the [integer software request](./figures/data/tiny-text-request.json) before restarting. The animation loops automatically. Reduced motion shows the complete text. The standalone simulation step has been removed. The software, RTL and physical-board status remains with the board drawing.

Performance and energy now follows the model walkthrough. The CPU, GPU, microcontroller, FPGA and ASIC comparisons still have their own chapter. This revision adds no hardware measurements. The original model has run on the KV260, and the newer text-input model’s physical board test remains pending.

### 11 November 2026 — lecture throughput figure

The [editable SVG](../../lectures/assets/fpga-inference-progression.svg) and [slide-ready PNG](../../lectures/assets/fpga-inference-progression.png) show tokens per second over time. The solid line steps up at the first model, moving token selection into the FPGA fabric, moving weights into BRAM, and moving the KV cache into distributed RAM. The curve uses illustrative values and the sequence is a teaching example. The first model ran on the KV260, and the newer text-input model has software and RTL checks with its physical board test deferred in the article's verification record. No verified throughput measurements support the curve. In the current design, the Arm CPU is outside the FPGA fabric on the same chip. The figure's “off-chip CPU” label refers to that host round trip.

### Recording measured builds

Use the [article’s measurement plan](./script.md#measuring-inference-on-the-kv260) for the initial BRAM, distributed RAM and DDR4 weight comparisons. For each run, keep the date, build and model identifiers, memory placement, prompt set, clock, correctness check and a pointer to the raw data. Record first-token latency, output tokens per second, effective weight bandwidth and whole-board energy when available, with units and measurement conditions. Keep any cost estimate with its assumptions. Note what AI helped change and record engineering time and build time separately. Mark software, simulation and board results explicitly so the article and lecture can draw on the right evidence.

## Model-first neuron introduction, 10 November 2026

The neuron chapter now previews the verified `a` → `R` → `Re` behaviour, reveals the one-block transformer’s main stages, and opens a weighted sum before returning to the existing DSP teaching example. The same chip shrinks to the lower-left corner while the model is the focus and grows back for the hardware close-up. New scene keys are `network-layers` and `network-sum`. The existing neuron prose, including Aidan’s latest opening sentence, remains in place. The illustrative bias/output rule is distinguished from the actual transformer. The detailed later walkthrough remains unchanged. The overview now uses columns of nodes and connections, with attention grouped and omitted nodes/operations explicitly acknowledged. One persistent SVG camera enlarges the highlighted neuron and its incident edges over 900 ms. The mathematical view fades before the chip expands for the DSP close-up. Fast skips settle immediately, and the existing reduced-motion rule removes these transitions. Keep this work local.

## Single-character hardware walkthrough, 10 November 2026

From “Our FPGA’s first neuron” onward, the main transformer example now follows lowercase `a` through the selected balanced integer model. It encodes as `[256, 278, 289]` and first generates `R`, then `e`. The projection close-up uses the same request’s first two Q outputs, with separate read, multiply, save and address steps. Those teaching stages do not claim physical clock timing. The historical cache inspector remains separate, and its reset requires the full-cache test first. A compact pipeline view keeps the later phone diagrams readable. The opening prose, figures and scene structure remain unchanged.

Raw export: inference worktree’s ignored `.agents/runtime/fpga-inference/outputs/tiny/20261110T095852130733`. The existing pinned, offline worker and 180-second supervisor were reused through a runtime-only export adapter. All 21 integer states, logits and cache values match full versus incremental execution across all four positions. The article’s compact JSON retains hashes for the export, generation, projection, selected manifest and payload. No training, model/source changes, board access, clock changes or new hardware measurements occurred. Latest project records still defer the new model’s board test. Keep local.

## Actual-text inference walkthrough, 9 November 2026

The transformer chapter now follows actual UTF-8 input, supplied-token processing, one complete prediction and deterministic token feedback. The new request excerpt in `data/tiny-text-request.json` comes from the selected original-scale integer software export’s `encoded-fu2p2q` golden. Its source hash and model-manifest hash are retained in that file. It is separate from the unchanged historical projection and cache traces. A small network-to-arithmetic zoom shows one saved coordinate joining Q before position adjustment and attention.

Read `research/fpga-inference/model/conditioned.md` and `conditioned.json` in the separate inference worktree for the current model. The original model has run on the KV260. The new actual-text model has passed Mac checks and seven server RTL-reference cases and is packaged with the existing bitstream. Its physical board test is deferred. The main article distinguishes these two models, and no performance or energy measurement is inferred. Earlier dated entries below retain their historical status. Only the transformer chapter and associated figures/data/tests changed for this walkthrough. Work remains local.

## Tiny-transformer integration, 4 November 2026

The canonical article now follows the authored chip-joke model after explaining configuration. Three manual interactions cover the token path, two recorded Q projection rows, and a K/V cache replay. Details hold model dimensions, fixed-point scales, simulation scope and exact implementation results. No board execution or performance is claimed.

Source identity and excerpt hashes live beside the figures in `data/tiny-transformer.json`. Projection run `20261102T224324264012` and cache run `20261103T113027485830` are historical component simulations. Full-cache memory values are a readback fixture, not a raw cycle trace. The two output rows retain their observed product, sum and output clock indices; controls advance recorded events, not assumed single clock cycles.

The model source is pinned to Mac revision `997f920c5656dffe1ea4c69f865b3b339d44fc68`. Later complete-build facts use server checkpoint `f7c57b7aa9801875825cf8d720a6d3d4f39c8017`, as supplied by Aidan and corroborated by read-only server-chat records. Remote messaging was blocked by automatic approval review; neither checkout was changed to obtain evidence. These GitHub citations may require repository access. Before publication, provide an approved public source for project records if the repository remains private.

The candidate bitstream configures the circuit; model weights and numerical tables load separately. Programmable logic owns neural arithmetic/cache, Arm owns loading/control/sampling and the laptop is the interface. Physical execution, boot compatibility, speed and energy remain unverified. The article remains a draft, and all work stays local until Aidan asks otherwise.

## Local editorial checkpoint, 2 November 2026

Applied Aidan’s authorised audit improvements locally: repaired the register-pair connection and moved its width labels; added the bit-addition bridge, worked neuron and KV260 relationship diagram; clarified configuration storage versus clocked working state; moved bitstream/interface detail to configuration; explained widening arithmetic buses and the PWM width range. The LUT, flip-flop waveform, PWM and neuron figures have compact phone layouts. SRAM references now share MIT’s readable explanation. The article remains a draft, with no hardware experiments or measurements claimed. These edits are not committed or pushed.

## Practical thread: build our own tiny inference circuit

Decision agreed with Aidan on 30 October 2026. Grow one real design through the article, rather than attaching a finished accelerator as an unexplained demonstration at the end. Aidan subsequently specified a language model as the destination, with customers able to select it through Gradiated’s API. This supersedes the earlier suggestion of handwritten-digit recognition. Aim for the best open-source or permissively licensed open-weight language model that the actual implementation can serve at acceptable quality and speed; memory fit alone is not sufficient. The model, numerical precision, context limit, runtime and detailed API integration remain open.

Aidan has confirmed that the available board is an AMD Kria KV260. Its board revision, current software image, installed tools and access still need checking. Consider a humorous personality through fine-tuning a pretrained model, or a separately trained small model; neither the training approach nor the character has been selected. Television characters and a Jensen Huang parody were suggestions. Train on a separate computer/GPU, then deploy inference to the FPGA.

Useful implementation leads already consulted are [llama-fpga](https://github.com/adamgallas/llama-fpga), which provides a KV260 implementation for quantised Llama 2 7B, and [Hummingbird](https://arxiv.org/abs/2507.03308), whose larger-model results involve offloading. These are external research results to investigate and reproduce, not measurements or promises about our board. Keep training-data suitability and model licensing in the eventual selection.

| Build milestone | What the reader learns | Figure progression |
| --- | --- | --- |
| Multiply two numbers | How number widths and a multiplier map to FPGA resources | Reuse the arithmetic-block view; trace two input values into one result. |
| Add products to a running total | An accumulator is an adder plus a register; prepared values are captured at clock edges | Adapt the counter’s register/adder loop. Feed multiplier results into it one at a time, with clear start and finish. |
| Build one artificial neuron | Learned weights, bias and an output rule turn that arithmetic into a useful unit | Retain the multiplier and accumulator, then reveal the bias and output rule. Trace one complete numerical example. |
| Connect a tiny network | Store weights and intermediate results, schedule work and connect layers | Keep the same neuron identity while showing where its inputs and outputs go. Explain reuse of arithmetic versus duplication; a logical neuron need not have its own physical multiplier. |
| Build towards language generation | Matrix calculations, attention, context storage and repeated next-token prediction extend the simpler neuron example | Retain the arithmetic and memory blocks as a transformer block is introduced. Follow one generated token, then feed it back for the next prediction. Define each added operation before using it. |
| Run it on our board | Simulation, limited-bit arithmetic, synthesis, routing, timing and real I/O | Move between the circuit, actual resource reports and a drawing of the verified board. Show exactly which calculations run in programmable logic and which tasks run on the host CPU. |
| Serve a real prediction | A request crosses software, hardware and network boundaries | Follow one request to the FPGA and its result back to the client. Separate circuit execution time from the complete API round trip. |

Introduce each idea only after its prerequisites. Define training as learning numerical values from examples, and inference as using those values to calculate a prediction. Teach limited-bit representation, rounding and overflow before relying on them in the actual design. Distinguish weights from FPGA configuration; whether new weights can be loaded without a new bitstream depends on the circuit we build.

The existing pulse-generator and four-reading-sum figures remain smaller teaching examples. Their current prose now connects to the inference destination. The browser now traces one illustrative neuron through multiplication, captured running sums, bias and an output rule, and shows the KV260 system hierarchy. A connected-network animation and practical board walkthrough remain planned. Expand these sections as the hardware build provides real examples; do not imply the current browser figures are running HDL or controlling a board.

Use a separate hardware chat and worktree for implementation. This chat owns article prose and visuals. Keep the canonical script here, link to implementation source once it exists, and bring verified milestones back into this plan. The KV260 board is confirmed by Aidan. Treat the earlier prototype and measurement claims in the company chip microarchitecture document as leads to verify, not evidence that this article’s language-model build is working.

For each milestone, preserve the software reference, tests and source needed to reproduce it. Distinguish proposed, simulated and measured results. Report accuracy, resource use, latency, throughput and energy only with the relevant model, precision, hardware and measurement boundary. The current article remains a draft; keep changes local unless Aidan requests a push.

## Narrative and teaching decisions

Figure switching disables browser scroll anchoring within the scrollytelling body and uses a 12px boundary tolerance, so changing figure height cannot repeatedly switch scenes. Figure families change without a new entrance fade; the existing camera and component transitions remain.

Build one continuous chain from a gate's input/output rule to a stored bit, stored logic answers, selectable connections, clocked working state, a complete device, a design toolchain and real uses. Define a gate before using one. Motivate custom timing and parallel signal handling before opening the chip. Do not open with a dense architectural overview whose labels the reader cannot yet interpret.

The ten chapters in the script are the contents entries. The forty-five scene keys identify semantic units; forty-four participate in scroll selection, while the datacentre disclosure stays optional. Group connected units into persistent figure sequences, as specified below. Readers must be able to inspect meaningful states without being forced through a fresh entrance animation and full-height pause for each paragraph.

Introduce one two-input selector before the three-selector tree. Trace `A=1, B=0` explicitly. Distinguish stored LUT rules from changing working state before introducing flip-flops. Introduce waveform axes before timing annotations. DRAM, transparent latches, carry detail, vendor LUT variants and the historical datacentre example are optional disclosures. Essential claims stay in the main prose.

Maintain five distinctions throughout.

| What it represents | What can change |
| --- | --- |
| Manufactured transistors and wire segments | Stay physically fixed during configuration and operation |
| Configuration cells | Their stored bits select LUT answers, routes and resource modes |
| Working state | Register and data-memory contents change as the circuit runs |
| Combinational signals | Voltages propagate and settle after input changes |
| Clocked capture | Prepared input values are stored at the specified edge |

The main example is an SRAM-configured architecture. The small six-transistor SRAM cell is a conventional explanatory cell, not a reverse-engineered claim about every vendor’s configuration cell. A generic FPGA overview may include DSP blocks, but the cited iCE40 LP/HX family does not provide all the resources of the larger AMD examples. Label family-specific views and do not imply our eventual board has every pictured block.

Keep the SRAM transistor count in an optional disclosure. Defer detailed sense amplifiers, configuration protocols, fractured-LUT implementation, LUT RAM, clock-domain crossings, external DRAM controllers and partial reconfiguration. Mention the need for safe external input handling without trying to teach all of those subjects here. The PWM output now has an explicit flip-flop and is prepared from the next count, preserving the count/output alignment in the prose. This is a selected teaching circuit, not a measured board implementation.

### Continuous figure sequences

These presentation groups are implemented as eighteen mounted figure families, not additional scene keys. Related figures retain geometry while the relevant prose advances. A group may have several inspection states, but does not need a full viewport of scroll per key. Optional disclosures must not create hidden or empty automatic scroll stops.

| Group | Scene keys | Persistent figure |
| --- | --- | --- |
| Opening | `reconfigure` | Same chip and input controls throughout the AND/XOR comparison |
| Stored bit | `stored-bit`, `write-and-hold` | Same feedback cell, first holding a state, then being written |
| Select an answer | `truth-table`, `selector` | Four stored rows, one selector becoming the tree |
| Package the rule | `lut`, `larger-luts` | Same table and tree becoming a small LUT block |
| Connections | `routing-grid`, `routing-switch`, `combined-logic` | Sparse grid, junction detail and connected example |
| Clocked storage | `flip-flop`, `register` | One storage element and waveform becoming four shared-clock bits |
| Bit addition and counter | `bit-addition`, `counter`, `simultaneous-capture` | Register/adder loop, followed by a clearly identified second register |
| Timing | `clock-network` | Existing registers, timing window and distribution tree |
| Resources | `logic-block`, `block-ram`, `arithmetic-blocks`, `neuron` | One chip view gains memory and multiplication as each need appears |
| Device boundary | `pins`, `memory-roles`, `our-board` | Same chip gains its pins and separate startup flash |
| Describe a pulse | `pulse-generator`, `hardware-description` | Counter, comparator and output register beside aligned waveforms and pseudocode |
| Test and implement | `simulate`, `map-and-route`, `timing-check` | Same pulse circuit moves through simulated, logical and physical representations |
| Configure and run | `configure`, `running-parameters` | Separate configuration path and working-width register |
| Arithmetic organisation | `replicate`, `pipeline` | Same four-reading sum, with retained input-item identities |
| Energy | `switching-energy`, `measurement` | Same circuit and task, with hypothetical units kept separate from real measurements |
| Hardware choices | `chip-choices`, `cpu-and-fpga`, `built-in-timers` | Task requirements, CPU cooperation and a fair timer alternative |
| Origins | `history`, `first-fpga`, `first-fpga-block` | Small grid evolves without introducing a new architecture legend |
| Applications and close | `networking-and-control`, `science`, `prototype`, `datacentre`, `change-the-circuit` | Three compact uses reuse the established blocks, then return to the pulse circuit. Catapult is optional text, not a required animated detour. |

## Matched scene plan

Every row below matches one prose marker. This table records the intended teaching behaviour; diagrams show settled logical values with bounded highlights, rather than a transistor-level propagation simulation. Reuse the same object identities through each group and reserve motion for the mechanism being explained.

### A chip that can change its job

| Scene | Figure, interaction and transition |
| --- | --- |
| `reconfigure` | Define low/high voltages and a gate's input/output rule before revealing symbols. One chip outline, two input switches and one output. Begin at `A=B=1` with AND and output `1`. A separate configuration control changes the function to XOR and output `0`. Pause evaluation while loading, then hold the completed result. Keep physical geometry fixed. Open the block to expose its stored settings. |

### Remembering one bit

| Scene | Figure, interaction and transition |
| --- | --- |
| `stored-bit` | Introduce NOT's `1→0` and `0→1` rules before drawing the loop. Trace the existing values once, from the second output's `1` through `0` and back to `1`, then hold both voltages. Show the reversed stable assignment too. Do not send orbiting packets around the loop or suggest a clock is needed. Keep power present. The optional disclosure can expand the NOT symbols into CMOS pairs. |
| `write-and-hold` | Reveal two access switches and writing wires carrying complementary values. Enable access and show the external drivers forcing the cell's two points to opposite values. Disable access and hold the new state. Keep configuration-writing controls apart from later LUT data inputs. Shrink the cell into a stored-bit symbol. DRAM has no mandatory animation. |

### How memory becomes logic

| Scene | Figure, interaction and transition |
| --- | --- |
| `truth-table` | Duplicate the cell into four rows alongside `00`, `01`, `10`, `11`. Store AND’s answers. Keep the XOR column in the prose table and reveal its answers only during the configuration comparison. |
| `selector` | First introduce one two-input MUX with inputs labelled first/second and a separate `0/1` selection control. Then build the three-MUX tree. `B` selects within both pairs, then `A` selects a pair. Trace `A=1, B=0` to row `10`, whose AND answer is `0`. Keep the circuit's actual signal direction from cells through first-level selectors to final selector, even when explaining the address by pair first. Allow inspection of all four combinations. |
| `lut` | Enclose the four cells and selector in one LUT. Preserve `A=1, B=0` while changing AND's answer `0` to XOR's `1`. Reading never writes the cells. Demonstrate that four independently chosen answer bits encode any two-input, one-output rule, without adding another gate vocabulary lesson. |
| `larger-luts` | Shrink the LUT into its symbol. Expand input-count examples with `4 → 16` and `6 → 64`, explicitly labelled inputs and answer bits. Show one output on both. Return to the teaching LUT, rather than leaving sixty-four readable cells on screen. |

### Choosing the connections

| Scene | Figure, interaction and transition |
| --- | --- |
| `routing-grid` | Grow a small grid, initially around two by three blocks, with a sparse set of available fixed wire segments. Keep unused wires faint but visible only where they explain a choice. |
| `routing-switch` | Open one junction into a two-way selector with one stored control bit. Change the chosen incoming wire. Preserve all wire positions. Mark genuine joins with dots and leave crossings without joins unconnected. |
| `combined-logic` | Hold two LUTs configured as AND and XOR. Route the first result into the second alongside `C`. Trace `A=1, B=1, C=0` to intermediate `1` and final `1`, including propagation delays. Label this as a deliberately expanded teaching implementation. A real larger LUT can contain the whole three-input function, so do not promise two LUTs in synthesis reports. Collapse unused blocks. |

### Adding time and memory

| Scene | Figure, interaction and transition |
| --- | --- |
| `flip-flop` | Contrast a LUT's held rule with changing working state before introducing the D flip-flop. Introduce time left-to-right and low/high waveform levels, then align `D`, clock and `Q`. Move `D` between rising edges, hold `Q`, then capture at the marked edge with clock-to-output delay. The transparent-latch comparison is optional and must not interrupt the main sequence. |
| `register` | Group four flip-flops sharing a clock. Show four wires becoming a bus with a diagonal width slash and `4`. Keep a binary value and its decimal reading aligned. |
| `bit-addition` | Two stored LUT rules, XOR and AND, produce the sum and carry of two individual input bits. Keep the settings fixed while input controls select all four cases. |
| `counter` | Reuse adder geometry. Connect a four-bit register, adder, constant `1` and feedback. Keep current output and prepared next value visibly distinct. The register stays still while the adder settles, then captures at the edge. Trace `14 → 15 → 0` without displaying a fifth stored bit. |
| `simultaneous-capture` | Place registers `A` and `B` side by side with a common clock. Show current outputs and prepared inputs in separate positions. Begin at `A=3`, then capture `A=4`, `B=3` together. Use the same edge on both waveforms. |
| `clock-network` | Keep the register pair, expose one complete launch-to-capture path, and show setup/hold intervals around the capture edge. Then expand the clock into a small distribution tree. Describe controlled skew without drawing zero-delay clock wires. |

### Building a complete FPGA

| Scene | Figure, interaction and transition |
| --- | --- |
| `logic-block` | Package a LUT, flip-flop and direct/stored-output selector. Transform the earlier components into this block, then duplicate a few blocks into the chip. Label it as a simplified block, not an exact vendor slice. |
| `block-ram` | Begin with one sensor reading in a register, then several readings needing storage. Add addressed words in block RAM, writing successive readings to locations `0` and `1` and reading one back. Choose an explicit synchronous model with visible read/write controls. No instantaneous access to the whole array. |
| `arithmetic-blocks` | Keep the reading visible and multiply it by a number using a dedicated DSP block. Carry-chain detail is optional, with a carry defined before any focused drawing. Do not claim a resource saving or speed ratio before actual tool results exist. |
| `neuron` | Reuse one multiplier for inputs `3, 2` and weights `2, −1`. Show the sum register capturing `6` then `4`, followed by bias `−1` and output `3`. Alternative inputs `1, 3` produce a negative biased total and output `0`. Inspection steps are not a board cycle count. |
| `pins` | Add input and output buffers at the chip boundary. Follow one complete path from an input pin through logic and storage to an output pin. Show which edge captures it. Keep configuration loading outside this data path. |
| `memory-roles` | Open three small, aligned callouts from configuration cells, flip-flops and block RAM. Label each by its job. Add a separate board-level flash chip only when explaining power-off retention and startup loading. Do not draw configuration memory as a fourth CPU-like interpreter. |
| `our-board` | A relationship diagram places the processing system and programmable logic inside the Zynq chip on the K26 module, alongside working memory and boot storage on the KV260. Omit other resources explicitly; this is not a floor plan or the actual application wiring. |

### From a description to a circuit

| Scene | Figure, interaction and transition |
| --- | --- |
| `pulse-generator` | Reuse the four-bit counter and adder. Compare the prepared next count with `width`, then capture count and output together in separate clocked storage. Show output high beside counts `0…3` for width `4` and `0…11` for width `12`. Use one shared time axis. Pair this with restrained LED brightness, not distracting flashing. See the exact model below. |
| `hardware-description` | Display the script's explicitly labelled pseudocode beside the same circuit. Highlight `next_count` at the adder, `next_output` at the comparator, then both captures at the same edge. Distinguish between-edge preparation from storage. Do not imply this pseudocode has been compiled or selects a board/toolchain. |
| `simulate` | Run a reproducible stimulus and expected-output check. Show count, width and output against the same time axis. Label this as functional simulation and slow time for inspection. Preserve an end state rather than endlessly replaying tests. |
| `map-and-route` | Convert the described circuit into a logical resource diagram, then selected physical sites and routes. Show synthesis, placement and routing as distinct changes of representation. No made-up resource totals or claim that these illustrative locations are an actual tool result. |
| `timing-check` | Expand one routed register-to-register path and its arrival deadline. Show a failing illustrative path and the available remedies, then hold a labelled timing-budget view. Numbers must be explicitly hypothetical until taken from a named target and tool run. |
| `configure` | Feed a configuration stream through a separate configuration interface into LUT and routing settings. Finish loading before the working counter starts. On power loss, separate retained flash contents from lost SRAM contents. Show a real measurement only after it has been made. |
| `running-parameters` | Change `width` through the working register interface. The LUT configuration and routing remain fixed. Contrast with a deliberate load of a different design, rather than implying all parameter changes rebuild the circuit. |

### Performance and energy

| Scene | Figure, interaction and transition |
| --- | --- |
| `replicate` | Reuse one adder for the three additions in `(a+b)+(c+d)`, then show two adders forming the pair sums and a third forming the total. Follow readings `1,2,3,4` to pairs `3,7` and total `10`. Keep input/output widths sufficient and storage/selection overhead visible. These are illustrative architectures, not promised tool mappings. |
| `pipeline` | Insert registers after both pair sums and at the final output, with input registers marking launch. Track sets `1,2,3,4 → 10` and `2,3,4,5 → 14`. Capture pair sums at the first edge after launch and final total at the second. Show two-cycle latency and one-result-per-cycle spacing after filling. Any change of clock period must use the declared illustrative timing model below. |
| `switching-energy` | Reuse the data path and distinguish active arithmetic, routing, clocks and data movement. Compare required activity or wire length qualitatively. Do not turn decorative flashes into a numeric energy meter. |
| `measurement` | Illustrate the explicitly hypothetical same-task comparison `2 W × 1 s = 2 J` and `1 W × 3 s = 3 J`. Define watts/joules and keep the included components identical. Then identify chip, board and off-chip measurement boundaries. No numeric animation is labelled as a tool estimate or physical measurement without evidence. |

### Choosing a chip

The following optional passage was removed from the chapter and retained here for possible further reading. Its citation key remains in the article reference file:

<details>
<summary>Can AI help reverse-engineer an IP block?</summary>

Reverse engineering means working backwards from a circuit to understand its design. Researchers are already using AI to infer descriptions and hardware code from netlists, the lists of gates and connections produced by design tools.[@ai-netlist-reconstruction] This demonstrates useful reconstruction under particular test conditions, rather than reliable recovery of any proprietary core. Access to the circuit’s details and verification of the result still matter.

</details>

| Scene | Figure, interaction and transition |
| --- | --- |
| `chip-choices` | Start with requirements such as response time, repeated parallel arithmetic, changing software and production volume. Reuse the four-reading sum to explain different organisations without pretending it benchmarks whole devices. Compare instruction-driven execution, parallel execution units, configurable circuitry and a manufactured custom path. No universal ranking. |
| `cpu-and-fpga` | A CPU writes a parameter and reads a result through registers beside the FPGA data path. Then distinguish a fixed manufactured CPU core from one built using configurable logic. Mark software and configuration loading as different flows. |
| `built-in-timers` | Keep the PWM waveform. Show a microcontroller timer generating the same kind of signal after software sets it up. Make this an honest alternative, not an animation of a CPU toggling each pin as the only possible implementation. |

### Where FPGAs came from and where they go

| Scene | Figure, interaction and transition |
| --- | --- |
| `history` | A short timeline links earlier programmable logic, the 1984/1985 FPGA milestone and later integrated resources. Reuse the same small grid becoming richer. Do not assign precise introduction dates to later resources without verifying them. |
| `networking-and-control` | Keep messages identifiable as they occupy successive stages of a configured inspection/response path. Explain the short-response requirement. The industrial-control sentence can reuse the same inputs/calculation/outputs without a separate entrance. Keep product identifiers in sources and avoid translating transceiver latency into whole-system latency. |
| `science` | Detector information enters parallel selection paths whose results combine into an event decision. Match the limited ATLAS claim in the text. No simulated physics measurement or invented event-selection accuracy. |
| `prototype` | A processor description becomes FPGA resources and runs a small software trace before a later custom chip is manufactured. Show testing and revision as the capability, with physical timing/power outside the claim. Keep project names in the source. |
| `datacentre` | Optional Catapult disclosure, with a static CPU-plus-FPGA thumbnail only if it helps. No mandatory scene entrance, hidden scroll stop or auto-advance when the disclosure is closed. Mark the case as 2014 and avoid current-deployment claims. |
| `change-the-circuit` | Return to our small counter within the larger FPGA. Hold configuration, working state and signal path in view. End with a stable circuit and the possibility of choosing another configuration, rather than cycling through unexplained examples. |

## Exact teaching models

### LUT and routing

- Treat `A` as the more significant address bit and `B` as the less significant bit. Stored row order is `00`, `01`, `10`, `11`.
- The first selector pair takes rows 0/1 and 2/3, each controlled by `B`. The final selector is controlled by `A`.
- AND answers are `0001`. XOR answers are `0110`. Configuration controls change those answers, while input controls choose a row.
- The composed example is `(A AND B) XOR C`, with one LUT for each two-input function. Check all eight input combinations before animating it.
- That two-LUT arrangement is deliberately expanded for teaching. The function has three inputs and can fit into a single larger LUT. Do not conflate this scene with an actual synthesis result.
- Selected-route yellow must also appear when the selected answer is `0`. It means active/selected, not logic high. Do not imply that switches can short unrelated driven outputs together.

### Working registers and timing

- Define an initial state explicitly. Counter starts at zero and wraps modulo sixteen. Initialisation/reset details for the physical board remain to be chosen.
- For the register pair, start at `A=3, B=0` and use `next_A = (A + 1) mod 16` and `next_B = A`. Compute both from pre-edge state before committing either update.
- At the first illustrated edge, `A=3` becomes `4` and `B` becomes `3`. The next edge produces `A=5`, `B=4`.
- Draw register output changes shortly after the edge, not exactly at zero elapsed delay. Do not allow a visual transfer to change stored values merely because it arrives.
- Setup, hold, clock-to-output and clock arrival differences matter. Avoid suggesting that increasing the clock period alone fixes every timing failure, particularly hold failures.

### Pulse generator

- Counter is four bits. Use a five-bit `width`, with the teaching control restricted to `0…16`. This permits fully off and fully on without an unexplained four-bit value of sixteen.
- Choose the registered-output circuit now described in the script. During each cycle compute `next_count = (count + 1) mod 16`, then `next_output = (next_count < width)`. At the rising edge capture both from the pre-edge combinational values. After clock-to-output settling, the displayed output matches the new count's comparison, not the previous count. A direct comparison of old `count` captured alongside the increment would introduce a one-cycle phase shift and is not this circuit.
- Initialise the teaching model at `count=0` and `output=(0 < width)`. Widths `0`, `4`, `12`, `16` give zero, four, twelve and sixteen high intervals per repetition. The script's initial output-high statement applies to widths `4` and `12` only. A real initialisation/reset circuit remains to be designed and verified for the selected board.
- Hold `width` constant during a repetition. A UI change updates a pending working value. When `next_count==0`, compute `next_width=pending_width`; otherwise use the existing width. Prepare `next_output=(next_count < next_width)` and capture count, width and output together. This extra boundary-update logic is an explicit teaching policy, not reconfiguration or a claim that assigning the width register magically makes a simultaneous comparator see its new value. If implemented in HDL, show that extra logic or use separate runs with fixed widths.
- Combinational next-count/comparison signals may glitch after the preceding edge. All illustrated capture values must settle and meet setup/hold before the next edge. The output flip-flop keeps intermediate glitches away from the pin. The timing-check scene must include the register-to-adder-to-comparator-to-output-register path, not only the counter increment.
- Four bits keep the mechanism readable. An eventual LED demonstration needs a suitable clock, a larger period counter or clock enable, and an appropriate LED/resistor/driver connection. Do not drive an external load without checking the board’s voltage and current limits.
- No board, language, synthesis flow or measurement equipment has been chosen. No compiled design, resource report, power figure or physical waveform is claimed yet.

### Arithmetic and energy examples

- All three organisations compute `(a+b)+(c+d)`. Use eight-bit unsigned readings, nine-bit pair sums and a ten-bit final sum. A reused adder must support the widest operation. Selection and storage are real resources, not free decorations.
- Set I is `1,2,3,4`, with pair sums `3,7` and total `10`. Set II is `2,3,4,5`, with pair sums `5,9` and total `14`. Set III can be `3,4,5,6`, with pair sums `7,11` and total `18`.
- In the reused circuit, one adder computes the first pair, second pair and total in successive cycles. The unpipelined three-adder circuit has two addition levels between input and output registers. The pipelined version has registers after both pair sums and at the final output, and accepts a new set into input registers each cycle.
- At launch edge 0, input registers capture set I. Edge 1 captures its pairs while input registers capture set II. Edge 2 captures result I and pairs II while input registers capture set III. Edge 3 captures result II and pairs III. Treat the initial pipeline contents as invalid until the appropriate edges, rather than presenting zero as a real result.
- If showing numeric timing, explicitly label a hypothetical model in abstract time units. Let each addition level take 5 units including its relevant combinational routing, and each clocked path have 1 unit of total register/setup timing budget, with zero clock skew in the model. The unpipelined clock period is 11 units and its latency is one period. The pipelined period is 6 units, latency is two periods or 12 units, and result spacing is 6 units once full. Show the extra registers. These are stipulated teaching delays, not a measured FPGA speed-up. Do not infer these times for the reused circuit's additional selector/control paths.
- The energy illustration holds task and included hardware boundary constant. Average powers are hypothetical constants over the execution interval, giving `2 W × 1 s = 2 J` and `1 W × 3 s = 3 J`. Neither example is claimed to be a CPU, FPGA or ASIC measurement. Include idle/static energy in any later real comparison.

## Reuse and implementation boundaries

Reuse existing typography, layout principles, yellow wire tokens, geometry and model-driven timing. Avoid a broad refactor of the working overview to share a few diagrams.

| Existing source | Useful elements | Boundary |
| --- | --- | --- |
| `hardware/publishing/sand-to-thought/articles/sand/figures/runtime/scenes2d.js` | Gate symbols, truth-table treatments, adder geometry, drawing helpers | Helpers live inside the scene builder. Inspect dependencies before extraction. |
| `memory-scenes.js`, `memory-interface-scenes.js` and their models | Selection paths, address/data buses, write controls, grouping | Earlier storage is based on transparent latches. Reuse geometry without mislabelling it as SRAM or a flip-flop. |
| `computer-scenes.js`, `controller-scenes.js`, `instruction-cycle-scenes.js` and `instruction-cycle-model.js` | Clock-edge highlights, simultaneous capture, state-driven values | Do not import LC-3 instruction sequencing into the LUT explanation or alter the existing controller. |
| `journey.css` and shared site fonts | Paper/ink colours, Instrument Sans, Barlow, JetBrains Mono, active route styling | Use shared tokens and preserve existing article styles. |
| [Saved programmable-logic draft](../sand/drafts/programmable-logic.md) and its JS companion | LUT-to-grid transition idea | Old three-input/eight-answer example and hard-coded indices are not a drop-in runtime. Replace ambiguous “3-to-1” wording. |
| Fabrication journey and shared article citations | Chapter sidebar, publication conventions, references/disclosures | Its physical processing model is not an FPGA simulation. Do not copy its process machinery. |

Prefer a small deterministic FPGA model that can produce a scene’s values from its inputs, state and local progress. Rendering should follow the model. Do not queue every skipped scene when a reader jumps far forward or backwards. Use absolute scene targets and bounded transitions so off-screen animations do not keep running.

Keep configuration and data controls distinguishable by labels and line treatment as well as colour. Show a binary label on configuration cells, clock markers on flip-flops and width slashes on multi-wire buses. Avoid idle pulsing on clocks whose edges do not agree with the displayed captures.

Support keyboard controls, stable states, reduced motion and small screens from the start. At narrow widths, simplify or reflow secondary views instead of shrinking labels until unreadable. Critical facts remain in prose and static diagrams.

## Sources and evidence boundaries

The reference JSON is the public bibliography source. This table records the passages checked and their limits. Highlight links use short verified wording where feasible. PDFs use verified page numbers. Text-fragment support varies by browser and is a convenience, not a prerequisite for understanding the reference.

| Citation key | Checked passage and scope |
| --- | --- |
| `fpga-introduction` | Microchip Developer Help, “Field Programmable Gate Arrays”, “Logic Block”, “Look Up Table” and “Interconnects”. Supports the mechanism and SRAM/flash distinction. Avoid its blanket product comparisons. |
| `sram-cell` | University of Hamburg, static text describing the conventional six-transistor cell and external writing drivers. The Java applet is obsolete, but the explanation is readable without it. |
| `combinational-logic` | Computation Structures chapter 7, sections 7.3 and 7.4. Truth-table rows, arbitrary single-output functions and gate symbols. Supports the generalisation beyond AND/XOR without requiring Boolean algebra in the main article. |
| `memory-technologies` | MIT 6.004, Caches & The Memory Hierarchy, slides 5–10. Supports SRAM feedback/access and DRAM refresh. Do not reuse its historical costs or capacities as current measurements. |
| `ice-forty` | Lattice iCE40 LP/HX data sheet, FPGA-DS-02029-4.3, February 2025, printed pages 11–18. LUT4, carry, synchronous block RAM and I/O. The old supplied PDF URL returned 404, so use the official document link. |
| `lut-six` | AMD UG474 revision 1.9, 1 April 2025, “Look-Up Table”. Supports the six-input example. Fractured/multiple-output modes remain outside the teaching model. |
| `sequential-logic` | Computation Structures chapter 8, edge-triggered flip-flops and timing discipline. Pair this with the article’s own worked register values. |
| `clock-network` | AMD UG572 revision 1.11, 29 May 2025, “Clocking Architecture Overview”. Dedicated routing and clock management, not a guarantee of identical arrival times. |
| `fpga-architecture` | Intel oneAPI FPGA developer guide, version 2024.2, architecture overview, register/DSP/RAM subsections. A fixed edition used as an architecture reference, not a claim about current corporate ownership. |
| `fpga-configuration` | AMD UG470 revision 1.17, 5 December 2023, printed page 11 and configuration-loading sections. External flash/host loading and configuration data. Use the readable guide landing page rather than an unstable content-download endpoint. |
| `simulation` | Amaranth 0.5.0 simulator documentation, counter/adder examples and waveform output. Evidence for simulation, not a decision to use Amaranth. |
| `synthesis` | Yosys documentation 0.70 as read on 29 October 2026, primer sections “Behavioural level”, “Register-Transfer Level” and “Physical gate level”. A described update becomes a continuously operating adder and clocked storage, with mapping/optimisation between representations. Ignore historical claims about which other tools exist. This source does not select Yosys as our eventual toolchain. |
| `design-flow` | AMD UG892 2026.1, “Placement and Routing”. Logical, physical and timing constraints. Do not imply that every tool uses the same commands or exactly one pass through this flow. |
| `registered-outputs` | Altera Quartus Prime Pro Edition design recommendations, version 25.1, section 3.2.3.1. Combinational glitches are blocked at a receiving register's data input. Our PWM is a data output, not an internally generated clock. Correct setup/hold and output timing still matter. |
| `timing-analysis` | AMD UG892 2026.1, “Running Timing Analysis”, and chapter 8 timing discipline above. Constraint-dependent analysis, not proof of functional correctness. |
| `pipeline-performance` | Computation Structures chapter 11, latency, throughput and pipelining. Examples in our animation must use a declared timing model, not invented measured speed-ups. |
| `power-basics`, `power-estimation` | AMD UG907 2026.1, “Power Terminology” and “Vectorless Power Analysis”. Includes static/design power, on/off-chip boundaries and activity assumptions. |
| `fpga-asic` | Kuon and Rose, 2007, abstract and introduction. Historic 90 nm comparison and configurable overhead. No numerical ratio is used as a modern universal result. |
| `cpu-gpu` | NVIDIA CUDA C++ Programming Guide 12.5.0, section 1.1, CPU/GPU design-goal comparison. This fixed edition supports the stable architectural distinction. Cite the architectural motivation, not its promotional comparisons with other devices. |
| `cpu-fpga` | AMD UG585 version 1.15, 6 February 2026, introduction. A manufactured Arm processing system and programmable logic share one device. |
| `processor-prototype` | OpenHW CVA6 manual and upstream FPGA tutorial. Both FPGA and ASIC targets, plus actual FPGA build instructions. Pin a commit before relying on a particular board/tool configuration. |
| `hardware-timers` | NXP LPC51U68 data sheet revision 1.5, 13 January 2020, section 7.15.2, printed page 36. PWM hardware with minimal/no CPU intervention. Not a board recommendation. |
| `fpga-history` | IEEE milestone citation. Freeman’s 1984 invention and XC2064 introduction in 1985. |
| `trading-platform` | AMD UL3524 launch announcement, 27 September 2023. A vendor-documented use, not independently measured end-to-end trading latency. |
| `measurement-control` | NI, “Distributed Measurement-Based Control Architecture”, control loops on FPGA subsection. Use only the concrete control/timing motivation, not blanket claims that added logic never affects timing. |
| `atlas-trigger` | ATLAS Collaboration, 28 February 2022, “New hardware at the starting level”. FPGA-based calorimeter trigger processing for Run 3. |
| `catapult` | Putnam et al., ISCA 2014, abstract/introduction and search-ranking evaluation. Cite the publication landing page. The full paper was consulted. No current fleet-deployment claim is made. |

Teaching inspiration was previously drawn from the full auto-generated transcript of [FPGAs Aren’t Processors (Unless You Want Them to Be)](https://www.youtube.com/watch?v=d3nuepnbmC4). Useful points are architecture at 04:16, timing/routing at 06:28–08:20, simultaneous register updates at 18:36, PWM at 21:06, implementation at 23:28, microcontroller peripherals at 29:38 and CPU cooperation at 32:46. No video is downloaded or saved here. Verify exact claims using the references above.

## Review and next steps

Review the revised prose and scene plan with Aidan before major animation work. The main decisions still open are the final title, pacing of the continuous figure groups, hardware/toolchain choice and how much optional SRAM detail to show. The registered-output PWM and its count alignment are now selected teaching models, rather than open waveform decisions.

After that review, build the LUT/configuration demonstration first. Then add routing and edge-capture models, followed by the counter/PWM example. A local review route can be added only when requested, with draft status and no library or overview links. Develop architecture, tools, comparisons and applications using the same established symbols.

Before any eventual implementation is considered complete, check the following.

- All four LUT addresses for AND and XOR, and all eight combinations of the composed function.
- Write/hold behaviour, configuration changes without data writes, counter wrap and simultaneous capture from old state.
- Registered PWM endpoint widths, simultaneous next-count/output capture, period-boundary width updates and waveform phase.
- Four-reading sum results, pipeline filling and two-cycle latency, with separately labelled hypothetical timing and energy examples.
- Timing illustrations, memory access latency and bus widths against their explicitly chosen models.
- Entering, leaving, reversing and rapidly skipping scenes, without accumulated timelines or stale values.
- Keyboard operation, reduced motion, small screens, readable labels and bounded background activity.
- Citation rendering, backlinks, all scene keys and draft publication boundaries.
- Existing overview, fabrication and library routes remain unchanged.

For this drafting task, validate the new Markdown and JSON with the existing citation renderer, check matched scene keys, run repository checks and verify preservation of existing files. A browser animation audit is not applicable until scenes are implemented. Do not claim this draft is available on localhost merely because the prose files exist.


## Current local implementation

- Page wrapper: `hardware/publishing/sand-to-thought/articles/fpga.mdx`.
- Runtime and scoped styles: `hardware/publishing/sand-to-thought/articles/fpga/figures/`.
- Deterministic teaching models: `model.ts`; seven model tests in `product/website/tests/fpga-model.test.ts`.
- Canonical Markdown uses the existing linked bibliography renderer through the generic `?cited-article` import. Existing fabrication imports remain supported.
- Only the active figure is mounted. Clock running is explicit, stops when off-screen or hidden, and is disabled for reduced motion. Skipped chapters do not enqueue animations.
- Small screens retain readable diagram sizes within keyboard-accessible, scrollable frames, with controls outside the diagram frame. Long portrait figure panels are capped at 70% of the viewport so prose remains visible. Chapter links select their target figure before aligning the text, and scrolling uses the visible reading area below the figure.
- Manual controls cover configuration versus working state, LUT inputs, routing, clocked capture, block RAM, startup configuration, PWM and pipelines. The simulations are browser teaching models; there is no claim of compiled HDL or measured hardware.
- Build checks include TypeScript, existing model and citation tests, preview/production SSR, and desktop/phone browser checks. Production excludes the draft route and card.

## History video and editorial inspiration

Aidan recommended Asianometry’s [The History of the FPGA: The Ultimate Flex](https://www.youtube.com/watch?v=m-8G1Yixb34), published 21 October 2022. The full English transcript was read on 29 October 2026; no video or audio was saved in the repository.

- **0:56–6:17:** early programmable memory and programmable logic. This strengthens our memory-to-logic explanation: it is a historical mechanism, not just a teaching analogy. The public article uses the readable Computer History Museum timeline as evidence and avoids introducing a catalogue of PROM, PLA and PAL abbreviations.
- **8:33–13:58:** configurable blocks plus routing, and the first Xilinx device. Preserve the independently cited 1984 concept/1985 product distinction. Do not repeat the first-working-wafer/inverter anecdote without a direct primary source.
- **14:21–17:03:** manufacturing scale, interconnect and design software. The article adds an optional account of early routing software, verified against Bill Carter’s oral history, page 18. The broader business history remains optional future material.
- Use the video as narrative inspiration, with claim-specific citations to checked sources. Do not repeat its broad claim that CMOS was unavailable in the US, infer that chemical-mechanical polishing alone drove FPGA success, or present its 2022 ownership summary as current.
- Useful further reading: Trimberger, S. M., [Three Ages of FPGAs: A Retrospective on the First Thirty Years of FPGA Technology](https://doi.org/10.1109/JPROC.2015.2392104), *Proceedings of the IEEE* **103**, 318–331 (2015). Keep any detailed claims tied to the relevant passage before citing them publicly.


### Real-device drawings

Aidan clarified that the video’s value is seeing an actual device opened and explained. The history chapter therefore includes an opened XC2064 package and an enlarged tile, drawn natively in the Sand to Thought palette. Keep the actual 8 × 8 tile count, peripheral I/O, central configuration/buffer divisions and tile-level logic/routing distinction. The package view represents a 68-pin variant; bond wires, pads and fine physical shapes are schematic rather than a mask reconstruction.

The tile view follows the die analysis’s upper routing region, distributed configuration-memory rows, input selection, flip-flop and two LUT regions. The labelled regions show logic, routing and stored settings together. It does not pretend that real tiles are isolated LUT rectangles surrounded by empty tracks. The original Xilinx specification verifies the two three-input LUTs / one four-input-function modes and the single storage element. Do not imply that its configuration cells are the conventional six-transistor cell used earlier: Shirriff identifies five-transistor cells in this device.


## LED wall and reusable IP additions — 5 November 2026

Aidan authorised an LED video-wall animation and a short introduction to reusable IP, including RISC-V, concrete examples and trade-offs. The new `led-wall` scene follows the other networking/control applications; `ip-blocks` follows CPU/FPGA cooperation. Both stay in the existing figure families and add no chapter. The script now has 51 scene keys, 50 automatically selected, in nineteen groups and eleven chapters.

The LED wall is an illustrative buffered arrangement: receive a 16-by-8 picture, arrange four vertical strips, send them to four LED-driver paths concurrently, then update the display together. The displayed image stays stable while the next is prepared. It runs only while visible and respects reduced motion; pause and manual stepping allow inspection. Pixel counts and timings are teaching choices, not a measured controller or a claim that all walls use this architecture.

The IP drawing groups existing configurable logic beneath an outline for a reusable design. The outlined resources remain visible as one RISC-V soft processor example. RISC-V names the open instruction-set standard, not a specific implementation or a claim about our KV260’s fixed Arm cores. The memory/video examples show configurable control logic; some interfaces also require dedicated circuitry. Main prose distinguishes soft/hard IP, gives benefits and costs, and retains system-level verification requirements. The optional AI aside cites GenEDA’s netlist-to-function/HDL research, without claiming arbitrary commercial-core recovery or bypassing bitstream protection.

Keep local; preserve draft status. These changes do not add a hardware experiment or measured result.


## Reading order — 5 November 2026

Aidan approved bringing motivation and real-device history forward. A short “Why use an FPGA?” section follows the opening reconfiguration demonstration, introducing camera data, a video wall and chip prototyping without requiring the later hardware vocabulary. A simple overview figure previews these alternative jobs. The existing detailed application figures and explanations remain near the end, now under their own heading, and explicitly revisit the opening examples.

The first-device history and XC2064 drawings follow the building blocks and memory roles, immediately before the return to our modern KV260. The workflow then leads into performance and energy before the transformer, so pipelining is already familiar when the model's implementation timing is discussed. Transitions connect these moves; the microcontroller timer example now follows chip comparisons before CPU cooperation and IP. Existing material, scene IDs and source citations are preserved. There are 52 scene keys (51 selected automatically), nineteen reusable figure families and thirteen chapters. Figure-family identity is independent of reading order.

Keep all changes local and preserve draft status. The structure change adds no board experiment or measured result.


## Recurring chip-map trial

The opening, packaged LUT, routing grid/junction and later logic-block explanation share one schematic 3 × 3 CLB map with four labelled I/O blocks on each side. The chip outline and CLBs are square. Three-track routing bundles use the same eight-unit wire spacing and 120-unit channel pitch horizontally and vertically, including all four edges of the array. Each I/O block aligns with a channel; its three available tracks fade towards the block rather than showing a fixed lead or junction. The selected example path fades at the I/O boundary too. The highlighted CLB stays in the upper-left position; the inspected routing selector sits on the interior track crossing at (220, 220), choosing CLB 1 or CLB 4 to feed CLB 5. The enlarged selector shows only the chosen internal path, with its configuration input separate below. Its surrounding chip tracks stay faint; the oversized map-level selector and focus marker disappear inside the close-up. Scrolling introduces each close-up. A small, static locator marks the region being inspected; readers do not need to operate scale controls. Compact block and junction layouts keep labels readable.

Keep the basic stored-bit, truth-table, selector and clock explanations in their existing teaching order. Configuration writes and input selection retain their interactive models. The map is a teaching architecture, not a KV260 floorplan or a claim that each real CLB has only one LUT. The XC2064 and KV260 illustrations remain separate, device-specific views.

The trial remains local. No article sections or technical explanations were removed; no hardware experiments, publication changes or deployments were made.

## Interaction restraint

Prefer a complete, readable illustration that works as the reader scrolls. Keep controls when an experiment exposes a mechanism: writing versus holding, selecting a LUT answer, clocked capture, routing configuration, timed parameter updates and recorded arithmetic/cache traces. Avoid controls that only reveal a label, swap equivalent examples or require a click to show already available results.

The opening is a scroll-led tour: an unassigned chip map, I/O, CLBs, available tracks and schematic switching junctions, followed by AND with inputs 1/0, AND with inputs 1/1 and XOR with inputs 1/1. This separates changing input data from changing configuration. Gold identifies the component under discussion or the selected path, not a high logic value. There are no opening controls. The rest of the article retains its close-ups and experiments. The revised script has 59 scene keys and thirteen chapters. The initial held bit, truth table, routing overview and composed logic example need no controls. Chip-map location is a static cue. The XC2064 package stays open and its tile regions remain visible together. The IP figure shows one RISC-V soft processor's resource grouping without example/view selectors. Chip choices are compared together in a table, simulation results are shown directly, and the illustrative neuron uses the prose's single set of inputs. Preserve meaningful memory, clock and calculation controls, along with pause/manual operation for running animations.

Keep all these changes local and preserve draft status.


## Website structure integration

The local `FPGA-deep-dive` branch now includes the website relaunch from `main` at `375de0f7e`. Article chapters register with the shared rail; the FPGA page no longer duplicates its desktop contents sidebar. The shared theme control retains system-preference updates, and the new Library uses the existing FPGA cloud/CLB artwork for its draft listing. Article prose, reference data, scene IDs and teaching models are preserved.

Fabrication keeps its scroll animation fixes and its separate local lecture controls and process indicator. The standalone lecture has the shared token scope without the website rail. The FPGA article remains a draft: available locally and in preview builds, excluded from production routes and listings. This integration is local and uncommitted. A verified archive of all pre-integration local files and a dedicated safety stash were retained outside the publication workflow.


## Applications around the opening chip

The early “Why use an FPGA?” section has three scroll scenes: CERN event selection, an LED wall and a future ASIC prototype. The opening 3 × 3 chip map stays mounted, shrinks about its centre and holds that position while restrained line-art environments crossfade around it. Signals meet the existing package pins; the chip’s physical geometry stays fixed. These scenes share figure family zero with the opening map, allowing forward and reverse zooms without remounting. The script now has 61 scene keys.

CERN distinguishes particle tracks, sensor hits and electronic packets, with illustrative keep/skip decisions rather than full particle reconstruction. The wall uses four parallel driver paths and holds the previous image until the next is ready. The workbench illustrates configuration, a failing test and a correction; it does not claim a real board experiment or ASIC timing equivalence. Animation pauses off screen/in hidden tabs and reduced motion shows stable explanatory states. No new controls. The article stays a local draft.


## Inside the configurable hardware — 6 November 2026

The applications now lead back into the same chip map, then into its upper-left CLB, the LUT and one specific answer cell (row `01`). A shared SVG camera retains the chip instance and follows nested coordinates into the conventional SRAM example. Separate scroll steps show the initial stored `0`, access enabled while writing `1`, and access disabled while feedback holds `1`. Returning to the complete LUT shows the second changed answer completing AND → OR. The conventional cell illustrates the mechanism, not a verified KV260 transistor schematic.

The tour returns to the CLB to introduce the name flip-flop and its role in holding working results. Three scroll states show D = 1 with Q = 0, a rising edge capturing Q = 1, then D changing to 0 while Q stays 1. The clock trace stays high after that edge; changing data alone does not trigger a capture. Optional detail explains two alternating latch stages, with MIT’s sequential-logic lecture as a source and an explicit illustrative-circuit caveat. The camera then zooms back to the map and into a routing selector. Three separate routing states show setting `0` selecting source 1, setting `1` selecting source 4, and new source data passing through the unchanged selection. Data and settings are labelled separately; the source outputs are not shorted together. Optional input and clock controls remain meaningful; scroll alone supplies the main explanation. Scene-derived states and interruptible CSS transforms avoid queues when readers reverse or skip ahead.

Sand to Thought already teaches binary arithmetic, feedback, latches/registers, addressed memory, selectors, clocked capture and a running total. The deep dive therefore removes the repeated register/bit-addition/counter construction from this introductory sequence. One link, at the SRAM feedback reminder, goes to the overview’s Memory chapter (`#sand-latch`). The later PWM example introduces its own counter concisely. LUT size trade-offs remain in optional detail. BRAM is identified as a separate resource for larger data collections; SRAM names a storage technology. The remaining board, history, workflow, performance and inference content is preserved. There are sixty-two scenes and thirteen chapters.

Keep local and preserve draft status. No commit, push, deployment or hardware-execution claim is part of this change.

The SRAM close-up has one complete gold cell boundary; parent outlines disappear at this deepest level. Its two NOT-gate symbols each stand for two transistors, while two larger enhancement-mode access-transistor symbols show the writing connection. The prose distinguishes these symbols. Reusable block labels use separate vertical positions for short and tall boxes, and descriptive details use the body face while numerical values retain the code face.

The CLB opening now includes a resource overview before the one-LUT/one-flip-flop example. It shows eight LUTs and sixteen flip-flops, explicitly identified as an AMD UltraScale example with a simplified layout and other circuitry omitted. The overview shows resources without connecting wires. Gold selects one LUT and one flip-flop; the next scroll scene enlarges that teaching example and introduces its connections. The following LUT/SRAM zooms and flip-flop capture states are preserved. The unsaved LUT-output path is labelled separately from the saved result.

The selected LUT and flip-flop now remain mounted and enlarge within a persistent CLB boundary; other resources fade without changing the outer shell. Two left-edge connections align with the chip map’s upper two left stubs, and the selected output exits through its middle right stub. The overview remains unconnected; internal wiring appears after the expansion. CSS transforms are interruptible and disabled for reduced motion.


The historical scenes (`history`, `first-fpga`, `first-fpga-block`) are temporarily parked at the end of the article, after the closing material, pending an editorial decision. Their prose, figures and citations are unchanged. The KV260 introduction stays after memory roles and before the design workflow.


## Continuing the chip map beyond routing

The opening chip remains mounted through clock distribution, BRAM/DSP introductions, working-memory roles, pin paths, placement/routing, configuration, parameters, energy, CPU cooperation, soft IP and the closing wrap-up. Its outline widens alongside the existing nine CLBs to reveal BRAM and then DSP resources; three extra overview scenes (`resources-map`, `arithmetic-map`, `neuron-map`) separate the reveals from their close-ups. The setup/hold waveform now accompanies the timing discussion as `timing-window`, rather than appearing during the clock-network overview. The script now has 66 scenes and thirteen chapters. History remains parked at the end.

A shared SVG detail slot places existing calculation diagrams at stable chip coordinates. Block RAM and DSP close-ups focus on their resources. Neuron and projection diagrams group several resource types; pulse and pipeline diagrams use a logic region. These are explanatory schematics, not floor plans or resource counts for the KV260. The cache view groups memory banks rather than claiming one BRAM tile holds the full cache. Preserve the existing calculation, memory and clock controls and their numerical models.

The board drawing, historical devices, software simulation, energy comparison, chip comparison and external application illustrations retain distinct views where enclosing them in programmable logic would imply the wrong physical boundary. No topics or reference entries were removed. Changes remain local.


## Opening inference profile

A static, shared SVG spider chart sits below the article title and before the chip tour. Clockwise from the top: Tokens per dollar, Tokens per second, Time to first token, Model size, Memory bandwidth, Tokens per joule, Customisation. The outline is explicitly illustrative, with placeholder scores on a shared normalised zero-to-one visual scale; it is not measured KV260 performance or a verified ranking. Further out means better, including shorter first-token latency. Keep the same axis order, visual scale and normalisation targets for future device profiles; define physical benchmark targets before replacing these placeholders with measured scores. Do not silently normalise each device or article to itself.

The accompanying specifications distinguish vendor-reported 4 GB external DDR4 from the current project's 26,720-parameter model and 16-bit weights/working values with 48-bit accumulated sums. Model size on the chart means parameters that fit at a stated precision and context, not the size of our tiny example. Future comparisons must state the model, precision, context, load and output quality; cost and energy must use declared equipment/host/power boundaries. There are no new controls, scene changes or hardware measurement claims.


The BRAM close-up now shows four four-bit words as individual SRAM cells, using the same red zero / green one convention as the configuration cells. The example explicitly starts with zeros. Write enable lifts a small illustrative barrier on the input bus, a data packet enters, and the selected row changes only when the clock pulse arrives. Read samples the chosen row with write enable low. Operations are single, bounded animations with timer cleanup on unmount, and reduced motion updates the values immediately. Address, data and read/write controls remain. The short landscape layout fits the complete close-up without internal scrolling.

BRAM writes now start automatically on entry, visiting a shuffled set of all four addresses before repeating and always choosing a different word for the selected row. A pause control and a decimal write-data selector allow manual experiments. Selecting address/data or reading/writing pauses the loop, and it resumes only when explicitly requested. Timers are cleaned up on unmount, off-screen/hidden-tab operation stops, reduced motion uses manual immediate updates, and automatic writes do not repeatedly announce live-region messages. The array is labelled “SRAM cells”.

The DSP introduction now traces moving numerical values through the existing multiplier, adder and saved-total feedback loop. The first two scroll steps prepare 3 × 2 and 0 + 6 while the register stays at 0. The final step captures 6 on a clock pulse, then reuses the circuit for 2 × 2 and 6 + 4, capturing 10 before holding. This is a finite, slowed teaching sequence with no new controls. Scene changes, hidden/off-screen playback and reduced motion clean up timers or show stable results. The shared datapath and later neuron/projection examples retain their behavior.

The running-total introduction now separates first capture and second calculation into distinct scroll scenes. A persistent addition, a value beside the return wire and an upward arrow make the feedback input explicit. “Next” labels the prepared result outside the saved-total register. The prose defines running total and distinguishes preparation from clocked replacement. First capture settles at 6, and the new `arithmetic-next` scene uses 6 + 4 before holding 10. There are now 69 scenes and thirteen chapters.

## 19 November 2026 — experiments 14–23

Experiments 14–17 compare DDR4 designs. Experiment 18 resumes the on-chip circuit from 13. Experiments 19–22 follow successively. Each scene highlights the affected stages and compares the complete Hello reply within its own run. Physical bars use the median mixed-workload completion time. Experiment 15 includes all four modes. Experiment 23 uses simulated request clocks and separately records routed cost. The immutable inputs and hashes are in the [results selection](results.json).

The resource histogram and cumulative three-metric chart continue through experiments 14–23. Histogram counts come from each build’s routed utilisation report. The timing points pool mixed-block prompt samples as before, and energy averages equal-work mixed blocks. Experiment 15 plots row bursts. Experiment 23 shows routed counts and an open performance slot pending a physical run.

## 20 November 2026 — DDR4 weight footprint

The sixth histogram column shows the size of the model weights read from external DDR4 during inference. Experiments 14–15 read the 2 KiB attention output matrix and 16–17 read the 20 KiB scoring matrix. The other designs use on-chip weights. Labels give KiB because both matrices occupy less than 0.001% of the module’s 4 GiB. The underlying routed UltraRAM counts remain in the [measurement data](figures/measurementData.ts). The four board runs are pinned in the [results selection](results.json).

## 20 November 2026 — Experiment 23 board measurements

The [physical comparison](../../../../research/inference/results/attention-value-pair-20261119T234247Z-e21df0/run.json) supplies the final graph points and their matched one-lane control. Each arm contributes eight timed mixed-workload replies per prompt. TTFT averages the 24 waits, decode speed pools their output intervals, and module energy divides the four mixed blocks’ total joules by their 2,528 useful output tokens.

## 20 November 2026 — FPGA diagrams in experiments 14–23

The later experiments share the centred fabric diagram used in experiments 1–13, above the before/after labels. DDR4 supplies weights from outside the fabric in 14–17. Callouts mark the type of hardware doing the work. Both BRAM and DSP are marked for paired value mixing in experiment 23. See the [selected run records](results.json).

## 20 November 2026 — Experiment 24 clock comparison

On the same Experiment 23 image, changing the configured FPGA clock from 50 to 52.63 MHz kept every reply and cycle count identical. Median replies took about 5% less time on all three prompts. Across the mixed-prompt blocks, module energy fell from 3.476 to 3.316 mJ per useful token. The 62.5 MHz target missed timing on two layouts and has no board measurement. The inference research checkout holds the physical record `attention-clock-20261120T004416Z-a9d9d2` and the final timing record `attention-clock-v1-stretch-build-20261120T003806Z`.

The article now includes the clock comparison. The graph adds the measured 52.63 MHz point and keeps the same resource counts as experiment 23. The 62.5 MHz target appears only in the timing discussion. [Board record](../../../../research/inference/results/attention-clock-20261120T004416Z-a9d9d2/run.json) · [Second layout](../../../../research/inference/results/attention-clock-v1-stretch-build-20261120T003806Z/run.json)
