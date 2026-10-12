import json
import os
from pathlib import Path
import signal
import tempfile
import time
import unittest
import uuid
from concurrent.futures import ProcessPoolExecutor

from remote import alive, execute


class RemoteLifecycleTests(unittest.TestCase):
    @unittest.skipUnless(os.geteuid() == 0, "requires root to run workload as nobody")
    def test_lifecycle_preserves_peer_and_runs_unprivileged(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first, second = str(uuid.uuid4()), str(uuid.uuid4())
            try:
                for uid in (first, second):
                    request = {"uid": uid, "pod": {"metadata": {"uid": uid}}}
                    self.assertTrue(execute(root, "create", request)["created"])
                    self.assertFalse(execute(root, "create", request)["created"])
                deadline = time.monotonic() + 5
                while "VK_READY" not in execute(root, "logs", {"uid": first})["logs"]:
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(0.05)
                self.assertIn("uid=65534", execute(root, "logs", {"uid": first})["logs"])
                self.assertEqual(len(execute(root, "list", {})), 2)
                execute(root, "delete", {"uid": first})
                self.assertFalse(execute(root, "delete", {"uid": first})["deleted"])
                self.assertTrue(execute(root, "status", {"uid": second})["running"])
            finally:
                for uid in (first, second):
                    execute(root, "delete", {"uid": uid})
                    for state in root.glob("*/state.json"):
                        info = json.loads(state.read_text())
                        if alive(info):
                            os.killpg(info["pid"], signal.SIGKILL)

    def test_invalid_uid_cannot_escape_workload_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                execute(Path(temporary), "create", {"uid": "../../etc"})

    def test_reused_pid_is_not_owned(self):
        self.assertFalse(alive({"pid": os.getpid(), "start": "wrong-birth-time"}))

    @unittest.skipUnless(os.geteuid() == 0, "requires root to drop workload identity")
    def test_concurrent_create_starts_one_process(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            uid = str(uuid.uuid4())
            request = {"uid": uid, "pod": {"metadata": {"uid": uid}}}
            try:
                with ProcessPoolExecutor(max_workers=4) as pool:
                    results = list(pool.map(execute, [root] * 8, ["create"] * 8, [request] * 8))
                self.assertEqual(sum(result["created"] for result in results), 1)
                deadline = time.monotonic() + 5
                while not execute(root, "status", {"uid": uid})["ready"]:
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(0.05)
            finally:
                execute(root, "delete", {"uid": uid})


if __name__ == "__main__":
    unittest.main()
