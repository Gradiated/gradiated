# Research log

## 2026-07-24 — director admission

Admitted one deep allocator-ownership project after the exact SWA leaf split
reduced transition occupancy by 9,170 tokens but left the request-809 HBM step
unchanged. PyTorch reserved bytes grew `5,960,105,984`, scope-matched to the
`5,166 MiB` HBM staircase.

The first paid evidence is one bounded allocation-history prefix through
request 870, not another full stock replay. It must identify and byte-reconcile
one concrete graph pool, target-verification workspace, or topology-shaped
tensor owner. Only a material, actionable site admits one source-specific
reuse/preallocation intervention and one candidate-only full trajectory.

## 2026-07-24 — allocation owner confirmed; memory fix is service-negative

Question: bind the request-809 PyTorch-reserved/HBM staircase to one concrete
allocation owner and conditionally test one semantics-preserving reuse.

Action: hash-checked all five director-bound inputs, captured the installed
SGLang/PyTorch sources before stopping the donor, and ran one stock-SWA
allocation-history prefix through request 870. The material owner admitted one
frozen candidate that broadcast the per-request additive penalty workspace
over NGRAM target tokens instead of materializing its expanded
`repeat_interleave` tensor. Ran that candidate once for all 1,036 requests.
The valid attribution producer was preserved across a controller wait-deadline
repair; a replacement PID owner adopted the live candidate without replay and
kept the same claim heartbeating through retrieval and release. The two
ordinary controller amendments are recorded in `CONTROLLER_AMENDMENT.json`.

Evidence: the stock prefix completed `871/871` with exact semantics.
`BatchedPenalizerOrchestrator.apply` at `sampling/penaltylib/orchestrator.py:77`,
called by `NgramVerifyInput.verify`, allocated the expanded FP32
`[bs*12, 262144]` tensor. Nineteen inactive segments in pool `(0, 0)` totaled
`5,410,652,160` bytes, exactly the measured reserved delta and `90.78%` of the
prior bound growth; HBM rose `5,160 MiB`. The candidate completed `1,036/1,036`
with exact output tokens, finish reasons, and usage, zero failures,
retractions, or final server queue. Sampled HBM range fell to `512 MiB`
(`90.08%` staircase reduction) and planning cost was `$0.1397649/M`.

Interpretation: allocation ownership and the memory prediction are confirmed,
but the service hypothesis is negative. Candidate client drift still ended at
`7.8578 s` and grew `+0.042519 s/request` over the final 100, failing both
sustainability gates. The staircase is a batch-growth symptom and capacity
cost, not the primary throughput-collapse owner. See
`ALLOCATION_ATTRIBUTION.json` and `RESULT_ANALYSIS.json`; replay neither arm.
