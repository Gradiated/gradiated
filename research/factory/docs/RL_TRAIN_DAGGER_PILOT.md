# RL training and correction pilot: morning result

Measured on 2026-11-03; source revision `e84c49235`. This is a terminal
negative/uncertain result, not a model promotion. SFT improved the primary pass
count by one task; neither privileged-context OPD variant improved over fresh
base Qwen. No further training or selection used the final scores.

## Fresh paired evaluation

The frozen holdout contains 24 task instances across 12 workflows, two worlds,
and one fictional reporting-product archetype. Each arm ran once on every task
with the same harness and sampling settings. Primary judging used Sol v3i;
Terra rejudged the same traces without additional model rollouts.

| Arm | Primary passes | Secondary passes | Primary mean score / 10 |
| --- | ---: | ---: | ---: |
| Fresh Qwen base | 8/24 (33.3%) | 6/24 | 5.925 |
| SFT | 9/24 (37.5%) | 8/24 | 6.138 |
| Procedural-context OPD | 4/24 (16.7%) | 4/24 | 5.779 |
| Contract-context OPD | 5/24 (20.8%) | 5/24 | 5.479 |

Against fresh base, SFT gained two passes and lost one: +4.2 percentage points.
Its workflow-cluster bootstrap 95% interval is [-8.3, +16.7] points. Procedural
OPD gained one and lost five: -16.7 points, interval [-29.2, -4.2]. Contract OPD
gained two and lost five: -12.5 points, interval [-29.2, +4.2]. These are small,
single-sample estimates with only 12 workflow clusters and two worlds; the
intervals do not capture all sources of uncertainty.

All 96 rollouts completed with status `ok`; all 96 recorded clean environment
restoration. A pass requires score >=7.5, zero materially wrong final claims,
and zero materially unsupported final claims. It is not merely successful
execution. Primary/secondary pass agreement was 22/24 for base, 23/24 for SFT,
24/24 for procedural OPD, and 24/24 for contract OPD: 93/96 overall. Mean
absolute score differences were 0.404, 0.392, 0.638, and 0.333 respectively.
Model agreement is not human validation.

Opus was **not measured**: the approved native `claude-opus-5-5` subscription
probe returned 429 with a cooldown beyond the morning deadline. There was no
paid fallback or substitution of another model under the Opus label.

## Training data and method

SFT used 313 verified source trajectories representing 147 canonical tasks
across all 12 workflows. The fixed 600-row training selection contains 294,739
completion tokens and 29,222,117 input-plus-target tokens. Every trajectory
contributes its first recorded root call; deterministic late/middle calls fill
the remaining budget. These are complete selected calls, not every call from
every trajectory. No selected sequence was truncated; maximum length was
125,851 tokens. Correction guidance was removed from student inputs and
guidance leakage, served-token alignment, repetition, duplicate traces, and
environment restoration were checked before the clean-data freeze.

This is DAgger-style fault-guided retry and hint-free SFT. It does not label an
expert action at every student-visited state, and this overnight comparison is
one update from base, not repeated DAgger iterations.

The paired OPD datasets use 59 fresh base-student rollouts on 34 training tasks,
out of 96 planned rollouts under a fixed collection cutoff. They contain 318
complete selected root-call rows and 173,136 completion tokens per variant
(17,295,994 input-plus-target tokens). Four rollouts passed and 55 did not;
row selection did not filter on success. There were no incomplete scored rows
within the selected paired intersection. Sampling metadata confirmed T=1,
top_p=1, top_k=-1, min_p=0, and repetition penalty=1 for all 1,106 recorded
requests. Student tokens and sampler logprobs are identical between variants.

Both teachers are the **same frozen local base Qwen**, given extra context:
procedural guidance in one arm and the verified training contract/reference
evidence in the other. Neither is a stronger external-model teacher. Teacher
context is absent from learner inputs. Full prompt-token logprob scoring was
checked for finite, aligned values; clean-prefix replay mean absolute logprob
difference was 0.0091. The objective uses sampled-token advantages
`clip(teacher_logprob - student_sampler_logprob, -2, 2)` with the existing
clipped policy update. It does not store or distill the entire vocabulary
distribution. These are exploratory privileged-context OPD variants.

Each arm independently started from the same base with LoRA rank 16,
learning rate 5e-5, one epoch, 24 minibatches, maximum length 131,072, and seed
0. All 24 steps completed with finite loss and gradient norm. Training times
were approximately 54 minutes for SFT and 34 minutes for each OPD arm on four
existing GPUs. Checkpoint choice was fixed-budget completion/latest finite
checkpoint, never final-holdout score. SFT and OPD have different training
distributions and token budgets, so this is not a controlled estimate of the
algorithm alone.

## Quality and scope limits

The generator is a hand-designed synthetic reporting product, not a fitted
distribution of production worlds. Train-only anonymized requests informed
authoring style/intent; they did not supply teacher answers. The curriculum
contains repeated workflow variants, not one distinct skill per instance.
An earlier 151-instance semantic review rated 66 as cosmetic near-clones;
additional operation scopes and retention quotas reduced repetition but do
not establish broad real-world coverage.

Earlier source lineages failed independent quality checks and were excluded
before training. The current source separates first-touch acquisition from
visit attribution. Three AI-correlation audit negatives were explicitly
adjudicated with independent schema-aware review and correct-key live SQL;
the original negative records remain preserved. The fixed final holdout uses
the older attribution recipe with known realism limitations. It was preserved
rather than rewritten after earlier scores, and kept out of all training,
correction guidance, teacher contexts, and checkpoint selection.

The heldout task SHA256 is
`23a07a82b838dec80b7f427d18240b05d21fcbeb10d38babb523a22617fc1ff4`.
The preregistered evaluation binds the harness, data, raw-world/proof hashes,
and each adapter before scoring. Adapter arms use an isolated launcher;
canonical base execution and shared model registration were not rewritten.

## Artifacts and terminal state

Raw tasks, prompts, trajectories, teacher contexts, token data, and adapters
remain on fbf8. The host root is
`/opt/posthog-sft/env-research/rl_train_dagger_v1/train_v3/morning_study_v1`.
Authoritative artifacts are `MORNING_RESULTS.json`, `evaluation/protocol.json`,
`evaluation/judge_agreement.json`, `data/SFT_FROZEN.json`, `data/OPD_READY.json`,
the three arm `protocol.json`/`SELECTED.json`/`READY.json` files, and
`CLEANUP.json`. This repository report contains derived aggregate results only.

All owned campaign work was inspected and stopped at the terminal result.
Both user-resident TP4 inference services and their gateway were restored and
health-checked; reservations and shared SSH were preserved. The recurring
schedule **RL training set and DAgger pilot** is disabled with no next run.
Do not restart from stale collection callbacks. No adapter was promoted.

The supported conclusion is a small, uncertain SFT improvement and negative
results for these two OPD configurations. A stronger teacher, better coverage
of complete decision chains, additional independently designed worlds, or
iterative student recollection remain hypotheses for a future development
experiment, not explanations established by this final test.
