# Research log

## 2026-07-16 — zero-cost committed-topology gate: unbound

**Question.** Can the recovered student39 c32 L40S point fit the fixed all-in production caps once mandatory ancillary costs and restart semantics are bound?

**Action.** Performed one bounded local evidence pass over the shared production-rate inventory, measured L40S VM-plus-disk summary, campaign ledger, and available instance specifications. No provider mutation, vendor contact, login, or GPU-price refresh occurred. Also checked the named recovery-canary project once; it remains a quality dependency and does not provide production-topology terms.

**Evidence.** The `$1.10/GPU-hour` rate is a derived 12–24 month GPU-only planning rate, not a matching all-in quote. The sole observed topology is a measured `$0.8581222/hour` preemptible single VM plus disk (`1gpu-16vcpu-64gb`, 100 GiB NETWORK_SSD); the ledger explicitly excludes public IPv4 and egress, and the instance contract uses `on_preemption=STOP` with `recovery_policy=FAIL`. It cannot establish committed CPU/RAM, persistent storage, network/egress, control/support, billing-minimum, or restart/replacement terms.

**Interpretation.** **Unbound** for both caps: the 8h case has only `$0.013384/hour` ancillary headroom and the 24h case `$0.045885/hour`. Since required production costs and restart semantics are unpriced, treating either as zero would violate the project contract. The lifecycle arithmetic itself remains conditional rather than disproven.

**Artifact / next move.** [STUDENT39_L40S_ALL_IN_GATE.json](STUDENT39_L40S_ALL_IN_GATE.json) and [all_in_gate.py](all_in_gate.py) reproduce the result. Keep the L40S production claim closed unless a content-bound committed 8–64 GPU topology term binds every required component and restart semantics.
