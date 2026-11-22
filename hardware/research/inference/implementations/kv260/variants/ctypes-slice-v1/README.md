# KV260 score extraction using a ctypes slice

This is the exact Python probe used for the matched physical KV260 comparison. It binds the pinned stock method or a derivative containing the single change from `list(values)` to `values[:]`. The returned signed integer scores, native library, model and FPGA image were held fixed.

The experiment is recorded in the [protocol](../../../../experiments/kv260-conditioned-score-extraction-v1.md) and [findings](../../../../results/resident-score-extraction-20261115T172914Z-489050/findings.md). The stock path remains the default. `wrapper_probe.py` matches the run's implementation SHA-256.
