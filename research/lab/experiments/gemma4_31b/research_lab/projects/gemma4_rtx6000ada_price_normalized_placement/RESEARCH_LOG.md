## 2026-07-28 — current RTX 6000 Ada placement surface

Question: can a commercially obtainable single RTX 6000 Ada run the fixed
Gemma 4 31B dual-KV representation at a sustainable cost at least 20% below
the qualified H200 result, without transferring L40S throughput?

Action: captured current unauthenticated direct-provider and NVIDIA sources,
checked the shared price/capability inventories, the fixed campaign target,
the exact L40S memory/representation terminal, the current L40S readiness
artifact, the empty lab inventory, and the archived RunPod control-plane
diagnostic. Used no provider API, account, credential, SSH, GPU, endpoint, or
paid action. Derived every venue hurdle from the fixed
`3.25 * 0.500119281574996 = 1.625387665118737` price-time budget and added an
explicit 90%-utilization planning sensitivity for 100 GB storage, headroom,
non-GPU cost, failures, orchestration, and unknown venue availability.

Evidence: RunPod Secure currently lists a dedicated RTX 6000 Ada Pod with
48 GB ECC, 10 vCPUs, 167 GB RAM, and `$0.84/hour`; Community is
`$0.74/hour`. Verda lists a 10-CPU/60-GB instance at `$1.04/hour`
on-demand, `$0.364/hour` preemptible, and public 8%/25% one-/two-year
discounts, giving derived committed rates of `$0.9568/$0.78`. QuantaCloud's
`$0.71/hour` row lacks the required bundle/runtime join, and Spheron's May
rate is no longer in its current catalog. The current raw service ceilings
are `1.934985 s/request` for RunPod Secure and `2.083830 s/request` for
Verda two-year; the optimistic burden-adjusted A=1 ceilings with standardized
storage are `1.553803` and `1.642908 s/request`.

Interpretation: preserve the placement as a real production lead, but admit no
experiment. Public sources do not prove current per-region stock, at least
`48,305,799,168` guest-visible bytes, ECC/no-slice state, the host driver,
sustained clocks, or availability burden, and the project has no authorized
authenticated route. Hardware FP8/INT4 capability and shared SM89 identity do
not establish the exact runner or endpoint throughput.

Next: a later director may bind one authenticated full-card RunPod Secure or
Verda instance and positive spend reservation. The first paid work must verify
the device/runtime contract, run matched RTX components, and only then run one
exact c32 endpoint if the component margins pass.
