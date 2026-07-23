from __future__ import annotations

import hashlib
import json
import os
import pathlib

import torch


TARGET = pathlib.Path(
    "/sgl-workspace/sglang/python/sglang/srt/mem_cache/common.py"
)
EXPECTED_SHA256 = "987c02d71dd773d32263d6d34d94d508b74c707e0ca3d918723e981088bb14a9"
CANDIDATE_PATH = "write_cache_indices.pinned_async_prefix_pointer_h2d"


def _audit(**row: object) -> None:
    path = os.environ.get("RESIDUAL_CANDIDATE_AUDIT")
    if not path:
        return
    destination = pathlib.Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a") as handle:
        handle.write(json.dumps({"candidate_path": CANDIDATE_PATH, **row}, sort_keys=True) + "\n")


def install() -> None:
    actual = hashlib.sha256(TARGET.read_bytes()).hexdigest()
    if actual != EXPECTED_SHA256:
        raise RuntimeError(f"bound mem_cache.common source mismatch:{actual}")

    from sglang.srt.mem_cache import common

    if getattr(common.write_cache_indices, "_pinned_prefix_pointer_h2d", False):
        return

    def write_cache_indices(
        out_cache_loc: torch.Tensor,
        req_pool_indices_tensor: torch.Tensor,
        req_pool_indices_cpu: torch.Tensor,
        prefix_lens_tensor: torch.Tensor,
        prefix_lens_cpu: torch.Tensor,
        seq_lens_tensor: torch.Tensor,
        seq_lens_cpu: torch.Tensor,
        extend_lens_tensor: torch.Tensor,
        extend_lens_cpu: torch.Tensor,
        prefix_tensors: list[torch.Tensor],
        req_to_token_pool,
    ) -> None:
        if common.support_triton(common.get_global_server_args().attention_backend):
            pointer_count = len(prefix_tensors)
            prefix_pointers_cpu = torch.tensor(
                [tensor.data_ptr() for tensor in prefix_tensors],
                dtype=torch.uint64,
                pin_memory=True,
            )
            prefix_pointers = prefix_pointers_cpu.to(
                req_to_token_pool.device, non_blocking=True
            )
            _audit(
                phase="runtime_invocation",
                source="sglang.srt.mem_cache.common.write_cache_indices",
                source_sha256=EXPECTED_SHA256,
                batch_size=pointer_count,
                bytes=pointer_count * torch.tensor([], dtype=torch.uint64).element_size(),
                dtype=str(prefix_pointers.dtype),
                shape=list(prefix_pointers.shape),
                pin_memory=prefix_pointers_cpu.is_pinned(),
                non_blocking=True,
                producer_semantics="ordered_prefix_tensor_data_ptr_uint64",
                consumer="write_req_to_token_pool_triton",
                consumer_grid=[int(req_pool_indices_tensor.shape[0])],
            )
            common.write_req_to_token_pool_triton[
                (req_pool_indices_tensor.shape[0],)
            ](
                req_to_token_pool.req_to_token,
                req_pool_indices_tensor,
                prefix_pointers,
                prefix_lens_tensor,
                seq_lens_tensor,
                extend_lens_tensor,
                out_cache_loc,
                req_to_token_pool.req_to_token.shape[1],
            )
        else:
            pt = 0
            for i in range(req_pool_indices_cpu.shape[0]):
                req_idx = req_pool_indices_cpu[i].item()
                prefix_len = prefix_lens_cpu[i].item()
                seq_len = seq_lens_cpu[i].item()
                extend_len = extend_lens_cpu[i].item()
                req_to_token_pool.write(
                    (req_idx, slice(0, prefix_len)),
                    prefix_tensors[i],
                )
                req_to_token_pool.write(
                    (req_idx, slice(prefix_len, seq_len)),
                    out_cache_loc[pt : pt + extend_len],
                )
                pt += extend_len

    write_cache_indices._pinned_prefix_pointer_h2d = True
    common.write_cache_indices = write_cache_indices
    _audit(
        phase="installation_complete",
        source="sglang.srt.mem_cache.common.write_cache_indices",
        source_sha256=EXPECTED_SHA256,
        intervention="pin transient uint64 prefix-pointer host tensor and use non-blocking H2D",
        consumer="write_req_to_token_pool_triton",
        layout_change=False,
        dtype_change=False,
        synchronization_added=False,
        device_scalar_read_added=False,
    )
