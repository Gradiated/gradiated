# Gemma 4 H200 NGRAM full arrival stream

## Question

Can the fixed 1,036-request production trace cross `$0.14/M` by releasing
every request at its bound `arrival_s`, instead of accumulating requests
behind c32 whole-wave barriers?

## Evidence

The final-tail-only stream completed all requests but rejected that exact
geometry: `776.618343545` seconds, `$0.148020725/M`, peak queue 41, and one
non-tail normalized mismatch at request 32. Release timing itself was
accurate to less than `0.00018` seconds.

The trace still held request 32 from arrival `22.227523626` until the c32
release at `43.760508632`. Full-wave server spans grew from `17.095` seconds
to more than `78` seconds while queueing accumulated. The remaining direct
scheduler question is therefore whether burst barriers, rather than the final
tail, cause the backlog. This is a new client scheduling geometry, not a
replay of the settled tail arms.

## Scope

Run exactly one candidate-only 1,036-request trajectory:

- Preserve the pinned model, image, checkpoint, native depth-12 NGRAM,
  page-1 E5M2 KV, dynamic chunking, request contents, runtime, and resident
  server.
- Release requests 0–1035 individually at their bound `arrival_s` values.
  Do not form c32 client barriers or a c12 tail barrier.
- Apply no source patch, priority policy, threshold bypass, broadcast/sparse
  patch, server reload, or provider mutation.
- Compare normalized `output_ids`, finish reason, and usage against the exact
  bound tail-overlap rows for every request identity. Ignore raw HTTP
  envelopes.
- Persist planned/actual release timing, per-request completion, queue/cache
  and NGRAM telemetry, reliability, elapsed time, and economics.
- Replay no comparator, wave, tail, component, prefix, suffix, or settled
  arm.

## Decision

Retain full-arrival streaming only if all 1,036 requests complete with exact
normalized semantics, zero failures, final server queue zero, peak queue at
most 30, no growing release drift, and planning cost at or below `$0.14/M`
(`734.536113231` seconds). Otherwise close this client scheduling geometry.

## Resources

Use only retained bench `h200-ngram-verifier-e00kcm9nfhwt7e7gbc` and its
verified healthy `gemma4-ngram-tail-overlap` server. Reserve at most `$3`,
write at most 6 GiB of artifacts, and release by
`2026-07-25T03:20:00Z` under the verified
`2026-07-25T03:30:00Z` watchdog. Researchers must not create, reload, stop,
delete, or otherwise mutate provider resources outside the candidate request
trajectory.
