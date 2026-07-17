# Research log

## 2026-07-16 — Director opening handoff

Rehabilitate the scientifically unmeasured upstream one-head FP8 MLA line while the W4 owner holds the provider lane. Correct all nine audited packet defects in one bounded `$0` turn and emit one directly runnable content-addressed command/artifact manifest. This packet is preparation for a later target-GPU component measurement, not CUDA, performance, capacity, or quality evidence. Close FP8 if the exact packet cannot be made coherent; do not open another support gate.

## 2026-07-16 — Packet ready for CUDA

Question: can the exact v0.25.1 one-head packet be made directly runnable without provider spend?

Action and evidence: added the exact benchmark, matching remote artifact script, focused test, and `PACKET_MANIFEST.json`. It binds commit `752a3a504485790a2e8491cacbb35c137339ad34`, image digest `94a0aff7a289f23bcefa189d11841e487991405d86da782a63bf6e5f95d0d39a`, and cached v0.25.1 source hashes. Offline self-test passed (`slot_count=64`, `b32_c8193_bytes=151289864`, L40S splits `32`, finite/saturation predicate exercised); focused packet test, Python compilation, shell syntax, and shared-controller CLI contract checks passed. The future CUDA path invokes upstream writer, stage, and reduction separately, applies a masked finite BF16/FP8 oracle predicate, rejects saturation, and records writer/stage/reduction/full timing.

Interpretation and next move: `PACKET_READY_FOR_CUDA`. Queue exactly one later direct component measurement after live W4 and unchanged-stock endpoint; this project remains `$0` and does not authorize spend.

## 2026-07-16 — Director admission override: PACKET_CLOSE

Pinned-source audit invalidates CUDA readiness. The stage-one call uses a stale signature, omits required scale/runtime arguments and `IS_MLA=True`, and supplies page stride `576` where the pinned layout requires `9,216`. It forces 32 splits although upstream selects 16 at context 8,193 and 32 at 9,215; its absmax/448 cache is rejected by its own saturation threshold; and its numerical reference is reconstructed from already-quantized cache rather than independent BF16 inputs. The manifest command also omits required controller arguments and offers only a textual retention trigger. Preserve the improved source hashes, slots, artifact roots, and attention scale as partial evidence, but close `PACKET_CLOSE`. Do not buy another setup-heavy null or open another readiness successor.
