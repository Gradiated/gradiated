from __future__ import annotations

import importlib
import os


if os.environ.get("QKV_STACK_ARM") == "candidate":
    importlib.import_module("stack_sitecustomize")
if os.environ.get("E5M2_FA3_LAYER_HYBRID") == "1":
    importlib.import_module("install_hybrid_backend").install()
