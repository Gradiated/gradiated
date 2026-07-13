import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKLOADS = ROOT / "workloads"
sys.path.insert(0, str(WORKLOADS))

from build_bundle import build_bundle
from validate_bundle import BundleError, load_and_validate


def tree_digest(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(path.iterdir()):
        if item.is_file():
            digest.update(item.name.encode())
            digest.update(item.read_bytes())
    return digest.hexdigest()


class WorkloadBundleTest(unittest.TestCase):
    def test_build_is_deterministic_and_valid(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            build_bundle(Path(first))
            build_bundle(Path(second))
            self.assertEqual(tree_digest(Path(first)), tree_digest(Path(second)))
            bundle = load_and_validate(Path(first))
            bindings_sha256 = hashlib.sha256((Path(first) / "TOKENIZER_BINDINGS.json").read_bytes()).hexdigest()

        self.assertEqual(bundle["contract"]["service_contract"], {
            "max_p95_ttft_ms": 10_000,
            "max_p95_inter_token_latency_ms": 100,
            "min_request_success_rate": 0.99,
            "silent_truncation_allowed": False,
        })
        self.assertIn("TOKENIZER_BINDINGS.json", bundle["manifest"]["files"])
        self.assertIn("REPLAY_SCHEDULE.json", bundle["manifest"]["files"])
        self.assertIn("AA_AGENTPERF_LENGTH_ONLY_GEOMETRY.json", bundle["manifest"]["files"])
        self.assertEqual(
            bundle["contract"]["tokenizer_contract"]["bindings_sha256"],
            bindings_sha256,
        )

    def test_required_classes_splits_and_fail_closed_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            build_bundle(Path(directory))
            bundle = load_and_validate(Path(directory))

        required = {"fixed_8k_1k", "agent_append", "agent_prefix"}
        self.assertEqual(set(bundle["contract"]["required_classes"]), required)
        development = bundle["records"]["development"]
        holdout = bundle["records"]["holdout"]
        self.assertEqual({record["workload_class"] for record in development}, required)
        self.assertEqual({record["workload_class"] for record in holdout}, required)
        self.assertFalse({record["fixture_id"] for record in development} & {record["fixture_id"] for record in holdout})
        dev_sessions = {record.get("tokenizer_binding", {}).get("raw_message_sha256") for record in development if record["content_representation"] != "length_only"}
        holdout_sessions = {record.get("tokenizer_binding", {}).get("raw_message_sha256") for record in holdout if record["content_representation"] != "length_only"}
        self.assertFalse(dev_sessions & holdout_sessions)
        for record in development + holdout:
            self.assertIn(record["provenance"]["reuse_status"], {"synthetic_owned", "length_only_public_distribution"})
            self.assertNotEqual(record["provenance"]["reuse_status"], "public_content_unverified")
            if record["workload_class"] == "fixed_8k_1k":
                self.assertEqual(record["input_tokens"], 8192)
                self.assertEqual(record["max_output_tokens"], 1024)
                self.assertEqual(record["content_representation"], "length_only")
            if record["workload_class"] == "agent_prefix":
                self.assertEqual(record["prefix_identity"]["kind"], "exact_sha256")

    def test_replay_schedule_is_explicit_and_public_proxy_is_length_only(self):
        with tempfile.TemporaryDirectory() as directory:
            build_bundle(Path(directory))
            bundle = load_and_validate(Path(directory))

        schedule = bundle["replay_schedule"]
        for profile in schedule["profiles"]:
            self.assertGreater(profile["request_count"], 0)
            self.assertGreater(profile["max_concurrency"], 0)
            self.assertIn("arrival", profile)
            self.assertIn("warmup", profile)
            self.assertIn("cache", profile)
        geometry = bundle["aa_agentperf_length_only_geometry"]
        self.assertEqual(geometry["content_representation"], "length_only_geometry")
        self.assertFalse(geometry["claim_gates"]["aa_agentperf_score_claim_permitted"])
        self.assertFalse(geometry["claim_gates"]["measured_performance_claim_permitted"])
        self.assertEqual(geometry["public_basis"]["minimum_input_tokens"], 5000)
        self.assertEqual(geometry["public_basis"]["maximum_input_tokens"], 131000)
        self.assertEqual(geometry["public_basis"]["approximate_mean_input_tokens"], 27000)

    def test_tokenizer_binding_tampering_is_rejected_even_when_manifest_is_rehashed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            build_bundle(path)
            bindings_path = path / "TOKENIZER_BINDINGS.json"
            bindings = json.loads(bindings_path.read_text())
            bindings["resolved_revision"] = "different"
            bindings_path.write_text(json.dumps(bindings, sort_keys=True, separators=(",", ":")) + "\n")
            manifest_path = path / "FROZEN_MANIFEST.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["files"]["TOKENIZER_BINDINGS.json"] = hashlib.sha256(bindings_path.read_bytes()).hexdigest()
            files = json.dumps(manifest["files"], sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
            manifest["bundle_sha256"] = hashlib.sha256(files).hexdigest()
            manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n")
            with self.assertRaises(BundleError):
                load_and_validate(path)

    def test_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            build_bundle(path)
            records_path = path / "development.jsonl"
            records = records_path.read_text()
            records_path.write_text(records.replace("agent_append", "agent_corrupt", 1))
            with self.assertRaises(BundleError):
                load_and_validate(path)

    def test_unverified_content_provenance_is_rejected_even_with_rehashed_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            build_bundle(path)
            records_path = path / "development.jsonl"
            records = [json.loads(line) for line in records_path.read_text().splitlines()]
            records[0]["provenance"]["reuse_status"] = "public_content_unverified"
            payload = copy.deepcopy(records[0])
            payload.pop("content_sha256")
            canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
            records[0]["content_sha256"] = hashlib.sha256(canonical).hexdigest()
            records_path.write_text("".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in records))
            manifest_path = path / "FROZEN_MANIFEST.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["files"]["development.jsonl"] = hashlib.sha256(records_path.read_bytes()).hexdigest()
            manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n")
            with self.assertRaises(BundleError):
                load_and_validate(path)


if __name__ == "__main__":
    unittest.main()
