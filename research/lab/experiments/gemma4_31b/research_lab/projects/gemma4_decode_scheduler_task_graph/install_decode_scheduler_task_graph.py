from __future__ import annotations

import argparse
import hashlib
import pathlib
import shutil


UPSTREAM_SHA256 = "eea77dac02f593da24e953f0a0ea03237f2874d0ef27522044e8fd6397fcb874"
RETAINED_SHA256 = "b6480f792867d7aba3dc39ef66048408c6c92ddad3ed81b23934493a351be459"
COMMON_SHA256 = "987c02d71dd773d32263d6d34d94d508b74c707e0ca3d918723e981088bb14a9"

OLD_IMPORT = """from sglang.srt.mem_cache.memory_pool import ReqToTokenPool
"""
NEW_IMPORT = """from sglang.srt.managers.decode_scheduler_task_graph import (
    commit_schedule_batch_decode_metadata,
)
from sglang.srt.mem_cache.memory_pool import ReqToTokenPool
"""
OLD_ALLOC = """        # Allocate memory
        self.out_cache_loc = alloc_for_decode(self, token_per_req=1)
"""
NEW_ALLOC = """        # Allocate memory. The task-graph path retains the stock allocator
        # decision but defers its req_to_token publication to one fused device task.
        task_graph_enabled = (
            self.enable_overlap
            and self.device == "cuda"
            and self.spec_algorithm.is_none()
            and not self.model_config.is_encoder_decoder
        )
        self.out_cache_loc = alloc_for_decode(
            self,
            token_per_req=1,
            publish_req_to_token=not task_graph_enabled,
        )
"""
OLD_INCREMENT = """        if self.enable_overlap:
            # New-tensor avoids racing model_worker_batch refs queued for
            # overlap forward.
            self.seq_lens = self.seq_lens + 1
            self.seq_lens_cpu = self.seq_lens_cpu + 1
            self.orig_seq_lens = self.orig_seq_lens + 1
        else:
            self.seq_lens.add_(1)
            self.seq_lens_cpu.add_(1)
            self.orig_seq_lens.add_(1)
"""
NEW_INCREMENT = """        if task_graph_enabled:
            commit_schedule_batch_decode_metadata(self, self.out_cache_loc)
            self.seq_lens_cpu = self.seq_lens_cpu + 1
        elif self.enable_overlap:
            # New-tensor avoids racing model_worker_batch refs queued for
            # overlap forward.
            self.seq_lens = self.seq_lens + 1
            self.seq_lens_cpu = self.seq_lens_cpu + 1
            self.orig_seq_lens = self.orig_seq_lens + 1
        else:
            self.seq_lens.add_(1)
            self.seq_lens_cpu.add_(1)
            self.orig_seq_lens.add_(1)
"""

COMMON_OLD_SIGNATURE = (
    "def alloc_for_decode(batch: ScheduleBatch, token_per_req: int) -> torch.Tensor:\n"
)
COMMON_NEW_SIGNATURE = """def alloc_for_decode(
    batch: ScheduleBatch,
    token_per_req: int,
    *,
    publish_req_to_token: bool = True,
) -> torch.Tensor:
"""
COMMON_OLD_WRITE = """    batch.req_to_token_pool.write(
        (batch.req_pool_indices, locs), out_cache_loc.to(torch.int32)
    )

    return out_cache_loc
"""
COMMON_NEW_WRITE = """    if publish_req_to_token:
        batch.req_to_token_pool.write(
            (batch.req_pool_indices, locs), out_cache_loc.to(torch.int32)
        )

    return out_cache_loc
"""


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"{label}_replacement_count:{text.count(old)}")
    return text.replace(old, new)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sglang-python", type=pathlib.Path, required=True)
    args = parser.parse_args()
    managers = args.sglang_python / "sglang/srt/managers"
    schedule_batch = managers / "schedule_batch.py"
    common = args.sglang_python / "sglang/srt/mem_cache/common.py"
    actual = sha256(schedule_batch)
    if actual not in {UPSTREAM_SHA256, RETAINED_SHA256}:
        raise RuntimeError(f"schedule_batch_source_mismatch:{actual}")
    common_actual = sha256(common)
    if common_actual != COMMON_SHA256:
        raise RuntimeError(f"common_source_mismatch:{common_actual}")

    schedule_text = schedule_batch.read_text()
    schedule_text = replace_once(
        schedule_text, OLD_IMPORT, NEW_IMPORT, "candidate_import"
    )
    schedule_text = replace_once(
        schedule_text, OLD_ALLOC, NEW_ALLOC, "decode_allocation"
    )
    schedule_text = replace_once(
        schedule_text, OLD_INCREMENT, NEW_INCREMENT, "decode_increment"
    )
    common_text = common.read_text()
    common_text = replace_once(
        common_text,
        COMMON_OLD_SIGNATURE,
        COMMON_NEW_SIGNATURE,
        "allocator_signature",
    )
    common_text = replace_once(
        common_text, COMMON_OLD_WRITE, COMMON_NEW_WRITE, "allocator_publish"
    )

    candidate = pathlib.Path(__file__).with_name("decode_scheduler_task_graph.py")
    shutil.copyfile(candidate, managers / candidate.name)
    schedule_batch.write_text(schedule_text)
    common.write_text(common_text)


if __name__ == "__main__":
    main()
