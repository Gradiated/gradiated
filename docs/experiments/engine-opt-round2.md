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

(interleaved A/B results inserted below)

## Ladder re-run

(ladder results inserted below)
