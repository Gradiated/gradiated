# Research log

## 2026-07-24 — director admission

Promoted the quality-qualified NGRAM endpoint to one direct sustainable-cost
measurement. Assigned the short-deadline warm H200 for a separate 10K c1 view
and one fixed 90%-capacity arrival stream with exact cache accounting. No
claim, guest command, server, or scientific arm was started by the director.

## 2026-07-24 — execution started

Frozen `IMMUTABLE_CONSUMER_v2.json` (`7abdf854…3d9488`) from the bound launch,
trace, and quality identities, then atomically claimed the assigned H200 at
13:24:56Z. A detached remote owner started at 13:25:36Z. Its first failure was
a local `Path + str` artifact-write bug before scientific invocation; the next
attempt reached the server but the OpenAI completion endpoint rejected the
token-list payload with HTTP 400 before a 10K result. Both are preserved in
the remote owner log. The consumer was repaired in place to use SGLang's native
`/generate` token-id transport and relaunched at 13:28:28Z under the same
claim. Checkpoint loading is in progress; no valid 10K or primary sample has
yet been persisted.

## 2026-07-24 — supervisor unblock amendment

The detached owner had actually exited at `13:30:07Z`; the stale project
status incorrectly reported it as loading. Its final HTTP 400 occurred before
a valid 10K response because the inherited runtime was launched with
`--context-length 5000` for a 10,000-token prompt plus 358 requested output
tokens. The primary consumer also serialized requests and therefore could not
realize the admitted open-loop arrival process.

`REPAIR_PACKET.json` freezes the causal repair: use context 11,000 only for
the disjoint 10K view, restart the original context-5,000 runtime for the
primary workload, and submit the fixed arrival schedule through 32 bounded
workers with unique deterministic suffixes. No valid sample is replayed.
Move the repaired consumer to the compatible warm verifier H200 whose
watchdog remains active through `17:00Z`.

## 2026-07-24 — valid sustainable-cost terminal

The repaired split-context consumer ran once on the retained verifier H200.
The separate 10,000-input/358-output request completed with exact usage
accounting in `5.667831 s`. The original context-5,000 runtime then completed
all `1,036/1,036` primary requests and `4,736,592` total tokens without a
failure in `729.863070 s`.

Measured throughput was `6,489.6995 tokens/s`, corresponding to
`$0.139109/M` raw GPU cost at the campaign's `$3.25/H200-hour` production
planning rate. Across 360 two-second samples, mean GPU utilization was
`96.31%`, median utilization `97%`, mean power `508.34 W`, and maximum power
`558.20 W`.

The admitted `1.439656551 request/s` arrival rate was not fully sustainable.
Client queue delay was negligible through roughly request 700, then latency
rose sharply: p50 request latency was `2.529 s`, p95 `23.651 s`, and final
client queue delay reached `8.148 s`. The late transition, rather than a
general utilization deficit, is the next causal opportunity; inspect NGRAM
corpus/state growth and lifecycle behavior before making a durable sub-$0.14/M
claim. The raw terminal, request rows, power samples, metrics, owner evidence,
and hashes are retained under
`artifacts/sustainable-repair3-20260724t1410z/`.

The project consumed `$2.8725687006` of its `$5` reservation across the
invalid short-watchdog claim and repaired claim. The repaired bench was
released ready at `14:35:00Z` with checkpoint, image, JIT, and runtime caches
retained.

## 2026-07-24 — active-owner snapshot

At the grouped `14:19Z` snapshot, the sole detached owner (`pid 52118`) was
live on claimed `h200-ngram-verifier-e00kcm9nfhwt7e7gbc`. It had atomically
persisted `TEN_K.json`, restarted the fixed-5K context server, and entered the
frozen primary open-loop stage (`1036` scheduled arrivals). GPU telemetry was
95% utilization, 123432 MiB HBM, and 493.88 W. Ownership and forward progress
are current; no second owner, replay, or extra poll was made.

## 2026-07-24 — current owner snapshot

One non-blocking snapshot found the same remote-shell owner (`pid 52118`) live
in `primary_open_loop`; `TEN_K.json` remains the only completed stage and no
`FINAL_TERMINAL.json` exists. The active fixed-context server reported 92%
GPU utilization, 123436 MiB HBM, and 479.80 W. The claim and owner are left
unchanged for the frozen stream to finish.

## 2026-07-24 — continued active-owner snapshot

The same owner is live in the frozen primary stage; the only persisted
decision-bearing stage remains `TEN_K.json`, and no terminal is present.
Current telemetry rose to 97% GPU utilization at 123436 MiB HBM and 512.14 W.
No replay, restart, release, or additional owner was created.

## 2026-07-24 — latest active-owner snapshot

PID 52118 remains live in `primary_open_loop`; `TEN_K.json` is retained and
no terminal exists. The current execution sample is 92% GPU utilization,
123436 MiB HBM, and 492.22 W. The existing claim and single owner remain
unchanged.

## 2026-07-24 — unchanged stream snapshot

The sole owner remains live with the same stage and evidence set: valid
`TEN_K.json`, active 1,036-arrival primary stream, and no terminal. Current
device telemetry is 93% GPU utilization, 123436 MiB HBM, and 497.36 W. No
lifecycle or workload mutation was made.

## 2026-07-24 — saturated active-owner snapshot

The owner remains live with no terminal and unchanged persisted stages. The
primary stream now reports 100% GPU utilization, 123436 MiB HBM, and 522.44 W,
which is forward progress under the admitted workload. The claim and owner
were not modified.

## 2026-07-24 — active-stream snapshot

The primary owner remains live with only the admitted 10K stage persisted and
no terminal. Current execution telemetry is 96% GPU utilization, 125778 MiB
HBM, and 500.63 W. The claim and owner remain unchanged.

## 2026-07-24 — latest stream snapshot

The detached owner is still live in the same frozen primary stage, with no
terminal and no additional persisted stage. Current utilization is 100%, HBM
is 128514 MiB, and power is 490.77 W. No mutation was made.
