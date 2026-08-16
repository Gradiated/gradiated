"""Attach the bound phase adapter to SGLang's single resident model at load.

This is intentionally a narrow launch-time bridge: it neither creates a model
nor changes attention execution.  The component driver must still supply the
bound TARGET_VERIFY/cache operations.
"""
from __future__ import annotations

import json
from pathlib import Path


def _record(payload: dict) -> None:
    path = Path("/work/artifact/adapter_attach.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    tmp.write_text(json.dumps(payload, sort_keys=True) + "\n")
    tmp.replace(path)


try:
    from sglang.srt.model_executor.model_runner import ModelRunner
    from forward_batch_dual_cache_driver import install_forward_batch_dual_cache_driver
    from phase_selective_full_model_remote import install_phase_selective_adapter

    _original = ModelRunner.load_model

    def _load_and_attach(self, *args, **kwargs):
        result = _original(self, *args, **kwargs)
        binding = install_phase_selective_adapter(self.model)
        driver = install_forward_batch_dual_cache_driver(self)
        _record({"attached": True, "converted_layers": binding["converted_layers"],
                 "one_resident_target_model": binding["one_resident_target_model"],
                 "forward_batch_driver": driver})
        return result

    ModelRunner.load_model = _load_and_attach
except Exception as error:
    _record({"attached": False, "preload_error": repr(error)})
    raise
