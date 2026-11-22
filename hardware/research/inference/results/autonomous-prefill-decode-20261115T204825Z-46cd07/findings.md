# KV260 autonomous comparison stopped at preflight

Transfer and boot checks passed. The kernel-log check compared the current board with a snapshot that preceded an earlier, completed observer comparison. The complete current board state had the same SHA-256 as the last verified restoration from that comparison. The kernel log contained no additional notices.

The runner stopped before the original-model check, candidate installation, any FPGA switch or model load. This attempt produced no timing or energy data. The original circuit remained active. The failed packet and its evidence are retained separately from subsequent attempts.

[Run record](run.json).
