from __future__ import annotations

import hashlib
import inspect
import json
import os
import pathlib
import tempfile
import time
from dataclasses import dataclass
from typing import Any


PINNED_GEMMA4_CAUSAL_SHA256 = (
    "bc8bc948a89e82b2118c32d380497ce76a568b8839c7f02150195af93a0e8989"
)
PINNED_LOGITS_PROCESSOR_SHA256 = (
    "e5d0d3a8781e74c1c7fe7508eb89d2eb198cc42bcd5e2fa4258217c756fdaf14"
)


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _append_audit(path: pathlib.Path | None, value: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _tensor_prefix(value: Any, count: int, *, fill: int) -> list[int]:
    if value is None:
        return [fill] * count
    result = value.detach().to("cpu").reshape(-1)[:count].tolist()
    if len(result) != count:
        raise ValueError(f"ownership_width:{len(result)}:{count}")
    return [int(item) for item in result]


@dataclass(frozen=True)
class CaptureConfig:
    destination: pathlib.Path
    audit: pathlib.Path | None
    maximum_rows: int
    expected_hidden_width: int | None
    require_eager: bool


class TargetVerifyHiddenCapture:
    def __init__(self, config: CaptureConfig):
        self.config = config
        self._hidden_batches: list[Any] = []
        self._proposal_batches: list[Any] = []
        self._position_batches: list[Any] = []
        self._ownership: list[dict[str, Any]] = []
        self._capture_count = 0

    @property
    def row_count(self) -> int:
        return len(self._ownership)

    def observe(
        self,
        input_ids: Any,
        hidden_states: Any,
        forward_batch: Any,
    ) -> Any:
        import torch

        is_target_verify = getattr(forward_batch.forward_mode, "is_target_verify", None)
        if not callable(is_target_verify) or not bool(is_target_verify()):
            return hidden_states
        if self.row_count >= self.config.maximum_rows:
            return hidden_states
        if self.config.require_eager and hidden_states.is_cuda:
            if torch.cuda.is_current_stream_capturing():
                raise RuntimeError("target_verify_capture_requires_eager_execution")

        depth_count = int(forward_batch.spec_info.draft_token_num)
        if depth_count <= 1:
            raise ValueError(f"invalid_depth_count:{depth_count}")
        available_rows = min(int(input_ids.numel()), int(hidden_states.shape[0]))
        active_requests, remainder = divmod(available_rows, depth_count)
        if remainder or active_requests <= 1:
            raise ValueError(
                f"request_major_shape:{available_rows}:{depth_count}:{active_requests}"
            )
        active_rows = active_requests * depth_count
        take_rows = min(active_rows, self.config.maximum_rows - self.row_count)
        take_rows -= take_rows % depth_count
        if take_rows == 0:
            return hidden_states

        width = int(hidden_states.shape[-1])
        if (
            self.config.expected_hidden_width is not None
            and width != self.config.expected_hidden_width
        ):
            raise ValueError(
                f"hidden_width:{width}:{self.config.expected_hidden_width}"
            )

        request_pool_indices = _tensor_prefix(
            forward_batch.req_pool_indices, active_requests, fill=-1
        )
        request_ids = _tensor_prefix(
            getattr(forward_batch, "rids_int", None), active_requests, fill=-1
        )
        request_ids_raw = getattr(forward_batch, "rids", None)
        if request_ids_raw is None:
            request_ids_raw = [str(value) for value in request_ids]
        else:
            request_ids_raw = [str(value) for value in request_ids_raw[:active_requests]]
            if len(request_ids_raw) != active_requests:
                raise ValueError(
                    f"request_id_width:{len(request_ids_raw)}:{active_requests}"
                )
        positions = _tensor_prefix(
            getattr(forward_batch, "positions", None), active_rows, fill=-1
        )
        hidden_cpu = (
            hidden_states[:take_rows].detach().to("cpu").contiguous().clone()
        )
        proposal_cpu = (
            input_ids[:take_rows]
            .detach()
            .to(device="cpu", dtype=torch.int32)
            .contiguous()
            .clone()
        )
        position_cpu = torch.tensor(positions[:take_rows], dtype=torch.int32)

        capture_index = self._capture_count
        base_row = self.row_count
        for local_row in range(take_rows):
            request_batch_index, depth_index = divmod(local_row, depth_count)
            self._ownership.append(
                {
                    "global_row": base_row + local_row,
                    "capture_index": capture_index,
                    "capture_row": local_row,
                    "request_batch_index": request_batch_index,
                    "request_pool_index": request_pool_indices[request_batch_index],
                    "request_id": request_ids_raw[request_batch_index],
                    "request_id_int": request_ids[request_batch_index],
                    "depth_index": depth_index,
                }
            )
        self._hidden_batches.append(hidden_cpu)
        self._proposal_batches.append(proposal_cpu)
        self._position_batches.append(position_cpu)
        self._capture_count += 1
        self._commit()
        _append_audit(
            self.config.audit,
            {
                "event": "target_verify_hidden_rows_committed",
                "capture_index": capture_index,
                "rows_added": take_rows,
                "rows_total": self.row_count,
                "hidden_width": width,
                "depth_count": depth_count,
                "active_requests": active_requests,
                "time_unix_s": time.time(),
            },
        )
        return hidden_states

    def _commit(self) -> None:
        import torch

        payload = {
            "schema_version": 1,
            "layout": "capture_then_request_major_then_depth",
            "hidden_states": torch.cat(self._hidden_batches, dim=0),
            "proposal_token_ids": torch.cat(self._proposal_batches, dim=0),
            "positions": torch.cat(self._position_batches, dim=0),
            "ownership": self._ownership,
            "capture_count": self._capture_count,
        }
        destination = self.config.destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=destination.parent,
            prefix=destination.name + ".",
            suffix=".part",
            delete=False,
        ) as handle:
            temporary = pathlib.Path(handle.name)
        try:
            torch.save(payload, temporary)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)


