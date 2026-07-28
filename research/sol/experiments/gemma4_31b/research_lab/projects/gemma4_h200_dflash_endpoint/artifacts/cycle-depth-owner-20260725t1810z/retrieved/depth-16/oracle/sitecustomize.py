import json
import os
from pathlib import Path

import torch

from sglang.srt.speculative.dflash_worker_v2 import DFlashWorkerV2


OUT = Path(os.environ["DFLASH_DEPTH_TIMINGS"])
ORIGINAL = DFlashWorkerV2.forward_batch_generation


def measured(self, *args, **kwargs):
    samples = []
    draft = self.draft_model_runner.forward
    verify = self.target_worker.forward_batch_generation

    def timed(name, fn):
        def run(*inner_args, **inner_kwargs):
            start, stop = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
            start.record()
            result = fn(*inner_args, **inner_kwargs)
            stop.record()
            samples.append((name, start, stop))
            return result
        return run

    self.draft_model_runner.forward = timed("draft_ms", draft)
    self.target_worker.forward_batch_generation = timed("verifier_ms", verify)
    try:
        return ORIGINAL(self, *args, **kwargs)
    finally:
        self.draft_model_runner.forward = draft
        self.target_worker.forward_batch_generation = verify
        torch.cuda.synchronize()
        row = {"depth": int(os.environ["DFLASH_DEPTH"]), "draft_ms": 0.0, "verifier_ms": 0.0}
        for name, start, stop in samples:
            row[name] += float(start.elapsed_time(stop))
        if row["draft_ms"] or row["verifier_ms"]:
            OUT.parent.mkdir(parents=True, exist_ok=True)
            with OUT.open("a") as handle:
                handle.write(json.dumps(row, sort_keys=True) + "\n")


DFlashWorkerV2.forward_batch_generation = measured
