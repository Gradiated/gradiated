import json
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from server import Host


class StartupTests(unittest.TestCase):
    def test_accepts_lease_heartbeats_before_loading_large_models(self):
        recipe = {"model": "test/glm", "gpu_count": 4}
        with (
            patch.dict(
                "os.environ",
                {
                    "NOMAD_ALLOC_DIR": "/tmp/allocation",
                    "NOMAD_ALLOC_ID": "allocation-1",
                    "TRAINING_RECIPE_JSON": json.dumps(recipe),
                },
            ),
            patch("server.TrainingRuntime") as trainer,
            patch("server.threading.Thread"),
        ):
            host = Host()
            trainer.assert_called_once_with("/tmp/allocation/training", recipe)
            trainer.return_value.load.assert_not_called()
            trainer.return_value.stop.is_set.return_value = False
            host.renew("allocation-1")


class TrainerEventTests(unittest.TestCase):
    def host(self):
        host = Host.__new__(Host)
        host.lock = threading.Lock()
        host.job = {"events": []}
        return host

    def test_method_specific_events_preserve_diagnostics_without_lifecycle_authority(
        self,
    ):
        host = self.host()
        host.emit({"type": "stage_entered", "stage": "succeeded"})
        host.emit(
            {
                "type": "trainer_failed",
                "message": "trainer_failed",
                "error_code": "internal",
            }
        )
        first, failure = host.job["events"]
        self.assertEqual(first["type"], "trainer_observation")
        self.assertEqual(first["details"], {"stage": "succeeded"})
        self.assertEqual(failure["type"], "trainer_observation")
        self.assertEqual(failure["level"], "error")
        self.assertEqual(failure["details"]["error_code"], "internal")

    def test_progress_and_checkpoint_events_retain_their_core_fields(self):
        host = self.host()
        progress = {"type": "trainer_progress", "step": 10, "train_loss": 0.5}
        checkpoint = {
            "type": "trainer_checkpoint",
            "step": 10,
            "key": "runs/test/checkpoint",
            "sha256": "a" * 64,
            "size_bytes": 100,
        }
        host.emit(progress)
        host.emit(checkpoint)
        self.assertEqual(host.job["events"], [progress, checkpoint])


class ReservationTests(unittest.TestCase):
    def host(self):
        host = Host.__new__(Host)
        host.lock = threading.Lock()
        host.allocation_id = "allocation-1"
        host.lease = 200
        host.deadline = 1000
        host.trainer = SimpleNamespace(stop=threading.Event())
        host.job = {
            "id": "operation-1",
            "status": "complete",
            "events": [],
            "result": None,
        }
        return host

    def test_renews_only_the_exact_allocation_and_caps_at_hard_deadline(self):
        host = self.host()
        with patch("server.time.monotonic", return_value=100):
            with self.assertRaisesRegex(ValueError, "Wrong allocation"):
                host.renew("allocation-2")
            self.assertEqual(host.lease, 200)
            host.renew("allocation-1")
            self.assertEqual(host.lease, 280)
            host.deadline = 250
            host.renew("allocation-1")
            self.assertEqual(host.lease, 250)

    def test_expired_reservation_cannot_be_revived_or_accept_compute(self):
        host = self.host()
        with patch("server.time.monotonic", return_value=200):
            with self.assertRaisesRegex(ValueError, "expired"):
                host.renew("allocation-1")
            with self.assertRaisesRegex(ValueError, "expired"):
                host.start({"id": "operation-2"})
            self.assertEqual(host.lease, 200)

    def test_polling_does_not_extend_reservation(self):
        host = self.host()
        host.poll("operation-1", 0)
        self.assertEqual(host.lease, 200)

    def test_watchdog_stops_abandoned_compute_before_exiting(self):
        host = self.host()
        with (
            patch("server.time.monotonic", return_value=201),
            patch("server.time.sleep"),
            patch("server.os._exit", side_effect=SystemExit) as exit_process,
        ):
            with self.assertRaises(SystemExit):
                host.watchdog()
        self.assertTrue(host.trainer.stop.is_set())
        exit_process.assert_called_once_with(75)
