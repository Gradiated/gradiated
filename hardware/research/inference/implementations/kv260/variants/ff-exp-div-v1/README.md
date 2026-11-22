# Exact feed-forward exponential divider

This variant starts three divisions by 45,426 with a proven prefix remainder, then runs the original two-bit restoring steps and exact finish state. The [protocol](../../../../experiments/kv260-ff-exp-div-v1.md) derives the bounds and defines the measurements.

`materialise_ff_exp.py --arm control|candidate --output /path/to/fresh/rtl` generates either closure. `test_experiment.py --help` gives the component and exact matched replay arguments.

## Evidence

- [Matched RTL simulation](../../../../results/ff-exp-div-rtl-20261116T214222Z/findings.md)
- [Routed 50 MHz build](../../../../results/ff-exp-div-build-20261116T213813Z/findings.md)
- [Matched physical comparison after serial qualification](../../../../results/ff-exp-div-20261116T230715Z-0969cc/findings.md)
- [USB transfer stop](../../../../results/ff-exp-div-20261116T220204Z-8d31b7-transfer-aborted/findings.md)
- [Retry qualification stop](../../../../results/ff-exp-div-retry-health-20261116T223649Z-aborted/findings.md)
