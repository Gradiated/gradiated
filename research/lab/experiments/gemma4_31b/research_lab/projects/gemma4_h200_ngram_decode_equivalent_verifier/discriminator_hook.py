"""Internal first-divergent-token trace for control and NGRAM verification."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import time

import torch


SOURCE_SHA256 = {
    "tp_worker": "f2e00ea7d53b7250231d44b9d52415c6f6b5f936b0e7c6af4a13f5aff6c1e509",
    "ngram_info": "ffa88c663e1893c306710ac801da0693d8248ebcfd1a5bc705c157f90657af1c",
}
_invocation = 0
_last_verify_invocation: int | None = None


def _source_hash(module: object) -> str:
    return hashlib.sha256(pathlib.Path(module.__file__).read_bytes()).hexdigest()


def _cpu(value):
    if value is None:
        return None
    if isinstance(value, torch.Tensor):
        return value.detach().cpu().tolist()
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_cpu(item) for item in value]
    return str(value)


def _append(row: dict) -> None:
    path = pathlib.Path(os.environ["DISCRIMINATOR_EVENTS"])
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
    try:
        payload = json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
        os.write(descriptor, payload.encode())
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _mode_name(mode: object) -> str:
    return getattr(mode, "name", str(mode))


def install() -> None:
    from sglang.srt.managers import tp_worker
    from sglang.srt.speculative import ngram_info

    observed = {
        "tp_worker": _source_hash(tp_worker),
        "ngram_info": _source_hash(ngram_info),
    }
    if observed != SOURCE_SHA256:
        raise RuntimeError(f"discriminator_source_mismatch:{observed}")

    worker_cls = tp_worker.TpModelWorker
    if not getattr(worker_cls, "_decode_equivalent_discriminator_installed", False):
        original_forward = worker_cls.forward_batch_generation

        def traced_forward(
            self,
            batch,
            forward_batch=None,
            pp_proxy_tensors=None,
            is_verify=False,
            skip_attn_backend_init=None,
        ):
            global _invocation, _last_verify_invocation
            if batch is None:
                return original_forward(
                    self,
                    batch,
                    forward_batch,
                    pp_proxy_tensors,
                    is_verify,
                    skip_attn_backend_init,
                )

            mode = batch.forward_mode
            interesting = (
                mode.is_decode()
                or mode.is_target_verify()
                or mode.is_extend()
            )
            if not interesting:
                return original_forward(
                    self,
                    batch,
                    forward_batch,
                    pp_proxy_tensors,
                    is_verify,
                    skip_attn_backend_init,
                )

            _invocation += 1
            invocation = _invocation
            if mode.is_target_verify():
                _last_verify_invocation = invocation
            spec = batch.spec_info
            prefixes = [
                list(req.origin_input_ids) + list(req.output_ids)
                for req in batch.reqs
            ]
            before = {
                "invocation": invocation,
                "mode": _mode_name(mode),
                "rids": [req.rid for req in batch.reqs],
                "prefix_ids": prefixes,
                "input_ids": _cpu(batch.input_ids),
                "seq_lens": _cpu(batch.seq_lens),
                "seq_lens_cpu": _cpu(batch.seq_lens_cpu),
                "out_cache_loc": _cpu(batch.out_cache_loc),
                "positions": _cpu(getattr(spec, "positions", None)),
                "retrieve_index": _cpu(getattr(spec, "retrieve_index", None)),
                "retrieve_next_token": _cpu(
                    getattr(spec, "retrieve_next_token", None)
                ),
                "retrieve_next_sibling": _cpu(
                    getattr(spec, "retrieve_next_sibling", None)
                ),
                "custom_mask_shape": (
                    list(spec.custom_mask.shape)
                    if spec is not None
                    and isinstance(getattr(spec, "custom_mask", None), torch.Tensor)
                    else None
                ),
                "attention_dispatch": None,
                "graph_requested_batch_size": batch.batch_size(),
                "target_symbols": {
                    "worker": f"{type(self).__module__}.{type(self).__qualname__}.forward_batch_generation",
                    "model_runner": f"{type(self.model_runner).__module__}.{type(self.model_runner).__qualname__}.forward",
                    "spec_info": (
                        None
                        if spec is None
                        else f"{type(spec).__module__}.{type(spec).__qualname__}"
                    ),
                },
            }
            backend = self.model_runner.attn_backend
            if hasattr(backend, "_select_backend"):
                selected = backend._select_backend(mode)
                before["attention_dispatch"] = {
                    "wrapper": f"{type(backend).__module__}.{type(backend).__qualname__}",
                    "selected": f"{type(selected).__module__}.{type(selected).__qualname__}",
                    "speculative_attention_mode": self.server_args.speculative_attention_mode,
                }

            result = original_forward(
                self,
                batch,
                forward_batch,
                pp_proxy_tensors,
                is_verify,
                skip_attn_backend_init,
            )
            logits = result.logits_output.next_token_logits
            values, ids = torch.topk(logits, k=2, dim=-1)
            before.update(
                {
                    "stage": "target_forward",
                    "at_monotonic": time.monotonic(),
                    "can_run_cuda_graph": result.can_run_cuda_graph,
                    "logit_rows": logits.shape[0],
                    "top2_values": _cpu(values),
                    "top2_ids": _cpu(ids),
                    "argmax_ids": _cpu(ids[:, 0]),
                }
            )
            if mode.is_target_verify():
                from decode_equivalent_lm_head import get_shadow_baseline

                baseline = get_shadow_baseline(logits.shape[0])
                if baseline is not None:
                    baseline_values, baseline_ids = baseline
                    before["native_shadow_top2_values"] = _cpu(baseline_values)
                    before["native_shadow_top2_ids"] = _cpu(baseline_ids)
                    before["native_shadow_argmax_ids"] = _cpu(
                        baseline_ids[:, 0]
                    )
            _append(before)
            return result

        worker_cls.forward_batch_generation = traced_forward
        worker_cls._decode_equivalent_discriminator_installed = True

    verify_cls = ngram_info.NgramVerifyInput
    if not getattr(verify_cls, "_decode_equivalent_discriminator_installed", False):
        original_verify = verify_cls.verify

        def traced_verify(
            self,
            batch,
            logits_output,
            page_size,
            vocab_mask=None,
        ):
            result = original_verify(
                self, batch, logits_output, page_size, vocab_mask
            )
            _append(
                {
                    "stage": "verification_result",
                    "invocation": _last_verify_invocation,
                    "at_monotonic": time.monotonic(),
                    "predict": _cpu(self.predict),
                    "accept_indices": _cpu(self.accept_indices),
                    "num_correct_drafts": _cpu(self.num_correct_drafts),
                    "num_accept_tokens": _cpu(self.num_accept_tokens),
                    "draft_tokens": _cpu(self.draft_token),
                    "next_token_ids": _cpu(result[1]),
                }
            )
            return result

        verify_cls.verify = traced_verify
        verify_cls._decode_equivalent_discriminator_installed = True

    _append(
        {
            "stage": "hook_installed",
            "at_monotonic": time.monotonic(),
            "source_sha256": observed,
        }
    )
