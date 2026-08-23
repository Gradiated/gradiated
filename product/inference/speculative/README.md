# Gemma 4 speculative decoder

`train_gemma4_mtp.py` domain-tunes Google's four-layer Gemma 4 assistant for
Gradiated's long-prefix coding-agent workload. It never trains on validation or
holdout sessions.

The capture phase runs the frozen target once per training session and stores
only the target features needed by the drafter. Each anchor trains four
recurrent draft positions against Gemma's own greedy next-token decisions. The
target KV remains frozen at the anchor, matching the production MTP algorithm.

```sh
python3 train_gemma4_mtp.py capture \
  --workload ../benchmarks/workloads/speculative-splits/train.jsonl \
  --features /var/lib/gradiated/speculative/gemma-4-31b/features-v1

python3 train_gemma4_mtp.py train \
  --features /var/lib/gradiated/speculative/gemma-4-31b/features-v1 \
  --output /var/lib/gradiated/speculative/gemma-4-31b/runs/v1 \
  --checkpoint-steps 50,150,400
```

Select a checkpoint only with the validation split. Run the selected
checkpoint once against holdout and require exact greedy parity with the
target-only oracle before considering production rollout.
