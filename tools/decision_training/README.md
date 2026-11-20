# Public decision-model training

`gradctl research decision-data`, `decision-train`, and `decision-compare` prepare public data, train direct decision adapters on Inkling 2 Mini, and compare predictions on the frozen 231 public JevBench items. Generated data, logs, checkpoints and comparisons belong under `.agents/runtime/` and the run's scoped development-training S3 prefix.

## Data

The builder pins these releases and records acquired file hashes:

- [Tasksource typed decisions](https://huggingface.co/datasets/tasksource/tasksource-jev-typed-decisions): original annotation distributions and deterministic recasts. Only rows marked `license_use=commercial` are admitted; their individual source licences remain in the output. The current selection gives larger caps to procedural reasoning, policy, temporal, entailment, preference and human-vote tasks, and smaller caps to other classifications.
- [SN92 generalist](https://huggingface.co/datasets/decisionmodels/sn92-generalist-train-v1) and [SN92 specialists](https://huggingface.co/datasets/decisionmodels/sn92-specialists): public training splits, with per-family caps. Credit REAX / decisionmodels and the original sources recorded by these datasets. Their compilation licence is CC-BY-4.0; source-specific terms remain applicable.

Named OpenAI, Anthropic and Gemini synthetic authors, hh-rlhf and UltraFeedback are excluded. Public dataset licence metadata is a filter, not a corpus-wide author-provenance guarantee. The normalizer preserves scalar native yes/no probabilities as `[1-p, p]`, keeps soft targets aligned to option order, and rejects unsupported or invalid distributions. It supports up to 26 options because the readout uses single-token Latin answer letters.

Exact normalized-state and word-13-gram matches against the frozen public JevBench states are excluded. This screen does not establish absence of pretraining contamination or overlap with inaccessible sealed tests. Train/dev groups stay together; normalized states appearing in train are also removed from dev. No JevBench item is used as a training or calibration example.

The Linden-1 card lists its public sources, but KnowLine's card says its training data is not released. Baseten's Mammoth-1 and Bison-1 cards describe their mixtures and objectives without a downloadable training corpus. Their `*-decision-index` repositories contain evaluation results and must not be treated as training corpora.

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

Checkpoint directories include adapters, optimizer/RNG state and a completion manifest. Only resume from a complete, hash-verified checkpoint produced by your own run: `--resume <checkpoint-directory>`. Python optimizer checkpoints are trusted pickle input. Restore the same model, data and arguments from S3 after preemption. The runner rejects changes to batch size, accumulation, token limit, learning rate, Brier weight, rank or scheduled step count; host paths and the wall-clock deadline may change. Use `--evaluate-only --resume <checkpoint-directory>` with the original training settings to score a saved checkpoint without continuing optimization. `--stop-file` permits a graceful stop followed by evaluation. Training requires a positive update count and a deadline exceeding the 15-minute evaluation reserve. If setup or a stop leaves no time for an update, the runner fails without producing a trained comparison. Provisioning and absolute allocation cleanup have separate deadlines.

The comparison reports untouched and trained models both raw and with temperatures fitted on their respective source-held-out dev predictions. It also computes paired bootstrap intervals and an exact McNemar test. Optional `--linden-results` accepts the official harness's native API result records for an identical-task reference. A public-only comparison is not an official JevBench rank: sealed tests, the current scoring edition and serving eligibility still matter. PyTorch evaluation timings are not production latency measurements for the original quantized model.

## Checks

```sh
python -m unittest discover -s tools/decision_training -p 'test_*.py'
python -m unittest discover -s tools/gradctl/tests -p test_cli.py
```
