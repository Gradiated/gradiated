# decide-1: facts for the post

Every number here is measured by us unless marked **vendor-reported**. S3 paths are relative to
`s3://$DEV_TRAINING_S3_BUCKET/gradiated-decide/`. `data.json` (built by `collect_data.py`) holds the raw series; the
charts are drawn from it by `make_charts.py`.

## What decide-1 is

- **decide-1 = 0.5 × gd-kl2 + 0.5 × KnowLine-31B-Gen1.5**, a linear interpolation of the weights (`gdecide.merge`),
  stored at `runs/merges/gd-kl2-s1000-a0.5/` (12 safetensors shards, about 62.5 GB bf16).
- Lineage: `PelaAI/KnowLine-31B-Gen1.5` (Apache-2.0; a LoRA fine-tune of `google/gemma-4-31B-it`, Apache-2.0;
  pinned revision `56ca884a`, weights byte-identical to the earlier pin `8e56aa1b`) → **gd-kl1** (full fine-tune,
  `runs/gd-kl1/`) → **gd-kl2** (gd-kl1's export-1155 trained further, `runs/gd-kl2/`) → blended 50/50 with KnowLine.
  So decide-1 carries half of KnowLine's weights plus half of a model that saw both fine-tuning stages.
- Same architecture, tokenizer and serving front end as KnowLine (release `knowline_server.py` + SGLang, label-token
  softmax, `temperatures.json`). The merged directory currently still contains KnowLine's README/README.zh/INFERENCE.md;
  a decide-1 model card has to replace them before any upload. `MODIFICATIONS` is present.
- Parameters: 29,288,059,136 trainable in the training model (train log `model` event; the language model with the
  readout; vision tower frozen/unused) — the release is the ~31B Gemma-4 dense checkpoint.

## Training recipe (both stages)

| | gd-kl1 | gd-kl2 |
|---|---|---|
| Start checkpoint | KnowLine-31B-Gen1.5 | gd-kl1 export-1155 |
| Data mix | `mixes/v1-knowline.json` → `data/v1-knowline` | `mixes/kl2-targeted.json` → `data/kl2` |
| Train rows / dev rows | 952,252 / 9,620 | 562,689 / 5,587 |
| Real tokens in the mix (sum of sequence lengths) | 1,061,637,093 | 724,971,742 |
| Sequence length p50 / p90 / p99 / max | 865 / 2,287 / 3,559 / 8,163 | 969 / 2,627 / 5,297 / 8,192 |
| Rows dropped (too long / no target) | 429 / 380 | 1,149 / 1,136 |
| Steps run / steps per epoch | 1,155 / 4,622 | 1,000 / 2,848 |
| Fraction of an epoch | 0.25 (`--epochs 0.25`) | 0.351 (`--epochs 1 --max-steps 1000`) |
| Token budget per step (8 ranks × 32,768, packed) | 262,144 | 262,144 |
| Real tokens per step (mix tokens / steps per epoch) | ~229.7k | ~254.6k |
| **Real tokens trained on** | **~265M** | **~255M** |
| Examples trained on | ~238k | ~198k |
| LR (body) / readout LR | 3e-6 / 1e-5, cosine to 10%, 30 warmup steps | 2e-6 / 1e-5, cosine to 10%, 30 warmup steps |
| Loss | soft CE on the option distribution + 0.5 × Brier | same |
| Weight decay / KL anchor | 0 / none | 0 / none |
| Seed | 20261112 | 20261113 |
| Hardware | 8× B200 (Nebius spot, me-west1, `gpu-b200-sxm-a`) | 8× B300 (Nebius spot, eu-west2, `gpu-b300-sxm`) |
| Precision / sharding | FSDP2, fp32 master weights, bf16 compute, activation checkpointing | same + `--balance --attn gd_fast --keep-activations 8` |
| Median step time | 20.2 s | 11.7 s |
| Real tokens/s (node) at median step | ~11.4k | ~21.8k (log `recent_tokens_per_s` median 21,367) |
| Active training time (log intervals < 30 min) | 8.85 h → **70.8 GPU-hours** | 3.76 h → **30.0 GPU-hours** |
| Wall clock first start → finish | 12.45 h | 5.88 h |
| Process starts / resumes from a saved state | 6 / at steps 437, 614 | 5 / at 152 (×3), 352 |

Sources: `runs/<run>/args.json`, `runs/<run>/train.log.jsonl` (`data`, `train`, `resumed`, `finished` events),
`data/<mix>/manifest.json`; hardware from the watchdog logs (`.agents/runtime/gdecide/watchdog-gdecide-2.log` for
gd-kl1, `watchdog-gdecide-4.log` for gd-kl2). Real-token counts are derived (mix tokens × steps / steps per epoch);
the logs record node tokens/s, not a running total. GPU-hours count training intervals only, not model loading,
dev evaluation, preemption downtime or the post-training evals.

**Totals for decide-1's fine-tuned half:** ~520M real tokens, 2,155 optimizer steps, ~436k examples, ~101 GPU-hours of
training (≈71 on B200 + 30 on B300). Not counted: the evaluation runs, the throughput bench, failed pilots (gd-v1/gd-v2
on the Qwen line, the v3 and probe pilots).

### Throughput work (gd-kl2)

Measured on 8× B300 with the gd-kl2 data (`logs/bench-gemma.tsv`, `vm/bench-train.sh`):

| Config | Real tokens/s | Peak memory/GPU |
|---|---|---|
| gd-kl1's setup (baseline, recorded in `vm/bench-train.sh`) | 9,284 | — |
| + 8 layers without activation checkpointing | 9,562 | — |
| `--balance` (global length-sorted batches) + `gd_fast` attention | 20,349 | 116.7 GiB |
| + keep activations of 8 layers (used) | 21,444 | 218.5 GiB |
| + 16 layers | OOM | — |

The profiler showed ~57% of GPU time inside the FSDP reduce-scatter: not slow NCCL (2 GiB fp32 in 2.9 ms) but ranks
waiting for the rank that drew the longest sequences. Global length-balanced batches plus flex attention for Gemma 4's
1,024-token sliding-window layers (SDPA causal for the global layers) gave 2.2–2.3×. Async checkpointing to RAM (16
writer threads) cut the training pause per 335 GB state from ~13.5 min to ~53 s. (Bench numbers: measured; the 57%
figure and NCCL timing: measured in this session's profiling, `OUT/profile.txt` on the VM, not uploaded.)

## Data

gd-kl1 mix (`data/v1-knowline/manifest.json`, rows per source): tasksource procedural-typed-decisions 386,545;
tasksource-jev-typed-decisions (commercial-licence rows only) 284,955; Decision Index train splits — ChessBench 29,700,
Amazon ESCI 29,700, HellaSwag 24,750, WinoGrande 24,750, CLINC150+OOS 18,015, HoVer 15,785, GSM8K 14,789,
New Yorker 10,220, SGD 9,900, BANKING77 9,866, When2Call 8,783, API-Bank 3,132, ARC-Easy 2,783, ARC-Challenge 1,398;
sn92 generalist 25,921 and 20 sn92 specialist sets (~1.9k–5.9k each).

gd-kl2 mix (`data/kl2/manifest.json`): aimed at gd-kl1's measured misses (JevBench temporal_numeric / long_policy /
judge_hard, Home appliance simulator, ContractNLI, BANKING77, iSarcasmEval, ESCI, Habermas Machine, CLadder) with about
a sixth replay of the v1 sources. Largest sources: HelpSteer2 70,670; procedural-typed-decisions 64,441; jev-typed
52,045; Amazon ESCI 29,700; DROP 29,700; TempReason 27,499; TimeQA 25,721; sn92 generalist 25,921; ShARC 21,672;
MASSIVE ar-SA 17,350; MAUD 15,977; OASST2 14,850; Stack Exchange preferences 14,845; GSM8K 14,789; MultiWOZ 2.2 13,785;
TAT-QA 13,096; HelpSteer3 12,479; LexGLUE LEDGAR 10,200 / CaseHOLD 8,601 / UNFAIR-ToS 7,992; FinQA 10,062; BANKING77
9,866; CUAD 8,110; CondaQA 5,646; sarcasm headlines 3,960; ConvFinQA 2,984; claim stance 1,028; sn92 specialists.

Licences (from `gdecide/data/broad_sources.py`, `extra_sources.py`, README "Licence"): TAT-QA CC-BY-4.0; FinQA,
ConvFinQA, MultiWOZ MIT; DROP, Stack Exchange prefs CC-BY-SA-4.0; TimeQA BSD-3; TempReason, ShARC, claim stance
CC-BY-SA-3.0; CUAD, MAUD, LexGLUE, HelpSteer2/3, MASSIVE, sarcasm headlines CC-BY-4.0; OASST2, CondaQA Apache-2.0;
procedural typed decisions Apache-2.0; sn92 CC-BY-4.0 minus rows written by OpenAI/Anthropic/Google/unknown/mixed
authors; tasksource-jev only `license_use == "commercial"` rows. HelpSteer2/3 multi-turn contexts written by
GPT/Claude/Gemini are filtered out row by row. Excluded for licence: ANLI, MMLU aux, RAGTruth, ContractNLI, NLI4CT,
Humicroedit, VAST, ACOS, iSarcasmEval, ToolRet train splits (terms-only/NC/unstated). **Several sources are
CC-BY-SA**; whether share-alike reaches model weights is unsettled — worth a line in the model card and a decision
before publishing weights.

Decontamination: every hub/broad/extra source goes through `gdecide.decontam` (exact match + word 13-gram overlap)
against the Decision Index 0.3 suite rows, the kit's full normalized test pools and, for gd-kl2, the JevBench public
and Gemini-panel items (`suite/extra-items.jsonl`); Decision Index train splits use a per-benchmark item-field check
(`gdecide.data.train_splits`). The extra sources lost 1 row (claim stance, 13-gram) — `logs/decontam-extra.log`.
We train on the ESCI, When2Call and New Yorker **train** splits, which the Gemini panel scores on their test rows.

## Loss over training

Training loss is the soft CE on the answer-option distribution (+ Brier), averaged over each 10-step logging window
(`train.log.jsonl`). It is noisy because each window mixes sources of very different difficulty.

| | first 10 windows (mean) | last 10 windows (mean) |
|---|---|---|
| gd-kl1 CE / Brier | 0.445 / 0.165 | 0.384 / 0.139 |
| gd-kl2 CE / Brier | 0.438 / 0.211 | 0.420 / 0.192 |

Held-out dev (1% of each mix, never trained on; different sets per run, so not comparable across runs):

| Run · step | dev accuracy | dev CE |
|---|---|---|
| gd-kl1 · 0 (= KnowLine) | 85.87% | 0.4742 |
| gd-kl1 · 400 | 88.87% | 0.3706 |
| gd-kl1 · 800 | 90.18% | 0.3297 |
| gd-kl1 · 1155 | 90.53% | 0.3163 |
| gd-kl2 · 0 (= gd-kl1) | 82.23% | 0.5007 |
| gd-kl2 · 250 | 83.93% | 0.4481 |
| gd-kl2 · 500 | 84.52% | 0.4250 |
| gd-kl2 · 750 | 84.55% | 0.4114 |
| gd-kl2 · 1000 | 84.93% | 0.4038 |

Notable per-source dev moves, gd-kl2 step 0 → 1000 (accuracy points, n): MAUD +13.0 (161), MultiWOZ +12.9 (140), ShARC
+6.4 (218), MASSIVE ar-SA +5.9 (170), TempReason +5.7 (281); dips mid-run at step 250 on GSM8K (94.6 → 91.3), CUAD
(90.3 → 87.1) recovered by step 500 (94.0, 91.9); LEDGAR ended ~1 point down. gd-kl1 step 0 → 1155: jev-typed
decisions +6.4 (2,843), New Yorker +6.8 (103), ChessBench −2.7 (300). (Small sn92 specialist sets swing ±20 points on
8–55 items; ignore them.)

## Blend sweep (Decision Index dev sample, 11,025 requests, `runs/evals/<name>-sample/gdecide-score.json`)

| Share of fine-tune | gd-kl1 | gd-kl2 |
|---|---|---|
| 0% (KnowLine alone, `knowline-sgl-sample`) | 69.83 | 69.83 |
| 50% | **70.59** | **70.49** |
| 70% | 69.97 | 69.77 |
| 100% (fine-tune alone) | 69.87 | 68.60 |

The fine-tunes alone are no better than KnowLine on the index (gd-kl2 alone is 1.2 worse) even though they gain several
points on their own dev sets; the 50/50 weight blend is what gains. Same pattern on the Qwen line (gd-v1: best blend
0.4–0.5).

### Decision Index 0.3 public panel (measured, our harness, same rows)

| Model | Index | knowledge | language | retrieval | tools | arts | source |
|---|---|---|---|---|---|---|---|
| pplx-decider-v1.2 (base of gd-v1) | 68.04 | 56.2 | 72.8 | 68.4 | 84.3 | 56.0 | `runs/evals/base-panel/gdecide-score.json` |
| gd-v1 0.5 blend (Qwen line) | 68.91 | 57.5 | 72.6 | 70.8 | 84.6 | 56.4 | `runs/evals/gd-v1-s1652-a0.5-panel/gdecide-score.json` |
| KnowLine-31B-Gen1.5 | 70.54 | 59.6 | 72.8 | 73.2 | 85.4 | 60.7 | `runs/evals/knowline-sgl-panel/gdecide-score.json` |
| gd-kl1 0.5 blend | 71.08 | 60.4 | 72.7 | 75.2 | 85.3 | 60.3 | `runs/evals/gd-kl1-s1155-a0.5-panel/gdecide-score.json` |
| **decide-1** (gd-kl2 0.5 blend) | 71.34 | 60.3 | 73.8 | 75.8 | 84.5 | 60.8 | `runs/evals/gd-kl2-s1000-a0.5-panel/gdecide-score.json` |
| ensemble KnowLine + gd-v1 (50/50, two models) | 71.93 | 61.4 | 74.6 | 74.5 | 85.8 | 61.6 | `runs/evals/ens-knowline-sgl+gd-v1-s1652-a0.5-w0.5-panel/gdecide-score.json` |
| ensemble three-way (local, gd-kl1 + gd-v1 + KnowLine) | 72.32 | 61.9 | 74.6 | 76.1 | 85.4 | 62.0 | `.agents/runtime/gdecide/ens/e-3way/gdecide-score.json` |

### Per benchmark, decide-1 vs KnowLine (skill x100; sorted by change)

| Benchmark | KnowLine | gd-kl1 0.5 | decide-1 | change |
|---|---|---|---|---|
| iSarcasmEval | 59.6 | 62.0 | 66.4 | +6.81 |
| BANKING77 | 82.6 | 87.7 | 89.4 | +6.79 |
| GPQA Diamond | 40.1 | 44.2 | 45.6 | +5.44 |
| HoVer claim verification | 71.5 | 74.7 | 75.2 | +3.70 |
| Amazon ESCI | 51.1 | 53.1 | 54.2 | +3.11 |
| New Yorker caption matching | 81.3 | 84.4 | 84.4 | +3.08 |
| FinEntity | 89.6 | 91.8 | 92.1 | +2.56 |
| CLINC150+OOS | 93.2 | 95.3 | 95.6 | +2.43 |
| RAGTruth response-level hallucination | 63.9 | 65.1 | 66.1 | +2.22 |
| BBH fixed-option tasks | 82.3 | 83.4 | 83.7 | +1.45 |
| BPoMP | 95.0 | 96.3 | 96.2 | +1.18 |
| CLadder | 78.6 | 79.2 | 79.6 | +1.00 |
| ANLI | 70.4 | 69.7 | 71.2 | +0.87 |
| HellaSwag | 95.0 | 95.9 | 95.9 | +0.87 |
| WinoGrande | 88.3 | 89.9 | 89.1 | +0.78 |
| GSM8K | 91.0 | 91.4 | 91.6 | +0.65 |
| BFCL | 96.9 | 97.0 | 97.3 | +0.40 |
| ChessBench | 25.4 | 25.8 | 25.8 | +0.37 |
| Habermas Machine | 35.1 | 32.3 | 35.5 | +0.35 |
| SATA-Bench | 38.4 | 40.1 | 38.7 | +0.32 |
| When2Call MCQ | 88.2 | 88.9 | 88.3 | +0.11 |
| ToolRet | 67.6 | 67.9 | 67.7 | +0.05 |
| HLE | 0.0 | 0.0 | 0.0 | +0.00 |
| ContractNLI | 70.6 | 68.0 | 70.4 | -0.16 |
| PhishNChips phishing decisions | 95.8 | 95.4 | 95.4 | -0.40 |
| MMLU-Pro | 73.6 | 73.7 | 73.2 | -0.42 |
| BRIGHT | 44.7 | 44.7 | 44.3 | -0.47 |
| CRUXEval | 88.9 | 88.3 | 88.3 | -0.56 |
| API-Bank | 89.2 | 88.8 | 88.6 | -0.61 |
| VAST | 72.9 | 72.3 | 72.1 | -0.85 |
| Humicroedit | 38.9 | 37.4 | 37.6 | -1.29 |
| ACOS | 53.1 | 52.2 | 51.8 | -1.31 |
| POP909-CL | 73.7 | 72.0 | 72.2 | -1.48 |
| cfcolor | 40.3 | 39.2 | 38.7 | -1.57 |
| MuSR | 51.2 | 50.3 | 49.3 | -1.89 |
| NLI4CT | 76.1 | 73.5 | 73.9 | -2.20 |
| Home appliance simulator | 81.8 | 80.7 | 77.3 | -4.55 |

### Gemini Decision 1 launch panel (measured by us unless marked vendor-reported)

| Benchmark | pplx-decider-v1.2 | gd-v1 0.5 | KnowLine (SGLang release serving) | gd-kl1 0.5 | **decide-1** | mammoth-1 (Baseten, measured by us) | Gemini Decision 1 (vendor) | Jev 1.14 (vendor) |
|---|---|---|---|---|---|---|---|---|
| JevBench | 89.18 | 90.04 | 90.91 | 90.48 | 91.34 | 93.94 | 92.2 | 90.0 |
| Amazon ESCI (macro-F1) | 62.45 | 64.64 | 61.02 | 62.61 | 63.50 | 64.52 | 58.7 | 56.7 |
| New Yorker | 78.79 | 81.44 | 85.04 | 87.50 | 87.50 | 87.12 | 79.7 | 72.0 |
| PubMedQA | 80.20 | 81.20 | 82.10 | 81.40 | 81.20 | 81.50 | 79.8 | 78.2 |
| Global-MMLU-Lite | 79.69 | 79.83 | 84.03 | 84.16 | 84.20 | 84.47 | 86.0 | 85.0 |
| When2Call | 90.33 | 92.06 | 91.13 | 91.65 | 91.21 | 91.65 | 79.9 | 82.0 |
| Top-1 ECE, mean of six | 0.0454 | 0.0395 | 0.0360 | 0.0373 | 0.0309 | 0.0381 | 0.025 (7 evals) | 0.049 (7 evals) |

Per-benchmark top-1 ECE, decide-1 vs KnowLine: JevBench 0.0358 → 0.0479, Amazon ESCI 0.0480 → 0.0330, New Yorker 0.0365 → 0.0317, PubMedQA 0.0343 → 0.0170, Global-MMLU-Lite 0.0166 → 0.0225, When2Call 0.0446 → 0.0333

Sources: `runs/external/<name>/external-score.json`; vendor columns from `research/gradiated-decide/README.md` (Google's table, 2026-11-11).

## Context: other decision models (vendor-reported / board)

From KnowLine-31B-Gen1.5's model card (`.agents/runtime/gdecide/knowline-src/README.md`), board data of 2026-10-29,
**vendor-reported**: DI 0.3 public / DI 0.4.1 full — mammoth-1 75.34 / 68.44; Jeffan-31b-1710 73.13 / 69.75;
StartLux-Decision v1.1 72.88 / 67.92; Fastino GLiDE V1.2 71.99 / 71.52; Sieve 31B v3 71.68 / 71.10; vLLM-SR d3-ultra
71.57 / 70.18; KnowLine-35B-A3B-Gen1.5 70.72 / 65.77; KnowLine-31B-Gen1.5 70.50 (self-run) / not scored; KnowLine-31B-
Gen1 70.13 / 71.86; WeMM-JEV-27B 69.37 / 68.49; Perplexity Decider v1.2 67.74 / 67.98 (its card: 68.09; we measured
68.04); H2O Lightning 67.75 / 68.64; Turion Jev 31B 66.16 / 70.47; Jev 1.14 60.70 / 60.24. The board now ranks on DI
0.4.1 (60% private same-skill + 40% private new-domain tasks); **we have no DI 0.4.1 score for decide-1** and the public
0.3 suite "no longer counts" on the board.

## Caveats to keep in the post

- decide-1's DI 0.3 public index (71.34) is below several board entries on the same public suite (mammoth-1 75.34,
  Jeffan 73.13, StartLux 72.88, GLiDE 71.99, Sieve 71.68, vLLM-SR 71.57). The honest claim is "+0.80 over its base
  KnowLine-31B-Gen1.5 on the same harness", not a leaderboard position.
- mammoth-1 (measured by us) beats decide-1 on JevBench (93.94 vs 91.34), ESCI, PubMedQA, Global-MMLU-Lite and
  When2Call; decide-1 is ahead on New Yorker (87.50 vs 87.12) and calibration (mean ECE 0.031 vs 0.038).
- JevBench: 91.34 vs KnowLine 90.91 is 1 item of 231; JevBench ECE got worse (0.036 → 0.048). Mean ECE improves
  because of ESCI, PubMedQA, New Yorker and When2Call.
- Gemini Decision 1 comparison is indicative only: Google did not publish prompts/subsets/harness, its ECE pools seven
  evals, and its column is vendor-reported. We train on ESCI/When2Call/New Yorker train splits; Google's training data
  is unknown.
- Several DI gains are on benchmarks whose train split is in our mix (BANKING77, ESCI, New Yorker, CLINC150, HoVer);
  iSarcasmEval (+6.8) has no train split in the mix but sarcasm-headlines data is. GPQA Diamond +5.4 is on 198 items and Home appliance simulator −4.5 on 160 (suite manifest), so both are within noise; iSarcasmEval (4,600) and BANKING77 (3,080) are not.
  Losses concentrate where we have no licence-clean data (Home appliance simulator −4.5, NLI4CT −2.2, MuSR −1.9,
  cfcolor, POP909, ACOS, Humicroedit).
- The README "KnowLine" column of the Gemini panel table (JevBench 90.48 etc.) is KnowLine through the transformers
  backend (`runs/external/knowline`); through its release SGLang serving it scores 90.91 (`runs/external/knowline-sgl`).
  gd-kl1 0.5 also scores 90.48 — a coincidence of 1 item, not a copy.
- Everything is single-seed; no confidence intervals were computed. DI dev-sample vs full-panel differences of a few
  tenths are within run-to-run noise of blending choices.
