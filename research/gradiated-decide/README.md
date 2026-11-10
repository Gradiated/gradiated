# Gradiated Decide

Post-training of `perplexity-ai/pplx-decider-v1.2` (Apache-2.0, Qwen3.8-27B backbone with non-causal full
attention and a 255-way readout at each question marker) into **Gradiated Decide**, and its evaluation on the
public Decision Index 0.3.

## Goal and acceptance

Beat the base model on the public Decision Index 0.3 (paired: same harness, same suite rows, same hardware) without
losing general decision ability. The board's ranking now comes from private same-skill and new-domain tests, so a
public-only gain is not enough: every candidate is also checked on held-out dev sets of the training sources that are
not Decision Index benchmarks, and no index area may fall by more than one point.

## Pipeline

1. **Suite.** Rebuild the public suite with the kit (`github.com/apolinario/decision-index`):
   `decision-index suite rebuild --edition 0.3`. HLE is gated on the Hub; without an accepted token it is left out
   and scores 0 for every model compared, as the base model already scores 0 skill on it.
2. **Data.**
   - `gdecide.data.hub_sources`: licence-filtered typed-decision datasets (tasksource procedural typed decisions,
     sn92 generalist and specialists, the commercial-licence rows of tasksource-jev-typed-decisions).
   - `gdecide.data.train_splits`: official train splits of Decision Index benchmarks, rendered with the kit's own
     normalizers so the format matches evaluation exactly, and decontaminated against every suite row (exact match and
     word 13-gram overlap).
   - `gdecide.prepare`: deterministic per-source sampling, option-order shuffling, a held-out dev slice per source,
     one-time tokenization into shards.
3. **Training.** `gdecide.train_full` (FSDP2 full fine-tune, fp32 master weights, soft cross entropy plus Brier) or
   `gdecide.train` (LoRA). Both reproduce the inference forward pass exactly (upstream non-causal mask hook and marker
   readout).
4. **Evaluation.** `gdecide.evaluate` (batched, one process per GPU, kit result format) and `gdecide.score` (the
   kit's scorer, optionally on a fixed sample, with paired deltas against another run).

## Spot VMs

Training runs on Nebius spot VMs from `tools/dev-training/dev_training.py`. `vm/bootstrap.sh` builds the
environment, downloads the pinned base revision and restores from S3; `vm/s3-sync.sh` mirrors finished
`state-*` (sharded model and optimizer, every ~40 minutes), `export-*` (loadable bf16 checkpoints), logs and
evaluation results to `s3://$DEV_TRAINING_S3_BUCKET/gradiated-decide/`. A replacement VM resumes from the newest
complete state.

## Licence

The base checkpoint and Qwen backbone are Apache-2.0. Exported checkpoints keep `LICENSE` and `NOTICE` and add a
`MODIFICATIONS` file. Training data is limited to sources whose licence permits commercial use; each source's licence
is recorded in the data manifests.

Data decisions (mix `v1`):

- Kept: procedural typed decisions (Apache-2.0); sn92 generalist and specialists (CC-BY-4.0) without rows written by
  OpenAI, Anthropic, Google, unknown or mixed authors, whose terms restrict training competing models; tasksource-jev
  rows marked `license_use == "commercial"`; train splits of API-Bank, BANKING77, CLINC150, SGD, ARC, WinoGrande,
  HellaSwag, GSM8K, ChessBench, Amazon ESCI, HoVer, When2Call and New Yorker.
- Excluded for licence: ANLI (CC BY-NC), MMLU auxiliary_train (includes research-only RACE), RAGTruth (MS MARCO and
  Yelp contexts), and splits with terms-only or unstated licences (ContractNLI, NLI4CT, Humicroedit, VAST, ACOS,
  iSarcasmEval, ToolRet-train).
- Decontamination: hub sources go through `gdecide.decontam` against the suite and the kit's full normalized test
  pools. Train splits use `gdecide.data.train_splits`' per-benchmark check on item fields (FEN for ChessBench, the
  question for GSM8K), because the generic 13-gram test treats shared option lists (legal moves, label sets) as
  overlap and removed almost every ChessBench and GSM8K row.

## Baseline

`perplexity-ai/pplx-decider-v1.2` at the pinned revision, joint requests, reference path, 8x B200: public index
68.04 on the 0.3 panel (HLE unavailable, scored 0 as on the board), against the model card's 68.09; 67.22 on the
11,025-request dev sample (`sample-ids.json`, 250 case groups per benchmark).
