# Exact LUTRAM weight-array replay

The two 32 × 32 dense test arms matched per clock. An independent integer oracle checked 37 complete matrix operations in each arm, with 1,184 outputs and 37,888 signed products and partial sums. Each arm exercised all 1,024 weight addresses, seven reset probes and held outputs. A row produced its result 65 edges after launch.

The full-model control traces come from the adopted Experiment 11 replay. The new candidate matched all seven cases and 716 processed positions. All 49 checked files matched byte for byte, including bus timing, BOS scores, cache snapshots, phase counts and the cache, attention divider and down-projection schedules. First, last and completion counters stayed identical.

This verifies the RTL behaviour. The routed checkpoints provide the separate evidence for the memory primitive change.

[Run record](run.json) · [Independent audit](audit-manifest.json) · [Experiment protocol](../../experiments/kv260-output-projection-lutram-v1.md)
