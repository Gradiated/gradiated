from __future__ import annotations

import hashlib
import pathlib


TARGET = pathlib.Path(
    "/sgl-workspace/sglang/python/sglang/srt/managers/schedule_batch.py"
)
EXPECTED_SHA256 = "eea77dac02f593da24e953f0a0ea03237f2874d0ef27522044e8fd6397fcb874"

OLD = """            latest_output_ids = torch.tensor(
                [
                    (
                        req.output_ids[-1]
                        if len(req.output_ids)
                        else req.origin_input_ids[-1]
                    )
                    for req in self.reqs
                ],
                dtype=torch.int64,
                device=self.device,
            )
            self.sampling_info.penalizer_orchestrator.cumulate_output_tokens(
                latest_output_ids
            )
"""

NEW = """            latest_output_ids_host = torch.tensor(
                [
                    (
                        req.output_ids[-1]
                        if len(req.output_ids)
                        else req.origin_input_ids[-1]
                    )
                    for req in self.reqs
                ],
                dtype=torch.int64,
                pin_memory=True,
            )
            latest_output_ids = latest_output_ids_host.to(
                device=self.device, non_blocking=True
            )
            if not getattr(self, \"_pinned_penalty_tokens_audited\", False):
                import json as _json
                import os as _os

                _audit = _os.environ.get(\"SYNC_CANDIDATE_AUDIT\")
                if _audit:
                    with open(_audit, \"a\") as _handle:
                        _handle.write(
                            _json.dumps(
                                {
                                    \"batch_size\": len(self.reqs),
                                    \"candidate_path\": \"ScheduleBatch.prepare_for_decode.pinned_async_penalty_tokens\",
                                    \"dtype\": \"torch.int64\",
                                    \"non_blocking\": True,
                                    \"phase\": \"runtime_invocation\",
                                    \"pin_memory\": True,
                                },
                                sort_keys=True,
                            )
                            + \"\\n\"
                        )
                self._pinned_penalty_tokens_audited = True
            self.sampling_info.penalizer_orchestrator.cumulate_output_tokens(
                latest_output_ids
            )
"""


def install() -> None:
    raw = TARGET.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != EXPECTED_SHA256:
        raise RuntimeError(f"pinned schedule_batch source mismatch:{actual}")
    text = raw.decode()
    if text.count(OLD) != 1:
        raise RuntimeError("penalty-token patch target is not unique")
    TARGET.write_text(text.replace(OLD, NEW))
