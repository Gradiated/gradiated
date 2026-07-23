from __future__ import annotations

import os
import runpy


baseline = os.environ.get("STACK_BASELINE_SITECUSTOMIZE")
if baseline:
    runpy.run_path(baseline, run_name="_gemma4_retained_stack_sitecustomize")

if os.environ.get("RMS_FP8_ARM") == "candidate":
    from rmsnorm_fp8_patch import install

    install()
