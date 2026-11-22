# Physical comparison harness

`prepare_packet.py` pins the Experiment 13 on-chip control, passing candidate
route and replay, Experiment 17 restoration, and exact retained host tools from
the Mac evidence store. Its readiness input comes from a same-boot, root-private
reuse check that verifies the old staged control and shared software by size and
SHA-256. The detached board supervisor checks every staged member again before
taking exclusive ownership. The local preparation directory of a completed run
preserves the USB slice sender, reassembler, replayed checksums and board receipt.

The board stages only the two on-chip trial images and their program overlays.
`lifecycle.py` uses the original interface, keeps the 50 MHz clock overlay, and
runs three image loads across A1/B1/B2/A2. It opens a resident session per
powered block and after each image load for the smoke set. It restores the original
image, interface, UIO permissions and original model, then verifies all 320 BOS
scores. The separate restoration deadline applies after any changed-board failure.

`measurement.py` pins request order, per-request watchdogs and exact first,
last and completion cycle checks. `bench_fixture.py` runs the existing
autonomous compact path and 20 Hz VCC_SOM sampler identically in both arms.
`score_fixture.py` verifies the raw capture against the workload, replay,
order, sampler trace and bracket evidence. `write_record.py` checks archive
and restoration evidence, fills the standard scorecard, and derives paired and
pooled summaries. The physical run record pins the actual raw evidence and
source patch.

[Experiment 18 protocol](../../../../../experiments/kv260-probability-div-v1.md)
