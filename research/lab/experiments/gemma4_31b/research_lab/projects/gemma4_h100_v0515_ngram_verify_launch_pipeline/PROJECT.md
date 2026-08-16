# H100 v0.5.15 NGRAM verification launch pipeline

## Question

Can the exact SGLang v0.5.15 native depth-12 NGRAM path remove one
semantics-preserving launch, host synchronization, or CUDA-graph boundary on
H100, with enough conservative whole-request relevance to change sustainable
fleet economics?

## Why this matters

The settled H100 discriminator is `0.707333994` seconds/request. One-replica
periodic stability requires `0.693939640` seconds/request, while strict 90%
headroom requires `0.624545676`. The direct 791-request endpoint is running,
and two H100 local-KV data-placement hypotheses are already closed. Offline
source work can prepare a distinct compatible follow-up without touching the
live bench.

## Scope

Using `$kernel-research`, reconstruct the exact NGRAM proposal, verification,
hybrid-attention, CUDA-graph, result-transfer, acceptance, and scheduler
sequence from the bound v0.5.15 sources. Separate compulsory compute from
avoidable launches, graph breaks, and host-visible synchronization. Produce
at most one source-complete semantics-preserving candidate with a CPU
event/state oracle and the smallest checkpoint-free H100 falsifier, or return
typed `none`.

Static event counts and timing envelopes are analytical or synthetic, not
measured speedups. Do not touch the live endpoint project or provider.

## Contract

All source identities, exact-result inputs, budgets, prohibitions, and output
requirements are frozen in `DIRECTOR_BINDING.json` at SHA-256
`db7ba5111865313e23b15980249a835fbd9bdf3e4304f157cb6f4a1612419dd4`.

## H100 falsifier iteration

The source iteration nominated `single_packed_cpu_full_mask_staging` and the
endpoint owner has now released the warm H100. The only admitted next result is
one checkpoint-free exact-consumer stock/candidate pair plus one short Nsight
Systems trace. It must preserve every producer and attention-consumer state,
reduce the predicted row-wise transfer/operation fanout, and lower measured
preparation-plus-consumer time outside noise.

The sole endpoint is consumed and showed a normalized semantic divergence, so
this component cannot trigger an endpoint replay or establish production
eligibility. The exact H100 iteration contract is frozen in
`DIRECTOR_H100_FALSIFIER_BINDING.json`.

## Fresh endpoint integration iteration

The component passed exactly, and the campaign cap now supports an independent
direct endpoint lane. Integrate only `single_packed_cpu_full_mask_staging`,
then compare stock and candidate on one new content-addressed 791-request
workload derived from the bound arrival and length trace. Capture verify-step
frequency so the component result receives a measured whole-request
interpretation. Candidate outputs must match the contemporaneous stock arm;
neither historical endpoint may be replayed or used as a direct delta.

The endpoint contract, identities, fresh-workload construction, budgets, and
cleanup requirements are frozen in
`DIRECTOR_PACKED_MASK_FRESH_ENDPOINT_BINDING.json`.
