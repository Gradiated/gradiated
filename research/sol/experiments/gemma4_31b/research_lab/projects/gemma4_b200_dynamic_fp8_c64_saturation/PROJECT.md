# B200 runtime-FP8 c64 saturation

## Question

Does the already-loaded runtime dynamic-FP8 Gemma 4 endpoint on the retained
B200 have enough unsaturated scheduling capacity at c32 that one c64 campaign
workload arm reduces service time to at most
`0.500119281574996 s/request`, or otherwise improves price-normalized
throughput enough to remain a useful stacked result?

## Why this matters

The authoritative absolute candidate terminal
`../gemma4_b200_dynamic_fp8_endpoint/artifacts/b200-dynamic-fp8-repair2-20260728t1517z/final-retrieval/handoff/DYNAMIC_FP8_TERMINAL.json`
(SHA-256
`4930d9666167e20096f0343736db6d0ed721ea30fad68f5fc4010ccfeeee9acf`)
measured a valid c32 runtime-FP8 endpoint at `0.633995593312477 s/request`
with 32/32 complete requests. FP8 consumption was proven by the selected
`CutlassFP8ScaledMMLinearKernel`. Duplicate endpoint executors make the
predecessor's BF16-paired reduction invalid, but do not invalidate this
absolute candidate or its 26.8% miss versus the campaign target. A single c64
measurement on the healthy resident server is the cheapest direct saturation
test.

## Scope

- Treat the hashed `DYNAMIC_FP8_TERMINAL.json` above as the authoritative
  source for checkpoint revision, runtime representation, c32 workload bytes,
  token accounting, and absolute comparator. Extract identities mechanically.
  Do not consume or report the invalid BF16-paired reduction.
- Reuse the healthy resident dynamic-FP8 server
  `gemma4-b200-dynamic_fp8_candidate` on port `30001`. Do not restart the
  server, restage the checkpoint, pull an image, or touch rejected NVFP4
  shards.
- Run exactly one c64 arm with the same per-request 4,214 prompt and 358
  completion-token workload and the same timing boundary as the predecessor.
  No c48/c64 sweep and no new BF16 control.
- Before `science_started`, prove there is no live predecessor endpoint
  executor, foreground SSH consumer, or owner retry capable of submitting the
  same scope. Use one fresh remote c64 output generation and exactly one
  driver under the durable owner.
- Require 64/64 complete nonempty responses, exact request/token accounting,
  runtime-FP8 consumption evidence from the resident server, service seconds
  per request, batch time, failures, and experiment plus price-normalized
  cost.
- Compare directly with the immutable predecessor c32 candidate and the fixed
  `0.625149101968745` denominator / `0.500119281574996` target. Preserve a
  reproducible positive result even if it does not close the full target.
- Stop after the one c64 result. A failure before `science_started` may use
  the retained-claim repair handshake; a submitted c64 arm must not replay.

## Immediate evidence path

Before any claim, read
`DIRECTOR_B200_C64_SERIALIZED_ABSOLUTE_BINDING_20260728T1536Z.json`, adapt the
predecessor endpoint driver into a minimal `b200_fp8_c64_driver.py`, and create
`b200_fp8_c64_saturation_owner.sh`. The owner must read connection identity
from the exact bench record, heartbeat the claim, confirm the named healthy
container and FP8 server without mutation, write `science_started`
immediately before the c64 submission, retrieve the terminal, and release.
Persist `PRECLAIM_TERMINAL.json` with both hashes and the mechanically
extracted immutable identities. Do not claim until this project's reservation
is durable and a later director turn marks the maintenance bench ready.

## Resources and bounds

- Intended bench:
  `b200-nvfp4-computeinstance-i00rqcq5yzr6xc991j`
- Provider state: retained B200 in maintenance with healthy runtime-FP8 server
- Authorized project ceiling: `$5.00`
- Claimed compute ceiling: 45 minutes
- Additional storage: 2 GiB
- Provider creation: forbidden; reuse only

## Portfolio-changing result

- A c64 endpoint at or below the fixed target becomes the next sustainable
  cost candidate.
- A smaller clean gain is retained for stacking and informs the next
  saturation/serving decision.
- Flat or worse c64 closes higher-concurrency saturation for this exact
  runtime and redirects B200 work to source-level hot-path changes.
