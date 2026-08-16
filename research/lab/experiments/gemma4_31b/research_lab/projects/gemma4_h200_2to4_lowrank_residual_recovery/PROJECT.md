# Gemma 4 H200 2:4 plus low-rank residual recovery

## Question

Can one exact Gemma 4 projection be represented as an H200-native 2:4 sparse
base plus one low-rank dense residual that materially recovers the pruning
error while retaining a positive complete execution bound versus the current
dense FP8 consumer?

## Why it matters

The locked qualified denominator is `0.625149101968745 s/request` and the
target is `0.500119281574996 s/request`. The prior exact-weight screen found
no natural 2:4 structure and only `86.29–89.09%` energy retention after
magnitude pruning, so an uncorrected sparse proxy is not credible. It also
found a `43.7498%` upper-bound reduction in represented projection bytes,
leaving enough nominal hardware opportunity to test one concrete recovery
method. A low-rank factorization of the *pruning residual*, rather than of the
original dense weight or a width-truncated model, is a materially different
model/chip hypothesis.

## Bound evidence

- `../exact_weight_structure_intervention_screen/WEIGHT_STRUCTURE_SCREEN.json`
- `../gemma4_h200_fp8_2to4_sparse_codesign/STATUS.json`
- `../gemma4_h200_width16384_lowrank_recovery/STATUS.json`
- `../gemma4_h200_mlp_w4_fp8_hybrid/STATUS.json`
- The campaign's locked `0.625149101968745 s/request` denominator and current
  dense dynamic-FP8 H200 path.

The earlier screen closes uncorrected magnitude 2:4 and standalone low-rank
sketches. Do not replay either. This project tests only their coupled
structured-sparse-base plus residual-factor representation.

## Scope

Use `$kernel-research`. Work for at most 90 wall-clock minutes and `$0`.
Select exactly one projection family from the existing architecture-weighted
screen before reading its tensor payload. Derive one maximum admissible
residual rank from a complete H200 physical model that includes:

- the supported sparse base GEMM;
- both dense low-rank factor GEMMs;
- activation/scale production and BF16 output;
- represented weight and metadata bytes;
- intermediate bytes, launches, and required reductions; and
- the strongest current dense FP8 consumer.

Evaluate exactly that rank; do not sweep ranks, tensor families, grouping
axes, kernels, or thresholds. Stream only the selected tensor from the
existing content-addressed checkpoint and do not copy or rehash checkpoint
shards. Construct magnitude 2:4 in the contraction layout, factorize only its
residual, and implement a source-complete representation producer plus a
reference consumer that reaches the BF16 output expected by the current
runtime. Characterize weight reconstruction error and deterministic
exact-shape output error separately, labeling any generated inputs synthetic.

A positive offline result requires both a sharply improved residual error over
the uncorrected sparse base and a positive complete physical bound after the
two correction GEMMs. It remains quality-unsafe until later task evaluation.
Return typed `none` if H200 lacks a maintained exact consumer, the admissible
rank is nonpositive, the correction does not materially recover error, or the
complete bound is nonpositive.

Do not claim a GPU, use SSH or provider APIs, run CUDA or an endpoint, train,
copy model files, inspect a second tensor family, or reopen the consumed
uncorrected 2:4, width-16,384 low-rank, W4, or prior sparse projects.

## Terminal

Persist `SPARSE_LOWRANK_RESIDUAL_OFFLINE_TERMINAL.json` containing:

- all direct input, source, and generated-artifact SHA-256 identities;
- selected projection, exact shape/layout/dtypes/scales, sparse grouping, and
  single derived residual rank;
- producer, sparse consumer, residual consumers, and BF16 ownership contract;
- uncorrected versus corrected reconstruction and output-error evidence;
- useful FLOPs, compulsory bytes, launches, intermediates, and complete
  locked-request bound with evidence labels and uncertainty;
- focused offline correctness checks; and
- one real current-runtime H200 exact-consumer command or typed `none`.

A positive terminal prepares one direct component falsifier for a later spend
decision. It does not reserve spend or authorize provider, GPU, endpoint,
training, or deployability work.
