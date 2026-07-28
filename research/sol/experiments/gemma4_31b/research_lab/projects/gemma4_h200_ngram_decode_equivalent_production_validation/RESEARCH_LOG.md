# Research log

## 2026-07-24 — director admission

Admitted the campaign-required quality decision for the measured
decode-equivalent NGRAM survivor. The persisted c32 result is
`0.625149101968745 s/request`; the ten-row feature difference is whitespace
formatting of an otherwise identical parsed single-tool call. Fresh
same-stack AR and NGRAM GPQA-Diamond/TauBench captures are required. No GPU was
claimed and no provider resource was mutated in this director turn.

## 2026-07-24 — in-claim quality-consumer repairs

The bound packet, H200 claim, and resident checkpoint were verified. Three invalid
pre-result attempts were retained: multiline source records were not parsed as a
JSON stream; a GPQA expected-answer comparison missed source whitespace; and the
TauBench tool schema omitted `properties`, producing HTTP 400. The last attempt
started control but persisted neither GPQA nor Tau rows and never invoked NGRAM,
so it is not a scientific sample. Repair packet `quality-repair4-20260724t1126z`
adds only record parsing, whitespace-normalized GPQA lookup, valid tool schemas,
and per-stage durable row flushing. Its remote bounded owner is running under the
unchanged verifier-bench claim; candidate capture remains unstarted.

## 2026-07-24 — persisted control GPQA retained through Tau repair

Repair4 atomically persisted all 198 control GPQA rows before TauBench reached
the first zero-action task. That task had no tools but was sent with required
tool choice, producing HTTP 400; the first 12 Tau rows are also retained. No
control aggregate or candidate result was produced. Repair5 resumes the same
control producer from those files, sends zero-action tasks without tool fields,
and flushes each remaining Tau row. It must not replay persisted GPQA or Tau
rows; NGRAM remains unstarted until the control stage is complete and zero-HBM
cleanup is proved.

## 2026-07-24 — measured production-quality terminal

Repair5 resumed the persisted control GPQA/Tau rows, completed zero-HBM cleanup,
and captured the one fresh NGRAM arm. Both arms scored GPQA-Diamond `55/198`
(`27.78%`) and TauBench `10/165` (`6.06%`); paired bootstrap deltas and both
95% intervals are exactly zero, satisfying the preregistered three-point
non-inferiority margin. NGRAM used `9,369` completion tokens versus control
`9,387` (inflation `-18`) and its aggregate captured latency was `85.398s`
versus `150.420s`. The semantic production gate passes. Raw captures and
terminal are at `artifacts/quality-final-20260724t1304z`; conservative
claim-to-release provider exposure was `$5.492318`. The verifier H200 was
released ready with checkpoint, image, and caches retained.
