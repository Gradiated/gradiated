# Research log

## 2026-07-15 — zero-cost MTP bound and capability falsifier

Question: Can native GLM-4.7-Flash MTP plausibly clear the campaign’s 5% c8 SLO-goodput gate?

Action: Audited retained SGLang v0.5.15 launch evidence and prior MTP preregistrations, then ran the deterministic 4-token acceptance/overhead simulation in `run_bound.py`. The model is the retained v8 c8 control (303.9548 output tok/s, 16 requests, 1024 output tokens each). The bound uses `speed=(1+4a)/(verify_cost+4*draft_cost)` and dilutes decode improvement by 90/95/100% decode fractions and 0/10% non-draftable work.

Evidence: `mtp_acceptance_bound.json` records 24 scenario rows. At 95% draftable decode, the minimum acceptance fractions / mean accepted draft tokens for 5% end-to-end gain are: optimistic 0.1207 / 0.483; moderate 0.2663 / 1.065; conservative 0.4119 / 1.648; harsh 0.6767 / 2.707. These are derived bounds, not measured acceptance or speed.

Capability result: EAGLE arguments parse in retained `attempt3-extracted/glm-campaign/server-mtp.stderr.log`, but that launch fails during model initialization; the campaign’s v8–v11 runs never admitted a valid MTP arm, and no acceptance, draft overhead, or verification counters exist. Therefore the native path is unsupported for this campaign’s checkpoint/runtime evidence.

Decision: KILL_FOR_CAMPAIGN. Do not spend on another unchanged MTP attempt. A future campaign may only reopen after a separately validated draft/checkpoint load and counters showing at least the conservative bound (about 1.65 accepted draft tokens per round under the stated scenario), followed by exact-quality and matched c8 A/B gates.
