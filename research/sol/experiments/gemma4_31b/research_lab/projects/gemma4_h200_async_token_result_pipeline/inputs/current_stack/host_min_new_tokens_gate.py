from __future__ import annotations

import hashlib
import pathlib


TARGET = pathlib.Path(
    "/sgl-workspace/sglang/python/sglang/srt/sampling/penaltylib/min_new_tokens.py"
)
EXPECTED_SHA256 = "bd63f0aab997da6e5a90ad27c4daaa6aadbac69d325bc9ae0510297103c0d276"

NEW = '''import json
import os

import torch

from sglang.srt.sampling.penaltylib.orchestrator import _BatchedPenalizer


class BatchedMinNewTokensPenalizer(_BatchedPenalizer):
    """Penalize stop tokens until each request reaches min_new_tokens."""

    def _is_required(self) -> bool:
        return any(
            req.sampling_params.min_new_tokens > 0 for req in self.orchestrator.reqs()
        )

    def _prepare(self):
        reqs = self.orchestrator.reqs()
        self.min_new_tokens = torch.tensor(
            data=[req.sampling_params.min_new_tokens for req in reqs],
            dtype=torch.int32,
            device=self.orchestrator.device,
        ).unsqueeze_(1)

        padded_stop_token_ids = torch.nn.utils.rnn.pad_sequence(
            sequences=[
                torch.tensor(
                    data=list(
                        (req.sampling_params.stop_token_ids or set())
                        | (req.tokenizer.additional_stop_token_ids or set())
                        | {req.tokenizer.eos_token_id}
                    ),
                    dtype=torch.int64,
                    device=self.orchestrator.device,
                )
                for req in reqs
            ],
            batch_first=True,
            padding_value=self.orchestrator.vocab_size,
        )
        self.stop_token_penalties = torch.zeros(
            size=(len(reqs), self.orchestrator.vocab_size + 1),
            dtype=torch.float32,
            device=self.orchestrator.device,
        ).scatter_add_(
            dim=1,
            index=padded_stop_token_ids,
            src=torch.full_like(
                input=padded_stop_token_ids,
                dtype=torch.float32,
                fill_value=float("-inf"),
                device=self.orchestrator.device,
            ),
        )[:, : self.orchestrator.vocab_size]

        self._min_new_tokens_host = {
            req.rid: req.sampling_params.min_new_tokens for req in reqs
        }
        self._len_output_tokens_host = {req.rid: 0 for req in reqs}
        self._active_host = {
            req.rid: req.sampling_params.min_new_tokens > 0 for req in reqs
        }
        for row, req in enumerate(reqs):
            if not self._active_host[req.rid]:
                self.stop_token_penalties[row].zero_()
        self._host_gate_audited = False

    def _cumulate_output_tokens(self, output_ids: torch.Tensor):
        for row, req in enumerate(self.orchestrator.reqs()):
            rid = req.rid
            previous = self._len_output_tokens_host[rid]
            current = previous + 1
            self._len_output_tokens_host[rid] = current
            if self._active_host[rid] and current >= self._min_new_tokens_host[rid]:
                self._active_host[rid] = False
                self.stop_token_penalties[row].zero_()

    def _apply(self, logits: torch.Tensor):
        active_count = sum(
            self._active_host[req.rid] for req in self.orchestrator.reqs()
        )
        if not self._host_gate_audited:
            if audit := os.environ.get("SYNC_CANDIDATE_AUDIT"):
                with open(audit, "a") as handle:
                    handle.write(
                        json.dumps(
                            {
                                "active_count": active_count,
                                "batch_size": len(self.orchestrator.reqs()),
                                "candidate_path": "BatchedMinNewTokensPenalizer.host_required_dense_add",
                                "host_counter": True,
                                "no_device_scalar_read": True,
                                "phase": "runtime_invocation",
                            },
                            sort_keys=True,
                        )
                        + "\\n"
                    )
            self._host_gate_audited = True
        if active_count:
            logits.add_(self.stop_token_penalties)

    def _filter(self, keep_indices: torch.Tensor):
        self.min_new_tokens = self.min_new_tokens[keep_indices]
        self.stop_token_penalties = self.stop_token_penalties[keep_indices]
        live = {req.rid for req in self.orchestrator.reqs()}
        self._min_new_tokens_host = {
            rid: value for rid, value in self._min_new_tokens_host.items() if rid in live
        }
        self._len_output_tokens_host = {
            rid: value for rid, value in self._len_output_tokens_host.items() if rid in live
        }
        self._active_host = {
            rid: value for rid, value in self._active_host.items() if rid in live
        }

    def _merge(self, their: "BatchedMinNewTokensPenalizer"):
        self.min_new_tokens = torch.cat(
            [self.min_new_tokens, their.min_new_tokens], dim=0
        )
        self.stop_token_penalties = torch.cat(
            [self.stop_token_penalties, their.stop_token_penalties], dim=0
        )
        self._min_new_tokens_host.update(their._min_new_tokens_host)
        self._len_output_tokens_host.update(their._len_output_tokens_host)
        self._active_host.update(their._active_host)

    def _teardown(self) -> None:
        for name in (
            "min_new_tokens",
            "stop_token_penalties",
            "_min_new_tokens_host",
            "_len_output_tokens_host",
            "_active_host",
            "_host_gate_audited",
        ):
            if hasattr(self, name):
                delattr(self, name)
'''


def install() -> None:
    raw = TARGET.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual == hashlib.sha256(NEW.encode()).hexdigest():
        return
    if actual != EXPECTED_SHA256:
        raise RuntimeError(f"bound min_new_tokens source mismatch:{actual}")
    TARGET.write_text(NEW)
