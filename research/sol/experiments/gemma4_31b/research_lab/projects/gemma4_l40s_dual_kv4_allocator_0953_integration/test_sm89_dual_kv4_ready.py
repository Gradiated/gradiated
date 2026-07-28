from pathlib import Path
import ast
import unittest


ROOT = Path(__file__).parent


class ReadyContractTests(unittest.TestCase):
    def test_runner_has_two_real_pairs_and_arm_isolation(self):
        source = (ROOT / "sm89_dual_kv4_runner.py").read_text()
        ast.parse(source)
        for token in ("local_kv4_outlier_cuda.cu", "global_tiered_kv4_cuda.cu", "extension.pack(", "extension.pack_old(", "extension.paged_attention(", "baseline_first_untimed_complete", "candidate_first_untimed_complete", "arm.upper()}_ROWS.json", "cuobjdump"):
            self.assertIn(token, source)
        self.assertNotIn("checkpoint", source.lower().replace("no checkpoint", ""))

    def test_owner_is_bounded_repair_aware_and_checkpoint_free(self):
        source = (ROOT / "l40s_dual_kv4_owner.py").read_text()
        ast.parse(source)
        for token in ("repair-handshake", "heartbeat", "--expected-claimed-at", "sudo -n docker", "SCIENCE_STARTED.json"):
            self.assertIn(token, source)
        self.assertNotIn("huggingface", source.lower())


if __name__ == "__main__":
    unittest.main()
