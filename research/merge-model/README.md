# Git merge resolution research

Replay public two-parent Git merges to build training examples for a low-latency merge model. A row contains the conflicting text, the merge-base text, local context and the replacement from the committed merge. Run Git against bare clones to inspect objects without checking out or running repository code. Each shard records the repository license reported by GitHub, repository ID, pinned HEAD, Git version, parents, blob IDs and replay counts. Train on the license-screened corpus and retain the provenance alongside it.

The miner accepts textual code conflicts when forward and reverse alignment agree on the committed replacement. It skips generated and vendored paths, conflicted files that lack a unique alignment, and binary, missing or oversized blobs. This selects for mechanically verifiable textual resolutions. Rename conflicts, structural conflicts and files with unrelated edits in the committed merge have lower coverage.

## Run the first collection

The following commands discover public repository candidates, start deadline-bound workers on isolated development VMs, and queue a first 0.8B, 2B and 4B LoRA comparison. Use an unused S3 prefix and a fresh local state directory. Select a spot region with the right quota before provisioning.

```bash
state=.agents/runtime/merge-model/first-pass
mkdir -p "$state"
gradctl research merge-discover -- --output "$state/repos.jsonl"
gradctl research merge-launch -- "$state/repos.jsonl" --state "$state" \
  --name merge-first-pass --s3-prefix merge-model/first-pass \
  --workers 1 --gpus-per-vm 8 --region eu-north1 --hours 7
gradctl research merge-train-night -- corpus --vm merge-first-pass-00 \
  --deadline "$(cat "$state/deadline")" \
  --s3 s3://gradiated-dev-training-873716897517/merge-model/first-pass --devices 0 1 2
```

Each new spot request uses a Nebius pricing policy capped at twice the current regional GPU price. An explicit lower `--max-price` bounds that ceiling. The launcher writes per-VM receipts and schedules teardown at the hard deadline. Each remote worker uploads compressed data before its SHA-256 manifest. The coordinator freezes snapshots roughly every 20 minutes. It checks shard integrity, removes conflicting duplicate training labels, excludes normalized duplicate conflicts across splits (including swapped sides), and protects both fixed W1B holdouts. Whole repository families go into the repository holdout. The 2026-01-01 UTC cutoff determines the temporal holdout for the other repositories.

The first checkpoint comparison starts at 25,000 unique training hunks across 25 repositories and six languages, with at least 150 rows in each fresh holdout. The three arms use the same dataset and pinned Qwen3.5 revisions. The evaluator retains exact scores for the two fixed W1B splits and the two new splits individually. Training writes the adapter, optimizer, input identity, actual total and supervised token counts, and a completion flag. Deadline-truncated runs keep their checkpoints and are excluded from the scored comparison. The process skips training if the gate arrives too close to teardown.

## Data budget

Measured with the pinned Qwen3.5-4B tokenizer and the trainer's 4,096-token limit. The early snapshot yielded 9,189 usable rows out of 9,290, with 8.12M prompt and 0.75M supervised tokens. The 22,531-row W1B source yielded 22,162 usable rows at that limit, with 27.36M prompt and 1.74M supervised tokens. Context mix changes total sequence length, while both samples average roughly 80 resolution tokens.

| Unique usable hunks | Total tokens at the early snapshot's density | Supervised tokens | Purpose |
| ---: | ---: | ---: | --- |
| 25,000 | 24M | 2M | First comparison at 0.8B, 2B and 4B |
| 100,000 | 96M | 8M | Same three sizes on a larger, more diverse snapshot |
| 300,000 | 290M | 24M | Extend the 2B and 4B curves if the earlier runs keep improving |

Use nested, deterministic samples from a common frozen corpus and log unique examples, total tokens and supervised tokens. Use `--token-limit` in `train.py` to cap a sample by full-sequence tokens. For the follow-on curve, choose models on a development set and reserve the final unseen repositories. Aim for several thousand unseen-repository examples across at least 20 projects, with per-repo and difficult-hunk scores. Use paired uncertainty grouped by merge and repository. Treat a rung as a plateau candidate when an interval can rule out a two-point improvement on difficult hunks at matched auto-apply precision. The three rungs are estimates for supervised adaptation of existing Qwen checkpoints.

## Repository history

Compare the same generic model with a time-bounded history index, a per-repository LoRA, and both together. Retrieve older resolved conflicts by shared identifiers and path, then test a dense retriever only if it returns better evidence for later merges. A separate experiment can train that retriever on historical conflict-to-resolution pairs. Keep same-repo adaptation data dated before every evaluation merge, remove duplicate triplets and family overlaps from generic training, and use an equal-size other-repository adapter or retrieval arm to control for more examples and tokens. Compare held-out exact resolution, coverage at matched precision, and cold and warm p95 latency.

For a sparse history, build the index from earlier commits and conflict-free branch diffs as well as real resolutions. Train a repository adapter only after a learning curve shows an improvement at the available history size. The repository index can be refreshed incrementally and evaluated using the same pinned base model.

## First-pass measurements

W1B exact resolution uses the same 316 final prompts across model families and counts abstentions and malformed outputs as misses. The tuned Qwen rows use the existing task adapters. The raw untuned 4B run completed and its chat-format counterpart timed out.

| Qwen3.5 size | Best completed untuned format | Tuned, all | Tuned, unseen repositories | Tuned, later merges in seen repositories |
| ---: | ---: | ---: | ---: | ---: |
| 0.8B | 4/316 | 254/316 | 120/163 | 134/153 |
| 2B | 8/316 | 260/316 | 124/163 | 136/153 |
| 4B | 30/316 | 270/316 | 131/163 | 139/153 |

The unseen split covers phpMyAdmin and QEMU, excluded from merge-task tuning. Checkpoint pretraining exposure is unknown. The split difference includes repository difficulty and the untuned results include output-format failures. GPT-6 Luna answered 115/316 exactly at low reasoning and 148/316 at high through the local subscription-backed endpoint. GPT-6.2 Astra reached 290/316 on the same inputs. Rich evidence improved GPT-6 Luna from 51/96 to 66/96 in a matched context comparison.

The first same-repository retrieval probe evaluated 58 W1B targets across phpMyAdmin and QEMU with GPT-6 Luna at high reasoning. Rank older resolved conflicts by inverse-document-frequency-weighted shared identifiers with a same-path bonus, exclude normalized triplets from the evaluation set, and prepend one prior resolution. Historical evidence gained eight exact answers and lost eight, leaving 34/58 in both arms. The small probe used a previous run for the paired control. It motivates testing parent-branch evidence and retrieval-aware task tuning with a larger development set.
