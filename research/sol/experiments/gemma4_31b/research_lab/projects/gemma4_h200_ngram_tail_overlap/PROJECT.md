# Gemma 4 H200 NGRAM final-tail overlap

## Question

Can the fixed 1,036-request production trace cross the `$0.14/M` planning
cost boundary by submitting the final 12 requests at their planned arrival
while the last c32 wave is still completing, instead of serializing that tail
behind a whole-wave barrier?

## Why this is the next experiment

The completed frontier stack was economically flat: `734.935408296` seconds
and `$0.140076104/M`, only `0.239959425` seconds (`0.032640%`) faster than the
frozen c32-wave control. Its broadcast and sparse source reductions therefore
do not justify another integration repair.

The same terminal exposes a distinct scheduling bottleneck. The final c12
tail was planned for `718.921467264` seconds but released at
`728.056302903`, a `9.134835639`-second barrier miss, while every full wave
remained stable at roughly `17.43–17.47` seconds with no growing drift. The
`$0.14/M` boundary requires elapsed time at or below `734.536113231` seconds,
only `0.399295065` seconds below the latest result.

## Scope

Run exactly one candidate-only 1,036-request trajectory:

- Preserve the pinned model, image, checkpoint, page-1 E5M2 KV, dynamic
  chunking, c32 geometry, fixed arrivals, and native depth-12 NGRAM.
- Remove the rejected broadcast/sparse frontier stack; change only submission
  scheduling.
- Keep waves 0–31 at c32. Submit the final c12 tail at its planned
  `718.921467264`-second arrival without waiting for wave 31 to finish.
- Permit at most 12 transient server-queued tail requests; require the queue
  to drain to zero, with no reload, OOM, or request failure.
- Compare semantic fields only: `output_ids`, finish reason, and usage for all
  1,036 request identities. Raw HTTP response bytes are timing-bearing
  envelopes and are not a semantic comparator.
- Replay no control, frontier stack, threshold bypass, component, prefix,
  suffix, quality, or prior scheduling arm.

## Decision

Retain the tail-overlap scheduler only if all 1,036 requests complete with
normalized semantic equality, zero failures, bounded transient queueing,
final queue zero, no growing full-wave release drift, and planning cost at or
below `$0.14/M` (`734.536113231` seconds maximum at the bound planning rate).
Otherwise close this exact scheduling geometry and preserve its telemetry for
the next materially different mechanism.

## Resources

Use only retained bench `h200-ngram-verifier-e00kcm9nfhwt7e7gbc`. Reserve at
most `$3`, add at most 6 GiB of artifacts, and release by `2026-07-25T02:50:00Z`
under the verified `2026-07-25T03:00:00Z` watchdog. Researchers must not
create, stop, or delete provider resources.
