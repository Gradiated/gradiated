# FPGA learning notebook

Keep Aidan’s questions and observations here, with explanations beside them.
Label proposed exercises, simulations and physical observations explicitly.
Do not turn a prediction into a reported experience.

## Why this project

Aidan is learning the semiconductor stack towards eventually designing and
taping out a custom chip. This project should teach that stack through a real
build and provide material for an interesting blog post. Another chat owns the
article prose and animations.

Aidan also explicitly wants a memorable marketing demo: an extremely silly,
possibly almost useless model running on the office FPGA, eventually selectable
through Gradiated’s API alongside the large professional models running on GPUs.
Its appeal can come from the humor, visible hardware and story. The current character is an overconfident intern at Gradiated, realised as a
small chip-joke transformer. Low practical utility is acceptable; genuine FPGA
inference and honest explanations remain requirements.

## Questions discussed

### Do I need another computer?

**Aidan’s question:** “I only have this mac, do i need another?”

**Explanation:** no purchase is needed now. The Apple Silicon Mac can run
appropriate simulations and software tools and communicate with the board.
AMD’s supported bitstream compilation tools need a compatible Intel/AMD build
system. We will need access to one for our own compiled circuits, but it need
not be a computer Aidan buys. A compatible prebuilt configuration may allow a
model demo first; that has not been verified.

A **bitstream** is the configuration data loaded into the FPGA to select its
logic functions and connections. Model weights are numerical data used by the
configured circuit; how they are loaded depends on the implementation.

### Where does the computation happen?

The KV260 contains an Arm processing system and programmable logic. An Arm
program executes software instructions. The programmable logic implements
configured circuits. Both can access system memory through the board’s
interconnect. Running an ordinary CPU inference program on the Arm cores alone
does not demonstrate an FPGA accelerator.

For every model implementation, we will identify which layer operations run
in programmable logic, which run on Arm, and whether an external host performs
any model computation.

## User-confirmed observations

- The board is an AMD Kria KV260, disconnected on Aidan’s table.
- Aidan currently has this Mac; no other build machine has been identified.
- Aidan wanted to discuss the plan before beginning practical implementation.
  The proposed progression was accepted before asking where project state lives.

## First exercise, not run yet

Predict `3 × 4 = 12`, then include signed examples such as `−3 × 4 = −12`.
Specify the representation before writing the circuit: two signed 8-bit inputs
have a full signed 16-bit product. Keeping too few output bits can change the
answer. Simulation will check the circuit’s behavior; only synthesis and
implementation reports can establish how a chosen tool maps it to actual DSP
blocks or other logic.

Next, an accumulator stores a running sum of successive products at clock
edges. A neuron adds a bias to a weighted sum and applies an output rule.
These are proposed explanations and exercises, not completed milestones.

## Aidan’s further questions and observations

No practical exercise or board observation has been recorded yet.

## Suggested learning route

Recommended on 30 October 2026; none of these resources is recorded as watched
or completed. Aidan wants to understand the whole project while the assistant
writes the implementation. The existing ETH notebook covers gates, sequential
logic and timing and records ongoing ISA study; build on that foundation.

Start with the first two items, then study the other material beside the
corresponding exercise. No full course is a prerequisite to connecting the board.

