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
3. **Training.** `gdecide.train_full` (FSDP2 full fine-tune, fp32 master weights, soft cross entropy plus Brier,
   optionally plus `--anchor` times KL(base || model) to a frozen bf16 copy of the base on the same inputs) or
   `gdecide.train` (LoRA). Both reproduce the inference forward pass exactly (upstream non-causal mask hook and marker
   readout).
4. **Evaluation.** `gdecide.evaluate` (batched, one process per GPU, kit result format) and `gdecide.score` (the
   kit's scorer, optionally on a fixed sample, with paired deltas against another run).

## KnowLine and ensembles

`gdecide.evaluate --backend knowline` runs `PelaAI/KnowLine-31B-Gen1.5` (Gemma-4-31B, Apache-2.0, pinned revision
`8e56aa1b`) with the prompts of its own release front end (`knowline_server.py` / `knowline_layout.py` from the model
repo: read twice up to 3,000 tokens, the question header for longer requests, label-token softmax, score questions at
`temperatures.json`), batched on one GPU per rank in transformers instead of one SGLang prefill per question.
`gdecide.ensemble` averages the per-option probabilities of several runs (REAX 1.3's 50/50 rule by default, `--mode
log` for log-linear pooling; rows a run did not answer come from the others) into a run directory that
`gdecide.score` scores as usual. `vm/run-ensemble-eval.sh` downloads KnowLine, evaluates it and scores its ensembles
with a Gradiated Decide run and with the base. `--family gemma` in `gdecide.prepare` and `gdecide.train_full` prepares
data with KnowLine's prompts and fine-tunes KnowLine with its label readout (not yet run on GPUs).

## Spot VMs

Training runs on Nebius spot VMs from `tools/dev-training/dev_training.py`. `vm/bootstrap.sh` builds the
environment, downloads the pinned base revision and restores from S3; `vm/s3-sync.sh` mirrors finished
`state-*` (sharded model and optimizer, every `--state-minutes`), `export-*` (loadable bf16 checkpoints), logs and
evaluation results to `s3://$DEV_TRAINING_S3_BUCKET/gradiated-decide/`. A replacement VM resumes from the newest
complete state. `vm/campaign.sh RUN DATA "ALPHAS" [train args]` runs bootstrap, training and the merge sweep
(`vm/after-train.sh`) unattended, and can simply be restarted on a replacement VM.

`vm/watchdog.sh NAME DONE_MARKER 'JOB'` runs on the workstation and keeps one job alive across preemptions: it
restarts a stopped VM on its own disk, moves the job to a new VM in another region when that fails, relaunches a job
that died (up to three times), and stops the VM once the job finishes. `s3-sync.sh` uploads results and logs every
5 minutes, including unfinished evaluation shards, so `run-eval.sh` and `run-external.sh` resume on a replacement VM.
Training states (280 GB for the Qwen decider) upload only once complete.

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

## Result: gd-v1

Full fine-tune on mix `v1` (617k rows, 341M tokens, one epoch, 1,652 steps of 262k padded tokens, lr 3e-6 cosine to
10%, readout lr 1e-5, CE + 0.5 Brier) on 8x B200, about 5 hours of training. The final export is then interpolated
with the base (`gdecide.merge`); 0.5 x fine-tuned + 0.5 x base is the candidate.

| Checkpoint | Dev sample | Full panel |
|---|---|---|
| pplx-decider-v1.2 (base) | 67.22 | 68.04 |
| gd-v1 step 400, unmerged | 66.56 | |
| gd-v1 final, unmerged | 67.34 | |
| gd-v1 final, 0.7 / 0.5 / 0.4 / 0.3 with base | 67.77 / 68.00 / 68.08 / 67.97 | 68.91 (0.5) |

The 0.5 merge gains on HoVer, ChessBench, CRUXEval, BANKING77, New Yorker, ESCI, When2Call, PhishNChips and GPQA
and loses up to 2.8 skill points on ACOS, cfcolor, RAGTruth and Home appliances, benchmarks with no licence-clean
training data; no area falls by more than 0.2 points. Unmerged, the fine-tune drifts on those benchmarks, which is why
the merge helps. The public index is the only score measured here; the board's private same-skill and new-domain
tests are not available to us.

Artifacts are in `s3://gradiated-dev-training-873716897517/gradiated-decide/`: `runs/gd-v1/` (exports, last training
state, log; rebuild the 0.5 blend with `gdecide.merge` from `export-1652`), `runs/evals/` (scores and results).

## Result: gd-v2 (KL anchor)

gd-v1's recipe and data plus `--anchor 1.0` (KL to the frozen base). The anchor kept the unmerged model closer to the
base (dev 67.33 unmerged, 67.81 at 0.7, 67.80 at 0.5) but the best blend scored 68.65 on the full panel, 0.26 below
gd-v1. gd-v1 stays the Qwen candidate.

## Result: KnowLine ensembles (dev sample)

| Model | Dev sample |
|---|---|
| pplx-decider-v1.2 (base) | 67.22 |
| gd-v1 0.5 | 68.00 |
| KnowLine-31B-Gen1.5 | 69.76 |
| 50/50 KnowLine + base | 70.69 |
| 50/50 KnowLine + gd-v1 0.5 | 71.12 |

## Gemini Decision 1 launch panel

`gdecide.external` runs the text benchmarks of Google's Gemini Decision 1 table (2026-11-11) and reports top-1
accuracy (ESCI: macro-F1) and top-1 ECE, counting unanswered requests as wrong: JevBench public (Benchmark Heaven,
231 decisions), PubMedQA (pqa_labeled), Global-MMLU-Lite (non-English test), and our Decision Index rows for Amazon
ESCI, When2Call and New Yorker (text descriptions). Google did not publish prompts, subsets or harness and its ECE
pools seven evals, so the comparison is indicative. We train on the ESCI and When2Call train splits.

| Benchmark | Base | gd-v1 0.5 | KnowLine | KnowLine + gd-v1 | Gemini Decision 1 | Jev 1.14 |
|---|---|---|---|---|---|---|
| JevBench public | 89.18 | 90.04 | 90.48 | 92.21 | 92.2 | 90.0 |
| Amazon ESCI (macro-F1) | 62.45 | 64.64 | 60.95 | 63.38 | 58.7 | 56.7 |
| New Yorker | 78.79 | 81.44 | 84.66 | 86.17 | 79.7 | 72.0 |
| PubMedQA | 80.20 | 81.20 | 82.20 | 81.90 | 79.8 | 78.2 |
| Global-MMLU-Lite | 79.69 | 79.83 | 84.05 | 84.94 | 86.0 | 85.0 |
| When2Call | 90.33 | 92.06 | 91.13 | 91.84 | 79.9 | 82.0 |
| Top-1 ECE (mean of six) | 0.045 | 0.040 | 0.037 | 0.035 | 0.025 (7) | 0.049 (7) |
