#!/usr/bin/env python3
"""Run the immutable framework oracle under the wheel's required config scope."""

from __future__ import annotations

import runpy
import sys

from vllm.config import VllmConfig, set_current_vllm_config


oracle, *arguments = sys.argv[1:]
sys.argv = [oracle, *arguments]
with set_current_vllm_config(VllmConfig()):
    runpy.run_path(oracle, run_name="__main__")
