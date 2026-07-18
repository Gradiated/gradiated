# Research log

## 2026-07-18 — exact H200 FP8 falsifier prepared; pool claim blocked

Question: can one authenticated checkpoint-free exact-shape measurement show at least 20% component-cost margin for a supported precision/hardware pair over H200 BF16?

Action: ranked the shared price/capability inventory, selected H200 native E4M3 versus BF16, and implemented `h200_fp8_exact_shape_falsifier.py`. It invokes the real `torch._scaled_mm` symbol on all six Gemma text-linear shapes at M12 decode and M3679 prefill, the tied 262144x5376 head, BF16 local/global decode attention, and BF16/E5M2 local/global KV writes. Timed outputs feed numerical oracles and the weighted component-floor aggregation. Three atomic pool claims were attempted; all failed because `gemma4_h200_critical_path_profile` had claimed the only compatible bench first.

Evidence: `artifacts/20260718t1532z-blocked/FRONTIER.json` records committed-price break-even thresholds (L40S 0.338x, MI355X 0.800x, H100 SXM 0.862x, B200 1.585x H200 throughput) and no endpoint nominee. `artifacts/20260718t1532z-blocked/TERMINAL.json` records the typed pool blocker, zero spend, exact bench identity/deadline, and the minimum reusable bench contract. The runner compiles locally, but no scientific acceptance boolean is inferred from that.

Interpretation: H200 FP8 remains the only authenticated shortest falsifier, but no measured frontier exists. The concurrent claim and imminent watchdog deadline are external execution availability, not a precision result. RTX 6000 Ada, MI300X/MI325X, and MI210 cannot be canonically price-ranked because the shared price inventory has no committed planning rate; L40S and H100 prior component evidence does not establish endpoint admission.

Next move: on the first compatible bench with at least ten safe lifecycle minutes, run the prepared runner once, retrieve `SENTINEL.json` and the terminal result, compute the measured frontier, and nominate H200 FP8 only if every oracle passes and weighted component margin is at least 20%.

## 2026-07-18 — H200 exact-shape FP8 route falsified by KV writer support

Question: does the admitted H200 E4M3/E5M2 component path clear every numerical oracle and the 20% component-floor hurdle versus BF16?

Action: claimed `h200-fp8-frontier-e00hjag28j32gvydxv`, repaired its stock CUDA image in place with a user venv containing Torch 2.13.0+cu130, and ran `h200_fp8_exact_shape_falsifier.py` exactly once. Retrieved its atomic sentinel, result, runner log, and dependency log into `artifacts/20260718t1600z-h200-fp8/`.

Evidence: the first real E4M3 `_scaled_mm` sentinel passed both numerical oracles (kernel/dequantized normalized RMSE 0.001661, cosine 0.999999; representation/BF16 normalized RMSE 0.037624, cosine 0.999292) and was faster at the decode sliding-QKV shape (0.039648 ms FP8 versus 0.057984 ms BF16 p50). The full run also persisted passing linear/head and BF16 attention rows, then stopped at the exact E5M2 KV-write operation with `NotImplementedError: "index_copy_cuda" not implemented for 'Float8_e5m2'`. `RESULT.json` is `pass: false`, its KV row set is empty, and no aggregate component floor or margin exists. Artifact SHA-256: sentinel `eed7097e89a226a5196bfcb0dcc960b8f78979f487a273d4bf3ab33eeb6e32ec`; result `0944aa7f113db04f6e8f938d8078f306ee5d9ba55f10c788ad41864ff72cb3ba`.

Interpretation: measured runtime support falsifies this H200 FP8 route before the numerical and 20% weighted component-floor admission gate can be evaluated. H200 FP8 is not an endpoint nominee. The recorded project cost is the conservative full 30-minute lifecycle maximum, $1.23, within the $1.50 reservation.

Next move: terminal for this allocation. A future candidate requires a separately admitted, actually supported FP8 KV writer and consumer path; do not replay this one-shot runner or allocation.

## 2026-07-18 — supported E4M3-compute/BF16-state proxy misses admission floor

Question: after retaining BF16 attention and identical BF16 KV-write cost in both arms, does supported H200 E4M3 compute clear the 20% exact-shape component-floor margin over all-BF16?

Action: claimed the warm `h200-fp8-frontier-e00hjag28j32gvydxv` bench, reused `/home/glmrunner/.venvs/gemma-fp8` without dependency setup, and ran the new `h200_fp8_compute_bf16_kv_falsifier.py` exactly once. The runner retains the original E4M3 `_scaled_mm` linear/head and BF16 attention paths, calls only BF16 `index_copy_` for KV, and charges that same measured KV component to both aggregates.

Evidence: every row passed (`all_rows_pass: true`), including the persisted E4M3 sentinel and BF16 KV serialization oracle. The measured all-BF16 component floor was 3.519696 s/request and the E4M3-compute/BF16-state proxy was 3.179684 s/request, a 9.6602% reduction. Shared BF16 attention alone remained 2.648159 s/request, so linear/head acceleration cannot reach the 20% aggregate gate in this component geometry. `RESULT.json` SHA-256 is `02b833cdaa6878816b350ca7cae6982e203fb91a98bdabde2e604d91f66d624a`; runner SHA-256 is `f7e5bb889cd051d820cb556918d98456e49c63c18dc6008bdd859ea0448e8a61`.

Interpretation: this is measured negative evidence for the supported representation, not a full-model throughput claim. H200 E4M3 compute with BF16 state is not a component-proxy nominee because it misses the required margin despite passing all numerical oracles.

Next move: terminal for this retained allocation. A future candidate needs a separately admitted representation or geometry that reduces the attention-dominated component floor; do not replay this arm.
