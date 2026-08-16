# Research log

## 2026-07-24 — admitted

Allocator attribution proved the dense NGRAM penalty temporary owns 90.78% of
the reserved-memory staircase. Exact broadcast reuse removed 90.08% of the
HBM step but left +0.042519 seconds/request late drift and a 7.858-second
final lag. This project tests the materially distinct remaining work: the
dense full-vocabulary penalty pass immediately before greedy verification.

## 2026-07-24 — exact sparse component positive; endpoint terminal negative

Question: is the remaining dense FP32 penalty consumer the late throughput
collapse owner? Action: captured the installed penalty/verify sources, measured
one real draft-12 `[384, 262144]` call, then ran the sole admitted direct sparse
min-new-token endpoint against the bound 1,036-row comparator.

Measured evidence: `BatchedMinNewTokensPenalizer` was the only active class,
with 32 nonzero coordinates (384 after draft-12 expansion). Direct column
writes preserved the full modified logits and all 384 greedy tokens exactly
while reducing median penalty-plus-argmax time from 1.193312 to 0.185936 ms
(84.42%). The endpoint matched 1,036/1,036 token sequences, finish reasons, and
usage rows with zero failures/retractions and zero final server queue. It was
only 0.107% faster than the bound broadcast endpoint: 732.520 versus 733.303
seconds, `$0.139616/M` versus `$0.139765/M`. Final client drift remained 7.095
seconds and the final-100 slope remained positive at +0.038268 seconds/request.

Interpretation: the dense penalty application is a valid small exact
inefficiency, but it is not the late-collapse owner and fails the endpoint
retention rule. Close this mechanism; do not replay either component or
endpoint. Evidence is in `RESULT_ANALYSIS.json` and
`artifacts/sparse-penalty-20260724t210733z/`.
