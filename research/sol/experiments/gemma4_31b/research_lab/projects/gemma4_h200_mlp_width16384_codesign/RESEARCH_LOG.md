# Research log

## 2026-07-23 — director admission

Admitted one explicitly quality-unsafe 21,504-to-16,384 SwiGLU-width proxy. It is a model–hardware cost experiment, not another FP8-kernel schedule and not a production candidate. At most one fixed selection, component, and conditional c32 invocation are allowed.

## 2026-07-23 — exact consumer is positive but misses the c32 gate

Question: does the frozen joint-norm-selected 16,384-channel representation remove at least 3% of the current whole-request trace?

Action: materialized one deterministic selection for all 60 layers from the bound checkpoint (`JOINT_NORM_SELECTION.json`, SHA-256 `185dbc56…`), then measured the real layer-0 gate/up → GELU-and-mul → down FP8 consumer on the retained H200 at M=32 and observed prefill M=118/1409/1631/2048. The component used the pinned SGLang `fp8_scaled_mm`, E4M3 dynamic weights/per-token activations, BF16 output, real weights, complete finite output consumption, and exact 5,376×43,008 / 21,504×5,376 control versus 5,376×32,768 / 16,384×5,376 candidate geometry.

Evidence: profiler-off median reduction was `16.868546%` at M=32 and `20.210729%`, `25.800758%`, `21.940813%`, and `21.412623%` at the four prefill shapes. The current trace mechanically maps `3.507850666 s` of its `22.344871517 s` non-overlapping window to gate/up plus down. Applying the worst measured shape reduction admits `0.591723412 s`, or `2.648139692%` whole-request reduction. Artifacts: `artifacts/width16384-component-repair2-20260723t1224z/`.

Interpretation: the aligned geometry creates a real component gain, but launch/tile realization yields less than the removed-channel fraction at M=32, and MLP owns too little current wall time for this frozen proxy to clear the 3% endpoint gate. The c32 quality-unsafe invocation did not start (`endpoint_candidate_science_started=false`). Cumulative provider exposure, including pre-science launcher repairs, was `$0.1137651592`; the bench was released ready.

Next move: close this candidate without endpoint timing, width/selection sweep, or recovery training. A later co-design would need a materially different intervention rather than a nearby width replay.
