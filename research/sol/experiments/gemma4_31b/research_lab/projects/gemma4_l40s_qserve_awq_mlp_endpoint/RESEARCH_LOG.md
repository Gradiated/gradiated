# Research log

## 2026-07-24 — director admission

- Bound exact model, checkpoint, AWQ snapshot, QServe revision, pinned image,
  SM89 schedule, measured Marlin resource reject, and measured QServe
  component-positive evidence in `AWQ_QSERVE_BINDING.json`.
- The new hypothesis is the interaction between existing activation-aware AWQ
  tensors and the fixed QServe dataflow. It neither reopens the uncalibrated
  W4 endpoint nor replays Marlin.
- Prepare one converter and immutable packet offline while priority-6300 KV4
  owns the retained L40S. No GPU, provider, calibration, sweep, or endpoint is
  authorized in this cycle.

## 2026-07-24 — exact progressive-layout reject

- Question: can the fixed QServe FP16-per-output × integer-per-group
  progressive representation encode the bound layer-0 AWQ gate/up/down
  dequantized tensors exactly, without calibration or requantization?
- Action: implemented `awq_to_qserve.py`, bound the AWQ and QServe packing
  orders, exercised five synthetic encode/decode and scale-factor tests, and
  ran the converter over every active group in snapshot
  `871a79d70b4fe23a5b036a765a129556ff2b4a2affc86606e843dbae215e04f8`.
- Measured evidence: all 42 gate/up groups and all 168 down groups are active
  for every output channel. The minimum, across output channels, of the
  required exact maximum stage-2 multiplier is 163 for gate, 166 for up, and
  251 for down; even the smallest per-channel required stage-1 absolute
  maxima are 1,377, 1,344, and 2,510 respectively. No gate/up/down output
  channel keeps its exact integerized stage-1 values and scaled zero inside
  the fixed signed-int8 contract;
  convertible channels are `0/21504`, `0/21504`, and `0/5376`.
- Interpretation: the existing activation-aware AWQ scales do not factor into
  the fixed QServe progressive scale lattice. Any runnable mapping would
  approximate scales or codes and therefore be the prohibited
  requantization. This is the preregistered semantic reject; no GPU packet is
  admitted and no quality claim is made.
- Artifacts: `artifacts/awq-qserve-layout-20260724t0800z/ROUND_TRIP_TERMINAL.json`,
  `SOURCE_MANIFEST.json`, and immutable offline rejection packet
  `eade73c33b55f05adb59501dafa7f2337a1e5cbe8746c893b5f18328db2a92c5`.
  No GPU claim, provider mutation, or spend occurred.
