# AWQ KV-B source falsification audit

Date: 2026-07-13

Scope: offline and read-only with respect to RunPod. This audit did not mutate a pod, campaign status, report, ledger, spend record, or credential.

## Decision

One causally changed 48 GB AWQ smoke remains justified after the stock BF16 baseline. It must be the final loader-compatibility smoke under the campaign's existing terminal rule, not an economics run. The prior patched L40S attempt did not execute the new branch: it completed only one of four checkpoint shards before the health timeout. The interrupted follow-up retained no terminal model artifact. Neither run falsified the branch.

## Measured boundary

Secure-L40S attempt 2 loaded all four shards with native SGLang and CompressedTensors WNA16 Marlin, then failed in `DeepseekV2WeightLoaderMixin.post_load_weights` at pinned `deepseek_weight_loader.py:522`. The code selected neither the legacy AWQ `qweight` path nor a compressed-tensors path and unconditionally read `kv_b_proj.weight`. The actual `ColumnParallelLinear` retained `weight_packed`, `weight_scale`, and `weight_shape`; it had no dense `weight`.

This falsifies explanations based on fused Q/KV-A metadata, checkpoint download, shard loading, Marlin capability selection, 48 GB capacity, tensor parallelism, request-time kernels, or output quality at that boundary. It does not prove that no later defect exists.

## Exact checkpoint contract

The exact checkpoint revision's index maps layer 1 KV-B tensors to `model-00001-of-00004.safetensors`. Range-reading the immutable safetensors header and the 16 shape bytes gives:

- `weight_shape`: I64 physical `[2]`, values `[8960, 512]`.
- `weight_packed`: I32 `[8960, 64]`.
- `weight_scale`: BF16 `[8960, 16]`.
- Quantization config: symmetric INT4, group size 32, no activation ordering.

The geometry closes exactly: eight INT4 values per I32 word restore 512 input columns, and sixteen scale groups times 32 columns restore the same 512 columns. No zero point or group index is required. The fixture records the immutable revision and source hashes.

## Source-level falsification of the correction

Pinned SGLang calls the model's `load_weights`, which invokes `post_load_weights`, before the outer loader iterates quantization methods and performs Marlin repacking. Therefore KV-B is still in checkpoint `pack-quantized` layout at the failing line. Compressed-tensors 0.17.1's `PackedQuantizationCompressor.decompress` performs the same inverse selected by the local patch: `unpack_from_int32` using the stored shape and bit width, followed by `dequantize` with the stored scale, zero point, and group index.

The local patch narrows that canonical inverse to the measured contract: INT4, symmetric, no activation ordering, a positive two-element shape, and an exact restored shape. It preserves the dense and legacy AWQ paths. It also does not transpose the compressed branch; the checkpoint and SGLang post-load code both use `[out_features, in_features]` at this point.

Independent upstream support exists in open SGLang PR 19106. That PR identifies the same dense-only KV-B post-load assumption, adds a packed WNA16 dequantization branch for MLA `w_kc`/`w_vc`, and reports successful serving of a related GLM-4.7-Flash compressed-tensors checkpoint. Its automated review correctly notes that hard-coding four bits would be unsafe for W8A16. The local patch avoids that transfer by deriving the stored bit width and then deliberately failing closed unless it is the exact INT4 contract. The PR is supporting source evidence and vendor-reported runtime evidence, not a matched measurement for this checkpoint.

## Capacity and remaining uncertainty

Attempt 2 measured at most 17,909 MiB allocated before the post-load exception on a 46,068 MiB L40S. From the immutable model config, dense BF16 KV-B splits for the 46 quantized layers total 402.5 MiB; a one-layer dense temporary is 8.75 MiB. These are analytical sizes, not peak-memory measurements, but they falsify a simple 48 GB-capacity objection with substantial headroom. Marlin repacking and allocator peaks remain unmeasured.

The correction is not GPU-validated. A valid smoke must complete all shards, cross KV-B post-load, reach health, and return two identical normalized greedy completions with MTP off. Passing establishes loader compatibility only. Any deterministic semantic loader/post-load failure after this correction, or deterministic smoke mismatch after health, kills the patched-SGLang AWQ branch for this campaign; no fifth loader patch is warranted.

## Required change from failed executions

The next smoke may retain the exact model/runtime/patch semantics, but it must change the failed execution variables: a separately enforced in-container health allowance based on the measured cold-read time, and an interruption-resilient watchdog/artifact path that preserves terminal evidence and independently deletes and verifies 404. Repeating the old lifecycle unchanged is not justified.

## Primary sources

- Pinned SGLang weight loader: <https://github.com/sgl-project/sglang/blob/f63458b5beaceabbd9d749b9fc956370e1b649e6/python/sglang/srt/models/deepseek_common/deepseek_weight_loader.py>
- Pinned SGLang model loader ordering: <https://github.com/sgl-project/sglang/blob/f63458b5beaceabbd9d749b9fc956370e1b649e6/python/sglang/srt/model_loader/loader.py>
- Pinned SGLang WNA16 scheme: <https://github.com/sgl-project/sglang/blob/f63458b5beaceabbd9d749b9fc956370e1b649e6/python/sglang/srt/layers/quantization/compressed_tensors/schemes/compressed_tensors_wNa16.py>
- Compressed-tensors 0.17.1 wheel: <https://pypi.org/project/compressed-tensors/0.17.1/>
- Independent SGLang correction: <https://github.com/sgl-project/sglang/pull/19106>
- Exact checkpoint config: <https://huggingface.co/cyankiwi/GLM-4.7-Flash-AWQ-4bit/blob/ab31d120fbe79988fe2a0259993cf3c222aa8881/config.json>
- Exact checkpoint index: <https://huggingface.co/cyankiwi/GLM-4.7-Flash-AWQ-4bit/blob/ab31d120fbe79988fe2a0259993cf3c222aa8881/model.safetensors.index.json>
