# Public decision-model training

`gradctl research decision-data`, `decision-train`, and `decision-compare` prepare public data, train direct decision adapters on Inkling 2 Mini, and compare predictions on the frozen 231 public JevBench items. Generated data, logs, checkpoints and comparisons belong under `.agents/runtime/` and the run's scoped development-training S3 prefix.

## Data

The builder pins these releases and records acquired file hashes:

- [Tasksource typed decisions](https://huggingface.co/datasets/tasksource/tasksource-jev-typed-decisions): original annotation distributions and deterministic recasts. Only rows marked `license_use=commercial` are admitted; their individual source licences remain in the output. The current selection gives larger caps to procedural reasoning, policy, temporal, entailment, preference and human-vote tasks, and smaller caps to other classifications.
- [SN92 generalist](https://huggingface.co/datasets/decisionmodels/sn92-generalist-train-v1) and [SN92 specialists](https://huggingface.co/datasets/decisionmodels/sn92-specialists): public training splits, with per-family caps. Credit REAX / decisionmodels and the original sources recorded by these datasets. Their compilation licence is CC-BY-4.0; source-specific terms remain applicable.

Named OpenAI, Anthropic and Gemini synthetic authors, hh-rlhf and UltraFeedback are excluded. Public dataset licence metadata is a filter, not a corpus-wide author-provenance guarantee. The normalizer preserves scalar native yes/no probabilities as `[1-p, p]`, keeps soft targets aligned to option order, and rejects unsupported or invalid distributions. It supports up to 26 options because the readout uses single-token Latin answer letters.

Exact normalized-state and word-13-gram matches against the frozen public JevBench states are excluded. This screen does not establish absence of pretraining contamination or overlap with inaccessible sealed tests. Train/dev groups stay together; normalized states appearing in train are also removed from dev. No JevBench item is used as a training or calibration example.

The Linden-1 card lists its public sources, but KnowLine's card says its training data is not released. Baseten's Mammoth-1 and Bison-1 cards describe their mixtures and objectives without a downloadable training corpus. Their `*-decision-index` repositories contain evaluation results and must not be treated as training corpora.

## Sources for a larger run

[`data_sources.json`](data_sources.json) is a discovery catalogue, not an acquisition lockfile or an admitted training release. It records 39 dataset/config candidates, reported training counts, label evidence, overlap relationships and admission requirements. Pinned source revisions are recorded where resolved; further acquisition, full scans and admission checks remain. The existing pilot source pins and admission policy are unchanged. Raw cards, previews and discovery hashes stay under ignored `.agents/runtime/decision-data-discovery/`.

Broad Hub queries retrieved 983 of 1,017 candidate model cards and extracted 240 dataset links; 34 retrievals failed after a resolver follow-up. Query hits include forks, variants and unrelated models: this is broad discovery rather than an exhaustive census of distinct trained decision models. Ten dataset/config previews (611 ordered rows) were collected to inspect formats; these samples do not establish whole-corpus quality or retention rates. Subsequent complete downloads of the five VerQen train files and 13 Tasksource filtered-full files passed their published SHA-256 checks. The pinned Tasksource files contain 1,304,043 rows, differing from the card count below; 1,218,577 pass the existing source/schema filters, with 1,178,701 distinct exact decision-target pairs and no exact conflicting targets. VerQen has 1,776,286 questions across 1,620,819 states/rows: 396 fail the structural checks, 15,333 valid questions exceed the current 26-option limit, and four exact decision inputs have conflicting target vectors. A subsequent full state exact/word-13 screen against the frozen public JevBench found two VerQen and three Tasksource matches; related groups still need exclusion. These are structural and lexical audits, not semantic admission or private-test decontamination.

| Candidate | Reported train rows | Contribution and admission concern |
| --- | ---: | --- |
| Tasksource `filtered-full` | 1,305,478 | Broad tasks and native distributions; commercial-use metadata and LLM-assisted cleanup. Includes 97,030 uncertain retained decisions. |
| VerQen, five train configs | 1,620,819 | Procedural policies, oracle environments, public labels, paraphrases and longer contexts. Later stages reuse scenarios. |
| Jev Decisions v1 | 11,269,408 | Agent actions and outcomes; only 6,214,185 records across **all splits** have Choice supervision. Software engineering dominates. |
| OpenDecisionMix | 957,323 | Routing, safety, grounding and response judgement. Original gold and Jev predictions are separate; upstream review required. |
| SargeDev v3 / Solar v4 | 655,806 / 756,619 | Soft targets; mostly overlapping scenarios with different teachers. Relabels are not additional unique cases. |
| Open-Jev controls, BEV, SN92, Plumb | See catalogue | Procedural, counterfactual, temporal, numeric, policy and multilingual diversity; shared upstream records need deduplication. |

Twenty to fifty times the pilot's 127,888 rows means 2,557,760–6,394,400 usable rows. Tasksource filtered-full plus VerQen supplies a **2,926,297-row candidate pool** before cross-source deduplication, provenance, source terms, benchmark exclusions and token/option limits. This does not establish a 23× clean release. The larger agent corpus adds scale, but repeated trajectories and failed actions cannot be counted as independent correct supervision.

Before assembling a larger training release:

1. Freeze full source revisions, files, hashes and original partitions. Resolve source terms and teacher provenance; hold out unknown or restricted components under the pilot's policy.
2. Preserve original gold, human vote distributions and teacher predictions as distinct evidence. Recompute procedural answers where possible; audit stratified samples per source/family and detected conflicts. Teacher agreement alone does not establish correctness or calibration.
3. Canonicalize question types, ordered scales, option identities and probabilities. Exclude rationales, gold answers, future outcomes and teacher predictions from inputs. The current renderer supports at most 26 options and filters over 2,048 tokens: remeasure retention with the exact Inkling tokenizer before choosing a larger context/readout.
4. Deduplicate exact model-visible decisions, shared upstream rows and near-identical scenarios across corpora; quarantine conflicting targets. Keep counterfactuals, translations and alternate questions as related views with a shared group. Report unique states, scenarios/trajectories, questions and tokens separately.
5. Protect public JevBench and additional benchmarks by source identity, exact text and approximate overlap. Use source/family/trajectory holdouts for validation and calibration. OpenDecisions, DecisionPivot, Fast Decisions and `*-decision-index` results remain evaluation data irrespective of Hub split names or card links.
6. Cap mixture shares by skill, source family, label evidence, language, type, length and trajectory. Publish accepted/rejected counts, cross-split checks, attributions and a hash-bound release manifest. Set size from survivors rather than repeating rows to fill a quota.

Strands Decider v2 describes 17,480,970 rows, but its [recipe says the data is not in the repository](https://github.com/strands-labs/strands-decider/blob/main/training/README.md#the-v2-recipes). Its older public recipe has smaller generated data and reconstruction steps. Recipe disclosure also does not make the complete Bison/Mammoth/KnowLine mixtures downloadable.

`gradctl research decision-data-scale -- --source-manifest <acquisition.json> --run-dir <empty-output-dir>` normalizes the pinned VerQen, filtered Tasksource and native procedural acquisitions into traceable candidate Parquet shards. Repeat `--source-manifest` for each acquisition. It verifies every input hash, archives builder sources, records per-question rejection reasons and preserves source groups and probability order. The completion marker binds the shard manifest. These shards are explicitly **candidates only**: benchmark/group exclusions, cross-source exact/near deduplication, semantic admission, holdouts and exact tokenizer limits must pass before exporting a training release.

`gradctl research decision-data-audit -- --candidates <candidate-dir> --benchmark <frozen-benchmark.jsonl> --run-dir <empty-audit-dir>` builds a hash-bound SQLite audit of exact decision duplicates and conflicting targets after aligning nominal option order. Ordinal order, numbers and operators remain significant. It screens every candidate state against the protected benchmark by exact normalized text and shared 13-word spans, then propagates exclusions and conflicts through connected source cases, shared states and exact decision inputs. Empty/short states group by complete decision input to avoid merging unrelated context-free questions. The audit records original candidate ordinals, exact survivors and case components; it also repairs numeric-zero Tasksource grouping from the retained raw acquisition. It does **not** certify semantic labels, source terms, near-duplicate/translation equivalence or tokenizer limits, and its survivors remain unadmitted candidates. `--seconds` bounds the audit, including SQL work; retain partial generations and write a new output directory after a failed run.

New candidate manifests record preserved numeric-zero grouping and need no raw acquisition paths for this audit. Legacy Tasksource candidates require explicit `--source-manifest <acquisition.json>` inputs with portable local paths; their bytes are verified against the candidate-bound original hashes before repairing groups. The audit archives and binds its local helper sources at startup.

`gradctl research decision-token-audit -- --candidates <candidate-dir> --tokenizer-dir <verified-tokenizer-dir> --tokenizer-manifest <tokenizer-acquisition.json> --run-dir <empty-token-audit-dir> --workers 8` measures every untruncated rendered prompt with the pinned native tokenizer/runtime. It writes compact per-candidate lengths, context-limit totals and a native-conformance panel. This uses the same renderer as the trainer and requires the frozen Transformers commit, Tokenizers 0.23.3 and Jinja 3.1.6. These totals describe the input candidates; changed prompts and later admission/deduplication require adjusted survivor totals.

`gradctl research decision-semantic-audit -- --source-manifest <procedural-acquisition.json> --run-dir <empty-semantic-audit-dir>` independently checks Bayesian sensor posteriors, timestamped incident replay and directed minimum-cost routes from rendered states. It records unsupported coverage and per-family mismatch counts rather than certifying unimplemented families. The reviewed sensor-posterior question repair asks about the incident event, preserving posterior targets and original wording; it applies to native questions and the Tasksource recast. Existing candidate generations require that curation during export, new exact deduplication after question convergence, and token-length adjustment.

## Run

Use a dedicated development-training GPU with `gradctl compute`. Keep the allocation owner and an independent cleanup watchdog running; the training program checkpoints but does not delete provider resources. Grant only the run's S3 paths using `gradctl compute s3`. No production credentials or customer inputs are needed.

The validated model implementation is Transformers commit `e3a65e2c21abb9c25a03704f2f25852f9ad03a18`; the checkpoint is `thinkingmachines/Inkling-2-Mini` at `6e7c8248f75265bdd4fbab5273304243b5d8c2cb`. This release implementation dequantizes the original NVFP4/MXFP8 experts to BF16 while loading. The original three loop passes are retained. Use the run's frozen package list for its exact environment; dependencies include CUDA PyTorch, Transformers at that commit, PEFT, Accelerate, safetensors, huggingface-hub, PyArrow, and boto3.

Run gradctl with the Python environment containing those packages:

```sh
python tools/gradctl/gradctl research decision-data -- \
  --run-dir .agents/runtime/inkling-decision --tasksource-shards 2

python tools/gradctl/gradctl research decision-train -- \
  --run-dir .agents/runtime/inkling-decision \
  --s3-uri s3://DEVELOPMENT_BUCKET/PROJECT/RUN \
  --steps 1500 --seconds 9000 --batch-size 16 --accumulation 2 \
  --max-length 2048 --brier-weight 1

python tools/gradctl/gradctl research decision-compare -- \
  --run-dir .agents/runtime/inkling-decision
```

Before training, download the pinned checkpoint to `<run-dir>/model` and save the pinned Hub API file manifest, including blob metadata, as `<run-dir>/model-manifest.json`. The runner checks file sizes and SHA-256 LFS or Git-blob SHA-1 digests and binds the verified manifest digest into its output identity. A verification marker is reused only for read-only files with unchanged storage metadata; writable files are rehashed. On another run in the same allocation, reuse verified immutable weights through a hard-linked view. Preparing all six Tasksource shards is the default; the two-shard option bounds the initial experiment. The data manifest records the actual selection, and the output identity also binds the token limit used to select training and calibration examples.

The training objective is soft cross-entropy plus a configurable Brier term over answer-letter logits. Rank-32 adapters target attention projections and the answer readout; vision and expert base weights remain frozen. Examples exceeding the training token limit are excluded, never truncated. All 231 evaluation items are retained. This is a text-only experiment despite the multimodal base.

Scored evaluation requests run individually without padding. The pinned release implementation showed substantial BF16 probability changes when an identical unpadded input was repeated in a batch; FP32 reduced that sensitivity. `gradctl research decision-probe` separates batch shape, padding, explicit positions and precision. The training runner checks single-request replay at three input lengths before scoring. Training remains batched, and the comparison binds the evaluation protocol in its identity file.

Checkpoint directories include adapters, optimizer/RNG state and a completion manifest. Only resume from a complete, hash-verified checkpoint produced by your own run: `--resume <checkpoint-directory>`. Python optimizer checkpoints are trusted pickle input. Restore the same model, data and arguments from S3 after preemption. The runner rejects changes to batch size, accumulation, token limit, learning rate, Brier weight, rank or scheduled step count; host paths and the wall-clock deadline may change. Use `--evaluate-only --resume <checkpoint-directory>` with the original training settings to score a saved checkpoint without continuing optimization. `--stop-file` permits a graceful stop followed by evaluation. Training requires a positive update count and a deadline exceeding the 15-minute evaluation reserve. If setup or a stop leaves no time for an update, the runner fails without producing a trained comparison.

For a whole node, run the same entry point with `torchrun --standalone --nproc_per_node=8 tools/decision_training/train.py <training arguments>`. Batch size is per rank; effective batch size is `batch-size × accumulation × world-size`. Distributed training uses adjacent length buckets across ranks, drops only the final incomplete global bucket (reported explicitly), averages gradients through DDP and suppresses intermediate accumulation synchronization. Ranks make collective stop/finite-loss decisions. Rank zero alone writes artifacts and performs singleton evaluation; checkpoints contain each rank's Python/PyTorch/CUDA RNG state and reject a changed world size on resume. Token logs distinguish useful tokens, padding and elapsed training time including checkpoints. Existing single-GPU pilot artifacts remain tied to their frozen executable sources.

Before a larger launch, run `torchrun --standalone --nproc_per_node=2 tools/decision_training/smoke_distributed.py --output-dir <empty-smoke-dir>` to compare accumulation and optimizer/RNG resume against a full-batch toy oracle. Its CPU Gloo result verifies those mechanics only. `--cuda` exercises the same toy on NCCL, but neither toy run establishes Inkling memory, numerical correctness, checkpoint recovery or throughput: those require a real short Inkling run on every intended GPU before the full job.

The runner checks the reserve before each microbatch and optimizer update, including the longest observed operation duration, and discards incomplete accumulated gradients. Evaluation checks the overall deadline before every request and flushes each completed prediction; partial files are retained for repair rather than silently replayed. S3 transfers check the deadline between files and in progress callbacks, with bounded SDK connection/read timeouts and retries. These checks cannot interrupt an in-flight CUDA operation, so provisioning and absolute provider cleanup still require an independent watchdog.

The comparison reports untouched and trained models both raw and with temperatures fitted on their respective source-held-out dev predictions. It also computes paired bootstrap intervals and an exact McNemar test. Optional `--linden-results` accepts the official harness's native API result records for an identical-task reference. A public-only comparison is not an official JevBench rank: sealed tests, the current scoring edition and serving eligibility still matter. PyTorch evaluation timings are not production latency measurements for the original quantized model.

## Checks

```sh
python -m unittest discover -s tools/decision_training -p 'test_*.py'
python -m unittest discover -s tools/gradctl/tests -p test_cli.py
```
