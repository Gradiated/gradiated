from __future__ import annotations

import importlib
import os


if os.environ.get("MIXED_KV_STACK_ARM") == "candidate":
    importlib.import_module("dependency_stack_sitecustomize")
if os.environ.get("E4M3_FA3_LAYER_HYBRID") == "1":
    importlib.import_module("install_hybrid_backend").install()
