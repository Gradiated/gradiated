import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "phase_b" / "remote_baseline.sh"


class PhaseBRuntimeHarnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = HARNESS.read_text()

    def test_shell_is_syntactically_valid_and_fail_closed(self):
        subprocess.run(["bash", "-n", HARNESS], check=True)
        self.assertIn("set -Eeuo pipefail", self.source)
        self.assertIn("trap finish EXIT", self.source)
        self.assertIn("CAMPAIGN_DEADLINE_EPOCH", self.source)
        self.assertIn("timeout --signal=TERM", self.source)

    def test_runtime_model_and_contract_identities_are_pinned(self):
        required = {
            "f63458b5beaceabbd9d749b9fc956370e1b649e6",
            "sha256:655d004115e384b56b73ad6869bb04b29cce7ba3e597ce8f92eeeb49e2acb0af",
            "zai-org/GLM-4.7-Flash",
            "75fce703a93da3705c4cf8d3caadbac1d1072c78",
            "c974f23e460a863be37b3cc04df80fc9aff977e239a5c49225cd8c85f1bb3d55",
            "c5258d650227ab3c474f25218263c5ac1898011f55aecef16def5fe10cf7fa64",
            "0a7ba38e9cd5b627381e59194f3ab5df8e402995b8e0424869ae34a97a077041",
        }
        for identity in required:
            self.assertIn(identity, self.source)
        self.assertIn("EXPERIMENT_SPEC_SHA256", self.source)
        self.assertIn("WORKLOAD_ARCHIVE_B64", self.source)
        self.assertIn("QUALITY_ARCHIVE_B64", self.source)

    def test_startup_allows_fifteen_minutes_and_fast_fails_server_exit(self):
        self.assertRegex(self.source, r"STARTUP_TIMEOUT_SECONDS=(?:\"?900\"?)")
        self.assertIn('kill -0 "$SERVER_PID"', self.source)
        self.assertIn('wait "$SERVER_PID"', self.source)
        self.assertIn("/health", self.source)

    def test_first_allocation_is_stock_only_and_attributable(self):
        self.assertIn("stock_no_cache_fcfs", self.source)
        self.assertNotIn("tuned_prefix_cache_fcfs", self.source)
        self.assertNotIn("tuned_prefix_cache_lpm", self.source)
        self.assertIn("--disable-radix-cache", self.source)
        self.assertIn("--schedule-policy fcfs", self.source)

    def test_mtp_is_off_and_obsolete_client_flag_is_absent(self):
        forbidden = (
            "--ignore-eos",
            "--speculative-algorithm",
            "--speculative-num-steps",
            "SGLANG_ENABLE_SPEC_V2",
            "NEXTN",
            "EAGLE",
        )
        for token in forbidden:
            self.assertNotIn(token, self.source)
        self.assertNotIn("ignore_eos", self.source)

    def test_frozen_workloads_and_deterministic_sampling_are_replayed(self):
        for profile in ("development_smoke", "fixed_8k_1k_c1", "fixed_8k_1k_c8"):
            self.assertIn(profile, self.source)
        self.assertIn('python3 "$WORKLOAD/replay_api.py"', self.source)
        self.assertIn("--random-input-len 8192", self.source)
        self.assertIn("--random-output-len 128", self.source)
        self.assertIn("token_ids_u32le_sha256", self.source)
        self.assertIn("token_hash(ids)", self.source)
        self.assertIn("materialized-plan-identities.json", self.source)
        for source_hash in (
            "19e773648cb4e65de8660ea6365e10acca112d42a854923df93db4a6f333a82d",
            "31a173e2797ddc8b72ac996803513e627fc28d7aad02cfcce321a431d865c86d",
            "d63ad536c3c81880043e22ec7fd08db42b4d8fb7c89c7138bc562bfa25281375",
        ):
            self.assertIn(source_hash, self.source)
        self.assertIn("silent_truncation", self.source)
        self.assertIn('row["latency_ms"]["itl"]', self.source)
        self.assertIn("--stream-interval 1", self.source)
        self.assertIn('python3 "$QUALITY/run_pair.py"', self.source)
        self.assertIn("--mode capture", self.source)
        self.assertIn("--mode score", self.source)

    def test_matrix_escalates_sequentially_and_excludes_headline_c32(self):
        self.assertIn("for profile in development_smoke fixed_8k_1k_c1 fixed_8k_1k_c8; do", self.source)
        self.assertIn('if [ "$runner_rc" -ne 0 ] || [ "$profile_gate" != PASS ]', self.source)
        self.assertIn("break", self.source)
        self.assertIn('"headline_c32_executed": False', self.source)
        self.assertNotIn("for profile in development_smoke fixed_8k_1k_c1 fixed_8k_1k_c8 fixed_8k_1k_c32", self.source)

    def test_materialized_plan_cardinality_is_bound_and_hashed(self):
        self.assertIn('"development_smoke": 5', self.source)
        self.assertIn('"fixed_8k_1k_c1": 4', self.source)
        self.assertIn('"fixed_8k_1k_c8": 16', self.source)
        self.assertIn('"plan_sha256": hashlib.sha256(payload).hexdigest()', self.source)
        self.assertIn("materialized request cardinality mismatch", self.source)

    def test_http_logs_cannot_mutate_the_packaged_artifact(self):
        self.assertIn('> "$PUBLIC/http-server.stdout.log"', self.source)
        self.assertIn('2> "$PUBLIC/http-server.stderr.log"', self.source)
        self.assertNotIn('> "$OUT/http-server.stdout.log"', self.source)
        self.assertNotIn('2> "$OUT/http-server.stderr.log"', self.source)

    def test_required_telemetry_profiler_and_packaging_are_present(self):
        for evidence in (
            "telemetry.csv",
            "dcgm-dmon",
            "/metrics",
            "SGLANG_TORCH_PROFILER_DIR",
            "--profile",
            "profiler",
            "startup-timings",
            "request-outcomes",
            "manifest.json",
            "tar -C",
            "sha256sum",
        ):
            self.assertIn(evidence, self.source)
        self.assertRegex(self.source, r"sleep (?:1|\"\$TELEMETRY_CADENCE_SECONDS\")")
        self.assertGreater(self.source.index("phase profiler begin"), self.source.index("phase workload_sequence complete"))
        self.assertIn("--random-output-len 128", self.source)
        self.assertIn("--num-prompts 1", self.source)

    def test_profile_runner_is_bounded_and_preserves_typed_failures(self):
        self.assertIn('timeout --signal=TERM 1800 python3 "$WORKLOAD/replay_api.py"', self.source)
        self.assertIn("runner_rc=$?", self.source)
        self.assertIn("convert_profile", self.source)
        self.assertIn('"error": has_error', self.source)
        self.assertIn("runner did not produce typed outcomes", self.source)


if __name__ == "__main__":
    unittest.main()
