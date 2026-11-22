# Cycle breakdown of the KV260 feed-forward block

Find the operations that occupy the adopted eight-lane model's 34,306 feed-forward clocks per processed token position. The adopted model and circuit stay fixed. Use the [eight-lane simulation record](../results/logits-eight-rtl-20261116T190922Z/run.json), its archived RTL and the same seven exact cases. The W16A16 weights, its byte-token protocol, cache and output assertions are inherited byte for byte.

This is a diagnostic simulation of one unchanged circuit. The optional conversion of cycles to time assumes 50 MHz. A later experiment would have to establish any speed-up, resource cost, timing or energy difference.

## Observation windows

Sample the signals immediately before the same rising clock edge used by the original testbench while the autonomous request is being observed. Count normalisation and input preparation separately. The parent `N2_WAIT` window includes normalisation work as well as 32 accepted transfers of normalised values into the gate and up projections. The `FF_START` window separately records one launch per position and any blocked launch clocks.

For the `FF_WAIT` phase, count one tick in the actual feed-forward controller state on every edge. Close each per-position row on acceptance of output row 31. Reconcile the position and request sums to the independent archived prefix and terminal counters. A missing position, unexpected controller state, unpaired command or incomplete output stops the replay.

Gate, up and down projection occupancy is recorded independently by each engine's states and its ready/valid handshakes. The occupancy of those engines can overlap. Record a four-bit activity mask for each parent state to find overlap between dense operand read, accumulation and rounding, and active scalar execution. The mask counts partition the same clocks as the parent controller. A busy engine holding a completed result is recorded as such. Its held-result clocks are separate from arithmetic activity.

Record accepted scalar opcodes and operand ranges before attributing response clocks. The six caller command classes distinguish the exponential, sigmoid division, two multiplies and two rounded shifts. Split scalar response wait by the actual scalar state. For the exponential, verify denominator 45,426 and record each divider invocation and its step and finish cycles separately by return state. A caller waiting for a result can include handshake and buffering time. Only occupied arithmetic substates count as observed arithmetic work.

## Prediction and verification

The independent source-derived prediction is 193 gate/up pair clocks, 25,728 scalar send and wait clocks, 128 hidden-store clocks, one down start clock and 8,256 down-run clocks per position. This predicts 34,306 clocks exactly in the absence of the exponential shortcut or external stalls. The exponential and sigmoid together are predicted to use 16,896 division step and finish clocks. Gate and up can start their next rows during scalar operations and hold the results, so their work may be largely hidden in elapsed processing time. The projection's alternating READ and MAC states may be another useful opportunity. Preserve the independently pinned prediction and report any observed differences.

Reuse the archived autonomous testbench with one observation include. Read the exact same fitted weights and fixture files, rerun all seven cases with a single compile, and require byte-identical archived AXI events, legacy BOS scores, prefix and terminal cache and phase snapshots. Original assertions continue to check retained scores, output IDs, limits, termination and the next BOS request. Startup weight loading and the two legacy BOS checks remain functional coverage outside the autonomous profile. Retain grouped per-case totals and position-level timings, state occupancy, handshakes and operand ranges.

Use the pinned Mac Verilator 5.052 toolchain with at most two compile jobs, a 150-second compile limit, a 120-second limit per replay and a 900-second absolute budget for the suite. Use a shrinking deadline and stop child process groups on expiry. Preserve source and results with exact hashes on the Mac, along with any first failure. Stop after independent review of the diagnostic. Use the measured cycles to propose one candidate and its falsifier before choosing an acceleration experiment.
