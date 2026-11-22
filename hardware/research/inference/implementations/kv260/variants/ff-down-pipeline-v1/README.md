# Pipelined feed-forward down projection

Each row starts by reading its first operand pair. On each subsequent clock the lane multiplies the previously registered pair and fetches the next one until the row is complete. The adopted divider, all other dense instances, the arithmetic and the output handshake retain their original logic.

`materialise_ff_down.py --arm control|candidate --output /path/to/new/rtl` checks the adopted RTL pins and generates the selected closure. See the [experiment protocol](../../../../experiments/kv260-ff-down-pipeline-v1.md) for the predicted cycle law and measurement scope.

Experiment 9’s [exact simulation](../../../../results/ff-down-rtl-20261117T000318Z/findings.md) matched all seven cases and saved 4,064 clocks per processed position. The [routed 50 MHz build](../../../../results/ff-down-pipeline-build-20261117T000146Z/findings.md) adds 14 LUTs and two registers overall, with DSP and block RAM counts unchanged. The [physical comparison](../../../../results/ff-down-pipeline-20261117T095726Z-1092a6/findings.md) matched all 36 timed requests, all measured counters and the original board restoration.
