# Autonomous greedy inference, version 1

Experimental controller for the frozen `chip-joke-text-20261109` W16A16 model at 50 MHz. The ten neural RTL modules are pinned and unchanged. Only the AXI wrapper gains prompt sequencing, exact signed top-1 selection, feedback, stopping and output buffering. Every processed position still computes and consumes all 320 scores, including intermediate prefix positions. This is not a prefill-computation optimisation.

[Protocol](../../../../experiments/kv260-autonomous-v1.md) governs validation and physical comparison. Simulation/build/physical results are distinct. No result is implied by this source directory. The original RTL and observer variant remain intact.

`materialise.py` verifies `manifest.json` against original RTL and creates a new source directory. The controller uses a 256-entry, 9-bit prompt buffer and a 256-entry, 9-bit output buffer. The frozen context permits at most 255 emitted IDs after BOS, so the whole answer fits without host reads gating inference. This is a bounded single-request interface, not unbounded streaming or concurrent requests.

## AU01 ABI

Legacy registers 0x00–0x20 retain the original diagnostic interface when the autonomous controller is idle. While it owns a request, including sticky completion, legacy token writes and logit reads are rejected. Context clear returns ownership to the legacy interface. Staging a prompt also rejects legacy token writes until clear. Model loading uses the unchanged pinned loader.

| Offset | Access | Meaning |
| --- | --- | --- |
| 0x24 | R | ABI `0x41553031` (AU01). |
| 0x28 | R | Bit 0 active, 1 done, 2 fault, 3 output available, 4 first-byte timing valid, 5 last-byte timing valid, 6 cycle overflow. Bits 8–11 stop reason. |
| 0x2c | R | Number of appended prompt tokens, 0–256. |
| 0x30 | W | Append token ID, 0–319, first token must be BOS 256. |
| 0x34 | RW | Maximum output IDs, 0–255, default 255 after clear/reset. |
| 0x38 | W | Write 1 to start. Requires configured idle core, context count zero and non-empty prompt. |
| 0x3c | R | Total emitted IDs. Includes a terminal non-byte ID, excludes EOS. |
| 0x40 | R | Pop one ID only on accepted AXI R response. An empty read returns SLVERR. |
| 0x44 | R | Unread output IDs. |
| 0x48 | R | First useful byte's internal cycle, valid only when status bit 4 is set. |
| 0x4c | R | Last useful byte's internal cycle, valid only when status bit 5 is set. |
| 0x50 | R | Terminal cycle. Read after done. |
| 0x54 | R | Accepted input positions in the autonomous request. |
| 0x58 | R | Consumed scores in the autonomous request. Healthy terminal count is 320 × positions. |

Stop reasons: 0 none, 1 EOS, 2 context limit, 3 non-byte token, 4 output limit, 5 fault. Fault sets done and fault and takes precedence over a nominal stop. State is sticky until context clear or full reset. Writes require aligned addresses and all byte strobes. Upper token bits and invalid values are rejected without side effects.

All prompt positions are processed even for maximum output zero or a full 256-position prompt. Output capacity is `min(maximum_output, 256 - prompt_count)`. Context limit wins if those caps coincide. EOS is not buffered. A selected non-byte ID is buffered then stops. At an output/context cap, the last emitted byte is not fed back into the core. Lowest ID wins equal signed scores, including all-negative scores and a winner at index 319.

First/last timing captures useful byte production inside the FPGA, not delivery to the CPU or client. Cycles are relative to the accepted START command, exclude prompt upload/clear and saturate into fault on overflow. Host-visible timing is measured separately. An absent byte has an invalid timing bit, not a zero-latency measurement.

Autonomous fault requires full reset and model reload. Context clear uses legacy 0x1c=1, only when neither core nor controller is active and no autonomous fault is sticky, and clears prompt/output state and limits. Legacy 0x1c=2 fully resets the core and requires model reloading. Pending or newly claimed output/logit reads block clear/reset until their response is accepted. Core error or saturation fails the autonomous request. Diagnostics and tests must cover reset/read races, output backpressure and next-request isolation.

## Ownership and validation

Coordinator owns RTL, numerical simulation, build and protocol. The isolated test worker owns the synthetic edge bench. SOL owns `host/`, physical packet preparation and sole board access. Preserve all existing work. Runtime artifacts belong under `.agents/runtime/hardware/inference/outputs/`, never solely on the temporary Linux server.

Current status: the final offline suite passed 146,880 autonomous score comparisons, 3,200 legacy BOS comparisons, three full completions, zero/one-output limits and synthetic AXI/fault tests. RTL SHA `ddb622a1e1b9d6bbdeac87fcdcf6d9535f76f475c11acb118ec1e1146317f517`. The [routed 50 MHz build](../../../../results/autonomous-build-20261115T204747Z/findings.md) passed, and all 321 archived server files were recovered and verified on the Mac. The [physical comparison](../../../../results/autonomous-prefill-decode-20261115T210134Z-97efcb/findings.md) completed all 14 gates, including exact output checks, three matched pairs and original firmware/weight restoration. The independent audit re-decoded the raw serial receipts and recalculated all request timings and six power traces. Aidan adopted this exact version as the circuit comparison baseline on 15 November 2026. The [adoption decision](../../README.md#selected-circuit-comparison-baseline) pins the circuit, captured host software and tested programming file, while preserving the original baseline.

Mac preparation: `.agents/runtime/hardware/inference/outputs/autonomous-20261115T201943Z-preparation/`. `final-tests/` contains the reusable test result and materialised source pins, `early-assets/` contains the verified companion library and overlay, and `build-packet/` captures the isolated build source. Existing Linux build root: `/home/admin/projects/gradiated/.agents/runtime/fpga-inference/autonomous-20261115T201943`. Each phase has a bounded process-group timeout. Recover and verify the resulting archive before relying on the temporary server. SOL alone owns live board access. The completed physical packet and captures are under `autonomous-prefill-decode-20261115T210134Z-97efcb/`, with a sibling `-audit/` directory. The first attempt `autonomous-prefill-decode-20261115T204825Z-46cd07/` remains preserved as aborted before inference. Its narrowly corrected warning anchor used the pinned, previously accepted restoration after explicit retry approval. `host/prepare_retry_support.py` preserves that derivative. The original circuit and weights are restored, and no further run is in progress.
