#!/usr/bin/env python3
"""One-pass SGLang hook for request-owned Gemma target-layer taps."""

from __future__ import annotations

import atexit
import hashlib
import json
import os
import pathlib
import threading
import time


TAP_LAYERS = (45, 54, 60)
COMMON_PREFIX_TOKENS = 535
REQUEST_MARKER_BASE = 200000
REQUEST_COUNT = 32
HIDDEN = 5376


def _atomic_json(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


class OffsetTapCapture:
    def __init__(self, root: pathlib.Path, rows_per_chunk: int = 128) -> None:
        self.root = root
        self.rows_per_chunk = rows_per_chunk
        self.lock = threading.Lock()
        self.request_by_rid: dict[str, int] = {}
        self.pending: list[dict] = []
        self.chunk_index = 0
        self.row_count = 0
        self.first_error: str | None = None
        self.root.mkdir(parents=True, exist_ok=True)

    def _rid(self, value: object) -> str:
        return str(value)

    def _map_prefill_requests(self, input_ids, forward_batch) -> None:
        if not forward_batch.rids:
            raise RuntimeError("prefill_rids_missing")
        lengths = forward_batch.extend_seq_lens_cpu
        starts = forward_batch.extend_start_loc
        if lengths is None or starts is None:
            raise RuntimeError("prefill_ownership_missing")
        starts_cpu = starts.detach().cpu().tolist()
        tokens_cpu = input_ids.detach().cpu()
        for row, (rid, start, length) in enumerate(
            zip(forward_batch.rids, starts_cpu, lengths, strict=True)
        ):
            if length <= COMMON_PREFIX_TOKENS:
                continue
            marker = int(tokens_cpu[start + COMMON_PREFIX_TOKENS].item())
            request_index = marker - REQUEST_MARKER_BASE
            if 0 <= request_index < REQUEST_COUNT:
                self.request_by_rid[self._rid(rid)] = request_index

    def _rows(self, input_ids, hidden_states, forward_batch, aux_hidden_states):
        mode = forward_batch.forward_mode
        if mode.is_extend() and not mode.is_target_verify():
            self._map_prefill_requests(input_ids, forward_batch)
            if not forward_batch.rids:
                return []
            lengths = forward_batch.extend_seq_lens_cpu
            starts = forward_batch.extend_start_loc.detach().cpu().tolist()
            selected = [
                int(start + length - 1)
                for start, length in zip(starts, lengths, strict=True)
            ]
            target_offsets = [0] * len(selected)
        elif mode.is_decode():
            if not forward_batch.rids:
                raise RuntimeError("decode_rids_missing")
            selected = list(range(len(forward_batch.rids)))
            sequence_lengths = (
                forward_batch.seq_lens_cpu.tolist()
                if forward_batch.seq_lens_cpu is not None
                else forward_batch.seq_lens.detach().cpu().tolist()
            )
            target_offsets = [int(length) - 4214 for length in sequence_lengths]
        else:
            return []
        if aux_hidden_states is None or len(aux_hidden_states) != len(TAP_LAYERS):
            raise RuntimeError("aux_tap_contract")
        rows = []
        for batch_row, (rid, tensor_row, target_offset) in enumerate(
            zip(
                forward_batch.rids,
                selected,
                target_offsets,
                strict=True,
            )
        ):
            request_index = self.request_by_rid.get(self._rid(rid))
            if request_index is None:
                continue
            rows.append(
                {
                    "request_index": request_index,
                    "rid": self._rid(rid),
                    "batch_row": batch_row,
                    "target_offset": target_offset,
                    "input_id": int(input_ids[tensor_row].detach().cpu().item()),
                    "taps": [
                        tap[tensor_row].detach().to("cpu", copy=True)
                        for tap in aux_hidden_states
                    ],
                    "final_hidden": hidden_states[tensor_row]
                    .detach()
                    .to("cpu", copy=True),
                }
            )
        return rows

    def observe(
        self, input_ids, hidden_states, forward_batch, aux_hidden_states
    ) -> None:
        if self.first_error is not None:
            return
        try:
            rows = self._rows(
                input_ids, hidden_states, forward_batch, aux_hidden_states
            )
            with self.lock:
                self.pending.extend(rows)
                self.row_count += len(rows)
                if len(self.pending) >= self.rows_per_chunk:
                    self.flush()
        except Exception as exc:
            self.first_error = f"{type(exc).__name__}:{exc}"[:2000]
            _atomic_json(
                self.root / "OBSERVER_ERROR.json",
                {
                    "schema_version": 1,
                    "classification": "observer_error",
                    "error": self.first_error,
                    "rows_persisted": self.row_count - len(self.pending),
                },
            )

    def flush(self) -> None:
        if not self.pending:
            return
        import torch

        rows = self.pending
        self.pending = []
        path = self.root / f"tap-chunk-{self.chunk_index:05d}.pt"
        temporary = path.with_suffix(".pt.part")
        payload = {
            "schema_version": 1,
            "tap_layers": TAP_LAYERS,
            "hidden_size": HIDDEN,
            "rows": [
                {
                    key: value
                    for key, value in row.items()
                    if key not in ("taps", "final_hidden")
                }
                for row in rows
            ],
            "taps": [
                torch.stack([row["taps"][index] for row in rows])
                for index in range(len(TAP_LAYERS))
            ],
            "final_hidden": torch.stack([row["final_hidden"] for row in rows]),
        }
        torch.save(payload, temporary)
        temporary.replace(path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        with (self.root / "chunks.jsonl").open("a") as stream:
            stream.write(
                json.dumps(
                    {
                        "chunk": path.name,
                        "rows": len(rows),
                        "sha256": digest,
                    },
                    sort_keys=True,
                )
                + "\n"
            )
            stream.flush()
            os.fsync(stream.fileno())
        self.chunk_index += 1

    def close(self) -> None:
        with self.lock:
            self.flush()
            _atomic_json(
                self.root / "CAPTURE_TERMINAL.json",
                {
                    "schema_version": 1,
                    "classification": (
                        "one_pass_target_tap_capture"
                        if self.first_error is None
                        else "observer_invalid"
                    ),
                    "pass": self.first_error is None,
                    "tap_layers": list(TAP_LAYERS),
                    "hidden_size": HIDDEN,
                    "rows": self.row_count,
                    "request_mapping_count": len(set(self.request_by_rid.values())),
                    "chunks": self.chunk_index,
                    "observer_error": self.first_error,
                    "completed_unix_s": time.time(),
                },
            )


_capture: OffsetTapCapture | None = None


def install() -> None:
    global _capture
    root_value = os.environ.get("CAUSAL_OFFSET_CAPTURE_ROOT")
    if not root_value:
        return
    root = pathlib.Path(root_value)
    _capture = OffsetTapCapture(root)
    import sglang.srt.models.gemma4_causal as gemma4_causal
    from sglang.srt.layers.logits_processor import LogitsProcessor

    original_init = gemma4_causal.Gemma4ForCausalLM.__init__
    original_forward = LogitsProcessor.forward

    def model_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.capture_aux_hidden_states = True
        self.model.layers_to_capture = list(TAP_LAYERS)

    def logits_forward(
        self,
        input_ids,
        hidden_states,
        lm_head,
        logits_metadata,
        aux_hidden_states=None,
        hidden_states_before_norm=None,
    ):
        if _capture is not None and hasattr(logits_metadata, "forward_mode"):
            _capture.observe(
                input_ids, hidden_states, logits_metadata, aux_hidden_states
            )
        return original_forward(
            self,
            input_ids,
            hidden_states,
            lm_head,
            logits_metadata,
            aux_hidden_states,
            hidden_states_before_norm,
        )

    gemma4_causal.Gemma4ForCausalLM.__init__ = model_init
    LogitsProcessor.forward = logits_forward
    atexit.register(_capture.close)
