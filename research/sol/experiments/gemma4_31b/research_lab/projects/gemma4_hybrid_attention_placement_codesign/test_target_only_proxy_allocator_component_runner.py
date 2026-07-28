from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def load_runner():
    spec = importlib.util.spec_from_file_location("target_only_runner_test", ROOT / "target_only_proxy_allocator_component_runner.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


class FakeTransport:
    def __init__(self, runner, *, corrupt=False):
        self.runner, self.corrupt = runner, corrupt
        self.calls: list[str] = []

    def remote(self, command):
        self.calls.append("remote")
        return self.runner.Completed(0, command, "")

    def copy_to(self, files, destination):
        self.calls.append("copy_to")
        return self.runner.Completed(0, destination, "")

    def copy_from(self, source, destination):
        self.calls.append("copy_from")
        result = destination / "artifact" / "forward-batch-activation-c32"
        result.mkdir(parents=True)
        (result / "INVOCATION.json").write_text(json.dumps({"science_started": True, "submitted_requests": 32}))
        root = result.parent
        (root / "adapter_attach.json").write_text(json.dumps({"attached": True, "one_resident_target_model": True}))
        (root / "forward_batch_dual_cache.json").write_text(json.dumps({
            "mode": "TARGET_VERIFY", "logical_rows": 384, "padded_rows_cache_inert": True,
            "cache_policy": "production_dual_allocator_shadow_write_accept_move_reject_free",
            "first_target_consumer": "NGRAMWorker.forward_batch_generation",
        }))
        if self.corrupt:
            (result / "TERMINAL.json").write_text("not json")
        else:
            (result / "TERMINAL.json").write_text(json.dumps({
                "kind": "activation_only_not_component_decision", "complete": 32,
                "accepted_request_observed": True, "candidate_cuda_invocation_started": True,
            }))
        return self.runner.Completed(0)


class TargetOnlyComponentRunnerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner = load_runner()

    def binding(self, artifact_root):
        return {"artifact_root": str(artifact_root), "remote_workspace": "/remote/work", "runtime_name": "phase-selective-readmission",
                "component_program": {"server_launch_command": "launch", "readiness_command": "ready", "target_verify_command": "consumer"}}

    def test_fake_transport_reaches_typed_pinned_consumer_boundary(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            transport = FakeTransport(self.runner)
            result = self.runner.run_component(self.binding(root), root, transport, {})
            self.assertTrue(result["interpretable_component_result"])
            self.assertTrue(result["scientific_component_consumed"])
            self.assertEqual(transport.calls, ["remote", "copy_to", "remote", "remote", "remote", "copy_from"])
            self.assertFalse(any("release" in call or "cleanup" in call for call in transport.calls))

    def test_corrupt_retrieval_is_typed_nondecision_bearing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = self.runner.run_component(self.binding(root), root, FakeTransport(self.runner, corrupt=True), {})
            self.assertEqual(result["failure_kind"], "component_evidence_corrupt")
            self.assertFalse(result["scientific_component_consumed"])
            self.assertFalse(result["interpretable_component_result"])

    def test_runner_has_no_pool_or_runtime_cleanup_authority(self):
        source = (ROOT / "target_only_proxy_allocator_component_runner.py").read_text()
        self.assertNotIn("grad_research.gpu_pool", source)
        self.assertNotIn("docker rm", source)
        self.assertIn(self.runner.START_COMMAND, source)


if __name__ == "__main__":
    unittest.main()
