"""One-shot exact c32 verifier capture for the bound SGLang runtime."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import time


def _append(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _install() -> None:
    target = os.environ.get("HIDDEN_PROPOSALS_CAPTURE_PATH")
    audit = os.environ.get("HIDDEN_PROPOSALS_CAPTURE_AUDIT")
    if not target or not audit:
        return

    from sglang.srt.layers.logits_processor import LogitsProcessor

    original = LogitsProcessor.forward
    captured = False

    def wrapped(self, input_ids, hidden_states, lm_head, logits_metadata, *args, **kwargs):
        nonlocal captured
        verify = getattr(logits_metadata.forward_mode, "is_target_verify", None)
        if not captured and callable(verify) and verify():
            shape = tuple(hidden_states.shape)
            input_shape = tuple(input_ids.shape)
            dtype = str(hidden_states.dtype)
            _append(
                pathlib.Path(audit),
                {
                    "event": "target_verify_observed",
                    "shape": list(shape),
                    "input_shape": list(input_shape),
                    "dtype": dtype,
                    "time_unix_s": time.time(),
                },
            )
            if shape == (384, 5376) and input_shape == (384,) and dtype == "torch.bfloat16":
                hidden = hidden_states.detach().to("cpu").contiguous()
                proposals = input_ids.detach().to("cpu").to(dtype=getattr(__import__("torch"), "int32")).contiguous()
                if bool(__import__("torch").isfinite(hidden).all().item()) and bool(
                    ((proposals >= 0) & (proposals < 262144)).all().item()
                ):
                    destination = pathlib.Path(target)
                    temporary = destination.with_suffix(destination.suffix + ".part")
                    __import__("torch").save(
                        {"hidden_states": hidden, "proposals": proposals}, temporary
                    )
                    os.replace(temporary, destination)
                    _append(
                        pathlib.Path(audit),
                        {
                            "event": "exact_capture_committed",
                            "path": str(destination),
                            "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                            "hidden_shape": list(hidden.shape),
                            "hidden_dtype": str(hidden.dtype),
                            "proposal_shape": list(proposals.shape),
                            "proposal_dtype": str(proposals.dtype),
                        },
                    )
                    captured = True
        return original(self, input_ids, hidden_states, lm_head, logits_metadata, *args, **kwargs)

    LogitsProcessor.forward = wrapped


try:
    _install()
except Exception as exc:  # Preserve the bound runtime; audit the hook defect.
    audit = os.environ.get("HIDDEN_PROPOSALS_CAPTURE_AUDIT")
    if audit:
        _append(pathlib.Path(audit), {"event": "hook_install_error", "error": repr(exc)})
