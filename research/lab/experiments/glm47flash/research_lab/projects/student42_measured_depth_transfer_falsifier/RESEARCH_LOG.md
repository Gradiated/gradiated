# Research log

Opened by the 2026-07-16 director after the exact local loader falsifier terminated at the real runtime process-group boundary. This project uses existing measured L40S traces once to decide whether the clean 42-layer fallback deserves later GPU information value; it does not own the live r3 session, provider, runtime, or checkpoint.

## 2026-07-16 — Measured transfer closes student42 (PARK)

Question/action: bind the full47 c16 and physical student39 c16/c24/c32 L40S traces, then produce one conservative student42 c16/c32 interval with zero c32 uplift and adverse fixed-cost/model stress at $0.

Measured evidence: the archives are comparable on NVIDIA L40S, model revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`, vLLM 0.15.0, BF16, `num_kv_splits=4`, 8,192-input/1,024-output geometry, disabled prefix caching with zero hit/query deltas, and complete `length` requests. Full47 c16 is 535.286 tok/s (32/32, 61.216 s); student39 is 674.424 tok/s at c16 (32/32, 48.587 s), 661.661 at c24, and 734.557 at c32 (64/64, 89.218 s). The `max_num_seqs` 16-versus-32 difference is retained as a material identity note; c24/c32 are not treated as transferable uplift.

Method/result: `analyze_transfer.py` reproduces `STUDENT42_TRANSFER_RESULT.json`. The inherited clean student42 depth bound is 597.529 tok/s; full47-proportional scaling is 599.011 tok/s, while inverse-rate affine interpolation is shown only as model-form sensitivity at 614.523 tok/s because its extrapolated fixed intercept is not conservative. The selected c16 point is the minimum defensible bound, 597.529 tok/s, and c32 is set to the same value under zero uplift. A deterministic 20,000-resample TPOT diagnostic gives roughly 1.99% maximum endpoint half-width; adding a 2% measurement allowance and 3% adverse fixed prefill/queue time yields [568.750, 597.529] tok/s for both c16 and c32.

Decision: PARK. The robust lower bound 568.750 tok/s misses the 606.355 tok/s nomination floor and even crosses the 594.466 economic gate. All complete background arms were below 300 s, but that does not rescue the margin. No provider, r3 service, launcher, checkpoint, or successor analysis was touched; quality remains deferred. The compact result is [STUDENT42_TRANSFER_RESULT.json](STUDENT42_TRANSFER_RESULT.json).
