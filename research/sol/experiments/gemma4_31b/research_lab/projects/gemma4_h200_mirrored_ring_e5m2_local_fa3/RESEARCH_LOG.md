# Research log

## 2026-07-23 — explicit Triton constexpr repair

The retained owner validated the exact resident checkpoint and all frozen inputs, then the first H200 smoke failed before candidate CUDA and before any scientific invocation. Triton rejected `LOGICAL_RING_TOKENS` at compile time because the three mirrored store/restore JIT kernels close over module globals. This is an ordinary integration defect, not evidence about doubled writes or one-call FA3.

Keep the owner and claim. In `mirrored_ring_kv.py` only, pass logical `1024` and physical `2048` ring sizes as explicit `tl.constexpr` kernel arguments at all three launches, preserving every expression and launch configuration. Do not enable non-constexpr globals. Reconcile the manifest and resume through the existing repair handshake, then run the frozen smoke and one producer-consumer component; the endpoint remains conditional on a credible positive complete-component bound.

## 2026-07-23 — repaired component terminal

Question: can the mirrored physical ring make the one-call direct-E5M2 FA3 local path admissible after charging doubled producer stores?

Action: repaired only the three Triton kernel signatures and launches to pass `LOGICAL_RING_TOKENS=1024` and `PHYSICAL_RING_TOKENS=2048` as `tl.constexpr`, rebuilt and verified the manifest (`mirrored_ring_kv.py` SHA-256 `5f01cb53e338b36b60b33a04bc394a3648ca4e2b378547d0215e47678c6efaf6`), and sent the retained owner's repair request. The owner consumed it, restaged only that changed input, passed the real CUDA smoke, and completed the single frozen producer-plus-consumer component.

Evidence (measured): smoke passed with exact mirror halves and relative L2 `0.0039668`. The candidate invoked the direct E5M2 FA3 consumer exactly once with no merge or fallback, consumed its output, and wrote both mirror positions. Component median was `0.258432 ms` versus `0.283520 ms` for settled-ring control (8.8488% point reduction; 95% lower reduction `5.5137%`). However, the first two decode-transition relative L2 values were `0.0551456` and `0.0552597`, failing the frozen semantic gate; the complete component therefore has no credible positive whole-request bound and projected lower-95 endpoint time remains `0.6501213 s/request`, above the `0.6381105 s/request` ceiling. The conditional c32 endpoint was not started. Actual provider exposure is `$0.28338057535`, below the `$14.00` reservation. Final terminal SHA-256: `f49f7fc1c61df43751dba20a1d7b2a776abbd4296ce9971506665c1888583f4b`; component SHA-256: `277050d79691439607a40364f30b6c6c7ce6446a716d3a8486f848507da001b2`.

Interpretation and next move: this exact mirrored-one-call E5M2 FA3 decomposition is closed as `component_semantic_or_nonpositive_reject`. The owner released the H200 ready while retaining compatible image, checkpoint, Triton, and FA3 caches; do not replay the endpoint or alter the frozen intervention in this project.

## 2026-07-23 — admitted

Use `$kernel-research` for one mirrored-ring producer and one-call direct-E5M2 FA3 consumer. The closed two-call split/merge component is immutable negative evidence. Measure the doubled producer-write cost in the same component, and admit one endpoint only on a credible positive complete bound.

## 2026-07-23 — execution prepared behind the stack

Question: can duplicated local E5M2 writes recover one contiguous FA3 call after charging the producer?

Action: validated `DIRECTOR_BINDING.json`; materialized the bound FA3 extension, settled ring control, endpoint comparator, and runtime inputs under this project; implemented the 2,048-physical/1,024-logical mirrored producer, one-call FA3 consumer, exact component, candidate-only endpoint, immutable manifest, and one bounded repair-capable owner. The component includes doubled decode stores, fresh E5M2-byte extend, wrap, negative padded rows, reorder, slot reuse, prefix restoration, and the predecessor's unit-scale first-two-transition discriminator. The content-identical FA3 binary retains measured 168 registers/thread, 1,024 static shared bytes, and no local memory for its direct-E5M2 hdim-256 single-tile kernel.

Evidence: all local binding, manifest, Python compilation, and shell checks pass. The only admitted H200 is actively claimed and heartbeating for priority-3600 `gemma4_h200_width16384_ring_stack`; its retained owner is at a recoverable pre-science repair handshake. This project has not claimed the bench and actual spend remains `$0`.

Interpretation and next move: the dependency is a typed in-scope queue boundary, not a scientific result. Durable unit `gemma4-mirrored-ring-e5m2-owner.service` waits without spend, then claims atomically and runs the component through the conditional endpoint gate by `2026-07-23T20:15:00Z`.
