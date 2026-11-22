# Prompt and context lengths on the KV260

**Status.** Inputs and analysis boundaries prepared. Execution and reference generation require a separate go-ahead.

Use the selected `scalar-div-v1` at 50 MHz with the frozen `chip-joke-text-20261109` W16A16 model, one resident worker, the same greedy decoding and a 256-position context. Long input should increase time to first token. Later score steps may also take longer as attention reads more cached entries. Actual output length, input content, host work and the timing boundary can change those effects.

## Natural prompts through the usual interface

The [manifest](../workloads/kv260-prompt-context-v1.json) defines two nested ASCII prompt families at 4, 12, 24 and 48 bytes, one BOS-only request and a multibyte UTF-8 control at 12 bytes. `prompt_cases` produces their exact bytes and token IDs, keeping trailing spaces. The interface accepts at most 48 UTF-8 bytes. Each input has a BOS ID and two IDs per byte, so the largest natural prefix occupies 97 positions. Use the existing resident AU02 path with output cap 255 and its own EOS, context and non-byte terminal rules.

Generate exact reference completions for those ten inputs only after a separate authorisation. Pin the reference bytes, input and output IDs, resulting context and stop reasons. Have a second check confirm the model and reference hashes. The historical three-prompt workload is a warm-up anchor and retains its existing evidence and identity.

Warm with one verified request per historical case. Use four rotations of the ten manifest cases, beginning at offsets 0, 3, 6 and 9, reversing the second and fourth rotations. Compare each prompt against its independent exact reference. Record host service first byte, first-to-last decode intervals, done and verified completion, output counts, stops and available full-request device cycles. Report medians and ranges by family and length. Report undefined first-byte or decode measurements as such when outputs are empty or too short. Present the multibyte case separately. This path does not expose a separate physical prefill timestamp. End-to-end first byte includes control and delivery costs.

## Fixed context diagnostic

Use `teacher_probe` with the pinned resident `score_sequence` method, a deadline-aware native call adapter and independent per-position signed-score digests. This diagnostic feeds selected tokens regardless of the model's choice. The two fixed input streams repeat the manifest ASCII sources and truncate after BOS at 17, 65, 129, 193 and 256 total IDs. The 256-ID stream can finish halfway through a byte encoding. It is a deliberate full-context token probe. References and results for these streams are separate from natural completions.

Run three fixed rotations of the ten probes, beginning at offsets 0, 3 and 6, reversing the middle rotation. Record each synchronous score-step duration and the median of the last eight steps per probe. Retain a compact per-step score digest and exact context count. The diagnostic requests full scores and uses the legacy host-driven sequence. It provides a fixed-input measure of the cost of late score steps, including host score return. AU02 prompt optimisation and autonomous output delivery follow a different path. There is no natural TTFT, decode TPS or model quality result in this diagnostic.

## Limits and evidence

Cap natural requests at 3 seconds each and fixed probes at 10 seconds each, with a shared 8-minute measured-work deadline and an outer watchdog. A verified error, timeout, unhealthy state or changed pin stops dispatch. The future packet must include an exclusive live owner, source and fixture pins, the exact call adapter, warm-up/rotation order, evidence/export budget and health-gated verification/restoration of the original circuit and weights. Keep all raw timing, context, stop and output receipts. Power and thermal measurements are outside this conditional diagnostic. Mark them as unmeasured in its coverage. It does not produce a full physical comparison scorecard. Follow [measurement standard v2](measurement-standard-v2.md) and the [preparation handoff](kv260-milestone-preparation.md).
