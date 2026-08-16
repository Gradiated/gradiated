from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parent


def module(name: str, path: Path):
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


class Layer:
    def __init__(self):
        self.self_attn = type("Attention", (), {})()


class Model:
    def __init__(self):
        self.language_model = type("Text", (), {"layers": [Layer() for _ in range(60)]})()


class FullModelMemoryAdapterTest(unittest.TestCase):
    def test_memory_contract_and_single_model_bridge(self):
        recovery = module("full_model_memory_adapter", ROOT / "full_model_memory_adapter.py")
        bridge = module("phase_selective_full_model_remote", ROOT / "phase_selective_full_model_remote.py")
        plan = recovery.memory_plan()
        self.assertLessEqual(plan["expected_peak_gib"], 132.0)
        self.assertGreaterEqual(plan["margin_gib"], 7.8)
        argv = recovery.production_server_argv()
        self.assertIn("sglang.launch_server", argv)
        self.assertNotIn("ModelRunner", " ".join(argv))
        model = Model()
        binding = bridge.install_phase_selective_adapter(model)
        self.assertTrue(binding["one_resident_target_model"])
        self.assertTrue(bridge.adapter_is_bound(model))
        for index in recovery.CONVERTED_LAYERS:
            self.assertEqual(model.language_model.layers[index].self_attn._phase_selective_cache_binding, binding)
        with self.assertRaisesRegex(RuntimeError, "already bound"):
            bridge.install_phase_selective_adapter(model)

    def test_terminal_is_source_complete_and_hashes_changed_inputs(self):
        recovery = module("full_model_memory_adapter_terminal", ROOT / "full_model_memory_adapter.py")
        terminal = recovery.build_terminal()
        self.assertEqual(terminal["classification"], "source_complete_operational_repair")
        self.assertFalse(terminal["scientific_component_consumed"])
        self.assertFalse(terminal["candidate_cuda_invocation_started"])
        self.assertEqual(terminal["adapter"]["converted_layers"], [11, 23, 35, 47, 59])
        self.assertIn("move_kv_cache", " ".join(terminal["adapter"]["insertion_points"]))
        json.dumps(terminal)


if __name__ == "__main__":
    unittest.main()