1. **FPGA overview: Nandland.** Watch
   [What is an FPGA? Intro for Beginners](https://www.youtube.com/watch?v=CfmlsDW3Z4c),
   then use [FPGA-101](https://nandland.com/fpga-101/) lessons 4 (LUTs),
   5 (flip-flops) and 6 (synthesizable code) as short notes. Aim to explain how
   a hardware description becomes logic, registers and connections, and what
   simulation checks before hardware exists. Its small-board examples introduce
   concepts; they are not a KV260 setup procedure.
2. **The actual board: Cathal McCabe.** Watch
   [Exploring the Kria KV260 board with PYNQ](https://www.youtube.com/watch?v=8 wTNApyt46Q).
   Use it to orient yourself to the board and the software/hardware boundary.
   This is an older walkthrough, originally from an FPL 2021 tutorial. Treat
   installation details separately: inspect our existing image first. PYNQ is
   a possible Python interface to programmable logic, not yet our selected stack.
3. **Our arithmetic exercises: Project F.** Read
   [Multiplication with FPGA DSPs](https://projectf.io/posts/multiplication-fpga-dsps/)
   beside the first multiplier, then
   [Fixed Point Numbers in Verilog](https://projectf.io/posts/fixed-point-numbers-in-verilog/)
   when fractional values enter the neuron. Focus on input/output widths,
   dedicated multiplier blocks, pipelining, range and rounding. These notes use
   multiple FPGA families; map resource details to the K26 before applying them.
4. **Neurons to language generation: 3Blue1Brown.** Use the videos and written
   lessons together:
   [But what is a neural network?](https://www.3blue1brown.com/lessons/neural-networks/),
   [Transformers, the tech behind LLMs](https://www.3blue1brown.com/lessons/gpt/),
   then [Attention in transformers, step-by-step](https://www.3blue1brown.com/lessons/attention/).
   Connect the weighted sums in our neuron to matrix operations, token vectors,
   attention and repeated next-token prediction. Study training and gradients
   when we reach personality changes; they need not delay first inference.
5. **Later code walkthrough: Andrej Karpathy.**
   [Let’s build GPT: from scratch, in code, spelled out](https://www.youtube.com/watch?v=kCc8FmEb1nY)
   is listed as 1 h 56 min in the author’s
   [Zero to Hero syllabus](https://karpathy.ai/zero-to-hero.html). Watch after the
   visual explanations and basic tensor concepts; the author recommends earlier
   makemore material for those foundations. Follow the forward calculation and
   generation loop first. This teaches a software model, not an FPGA toolchain.

For every stage, the assistant should show the circuit/block diagram, a tiny
numerical example, relevant source and its test result. Aidan should have the
opportunity to predict the result and ask questions before the next abstraction
is introduced. Keep learning goals tied to the working build.

## Current model and where files live

The active model has 26,720 parameters and one transformer block. It was trained
from random weights on 48 authored jokes. It is deliberately a small memorising
teaching example. The selected weights/configuration live under ignored
`.agents/runtime/fpga-inference/models/tiny/`; code and the exact training corpus
are tracked under this project. The Python environment is under ignored runtime
venv/, using its pinned local Python distribution. MLX performs inference on the
Mac's GPU. No computation currently executes in FPGA programmable logic.

The raw joke text is smaller than the learned model. We are demonstrating real
inference arithmetic, not finding the most efficient way to store 48 sentences.
A literal text lookup would be simpler; our model predicts every output byte.

## How this transformer generates a joke

1. Start with BOS token 256. Its embedding is a vector of 32 learned numbers.
2. In one block, normalise and compute query/key/value projections. Two heads
   each use 16 coordinates. Attention compares the current query with earlier
   keys, weights the stored values, and projects the result back to 32 numbers.
3. Apply a residual addition, normalise, expand through the SwiGLU feed-forward
   layer of width 128, project back to 32, and add the other residual.
4. Final normalisation and the tied embedding/output matrix produce 320 logits.
5. For the first 32 generated bytes, a host RNG samples the probabilities at
   temperature .8. Later bytes use argmax. Feed the chosen byte back through the
   transformer. EOS 257 stops generation; the limit is 255 output tokens.

Every request starts with the same start token. Enter chooses a fresh sampler
seed; typed text hashes to a repeatable seed. The model never sees the question
or a joke identifier. The randomness is in autoregressive token sampling, not a
diffusion noise vector. There is no answer lookup, output mask, retry or hidden
repeat suppression. Identical seeds reproduce the same output; repeats and
occasional gibberish are expected. New seeds do not test unseen language ability.

## Numbers and verification

The selected eight-bit matrix format uses affine groups of 32, with FP32
scales/offsets, norms, intermediate arithmetic and KV cache. It is not an
integer-only hardware design. Weight file: 36,310 bytes; tensors: 33,664 bytes.
A full 256-position FP32 KV cache needs
`256 positions × 2 (K,V) × 32 coordinates × 4 bytes = 65,536 bytes`.
The tensor/cache total is analytically 99,200 bytes before buffers/packing.
No synthesized FPGA fit follows from that sum.

The original selected model produces 127 exact authored jokes across 41 distinct
jokes in 128 reserved random seeds. One gibberish result is retained. All end in
EOS/valid UTF8, demonstrating that a finished string need not be coherent.
Cleanup reproduces all 128 original token sequences exactly, including that
failure. Independent NumPy and cached/full checks cover three model prefixes;
all eight quantized matrices are independently unpacked. These are scoped
correctness checks, not exhaustive mathematical proof or FPGA measurements.

The actual model/trace.txt records seed-47 probabilities, random draws and bytes
from this model. Earlier keyed-model layer traces use different trained weights;
they remain in Git history and must not be presented as this model's values.

## Teaching route from here

Before implementing hardware, agree the numerical formats, rounding/overflow,
weight layout and CPU/PL boundary, including sampling. Then trace a real model
projection as multiply-and-accumulate steps, implement and simulate that unit,
and expand to the transformer. Physical multipliers/DSPs can be reused across
logical coordinates; a model neuron does not require its own permanent circuit.

The board remains disconnected. No circuit, simulator, bitstream, measured
latency, energy or cost-per-token result exists. AMD build-tool access is still
a later decision; this cleanup neither installs tools nor starts FPGA work.
The article belongs to another chat. Keep the distinctions between measured Mac
outputs, analytical budgets, simulation and actual board measurements explicit.

## Earlier questions and observations

All earlier learning notes and character feedback are preserved verbatim as a
historical learning.md source record in material/library.jsonl. The current
character guide is material/character.md; creative drafts and reviewed dialogue
remain under material/. Earlier training findings and the recovery checkpoint
are summarised in history.md. That material is preserved without making the old
experiment tree part of the active workflow.

## Measured fixed-point lesson

The Mac software experiment keeps the network and learned source weights, then
emulates integer arithmetic throughout the layers. Aidan chose **16-bit weights
and stored working values** to make the teaching example clearer. This does not
mean every temporary calculation is only 16 bits: multiplying two signed 16-bit
values needs up to 32 bits, sums use 48 bits, and scalar nonlinear work uses
checked 64-bit scratch. Scores/logits and probabilities have explicit formats.

The selected version reproduced 64/64 development jokes and 127/128 confirmation
jokes across 42 different jokes, with no observed overflow or saturation. Of the
128 outputs, 127 matched q8 exactly; one selected a different complete joke.
Both retained the same one gibberish case. No guarantee for every future seed.

Maximum prediction-score difference .1092 still exceeds our original .1 limit.
The user-selected teaching policy reports that miss separately, while keeping
the normalized-error, joke-quality and arithmetic checks. The earlier 18-bit
working-value candidate reduced the maximum difference to .0480, but its extra
precision is not required for the chosen teaching acceptance policy.

The actual 32-term weighted sum for the first Q output after BOS uses 16-bit
inputs and weights. Its integer sum -3,760,136 has scale 2^-26, then rounds to
-115 with scale 2^-11. A future circuit must reproduce these partial sums and
output exactly. The reference models arithmetic, not physical clocks or energy.
See the [hardware blueprint](hardware.md) and
[model notes](model/README.md#fixed-point-software-study).


## First circuit: observed in simulation

The first actual SystemVerilog block now computes the 32-term sum. Two small
memories hold the inputs/weights; a counter chooses the pair, one multiplier
forms the product, and an adder feeds a register that remembers the total.
A separate rounding step produces the stored 16-bit result. Memory reads and
multiplications alternate in this intentionally simple schedule.

`generative.sh rtl` checks the circuit and creates a local projection.html page
with the observed values and clock controls. It computes one coordinate inside
the transformer. The schematic on that page explains the RTL architecture;
a synthesized FPGA schematic and physical placement remain future views.
All 156 full test calculations and 4,992 observed terms passed. This is genuine
RTL simulation on the Mac, not yet physical FPGA execution or a token generator.


## From one output to the whole Q vector

The next circuit milestone is now simulated: keep the 32 input values, change
the row of weights, clear the running total and calculate another output.
Repeat for all 32 rows. The hardware description contains the same single
multiplier and accumulator throughout; the row counter changes which weights
it reads. The 32 tagged outputs are streamed out one at a time.

The walkthrough now lets you select any output and follow its 32 products.
For the starting token, outputs begin -115, -5711, 2007, 3393. The full matrix
requires 1,024 multiplications. All 32 outputs match the integer model, and
broader simulation checked 1,696 outputs / 54,272 products and sums exactly.
Inputs are still prepared in Python; this has not moved normalization, attention
or the entire transformer into the FPGA. No board inference is claimed.


## Three lists from the same input: Q, K and V

The circuit now repeats the same calculation for all three lists. Q is a query
(what to look for), K is a key (what can be matched), and V is a value (the
information attention can gather). These are learned lists of numbers, not
literal questions or labels. We have not built the attention calculation yet.

Each list has 32 numbers. To produce one number, multiply the 32 inputs by one
row of weights and add the products. Then choose another row and repeat. Q, K
and V have different weight matrices but use the same input and the same single
multiplier/accumulator. That is 96 outputs and 3,072 multiplications, performed
one after another; it does not mean 96 separate physical calculators.

Choose Q, K or V in the walkthrough, then an output numbered 0..31. The products
and running total come from the simulated circuit. Rounding divides by 32,768
for all three lists, although V's final integers represent smaller units than
Q/K: integer × 2^-12 rather than integer × 2^-11. The page explains the selected
scale. Inputs still come from Python; positional rotation, remembering K/V and
attention are later building blocks. All 5,280 tested outputs matched exactly.
This is still simulation on the Mac, with no full-model FPGA execution yet.


## RoPE: position changes the direction of a pair

Q and K now have a separate simulated positional-rotation circuit. Treat two
numbers as coordinates of an arrow. Position selects an angle; RoPE rotates
the arrow. Different pairs use different rotation speeds, helping later Q/K
comparisons reflect token spacing. The coefficients are fixed mathematical
table values, not extra learned weights. Position counts from zero; at zero
there is no rotation. Position one makes the effect visible in the walkthrough.

Our model pairs the first and second halves of each 16-coordinate head:
0 with 8, 1 with 9, through 7 with 15. It does that separately for two Q heads
and two K heads, giving 32 pairs / 64 output numbers. V is not rotated.
For each pair a,b, the circuit uses its one multiplier four times, then forms
`a*c - b*s` and `b*c + a*s`. Dividing each combined value by 16,384 removes the
coefficient encoding scale. Both rounded outputs keep the same units as inputs.

Open the generated rope.html, choose a pair and press Show completed pair to
see the input and observed output arrows. Its clock controls expose the four
products in order. The page uses real simulated values; all 27,072 tested output
coordinates match the independent integer calculation. This block still receives
its Q/K inputs from Python. Wiring it to projections, saving K/V and calculating
attention are later steps; no full-model inference in FPGA hardware is claimed.


## KV cache: remembering a completed token

A separate simulated circuit now stores K after RoPE and V unchanged. Each token
has 32 K numbers and 32 V numbers. Two memories have room for 256 tokens each;
at two bytes per number their total logical storage is 32 KiB. These are working
results from processed tokens, separate from the model's learned weights.

Imagine 256 rows, one per token, with 32 columns in each of two notebooks.
Position p and coordinate c choose cell p×32+c. The circuit writes one K/V pair
at a time. A row stays unreadable while it is partly written; the final pair
makes the whole token readable. Reads can revisit earlier completed rows.
The cache returns a registered K/V pair and waits for the receiver to accept it.

Reset sets the complete-token count to zero. Old bits remain in RAM, but the
controller refuses to read them until a complete new row has replaced them.
The 257th token is refused rather than wrapping around and overwriting token0.
The cache.html walkthrough shows these states and lets you inspect addresses.
It replays actual observed simulation; choosing a location does not issue a
live FPGA read. All 54,024 tested returned values matched independent checks.
The circuits remain separate and receive prepared inputs from Python; connecting
projections/RoPE/cache and building attention are later work.
