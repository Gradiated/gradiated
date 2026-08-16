# Research log

## 2026-07-23 — director admission

Admitted one explicitly quality-unsafe 21,504-to-16,384 SwiGLU-width proxy. It is a model–hardware cost experiment, not another FP8-kernel schedule and not a production candidate. At most one fixed selection, component, and conditional c32 invocation are allowed.

## 2026-07-23 — exact consumer is positive but misses the c32 gate

Question: does the frozen joint-norm-selected 16,384-channel representation remove at least 3% of the current whole-request trace?

Action: materialized one deterministic selection for all 60 layers from the bound checkpoint (`JOINT_NORM_SELECTION.json`, SHA-256 `185dbc56…`), then measured the real layer-0 gate/up → GELU-and-mul → down FP8 consumer on the retained H200 at M=32 and observed prefill M=118/1409/1631/2048. The component used the pinned SGLang `fp8_scaled_mm`, E4M3 dynamic weights/per-token activations, BF16 output, real weights, complete finite output consumption, and exact 5,376×43,008 / 21,504×5,376 control versus 5,376×32,768 / 16,384×5,376 candidate geometry.

Evidence: profiler-off median reduction was `16.868546%` at M=32 and `20.210729%`, `25.800758%`, `21.940813%`, and `21.412623%` at the four prefill shapes. The current trace mechanically maps `3.507850666 s` of its `22.344871517 s` non-overlapping window to gate/up plus down. Applying the worst measured shape reduction admits `0.591723412 s`, or `2.648139692%` whole-request reduction. Artifacts: `artifacts/width16384-component-repair2-20260723t1224z/`.

Interpretation: the aligned geometry creates a real component gain, but launch/tile realization yields less than the removed-channel fraction at M=32, and MLP owns too little current wall time for this frozen proxy to clear the 3% endpoint gate. The c32 quality-unsafe invocation did not start (`endpoint_candidate_science_started=false`). Cumulative provider exposure, including pre-science launcher repairs, was `$0.1137651592`; the bench was released ready.

Next move: close this candidate without endpoint timing, width/selection sweep, or recovery training. A later co-design would need a materially different intervention rather than a nearby width replay.

## 2026-07-23 — endpoint arm reopened by user direction

- The `2.648139692%` conservative whole-request bound is positive and the endpoint launcher is already implemented; the prior 3% cutoff was an arbitrary portfolio heuristic.
- Preserve the completed component, deterministic 60-layer selection, and persisted control. Run only the previously unstarted quality-unsafe c32 candidate and retain any measured positive endpoint gain for stacking.
- The owner is now genuinely endpoint-only: it consumes the hashed settled bound, does not replay the component, and no longer stages the 638.6 MB gate/up or 231.2 MB down-projection snapshots. This removes duplicate science and roughly 870 MB of avoidable transfer from the next claim.

## 2026-07-23 — endpoint resource boundary before candidate science

Action: claimed the released H200, verified the project-local immutable selection and settled bound, and repaired the launcher’s port/readiness ordering so it could not mistakenly query the resident service. The candidate still could not load alongside that healthy resident async server.

Evidence: the retrieved candidate log records `torch.OutOfMemoryError` allocating 168 MiB with only 159.94 MiB free. The invocation marker is `endpoint_candidate_cuda_started=true` and `endpoint_candidate_science_started=false`; no MLP audit, coherence request, or c32 row was produced. The compact diagnostic is in `artifacts/width16384-endpoint-repair1-20260723t1421z/retrieved/`, with typed terminal `FINAL_TERMINAL.json`. Cumulative project exposure is `$0.3152518719`.

Interpretation and next move: this is a shared-resident-memory boundary, not evidence against the frozen width proxy. Do not replay the component or candidate. A director must quiesce/reconfigure the resident server or provide an H200 with enough free memory, then run only the unchanged endpoint arm.

## 2026-07-23 — measured c32 endpoint gain

Action: after director maintenance cleared the H200, repaired only the pre-science multimodal loader routing and runner import defects, then ran the one unchanged quality-unsafe c32 endpoint arm. The settled component and selection were not replayed.

Evidence: `PATH_PROOF.json` records all 60 layers and 180 gate/up/down routes at the exact 16,384 geometry. The candidate completed 32/32 rows with finite text and exact `17,120` cached / `117,728` fresh prompt-token deltas. It measured `0.6323543743 s/request` versus the persisted `0.6743258590 s/request` control: a `6.224214%` reduction and below the `0.6381105231 s/request` ceiling. Artifacts: `artifacts/width16384-endpoint-repair2-20260723t1502z/`. The three small coherence prompts were finite but semantically incorrect, as expected for this explicitly quality-unsafe proxy.

Interpretation and next move: retain the positive endpoint gain for stacking and nominate exactly one future structured recovery/distillation effort. This proxy is not production eligible and this project must not replay its component, endpoint, width, or selection. Cumulative project exposure is `$0.7590146794`.
