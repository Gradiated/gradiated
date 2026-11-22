# Model baselines

The frozen default for hardware experiments is **`chip-joke-text-20261109`, selected W16A16 conversion**, designated on 15 November 2026. It has 26,720 parameters and uses sixteen-bit weights and stored activations, with wider accumulators and other declared intermediate widths. The original board-tested joke model is retained as a historical baseline and control. Neither is a general conversational model.

The [registry](baselines.json) records the default, exact model-manifest hash, selected integer-weight hash, reference board-package hash and frozen completion-reference hash. The text-input model passed [physical acceptance](../results/physical-acceptance-20261114T232418Z-c39918/run.json) and has a [fresh-session speed baseline](../results/speed-20261115T125210Z-f3c38c/run.json). The resident run measured the same three prompts in one boot, with score capture and checking included in the back-to-back rates. Longer-duration throughput and energy remain unmeasured. [Resident-session benchmark](../results/resident-speed-20261115T150400Z-f42f45/run.json)

Earlier dated manifests and development notes still describe the candidate before its board test. Preserve those pinned historical files and use this registry with the subsequent run records for current status.

## Freeze policy

Never overwrite the selected weights or change the geometry, input encoding, decoding or numerical rules under this baseline identity. Do not silently incorporate edits from `material/one-liners-review-v2.txt`. New training, weight changes and precision experiments get separate identities and payloads, with an explicit link to their parent. The frozen baseline remains available even if a later model is selected as the default. The freeze is a recorded selection backed by checksums, not a filesystem write lock.

Memory placement, arithmetic parallelism and the division of work between CPU and FPGA may change in separately identified implementations. Keep the baseline model and the experiment's declared inputs and output checks fixed. Check matching outputs before accepting performance comparisons. New workloads or measurement boundaries receive new protocol identities rather than silently changing an existing comparison.

## Saved payloads

The model configuration, training corpus, decoding rules and payload pins remain in the implementation's `model/` directory. Weight bytes are outside Git. Under the preserved Mac runtime `/Users/aidanmcconnell/dev/gradiated/.agents/runtime/hardware/inference/`:

- `models/tiny/`: original FP32, Q8 and selected fixed-point artifacts.
- `outputs/tiny/20261109T180555600902/checkpoint/`: selected text-input FP32 weights and training state.
- `outputs/tiny/20261109T190531255188/`: frozen text-input W16A16 conversion and numerical evidence.
- `outputs/tiny/20261109T181627379566/`: earlier text-input integer conversion, retained for history.

The verified board packages are under `/Users/aidanmcconnell/dev/gradiated/.agents/runtime/hardware-consolidation/2026-11-14/server-runtime/board-packages/`: `conditioned-6wbein7j` for the frozen text-input model and `text-bgjxdjep` for the original. These historical directory names are resolved by package hashes, not treated as model identities. The active checkout reuses preserved runtime payloads as described in the [project guide](../README.md). Shared backup remains pending in the [storage record](../storage.json).

Promote a future candidate only after its declared quality checks, numerical checks and required device checks pass. Record the decision and retain the previous selection. A software result is not a board result. Future training must freeze a fresh final evaluation before tuning if an earlier holdout has already been inspected.
