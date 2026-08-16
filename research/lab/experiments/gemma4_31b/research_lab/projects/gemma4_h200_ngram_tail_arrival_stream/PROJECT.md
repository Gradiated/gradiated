# Gemma 4 H200 NGRAM streamed final arrivals

## Question

Can the fixed 1,036-request production trace cross `$0.14/M` by releasing
the final 12 requests at their individual bound arrivals instead of holding
them behind one c12 tail barrier?

## Evidence

The completed final-tail overlap was exact for all 1,036 normalized semantic
rows with zero failures and stable c32 waves, but finished in
`734.979990111` seconds at `$0.1400846013723668/M`. The economic boundary is
`734.536113231` seconds, a remaining gap of `0.443876880` seconds.

Requests 1024–1035 have bound individual arrivals from
`711.280756017772` through `718.9214672640567` seconds. The completed arm
withheld all 12 until `718.9215570489996`, delaying the first tail request by
about 7.64 seconds. Its peak queue of 30 also proves the inherited
tail-only queue limit of 12 was not a valid whole-server gate.

## Scope

Run exactly one candidate-only 1,036-request trajectory:

- Preserve the pinned model, image, checkpoint, native depth-12 NGRAM,
  page-1 E5M2 KV, dynamic chunking, fixed request contents, and waves 0–31.
- Release each of requests 1024–1035 at its own `arrival_s` from the bound
  prior request rows. Do not hold them for request 1035 or the completion of
  wave 31.
- Apply no broadcast/sparse patches, threshold bypass, priority policy,
  source patch, server reload, or model/runtime change.
- Compare `output_ids`, finish reason, and usage against the bound semantic
  rows for all 1,036 request identities. Ignore timing-bearing raw envelopes.
- Persist individual planned/actual tail releases, per-request completion,
  full-wave timing, queue/cache telemetry, reliability, and economics.
- Replay no comparator, component, prefix, suffix, wave-frontier, tail
  overlap, or other settled arm.

## Decision

Retain streamed final arrivals only if all 1,036 requests complete with exact
normalized semantics, zero failures, final server queue zero, peak queue no
higher than the measured canonical maximum of 30, stable full-wave release
drift, and planning cost at or below `$0.14/M` (`734.536113231` seconds).
Otherwise close this exact client scheduling geometry.

## Resources

Use only retained bench `h200-ngram-verifier-e00kcm9nfhwt7e7gbc` and its
healthy resident `gemma4-ngram-tail-overlap` server. Reserve at most `$3`,
write at most 6 GiB of artifacts, and release by `2026-07-25T03:20:00Z`
under the verified `2026-07-25T03:30:00Z` watchdog. Researchers must not
create, stop, reload, or delete provider resources.
