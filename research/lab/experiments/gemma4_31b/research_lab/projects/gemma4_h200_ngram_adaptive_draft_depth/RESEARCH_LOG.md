# Research log

## 2026-07-24 — admitted

The exact sparse-penalty component is retained as a simple incremental gain,
but its endpoint improvement is only about 0.107%. Bound telemetry shows a
sharper runtime transition: acceptance averages 11.876 tokens at 1–7 running
requests and about 5.1 at eight or more while verification remains depth 12.
This project tests one frozen high-load depth of six.

## 2026-07-24 — valid negative component; endpoint gate closed

Question: can the frozen depth-12-below-eight/depth-6-at-eight-or-more rule
halve high-load target rows without changing deterministic greedy outputs?

Action: hash-checked and materialized every bound input, stacked the retained
direct sparse min-token change, implemented dedicated depth-6 request-major
buffers, and ran a fresh eight-request depth-12 reference plus one real
depth-6 CUDA component. Pre-science donor/retrieval defects and two corrupt
observer/integration attempts were preserved and repaired without counting
them as samples. The final localized repair disabled fixed depth-12 CUDA graphs
for depth-6 target verification and made the observer serialize the real
accepted/bonus-token rows.

Measured evidence: the final depth-6 call used exactly `48` target rows for
eight requests (`6/request`) and saw the same first-six draft-token rows as
the depth-12 reference for all `8/8` prompts. However, target-prediction
prefixes matched for `0/8`, accepted/bonus-token rows matched for `0/8`, and
one request changed accepted-draft count. A subsequent depth-6 verify reached
a CUDA illegal-memory access and all eight HTTP requests failed. The terminal
is content-addressed at
`artifacts/adaptive-depth-20260724t215325z/snapshots/d47b1a65.../`.

Interpretation: the row reduction is physically real, but this fixed-width
runtime's attention/metadata path is not semantics-preserving when verification
depth changes. This exact 12/6 implementation is rejected. The conditional
1,036-request endpoint remained unstarted, as required. Conservative cumulative
provider exposure was `$0.73137179035`; the bench was released to maintenance.
