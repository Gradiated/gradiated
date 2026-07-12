# Functional Twin — Surgery Round 2: CLA KV-sharing retrofit

Retrofit cross-layer attention (CLA-2, Brandon et al. style) onto
SmolLM2-135M-Instruct **post hoc on real weights**: adjacent layer pairs
share one KV — layer 2k+1 ("consumer") reuses layer 2k's ("producer")
post-RoPE K/V and its own `k_proj`/`v_proj` are deleted. Same environment,
data, and perplexity protocol as round 1
(`docs/experiments/twin-surgery-round1.md`).

Date: 2026-07-12 (overnight session).

## Why this surgery

KV-cache bytes/token halve **architecturally** (30 → 15 KV-producing
layers): at fixed memory a serving engine can hold ~2x the concurrent
sequences or 2x the context. Unlike head pruning this is not a FLOP cut — it
is a memory-bandwidth/capacity cut, which is what batch-serving economics
actually price. Also removes 15 × 221,184 = **3.32M params (−2.5%)**:
134.52M → 131.20M.

## Implementation

`twin/cla.py`: per-instance monkeypatch of `LlamaAttention.forward`
(transformers 5.13). Producers run the stock computation and stash post-RoPE
`(key_states, value_states)` in a dict shared across the pair; consumers
compute only `q_proj` + RoPE-on-Q and attend over the producer's K/V.
Consumer `k_proj`/`v_proj` are set to `None` (truly removed from the module
tree, the state dict, and the optimizer). Cache-free forward only
(`config.use_cache = False`): eval and training work; incremental generation
would need engine-side support.

**Correctness gate**: `apply_cla(model, replica_mode=True)` routes every
layer through the reimplemented forward *without* sharing —
logits are **bit-identical** to the stock model (max abs diff 0.0).
The measured CLA effect is therefore purely the KV sharing, not a forward
reimplementation artefact.

Sharing post-RoPE K across a layer pair is position-consistent because RoPE
angles depend only on token position, which is identical for both layers.

```bash
cd /Users/js/dev/sartor/twin
# unhealed eval
.venv python eval_ppl.py --model models/smollm2-135m-instruct --cla --tag smollm2-135m-cla2-unhealed
# healing (same recipe as round-1 heal, 2000 steps)
.venv python heal.py --steps 2000 --cla --src models/smollm2-135m-instruct \
    --dst models/smollm2-135m-cla2-healed --curve cla_healing_curve.json --force-head-dim 0
```

## Results (wikitext-2 test, window 1024 / stride 512, fp32)

| model | ppl |
|---|---|
| baseline | 16.60 |
| CLA-2 retrofit, unhealed | **133,120** |
| CLA-2 + healed (2000 steps) | TBD (running) |
| round-1 control (baseline + wikitext finetune, 1500 steps) | 14.64 |

Unhealed CLA is catastrophic (ppl 133k ≈ random-ish attention for odd
layers): consumer queries attend into a key space produced for a *different*
layer's queries. This was expected — CLA models are normally *trained* with
sharing from scratch; the question this round answers is how much healing a
**retrofit** needs, versus head pruning's near-instant recovery.

Healing: same recipe as round 1 (AdamW β 0.9/0.95, wd 0.01 matrices, lr 1e-4
cosine → 1e-5, warmup 100, seq 1024, batch 8, fp32/MPS, seed 0) but **2000
steps = 16.4M tokens** (vs 1500 for head-prune healing) since the damage is
orders of magnitude larger. Checkpoint + val every 250 steps. Curve:
`experiments/results/twin/cla_healing_curve.json`.

TBD: healing curve table, final healed ppl, comparison against control,
verdict.

## barge / engine note

Not benchmarked in barge: the engine has no cross-layer KV indirection
(each layer allocates and reads its own cache — `crates/engine/src/kv.rs`
lays out `[layer][slot, kv_head, ctx, head_dim]`). The throughput effect is
architectural rather than kernel-level: **KV bytes/token halve → the
`max_slots`/`max_ctx` product doubles at fixed KV memory** — the serving
simulator prices this directly. The healed checkpoint is saved as
safetensors with `"kv_sharing": "cla2"` in `config.json` (odd-layer k/v
projections absent); `twin/cla.py::load_cla` reconstructs the patched model.

## Artefacts

```
twin/cla.py                                   retrofit + loader (+ replica-mode correctness test)
twin/heal.py --cla                            healing path
models/smollm2-135m-cla2-healed/              healed CLA checkpoint
experiments/results/twin/ppl_smollm2-135m-cla2-*.json
experiments/results/twin/cla_healing_curve.json, cla_train.log
experiments/results/twin/instruct_sanity.json (round-1 sanity suite; see round-1 doc)
```
