# Research log

## 2026-07-17 — director admission

Activated independently while the actual L40S online-FP8 component owner runs. It converts exact FP8 KV and attention work into optimistic c12/c14 residual thresholds, without transferring H200 timing or polling the paid owner.

## 2026-07-17 — typed terminal

- **Question:** What exact FP8 attention/KV residual and component headroom remain at L40S c12/c14?
- **Action:** Bound the named geometry, FP8-per-token-head contract, workload, L40S inventory, and economic gate by hash; generated a deterministic calculator and manifest without inspecting any paid-owner state.
- **Evidence:** 142,337,649,600 decode KV bytes/request (139,488,256,000 values + 2,849,393,600 scales), independent of concurrency. Campaign prompt/decode QK+AV are 11.703/1.631 TFLOP. The preregistered one-96-MB-credit residual is 0.164631539 s/request; shared-L2-per-step sensitivities are 0.161427835 at c12 and 0.161901380 at c14. Strict planning/conservative component maxima are 1.229949102/0.698661566 s/request. The 10K/358 c1 residual sensitivity is 0.263597854 s/request.
- **Interpretation:** `residual_threshold_bound`; attention/KV alone does not close either point. FP8 peak is only an absolute arithmetic denominator, and persistent L2 reuse is separately sensitivity-labeled.
- **Next:** Merge only with a typed, identity-matched independent actual-consumer result that is already normalized to seconds/request and excludes attention; use `component + residual <= ceiling`.
- **Artifacts:** `ATTENTION_KV_RESIDUAL_FLOOR.json` SHA-256 `f38704b6ae0e47e389643062c239a492d430079bf80754d8819f9a36b79aef08`; `SOURCE_MANIFEST.json` SHA-256 `a4344e8d7acdc6ebe0c7636677dd4a1547de728fdbdbb6b513c36a79ea877e8d`; calculator SHA-256 `702bf6788131eb12ac1dd10af4e257a7edd43c4b8055be20bc507de8f78af7bf`.
