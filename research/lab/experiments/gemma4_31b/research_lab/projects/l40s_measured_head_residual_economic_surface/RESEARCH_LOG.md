# Research log

## 2026-07-17 — director delegation

Activated as materially different `$0` evidence while the H200 checkpoint owner runs. Substitute the measured M8/M16/M32 head costs into the exact L40S capacity, queue, and service-time surfaces; exclude rejected or zero-row timing claims; then close the one-byte endpoint or return at most one c16/c32 direct falsifier. Budgets are 35 wall minutes, 1 CPU-hour, 512 MiB, and `$0`; no interaction with the live checkpoint owner and no provider/checkpoint/image/compile/CUDA/endpoint/quality work.

## 2026-07-17 — measured residual surface

Question: do the actual tied-head rows leave enough L40S residual budget at c8/c16/c32?

Action/evidence: consumed the execution-equivalent vLLM L40S head summary and corrected W4/queue/KV artifacts. Measured head seconds/request at 358 output steps were 0.178124/0.090522/0.049804 for c8/c16/c32. Recomputed primary cycles were 8.391/8.415/8.560 s per batch; 10K cycles were 9.211/9.235/9.380 s. c16 and c32 clear the conservative service envelope with 0.337/0.596 s primary residual and 0.286/0.570 s at 10K. c8 fails the conservative envelope. c32 10K is allocator-sensitive with 0.612795 GiB logical headroom.

Interpretation/decision: retain c16/c32 conditionally and rank one exact-revision W4 c16 direct endpoint/quality falsifier. The tied one-byte shared consumer remains terminal `NONE`; no rejected timing claims or provider action were used. The shared inventory command was streamed after a `/tmp` tmpfs-full redirection failure; this has no bearing on the scientific rows.
