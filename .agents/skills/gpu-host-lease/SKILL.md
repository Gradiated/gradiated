---
name: gpu-host-lease
description: Lease a whole GPU host out of the serving pool for hand-run work such as training or experiments, use it safely, and hand it back so it is wiped and rejoins the pool. Use whenever an agent wants to run anything by hand on a GPU host, or to SSH into one for more than read-only inspection.
---

# GPU host lease

Hand-run GPU work happens only on a host you hold a lease on. A lease takes the
whole host out of the pool: the gpu-fleet operator moves its model replicas
elsewhere, drains it and keeps it cordoned. Handing it back re-images the host,
which deletes everything on it, before it rejoins the pool. The mechanism is
described in [Leasing a host](../../../tools/virtual-kubelet/README.md#leasing-a-host).

## Lease

1. Pick a host: `grad-ctl gpu lease status`. Choose one with the GPUs
   you need that is `in pool`. Reserved hosts, cordoned hosts and hosts with a
   RunPod volume are refused.
2. Request it for the time you need, with a purpose a teammate would understand:
   `grad-ctl gpu lease acquire <instance> --hours 6 --purpose "..." --holder <agent or person>`.
   Leases are preemptible by default: if a model needs the host, the operator
   takes it back and wipes it with no warning. Add `--no-preempt` only for work
   that cannot lose the host, such as a run without checkpoints, and say why in
   the purpose.
3. `grad-ctl gpu lease wait <instance> --holder <the same holder>`
   until it prints `leased`; it fails if someone else holds the host.
   Draining can take as long as the host's models take to start elsewhere. If it
   reports `Lease failed`, the reason says why (no room for its replicas, a
   training job, or a refused host). The operator does not retry and removes
   the request; pick another host, or run `acquire` again later. Do not cordon,
   drain or delete pods yourself to make room.

Reach the host with Tailscale SSH as root, as in
[instance setup](../../../docs/INSTANCE_SETUP_PLAN.md#credentials-and-traffic).

## While leased

- Before each session, run `grad-ctl gpu lease status <instance>` and confirm it is
  `leased` to you and not near `until`. Never touch a host you do not hold. A
  host that shows anything else, such as `returning` or `in pool (last lease
  preempted)`, is no longer yours, even if SSH still works.
- The host is yours: use any GPU and any path. Keep your files under one
  directory, such as `/workspace/<project>`, so you know what to copy out.
- Do not change the RunPod pod's image, environment, ports or state, stop the
  host agent or Tailscale, or install drivers. The return depends on them, and
  provider changes can lose the reservation.
- Write results you need, checkpoints and logs to S3 as you go. The return
  deletes everything on the host, and a crashed or expired session gets no
  second chance to copy them out.
- If you need longer, `grad-ctl gpu lease extend <instance> --hours N` sets the new
  remaining time. At `until` the operator returns the host whether or not you
  are done.

## Hand back

1. Stop your processes and confirm everything you need is in S3.
2. `grad-ctl gpu lease release <instance>`, as early as you can.
3. Report the host, the lease's purpose, and where the results are in your
   response or PR. The host rejoins the pool after a re-image, enrollment and a
   five-minute soak; `status` shows `returning (<step>)` until then.

If you ran untrusted code as root, say so: the host's management key survives
the return and should be rotated by hand.
