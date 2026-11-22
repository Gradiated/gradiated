# Skip intermediate prompt scores

This KV260 variant inherits the pinned autonomous-v1 RTL. It processes the whole prompt, including final normalisation and KV writes at each position. It omits vocabulary projection before the final prompt position. Legacy single-token calls, final prompt projection and decode retain the full score stream.

Materialise the candidate from this directory with `python3 materialise.py --output /absolute/path/to/new/rtl`. The output manifest pins all eleven generated sources. For the matched simulation, run `test_prefill_skip.py --help` and supply the pinned local verifier, accepted model package and reference captures. The simulation checks the retained scores, exact completions, cache contents and counts at the prompt boundary and request completion against autonomous-v1.

The shared host adapter is generated with `prepare_host.py` from the pinned autonomous-v1 host directory. Both arms use its same native polling and timestamp path. The baseline signature remains AU01 and reports all scores. The candidate reports AU02 and exposes a read-only completed-skip count at `0x5c`. The host checks that count after delivery and separately verifies position and score geometry.

[Experiment protocol](../../../../experiments/kv260-prefill-skip-v1.md)
