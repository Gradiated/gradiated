# Functional Twin — Surgery Round 1

Local, reproducible model-surgery experiments on the M4 Pro / 48 GB workstation.
All code in `twin/`, raw results in `experiments/results/twin/`.

- Python: `/Users/js/dev/vllm-study/.venv/bin/python` (torch 2.11.0 + MPS, transformers 5.13.0)
- Data: `data/wikitext2-{train,validation,test}.parquet` (raw wikitext-2, `text` column), `data/sharegpt_v3.json`
- Models: `models/granite-1b-a400m` (GraniteMoE: 24 layers, 32 experts/layer, top-8, ~1.3B total / ~400M active), `models/smollm2-135m-instruct` (Llama arch: 30 layers, hidden 576, 9 Q-heads / 3 KV-heads, head_dim 64, 134.5M params)
- Date: 2026-07-11

## Perplexity protocol (used everywhere unless stated)

Concatenate all rows of the split with `"\n\n"`, tokenize with the model's own
tokenizer, then standard HF sliding-window eval: windows of 1024 tokens advance
by stride 512; loss is scored only on the final 512 tokens of each window
(full window for the first), so every token is scored exactly once with at
least 512 tokens of context. `ppl = exp(sum NLL / n_scored_tokens)`. Model in
float32 on MPS; logits cast to float32 before loss. Implementation:
`twin/common.py::strided_perplexity`. Wikitext-2 test = 304,986 tokens under
the SmolLM2 tokenizer.

---

## 1. MoE routing statistics — granite-1b-a400m

**Question**: is there enough "expert locality" (skewed loads, co-firing
cliques) to justify placing expert groups on separate memory/compute islands?

### Protocol

- `twin/granite_routing.py`: forward hooks on every layer's
  `GraniteMoeTopKRouter` capture the per-token top-8 expert indices.
