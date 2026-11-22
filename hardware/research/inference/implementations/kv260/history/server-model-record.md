# Selected 27K BOS-only transformer

One block, hidden width 32, two 16-wide query/key/value heads, SwiGLU width 128,
vocabulary 320, tied embeddings, RMSNorm and RoPE, context 256. Exactly 26,720
parameters. Fresh seed-47 weights trained on 48 authored UTF8 jokes, each as
`[BOS=256, text bytes, EOS=257]`; the first byte and EOS are supervised.
No joke identifier is supplied. The vocabulary retains unused special slots to
keep the measured teaching architecture unchanged.

The host samples the first 32 output bytes from all 320 logits at temperature
0.8 using an independent NumPy RNG; later bytes use argmax. Output bytes are fed
back autoregressively. Randomness enters the sampler, not a diffusion noise
vector or model input. Text input hashes to a seed. Repeats and errors remain.

## Measured result

The frozen eight-bit choice gives **127/128 exact authored jokes across 41
jokes** on seeds 10001–10128. One gibberish output, seed 10125, is retained in
expected.jsonl; all outputs happen to end in EOS and valid UTF8. Those two checks
alone do not establish coherence. The largest joke frequency is eight. Every
joke is training data; new random seeds are not unseen language situations.

The cleanup regression reproduces all 128 original token sequences exactly,
including the failure. Independent NumPy checks cover all 320 logits on three
prefixes, full/cached agreement and equal top token. Independent unpacking
covers eight quantized matrices / 26,624 matrix values. Tolerances remain
atol .002 / rtol .0002. These are scoped checks, not exhaustive proof.

The original fit selected the primary 2,000-pass checkpoint; the conditional fit
never ran. AdamW learning rate .001, decay .01, gradient norm 1, batch 8;
12,000 updates, 96,000 joke exposures, 9,070,000 supervised tokens. At 600 passes
fidelity was insufficient. The FP32/q8 development screen each yielded 64/64
exact across 36 jokes, but seven seeds chose different jokes between formats.
The registered reserved quality gate passed; humour remains the user's judgment.

## Files and retained payloads

- jokes.json: exact original 48 trained targets, distinct from the editable draft.
- selection.json: fixed architecture, recipe, artifact pins and payload hashes.
- expected.jsonl: all 128 actual pre-cleanup outputs and tokens.
- trace.json / trace.txt: actual seed-47 sampling probabilities, draws and bytes.

FP32 weight file: 107,983 bytes; q8 file: 36,310 bytes. The q8 format is eight-bit
affine group 32, with FP32 scales/offsets, norms, activations and KV cache. Tensor
storage is 33,664 bytes; a full 256-position FP32 KV cache adds 65,536 bytes.
Their analytical total is 99,200 bytes before buffers, alignment and memory-bank
packing. No physical FPGA fit is established. The 4,487-byte joke text is smaller
than the model: teaching inference, not text compression, is the purpose.

The trace is Mac software evidence, not FPGA clocks or a full layer trace. The
older keyed model's layer vectors come from different weights and must not be
transplanted. No conversation, novel-joke, uniform coverage, no-repeat, FPGA
performance or energy claim.

Origin: commit e164e1958, data/generative-tiny-v1. Complete historical plans,
outputs and failures remain recoverable at the pre-cleanup Git tag; see
../history.md. Runtime weights themselves were never in Git.

## Fixed-point software study

Measured on the Mac, with the original selected q8 values independently unpacked
and converted, not retrained. The frozen 48 targets and decoding recipe are
unchanged. All network calculations use integer operations; offline calibration/
table construction and the external FP64 sampler use floats. NumPy int64 holds
emulated values on the CPU while enforcing the declared narrower boundaries.
This is an arithmetic reference, not a clock/memory-port or RTL simulator.

