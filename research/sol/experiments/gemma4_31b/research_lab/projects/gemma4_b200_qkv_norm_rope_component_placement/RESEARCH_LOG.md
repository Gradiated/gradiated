# Research log

## 2026-07-29T17:48Z — admitted

Admitted a checkpoint-free hardware-transfer discriminator using the frozen
accepted H200 QKV exact-consumer runner. No B200 science or provider mutation
has occurred. The project is non-claimable pending its exact `$5` reservation.

## 2026-07-29T18:16Z — retained pre-science launcher defect

The durable owner claimed the bound B200 at `18:06:30Z`, verified its strict
SSH fingerprint, pulled the pinned image, and staged the immutable runner.
Docker created the bind-mounted `/output` target, while the unchanged runner
correctly requires `mkdir(..., exist_ok=False)` on that exact path. It exited
with `FileExistsError` before `IDENTITY.json`, `SCIENTIFIC_STARTED`, CUDA, or
any result row. This is a zero-sample launcher defect.

The narrow repair is to archive the zero-row root, bind-mount its parent, and
pass a fresh child output directory. The current PID `206050` owner cannot
consume that repair: its `hold_repair()` waits, but its only post-wait path
unconditionally releases the claim to maintenance. No repair request was
written; the claim and live owner remain untouched pending a director rebind.
See `artifacts/b200-qkv-component-20260729t1802z/OWNER_REPAIR_ENTRYPOINT_CONFLICT.json`.

## 2026-07-29T18:25Z — B200 local/global ledger complete; placement-negative

The authorized owner-only output-path repair mounted a parent and passed the
fresh `/output-parent/run` child to the unchanged frozen runner. A root-owned
stale remote staging directory caused one further pre-science `scp` permission
failure; the same claim generation was retained and a fresh user-writable
remote staging root completed the one authorized submission. The retrieved
terminal and `RESULT.json` prove both exact consumer paths and numerical gates:
local candidate `0.223360 ms` (vs H200 `0.227552 ms`) and global candidate
`0.397440 ms` (vs H200 `0.416032 ms`), with relative-L2 `0.0` for both.

At the actual B200/H200 rates, the normalized component-cost ratios are
`1.58254` local and `1.54020` global, so this is a correct within-device
component gain but a hardware-placement negative. The owner retrieved and
hashed the terminal, released the original claim generation ready at 18:25Z,
and did not send endpoint traffic. The terminal's measured registered-start
exposure is `$2.131380`; project settlement conservatively records the
director binding's `$4.608333` full-lifecycle exposure pending the omitted
pre-registration interval reconciliation.
