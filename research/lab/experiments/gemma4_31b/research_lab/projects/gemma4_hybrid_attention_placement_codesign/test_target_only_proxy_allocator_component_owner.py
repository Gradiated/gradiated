from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
import hashlib
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def load_owner():
    spec = importlib.util.spec_from_file_location("target_only_owner_test", ROOT / "target_only_proxy_allocator_component_owner.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


class RecordingActions:
    def __init__(self): self.events = []; self.runtime_removal_calls = 0; self.gpu_pool_release_calls = 0
    def persist_repair_ready(self, outcome): self.events.append("repair_ready_persisted")
    def persist_disposition(self, disposition, outcome): self.events.append("disposition_persisted")
    def remove_runtime(self): self.events.append("runtime_removed"); self.runtime_removal_calls += 1
    def release_bench(self): self.events.append("bench_released"); self.gpu_pool_release_calls += 1


class TargetOnlyOwnerDispositionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.owner = load_owner()

    def test_recoverable_prescience_failure_retains_runtime_and_bench(self):
        actions = RecordingActions()
        result = self.owner.apply_disposition(actions, {"kind": "ordinary_allocator_exception", "scientific_component_consumed": False})
        self.assertEqual(result, "retained_repair")
        self.assertEqual(actions.events, ["repair_ready_persisted"])
        self.assertEqual(actions.runtime_removal_calls, 0)
        self.assertEqual(actions.gpu_pool_release_calls, 0)

    def test_unclassified_failure_defaults_to_retained_repair(self):
        actions = RecordingActions()
        result = self.owner.apply_disposition(actions, {"kind": "unknown", "scientific_component_consumed": False})
        self.assertEqual(result, "retained_repair")
        self.assertEqual(actions.runtime_removal_calls, 0)
        self.assertEqual(actions.gpu_pool_release_calls, 0)

    def test_decision_bearing_terminal_persists_before_cleanup_and_release(self):
        actions = RecordingActions()
        result = self.owner.apply_disposition(actions, {"interpretable_component_result": True, "scientific_component_consumed": True})
        self.assertEqual(result, "decision_bearing_terminal_cleanup")
        self.assertEqual(actions.events, ["disposition_persisted", "runtime_removed", "bench_released"])

    def test_unsafe_guest_selects_only_safety_cleanup_branch(self):
        actions = RecordingActions()
        result = self.owner.apply_disposition(actions, {"guest_unreachable": True, "scientific_component_consumed": False})
        self.assertEqual(result, "safety_terminal_cleanup")
        self.assertEqual(actions.events, ["disposition_persisted", "runtime_removed", "bench_released"])

    def test_absolute_deadline_remains_cleanup_and_release_backstop(self):
        actions = RecordingActions()
        result = self.owner.apply_disposition(actions, {"kind": "ordinary_allocator_exception"}, absolute_deadline=True)
        self.assertEqual(result, "absolute_deadline_cleanup")
        self.assertEqual(actions.events, ["disposition_persisted", "runtime_removed", "bench_released"])

    def test_hash_mismatch_rejects_before_claim(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            binding = self._binding(root)
            binding["component_runner"]["sha256"] = "0" * 64
            path = root / "binding.json"; path.write_text(json.dumps(binding))
            previous = os.environ.get("HYBRID_TARGET_ONLY_READMISSION_BINDING")
            os.environ["HYBRID_TARGET_ONLY_READMISSION_BINDING"] = str(path)
            old_verify, old_claim = self.owner.verify_bench_identity, self.owner.pool_claim
            self.owner.verify_bench_identity = lambda value: {}
            self.owner.pool_claim = lambda value: self.fail("claim must not run after hash mismatch")
            try:
                self.assertEqual(self.owner.main(), 2)
            finally:
                self.owner.verify_bench_identity, self.owner.pool_claim = old_verify, old_claim
                if previous is None: os.environ.pop("HYBRID_TARGET_ONLY_READMISSION_BINDING", None)
                else: os.environ["HYBRID_TARGET_ONLY_READMISSION_BINDING"] = previous

    def test_owner_hash_mismatch_rejects_before_claim(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            binding = self._binding(root)
            binding["owner_entrypoint"]["sha256"] = "f" * 64
            path = root / "binding.json"; path.write_text(json.dumps(binding))
            previous = os.environ.get("HYBRID_TARGET_ONLY_READMISSION_BINDING")
            os.environ["HYBRID_TARGET_ONLY_READMISSION_BINDING"] = str(path)
            old_verify, old_claim = self.owner.verify_bench_identity, self.owner.pool_claim
            self.owner.verify_bench_identity = lambda value: {}
            self.owner.pool_claim = lambda value: self.fail("claim must not run after owner hash mismatch")
            try:
                self.assertEqual(self.owner.main(), 2)
            finally:
                self.owner.verify_bench_identity, self.owner.pool_claim = old_verify, old_claim
                if previous is None: os.environ.pop("HYBRID_TARGET_ONLY_READMISSION_BINDING", None)
                else: os.environ["HYBRID_TARGET_ONLY_READMISSION_BINDING"] = previous

    def test_bench_identity_rejects_before_claim(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "binding.json"; path.write_text(json.dumps(self._binding(root)))
            previous = os.environ.get("HYBRID_TARGET_ONLY_READMISSION_BINDING")
            os.environ["HYBRID_TARGET_ONLY_READMISSION_BINDING"] = str(path)
            old_verify, old_claim = self.owner.verify_bench_identity, self.owner.pool_claim
            self.owner.verify_bench_identity = lambda value: (_ for _ in ()).throw(RuntimeError("bound bench connection identity differs from current inventory"))
            self.owner.pool_claim = lambda value: self.fail("claim must not run after identity mismatch")
            try:
                self.assertEqual(self.owner.main(), 2)
            finally:
                self.owner.verify_bench_identity, self.owner.pool_claim = old_verify, old_claim
                if previous is None: os.environ.pop("HYBRID_TARGET_ONLY_READMISSION_BINDING", None)
                else: os.environ["HYBRID_TARGET_ONLY_READMISSION_BINDING"] = previous

    def _binding(self, root):
        owner = ROOT / "target_only_proxy_allocator_component_owner.py"
        runner = ROOT / "target_only_proxy_allocator_component_runner.py"
        return {"artifact_root": str(root / "artifact"), "deadline_utc": "2999-01-01T00:00:00Z", "bench": "fake",
                "source_sha256": hashlib.sha256((ROOT / "forward_batch_dual_cache_driver.py").read_bytes()).hexdigest(),
                "bench_connection_identity": {},
                "owner_entrypoint": {"path": owner.name, "sha256": hashlib.sha256(owner.read_bytes()).hexdigest(), "command": self.owner.START_COMMAND},
                "component_runner": {"path": runner.name, "sha256": hashlib.sha256(runner.read_bytes()).hexdigest(), "command": "python3 target_only_proxy_allocator_component_runner.py"}}


if __name__ == "__main__":
    unittest.main()