| Format | Development jokes | Worst logit error | Numerical gate | Confirmation |
| --- | --- | --- | --- | --- |
| W16A16: 16-bit weights/working values; selected for teaching | 64/64 exact; 36 distinct | .10922515 | Failed original .1 absolute limit; passed explicit teaching policy | 127/128 exact; 42 distinct |
| W16A18: earlier wider candidate | 64/64 exact; 37 distinct | .04796648 | Passed original strict gates | 127/128 exact; 42 distinct |

Aidan selected W16A16 for a clearer teaching example. The original absolute
error limit remains failed, not retroactively passed. The teaching policy makes
that absolute error diagnostic while retaining normalized logit RMSE <= .01,
all output-quality gates, primitive/float oracles, cached/full equality and zero
observed saturation. No arithmetic, scales, training or sampling were tuned on
confirmation outputs. The selected maximum normalized RMSE is .005558478
(about .556%). All 320 logits were compared at 16,125 teacher/development and
11,971 confirmation prefix evaluations, including repeated prefixes. All
most-likely next tokens agreed on those paths; sampling can still change a joke.

On matched seeds 20001–20128, selected W16A16 and q8 each produce 127/128 exact
jokes across 42 distinct jokes, largest count nine, all EOS/valid UTF8.
**127 complete token sequences match**. Seed 20087 switches from the q8
resist-development/curl joke to this complete trained joke:

> Ready salted. I respect a potato that doesn't need a marketing department.

Both retain this unfiltered failure at seed 20003:

> Nvidia has liquid couripechipen. Theyor tepe toenthereces eam finghhre prorticheses arug aidedere.

Completion and valid UTF8 do not establish coherence. Repeats remain. These
seeds were previously examined for q8/W16A18, so this is a matched format
comparison, not a fresh independent holdout. All jokes are trained; the finite
sample does not prove universal equivalence. W16A18 matched all 128 q8 sequences;
the earlier 41-distinct result uses a different seed set.

The first direct exponential table failed an isolated precision probe; the
accepted table uses explicit binary range reduction. Norms use integer square
sums, a reciprocal-square-root table/two Newton steps, and nonzero encoded
epsilon. RoPE, attention softmax and SwiGLU remain present. Rounding is nearest
ties-to-even; narrowing saturates/counts, and checked wide arithmetic rejects
overflow. Details and negative results are recorded in ../hardware.md.

`fixed.json` pins tensor shapes/types/hash, static binary exponents, table formats,
the arithmetic source digest and all 128 output token hashes. Its teaching trace
is the actual BOS input's first Q projection: 32 16-bit inputs ×16-bit weights,
48-bit accumulator -3,760,136 at exponent -26, rounded to integer -115 at
exponent -11. The trace is computed software data, not FPGA clocks.

Local models/tiny/fixed/fixed-tensors.safetensors is 64,648 bytes: 53,440 parameter
bytes, 8,192 RoPE bytes, 1,028 exp bytes, 1,024 reciprocal-sqrt bytes plus header.
The logical 16-bit KV cache is 32,768 bytes; weight+KV subtotal 86,208 bytes,
excluding tables/buffers/packing. The planned 47-BRAM layout is still analytical.

Verification includes 5,040 primitive integer-oracle cases, 51 float-observation
checks against the existing NumPy reference, cached/full equality through 256
positions, rejection of position 257, and exact SafeTensors reload. Long-context
probes use synthetic repeated training token sequences, including BOS at repeat
boundaries. The unchanged original q8/FP32 regression also passes.

First W16A16 comparison: ignored runtime job 20261102T220133840873. Real-trace
export regression: 20261102T220222626346; all 128 sequences match the first run.
Earlier W16A18 first confirmation: 20261102T213030461825, packaging replay:
20261102T213326245413. Further runs reuse examined seeds and are regressions.
Runtime results contain complete outputs, operation errors, counters, phase
times and source snapshots/hashes. Original FP32/q8 payloads remain unchanged;
the 16-bit selection shares the same integer weight/table image as W16A18,
with narrower activation exponents and a different pinned trace/token fixture.
