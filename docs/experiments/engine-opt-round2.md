# Engine optimization round 2: fused RoPE, scatter-index cache, f16 softmax

Target: barge decode path on SmolLM2-135M-Instruct, Metal f16, M4 Pro.
Reference: llama.cpp on the same model/hardware = 7,186 tok/s @ b=64 (fused kernels).

Bench command (all numbers = output tok/s, 3-run medians):

```
barge bench --model models/smollm2-135m-instruct --device metal --dtype f16 \
  --num-requests 128 --input-len 128 --output-len 128 --max-slots 72
```

## Measurement caveat

A sibling agent ran PyTorch/MPS training on the same GPU throughout this round;
observed load swings moved the *same binary* between ~500 and ~2,270 tok/s.
Sequential per-step medians are therefore reported but not trusted; the
authoritative numbers come from an **interleaved A/B** (base → s1 → s1+2 → full,
repeated 3 rounds back-to-back, medians per variant) so all variants sample the
same load distribution.

## Optimizations

### 1. Fused RoPE (model.rs)

Replaced the manual rotate-half `apply_rope` (2 narrows, 4 broadcast muls,
1 sub/add pair, 1 cat ≈ 7 kernel dispatches per call, ×2 calls ×30 layers) with
`candle_nn::rotary_emb::rope` — a single fused Metal kernel per call.

- Prefill: q reshaped to `[1, kv*g, t, hd]`, k to `[1, kv, t, hd]`; cos/sin
  passed rank-2 `[t, hd/2]` (a contiguous narrow of the precomputed table).
- Decode: per-slot positions go through the kernel's batched-cos path —
  cos/sin rank-3 `[b, 1, hd/2]` (Metal `stride_b`, CPU `unbatched_rope` branch,
  verified identical rotate-half math in candle-nn 0.9.2 source).
- Head-order preserved: `[b, kv, g, hd] -> [b, kv*g, 1, hd]` is a pure view.
- Saves ~24 dispatches/layer-pair per step (the D8 "fused rope" item from the
  135M optimization log).

Parity: 6/6 green (max abs diff unchanged, ~1e-4 class).

### 2. Per-step scatter-index cache (kv.rs)

`write_decode` rebuilt the scatter row-index tensor (CPU vec build + host->GPU
upload + broadcast/contiguous) once per **layer**; positions are identical
across all 30 layers within a step. Added a one-slot `Mutex<Option<(Vec<usize>,
Tensor)>>` cache keyed by the exact positions vector — hit ⇒ reuse uploaded
tensor, miss ⇒ rebuild. Exactly correct by construction (key equality ⇔
identical rows). Probe had shown `kv write_decode` at ~433 us/layer (b=64),
the single largest per-layer decode cost.

Parity: 6/6 green.

### 3. f16 end-to-end decode softmax (model.rs)

Decode attention was `att(f16) -> to_dtype(F32) -> +mask(f32) -> softmax ->
to_dtype(f16)`. Now the length mask is cast to model dtype once per step and
softmax runs in f16 directly: verified in candle-metal-kernels 0.9.2
`reduce.metal` that the online-softmax `MD` struct accumulates the exp-sum `d`
in `float` even for f16 inputs, so no accumulation-precision loss. Removes 2
dtype-conversion dispatches per layer.

Parity: 6/6 green (CPU/F32 path unaffected — mask cast is a no-op there).
Metal f16 coherence: greedy gen single + batched (n=4) produce coherent,
batch-invariant text ("...three primary colors: red, blue, and yellow...").
NOT REVERTED.

## Results

### Interleaved A/B, SmolLM2-135M f16 Metal (output tok/s)

| round | base (HEAD) | +rope (s1) | +scatter cache (s12) | +f16 softmax (full) |
|---|---|---|---|---|
| 1 | 515.2 | 988.3 | 1829.9 | 1502.3 |
| 2 | 512.3 | 823.6 | 839.1 | 996.5 |
| 3 | 385.9 | 1458.6 | 2271.9 | 2255.6 |
| **median** | **512.3** | **988.3** | **1829.9** | **1502.3** |

Per-round speedups vs base (immune to slow load drift within a round):

| round | s1/base | s12/base | full/base | s12/s1 | full/s12 |
|---|---|---|---|---|---|
| 1 | 1.92x | 3.55x | 2.92x | 1.85x | 0.82x |
| 2 | 1.61x | 1.64x | 1.94x | 1.02x | 1.19x |
| 3 | 3.78x | 5.89x | 5.84x | 1.56x | 0.99x |
| **median** | **1.92x** | **3.55x** | **2.92x** | **1.56x** | **0.99x** |

Read: fused RoPE ≈ **1.9x**, scatter-index cache ≈ a further **1.6x**,
f16 softmax ≈ **neutral within noise (0.99x median)** — kept anyway (2 fewer
dispatches/layer, no parity cost; it never hurts outside noise).
Combined median **~2.9x**; the least-loaded round shows **5.8x** (386 → 2,256).

Best observed absolute (round 3, load momentarily low): **2,256 tok/s** vs
llama.cpp reference **7,186 tok/s** → barge now at **~31% of llama.cpp**
(was ~14–17% at the unloaded 977–1,244 baseline; a quiet-machine rerun is
needed for a clean absolute).

### Probe deltas (b=64; caution: after-probe ran under much heavier ambient load — dispatch floor 7.0 → 48.2 us)

| op | before | after |
|---|---|---|
| FULL decode step (all layers) | 45,062 us | **27,628 us** (−39% despite ~7x higher ambient load) |
| kv write_decode (1 layer) | 433 us | 805 us (isolated-op probe defeats the per-step cache; in-engine cost is paid once per 30 layers) |
| softmax (decode dtype path) | 71.4 us (f32) | 18.9 us |
| lm_head GEMM | 616 us | 609 us (unchanged, as expected) |

## Ladder re-run (2026-07-12, sibling MPS training active — numbers load-suppressed; compare timestamps, not absolutes)

3-run medians; median-run JSON rows appended to experiments/results/ladder.jsonl:

| model | params | prior row (unloaded) | this run (loaded) |
|---|---|---|---|
| smollm2-135m-instruct | n=128, in/out=128, slots=72 | — (baseline quote 977–1,244) | 585.0 [579.1, 585.0, 602.5] |
| qwen2.5-0.5b-instruct | n=128, in/out=128, slots=72 | 965.9 | 509.8 [504.4, 509.8, 515.5] |
| qwen3-4b-instruct | n=48, in/out=128, slots=24, ctx=1024 | 112.5 | 121.7 [119.0, 121.7 — 2 runs; run 3 abandoned after >20 min under load (prior row: 55 s wall)] |

The ladder deltas are not interpretable this session: the interleaved A/B above
is the controlled result. Re-run the ladder on a quiet machine before quoting
absolutes.

## Verdict

- Fused RoPE: **kept** (median 1.9x, parity 6/6).
- Scatter-index cache: **kept** (median 1.56x on top, parity 6/6).
- f16 decode softmax: **kept** (0.99x median — neutral, not reverted; parity
  6/6, Metal f16 generation coherent and batch-invariant, Metal kernel
  accumulates exp-sum in f32).
- No reverted steps.