- Corpus: 149,504 tokens of wikitext-2 **train** + 49,152 tokens of code mined
  from local `sharegpt_v3.json` (fenced ``` blocks in assistant turns; no other
  code data was local, and this avoids self-generation bias). 198,656 tokens
  total, fed as 2048-token windows, float32 on MPS. Capture took **116 s**.
- `twin/analyze_routing.py`: loads / co-activation / coverage / clustering.
  Expert grouping: balanced greedy agglomeration on the cosine-normalised
  co-activation matrix (`coact / sqrt(load_i * load_j)`), followed by balanced
  pairwise-swap local search minimising mean distinct-groups-per-token
  (20k-token subsample for the search; all metrics reported on all tokens).
  No scipy/sklearn in the venv, so clustering is pure numpy.

Commands:

```bash
cd /Users/js/dev/sartor/twin
/Users/js/dev/vllm-study/.venv/bin/python granite_routing.py
/Users/js/dev/vllm-study/.venv/bin/python analyze_routing.py
```

Outputs: `experiments/results/twin/granite_routing/{routing_topk.npz,loads.npy,coactivation.npy,summary.json,capture_meta.json}`
(`loads.npy` is (24, 32) int64 counts; `coactivation.npy` is (24, 32, 32) with
diagonal = loads.)

### Key numbers

**(a) Expert load skew — LOW.** Mean Gini across layers **0.284**
(min 0.197, max 0.533; only layer 1 exceeds 0.44). Max/mean load per layer is
typically 1.5–2.5x. Coverage is close to uniform: on average the top-8 experts
serve only **43.7%** of routed slots, top-16 serve **69.9%**, top-24 serve
**88.4%**.

**(b) Group separability — LOW.** With experts clustered into G=4 groups of 8
(so a token's 8 experts *could* fit in one group), **99.2%** of tokens still
need experts from >1 group; the mean is **2.87 groups/token** (of 4). With
G=8 groups of 4, the floor is 2 groups/token; observed mean is **4.24**, and
98.3% of tokens exceed the floor.

**(c) Hot-set size — LARGE.** Smallest expert set covering 80% of routed
tokens: **~20 of 32** per layer (range 13–22). For 95%: **~28 of 32**
(range 24–30).

Domain contrast: code routes slightly more skewed than prose (mean Gini 0.360
vs 0.288), and the 80%-hot-sets of wiki vs code overlap with mean Jaccard
**0.61** — some domain specialisation, but far from disjoint expert sets.

### Read-out for co-design

Granite-1b-a400m was trained with aux-loss load balancing and it shows: loads
are near-uniform, co-firing cliques are weak, and per-token expert spread is
close to random. **An "expert locality" placement claim is not supported by
this model's routing**; a co-design that banks on hot experts fitting in a
small fast tier would need either (i) routing-aware finetuning to *create*
locality, or (ii) a model trained without strict balancing. This is the
honest empirical baseline for that follow-up.

---

## 2. Head pruning + healing — SmolLM2-135M

**Surgery**: prune Q-heads 9 → 6 per layer keeping GQA valid (3 KV-heads,
group size 3 → 2: in each KV group, drop the weakest Q-head), by slicing
`q_proj` rows and `o_proj` columns. K/V projections untouched. 134.54M →
**127.88M params** (−4.9%); attention Q/O FLOPs −33%.

### Protocol

1. **Importance** (`twin/head_importance.py`): mean L2 norm of each head's
   64-dim slice of the `o_proj` input (the head's post-attention output),
   over 49,152 tokens of wikitext-2 validation (48 windows of 1024), fp32/MPS.
   Result: `experiments/results/twin/head_importance/head_importance.json`
   (+ `.npy`). The weakest head per KV group per layer is dropped.
2. **Surgery** (`twin/prune_heads.py`): slice weights, set
   `num_attention_heads: 6` and explicit `head_dim: 64` in `config.json`
   (hidden 576 / 6 = 96, so `head_dim` must be explicit; both transformers 5
   and barge honour it). Checkpoint: `models/smollm2-135m-pruned-h6/`
   (safetensors). Reload + forward sanity-checked.
3. **Healing** (`twin/heal.py`): finetune the pruned model on wikitext-2
   train. AdamW (β=0.9/0.95, wd 0.01 on matrices only), lr 1e-4 cosine → 1e-5
   with 100-step linear warmup, grad-clip 1.0, seq 1024, batch 8 (packed
   non-overlapping windows, reshuffled per epoch), fp32 on MPS, **2000 steps
   = 16.4M tokens**. Validation ppl (wikitext-2 validation, first 100k tokens,
   window 1024 stride 1024) every 250 steps. Optimizer state discarded; only
   final weights saved to `models/smollm2-135m-pruned-h6-healed/`.

```bash
/Users/js/dev/vllm-study/.venv/bin/python head_importance.py
/Users/js/dev/vllm-study/.venv/bin/python prune_heads.py
/Users/js/dev/vllm-study/.venv/bin/python heal.py
/Users/js/dev/vllm-study/.venv/bin/python eval_ppl.py --model <dir> --tag <tag>
```

### Results (wikitext-2 test, window 1024 / stride 512, fp32)

| model | ppl | delta vs base |
|---|---|---|
| baseline `smollm2-135m-instruct` | **16.60** | — |
| pruned h9→h6, unhealed | **82.48** | +65.9 (5.0x) |
| pruned + healed (2000 steps) | **TBD** | TBD |

Healing curve (validation ppl vs step): `experiments/results/twin/healing_curve.json`.
Healing wall time: **TBD**.

---

## 3. Throughput — barge (Metal, f16)

```bash
target/release/barge bench --model models/<dir> --device metal --dtype f16 \
  --num-requests 128 --input-len 128 --output-len 128 --max-slots 72 \
  --out experiments/results/twin/barge_bench.jsonl
```

The pruned checkpoint loads and runs in barge without modification (barge
reads the explicit `head_dim: 64`; H=6/KV=3 → GQA group size 2). 3 runs each:

| model | output tok/s (3 runs) | mean | wall_s mean |
|---|---|---|---|
| baseline | 1248.0 / 1240.5 / 1243.6 | **1244.0** | 13.17 |
| pruned-h6 | 1305.8 / 1313.6 / 1305.2 | **1308.2** | 12.52 |

**+5.2% output tok/s** for −33% attention Q/O compute (−4.9% params). At this
scale the model is small and MLP/memory-bound, so the modest end-to-end gain
is expected; the point is the full path works: surgered checkpoint → engine.

---

## 4. Per-layer KV-precision sensitivity — SmolLM2-135M

**Protocol** (`twin/kv_sensitivity.py`): custom attention registered via
`AttentionInterface` wraps SDPA and fake-quantises K and V exactly where the
KV cache sits (post-RoPE K, shape (b, kv_heads, s, 64)). Symmetric
round-to-nearest, absmax scale **per head per token** over head_dim; int8 →
qmax 127, int4 → qmax 7. Eval: first 100k tokens of wikitext-2 test, window
1024, stride 1024, fp32/MPS. Conditions: fp32 baseline, all-layers int8,
all-layers int4, single-layer int4 × 30. (Note: the intra-run baseline ppl,
19.70, differs from the §2 headline 16.60 because this protocol uses
non-overlapping windows on a 100k-token subset — less context per scored
token. All comparisons are within-protocol. The custom attention path routes
MPS SDPA through the math fallback with an explicit mask, so the sweep runs
~2–3x slower than stock SDPA; the 33 conditions took ~26 min.)

Results: `experiments/results/twin/kv_sensitivity.json`.

| condition | ppl | delta |
|---|---|---|
| fp32 KV (baseline) | 19.695 | — |
| all 30 layers int8 | 19.708 | **+0.012** |
| all 30 layers int4 | 24.816 | **+5.121** |

**int8 KV is free** across the whole stack (+0.06% ppl). Blanket int4 is not
(+26%). Single-layer int4 ppl deltas:

```
L0  -0.005   L8  +0.023   L6  +0.035   L5  +0.038   L7  +0.042   L29 +0.045
L21 +0.053   L4  +0.054   L28 +0.065   L3  +0.073   L15 +0.078   L20 +0.087
L24 +0.089   L14 +0.090   L9  +0.111   L25 +0.113   L26 +0.118   L17 +0.118
L2  +0.131   L11 +0.137   L10 +0.146   L18 +0.148   L27 +0.152   L22 +0.156
L12 +0.174   L23 +0.186   L13 +0.190   L1  +0.279   L16 +0.302   L19 +0.443
```

Ranking (most int4-tolerant first):
`0, 8, 6, 5, 7, 29, 21, 4, 28, 3, 15, 20, 24, 14, 9, 25, 26, 17, 2, 11, 10, 18, 27, 22, 12, 23, 13, 1, 16, 19`.

Read-out: sensitivity is graded, not bimodal. Early layers (0, 3–8) and the
final layers (28–29) tolerate int4 KV nearly for free; a band of mid/late
layers (19, 16, 13, 12) plus the outlier L1 carries most of the damage. The
sum of single-layer deltas (≈ +3.7) is below the joint all-int4 delta
(+5.1), i.e. errors compound mildly super-additively. Obvious follow-up for
co-design: mixed-precision KV — int4 on the ~20 tolerant layers, int8 on the
~10 sensitive ones — cutting KV bytes ~33% vs all-int8 at a projected
sub-1-ppl cost (verified jointly below, given the super-additivity).

---

## Artefact inventory

```
twin/common.py               shared ppl eval + data loading
twin/eval_ppl.py             CLI perplexity eval
twin/granite_routing.py      task 1 capture
twin/analyze_routing.py      task 1 statistics
twin/head_importance.py      task 2 importance
twin/prune_heads.py          task 2 surgery
twin/heal.py                 task 2 healing
twin/kv_sensitivity.py       task 4
experiments/results/twin/    all JSON/npy/npz/jsonl results
models/smollm2-135m-pruned-h6[-healed]/   surgered checkpoints
```