def install_logits_processor_capture(
    logits_processor_class: type,
    capture: TargetVerifyHiddenCapture,
) -> Any:
    original = logits_processor_class.forward
    if getattr(original, "_diverse_hidden_capture_installed", False):
        return original

    def wrapped(
        self: Any,
        input_ids: Any,
        hidden_states: Any,
        lm_head: Any,
        logits_metadata: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        try:
            capture.observe(input_ids, hidden_states, logits_metadata)
        except Exception as exc:
            _append_audit(
                capture.config.audit,
                {
                    "event": "capture_observer_error",
                    "error": repr(exc),
                    "time_unix_s": time.time(),
                },
            )
        return original(
            self,
            input_ids,
            hidden_states,
            lm_head,
            logits_metadata,
            *args,
            **kwargs,
        )

    wrapped._diverse_hidden_capture_installed = True
    wrapped._diverse_hidden_capture_original = original
    logits_processor_class.forward = wrapped
    return original


def install_from_environment() -> TargetVerifyHiddenCapture | None:
    destination = os.environ.get("DIVERSE_HIDDEN_CAPTURE_PATH")
    if not destination:
        return None
    audit_value = os.environ.get("DIVERSE_HIDDEN_CAPTURE_AUDIT")
    audit = pathlib.Path(audit_value) if audit_value else None

    from sglang.srt.layers.logits_processor import LogitsProcessor
    from sglang.srt.models.gemma4_causal import Gemma4ForCausalLM

    logits_source = pathlib.Path(inspect.getsourcefile(LogitsProcessor) or "")
    gemma_source = pathlib.Path(inspect.getsourcefile(Gemma4ForCausalLM) or "")
    source_hashes = {
        "logits_processor": sha256_file(logits_source),
        "gemma4_causal": sha256_file(gemma_source),
    }
    expected = {
        "logits_processor": PINNED_LOGITS_PROCESSOR_SHA256,
        "gemma4_causal": PINNED_GEMMA4_CAUSAL_SHA256,
    }
    if source_hashes != expected:
        raise RuntimeError(f"pinned_source_mismatch:{source_hashes}:{expected}")

    capture = TargetVerifyHiddenCapture(
        CaptureConfig(
            destination=pathlib.Path(destination),
            audit=audit,
            maximum_rows=int(os.environ.get("DIVERSE_HIDDEN_CAPTURE_MAX_ROWS", "1536")),
            expected_hidden_width=int(
                os.environ.get("DIVERSE_HIDDEN_CAPTURE_EXPECTED_WIDTH", "5376")
            ),
            require_eager=os.environ.get(
                "DIVERSE_HIDDEN_CAPTURE_REQUIRE_EAGER", "1"
            )
            == "1",
        )
    )
    install_logits_processor_capture(LogitsProcessor, capture)
    _append_audit(
        audit,
        {
            "event": "capture_hook_installed",
            "source_hashes": source_hashes,
            "destination": destination,
            "time_unix_s": time.time(),
        },
    )
    return capture
