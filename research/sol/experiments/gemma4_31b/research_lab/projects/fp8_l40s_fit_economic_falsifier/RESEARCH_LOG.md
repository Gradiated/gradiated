# Research log

No researcher turn has completed. The immediate endpoint is one direct paid L40S packet or a quantified closure, not another readiness project.

## 2026-07-17 — direct L40S packet

Question: does the exact pinned Gemma 4 31B target have a bounded current FP8 consumer that fits one 48 GB L40S, and what paid arm would falsify the economic route?

Action: used the immutable target config/index and completed geometry/runtime packet, queried the shared accelerator and price inventories, checked the existing shared lifecycle tools once, and reviewed current first-party vLLM FP8/Gemma4 issue evidence. No weight shard or provider was created.

Evidence: metadata is 32,682,372,656 parameters / 62,546,177,752 BF16 bytes. The tied embedding/output is 1,409,286,144 parameters and remains BF16. Explicit language MLP and attention classes are 29,396,882,160 parameters; the exact residual is carried in the packet. The conservative online-FP8 10K bound is 40.504 GiB against 44.704 GiB at 0.92 allocation, leaving 4.20 GiB. L40S planning rate is $1.10/GPU-hour versus H100 SXM $2.80, so raw break-even is 39.2857% of measured H100 throughput.

Interpretation: memory fit is plausible but load-time behavior and FP8 numerical correctness are unmeasured. vLLM issue #39049 reports Gemma4 dynamic FP8 gibberish output and #39407 reports an FP8_BLOCK scale bug; these make the first request a mandatory correctness falsifier, not a closure or quality transfer. The route is nominated, not promoted.

Next move: schedule exactly one direct CUDA L40S arm with the pinned Gemma4 image, `--quantization fp8`, eager mode, max model length 10K, complete 4,214/358 and 10K requests, raw-output capture, matched H100 fields, and verified cleanup. Do not create a support successor or wait for H100.
