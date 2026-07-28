import importlib.util
import json
import pathlib
import subprocess
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "ngram_readmission_controller_test",
    ROOT / "ngram_readmission_controller.py",
)
CONTROLLER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(CONTROLLER)


class PreloadReadinessTest(unittest.TestCase):
    def test_rejects_live_attached_container_during_graph_capture(self):
        output = (
            '{"attached": true}\n'
            '{"installed": true}\n'
            "CONTAINER_RUNNING=true\n"
            "Capture cuda graph begin\n"
        )
        self.assertFalse(CONTROLLER.preload_ready(output))

    def test_accepts_native_post_graph_ready_marker(self):
        output = (
            '{"attached": true}\n'
            '{"installed": true}\n'
            "CONTAINER_RUNNING=true\n"
            f"{CONTROLLER.CUDA_GRAPH_COMPLETE_MARKER}\n"
            f"{CONTROLLER.SERVER_READY_MARKER}\n"
            "TCP_LISTENER=True\n"
        )
        self.assertTrue(CONTROLLER.preload_ready(output))

    def test_rejects_ready_log_from_stopped_container(self):
        output = (
            '{"attached": true}\n'
            '{"installed": true}\n'
            "CONTAINER_RUNNING=false\n"
            f"{CONTROLLER.CUDA_GRAPH_COMPLETE_MARKER}\n"
            f"{CONTROLLER.SERVER_READY_MARKER}\n"
            "TCP_LISTENER=True\n"
        )
        self.assertFalse(CONTROLLER.preload_ready(output))


class RepairRetentionTest(unittest.TestCase):
    def setUp(self):
        self.original_art = CONTROLLER.ART
        self.original_state = CONTROLLER.STATE
        self.original_deadline = CONTROLLER.DEADLINE
        self.temporary = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.temporary.name)
        CONTROLLER.ART = root
        CONTROLLER.STATE = root / "OWNER_STATE.json"
        CONTROLLER.DEADLINE = "2099-01-01T00:00:00Z"
        self.diagnostic = root / "diagnostic.log"
        self.diagnostic.write_text("typed integration failure\n")

    def tearDown(self):
        CONTROLLER.ART = self.original_art
        CONTROLLER.STATE = self.original_state
        CONTROLLER.DEADLINE = self.original_deadline
        self.temporary.cleanup()

    def test_hash_bound_request_preserves_claim_for_replacement_owner(self):
        complete = subprocess.CompletedProcess([], 0, "", "")
        with (
            mock.patch.object(CONTROLLER, "run", return_value=complete),
            mock.patch.object(CONTROLLER.subprocess, "run", return_value=complete),
            mock.patch.object(CONTROLLER, "release_bench") as release,
        ):
            self.assertEqual(
                CONTROLLER.repair(
                    "component_consumer_failed",
                    self.diagnostic,
                    "repair_ready",
                    science_started=True,
                ),
                2,
            )
        state = json.loads(CONTROLLER.STATE.read_text())
        self.assertEqual(state["phase"], "repair_requested")
        self.assertTrue(state["science_started"])
        self.assertTrue(state["replacement_owner_required"])
        release.assert_not_called()

    def test_repair_deadline_releases_claim(self):
        complete = subprocess.CompletedProcess([], 0, "", "")
        expired = subprocess.TimeoutExpired(["repair-handshake", "wait"], 1)
        with (
            mock.patch.object(CONTROLLER, "run", return_value=complete),
            mock.patch.object(CONTROLLER.subprocess, "run", side_effect=expired),
            mock.patch.object(CONTROLLER, "release_bench") as release,
        ):
            self.assertEqual(
                CONTROLLER.repair(
                    "component_consumer_failed",
                    self.diagnostic,
                    "repair_ready",
                    science_started=True,
                ),
                2,
            )
        state = json.loads(CONTROLLER.STATE.read_text())
        self.assertEqual(state["phase"], "repair_deadline_released")
        release.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
