# Decision

`MTP_BOUND.json` is a reproducible derived/synthetic result; no provider, CUDA, checkpoint, or quality execution occurred.

Native one-token MTP remains worth at most one later matched arm. With one target verification pass per proposal, the modeled request ratio is

`(1 - f_decode) + f_decode * (1 + assistant_cost/verify_cost + proposer_overhead) / (1 + mean_accepted_tokens)`.

At the representative `f_decode=0.50`, assistant/verification cost `0.02`, and proposer overhead `0.05`, the minimum mean accepted tokens is `0.189` for a 5% whole-request gain and `0.338` for 10%. The optimistic one-token ceiling is 23.25%. The surface includes decode shares 0.25/0.50/0.75 and assistant cost 0.02/0.05/0.10; it does not elide target verification or count rejected tokens as accepted.

Market break-even is not established. Using the captured cheapest request price `$0.000614287` and the shared utilization/headroom factors, the required sustainable rate is `1.825 req/s` on H100 at `$2.80/GPU-hour` and `0.717 req/s` on L40S at `$1.10/GPU-hour`. A stock H100 at 1.0 req/s would need 45.2% improvement, beyond the one-token bound at `f_decode=0.50`; a stock L40S at 0.6 req/s would need 16.3%, requiring 0.589 accepted tokens under the representative costs. These are conditional thresholds, not throughput measurements.

The assistant adds `0.875 GiB` per replica. Approximate primary residency becomes `70.523 GiB` for BF16 H100 c16 and `81.915 GiB` at c32 before allocator/runtime reserve; W4 L40S c16/c32 become `32.033/37.848 GiB` from the corrected W4 bound. c32 H100 is therefore not a credible default; c16 requires measured headroom. Async scheduling remains the zero-weight fallback and should be promoted only on a matched c8/c16 result with at least 5% gain.

## Later-arm contract

Run only `native_mtp_num_speculative_tokens_1`, after exact target/assistant/runtime/image identity checks. Capture `accepted_tokens`, draft and verification calls, exact output IDs, complete requests, prefill/decode/request wall phases, HBM, and power. Require exact-greedy output-ID agreement, at least 30 complete requests per arm, mean acceptance above the measured-surface threshold, and at least 5% all-in cost reduction. Otherwise emit typed `none`; no 10% or market claim follows from this artifact.
