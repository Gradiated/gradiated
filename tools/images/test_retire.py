import contextlib
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import retire


NOW = datetime(2026, 10, 20, tzinfo=timezone.utc)
REPO = "gradiated/prod/inference"
REGISTRY = "123456789012.dkr.ecr.us-east-1.amazonaws.com"


def digest(number):
    return "sha256:" + f"{number:064x}"


def image(number, age=100, pulled=None, tags=None):
    result = {"imageDigest": digest(number), "imagePushedAt": (NOW - timedelta(days=age)).isoformat(),
              "imageTags": tags or []}
    if pulled is not None:
        result["lastRecordedPullTime"] = (NOW - timedelta(days=pulled)).isoformat()
    return result


class RetirementTests(unittest.TestCase):
    def plan(self, entries, manifests=None, protected=None):
        if manifests is None:
            manifests = {(REPO, item["imageDigest"]): {} for item in entries}
        return retire.retirement_plan({REPO: entries}, manifests, protected or set(), NOW, 90)

    def test_long_lived_pod_and_stopped_pod_images_survive_even_without_recent_pull(self):
        entries = [image(1, tags=["old-base"]), image(2, tags=["stopped-base"]), image(3)]
        references = [f"{REGISTRY}/{REPO}:old-base", f"{REGISTRY}/{REPO}:stopped-base"]
        protected = retire.protected_images({REPO: entries}, references, REGISTRY)
        self.assertEqual([item["digest"] for item in self.plan(entries, protected=protected)], [digest(3)])

    def test_split_kustomize_digest_pin_and_resolved_pod_id_protect_images(self):
        entries = [image(1), image(2)]
        references = [f"newName: {REGISTRY}/{REPO}\ndigest: {digest(1)}",
                      f"containerd://{digest(2)}"]
        protected = retire.protected_images({REPO: entries}, references, REGISTRY)
        self.assertEqual(self.plan(entries, protected=protected), [])

    def test_recent_push_or_recent_pull_survives(self):
        self.assertEqual(self.plan([image(1, age=20), image(2, pulled=20), image(3, age=90)]), [])
        self.assertEqual(len(self.plan([image(1, age=100, pulled=91)])), 1)

    def test_retained_index_protects_old_platform_and_attestation_manifests(self):
        entries = [image(1, age=10), image(2), image(3)]
        manifests = {(REPO, digest(1)): {"manifests": [{"digest": digest(2)}, {"digest": digest(3)}]},
                     (REPO, digest(2)): {}, (REPO, digest(3)): {}}
        self.assertEqual(self.plan(entries, manifests), [])

    def test_delete_unused_index_before_children_and_subject(self):
        entries = [image(1), image(2), image(3)]
        manifests = {(REPO, digest(1)): {"manifests": [{"digest": digest(2)}]},
                     (REPO, digest(2)): {"subject": {"digest": digest(3)}},
                     (REPO, digest(3)): {}}
        self.assertEqual([item["digest"] for item in self.plan(entries, manifests)],
                         [digest(1), digest(2), digest(3)])

    def test_protected_child_can_survive_retired_parent(self):
        entries = [image(1), image(2)]
        manifests = {(REPO, digest(1)): {"manifests": [{"digest": digest(2)}]}, (REPO, digest(2)): {}}
        self.assertEqual([item["digest"] for item in self.plan(entries, manifests, {(REPO, digest(2))})],
                         [digest(1)])

    def test_retained_subject_keeps_its_signature_referrer(self):
        entries = [image(1, age=10), image(2)]
        manifests = {(REPO, digest(1)): {},
                     (REPO, digest(2)): {"subject": {"digest": digest(1)}}}
        self.assertEqual(self.plan(entries, manifests), [])

    def test_missing_manifest_and_unresolved_reference_fail_closed(self):
        with self.assertRaisesRegex(RuntimeError, "Missing manifest"):
            self.plan([image(1)], {})
        with self.assertRaisesRegex(RuntimeError, "missing from ECR"):
            retire.protected_images({REPO: [image(1)]}, [f"{REGISTRY}/{REPO}:unknown"], REGISTRY)
        with self.assertRaisesRegex(RuntimeError, "outside cleanup"):
            retire.protected_images({REPO: []}, [f"{REGISTRY}/gradiated/prod/other:tag"], REGISTRY)

    def test_inventory_ignores_historical_annotations_but_keeps_current_spec_status_and_config(self):
        def output(arguments):
            if arguments[0] == "git":
                return ""
            resource = arguments[3]
            item = {"metadata": {"annotations": {"old": "historical-pin"}},
                    "spec": {"image": "current-spec"}, "status": {"imageID": "current-status"},
                    "data": {"image": "current-config"}}
            return json.dumps({"items": [item]})

        with patch.object(retire, "runpod_images", return_value=["provider-base"]):
            with patch.object(retire, "run", side_effect=output):
                references = retire.inventory("private-test-key")
        self.assertNotIn("historical-pin", references)
        for reference in ["provider-base", "current-spec", "current-status", "current-config"]:
            self.assertIn(reference, references)

    @patch.dict("os.environ", {"RUNPOD_API_KEY": "private-test-key"})
    @patch.object(sys, "argv", ["retire.py", "--account", "123456789012", "--repositories", REPO, "--apply"])
    def test_inventory_failure_never_deletes(self):
        with patch.object(retire, "aws", return_value={"Account": "123456789012"}) as aws:
            with patch.object(retire, "inventory", side_effect=RuntimeError("incomplete")):
                with self.assertRaisesRegex(RuntimeError, "incomplete"):
                    retire.main()
        self.assertEqual(aws.call_count, 1)

    @patch.dict("os.environ", {"RUNPOD_API_KEY": "private-test-key"})
    def test_apply_rechecks_inventory_and_keeps_newly_referenced_image(self):
        entries = {REPO: [image(1)]}
        manifests = {(REPO, digest(1)): {}}
        arguments = ["retire.py", "--account", "123456789012", "--repositories", REPO, "--apply"]
        with patch.object(sys, "argv", arguments), contextlib.redirect_stdout(io.StringIO()):
            with patch.object(retire, "aws", return_value={"Account": "123456789012"}) as aws:
                with patch.object(retire, "inventory", side_effect=[[], [digest(1)]]):
                    with patch.object(retire, "ecr_inventory", return_value=(entries, manifests)):
                        with patch.object(retire, "datetime") as clock:
                            clock.now.return_value = NOW
                            clock.fromisoformat.side_effect = datetime.fromisoformat
                            retire.main()
        self.assertEqual(aws.call_count, 1)

    @patch.dict("os.environ", {"RUNPOD_API_KEY": "private-test-key"})
    def test_preview_never_deletes(self):
        arguments = ["retire.py", "--account", "123456789012", "--repositories", REPO]
        with patch.object(sys, "argv", arguments), contextlib.redirect_stdout(io.StringIO()):
            with patch.object(retire, "aws", return_value={"Account": "123456789012"}) as aws:
                with patch.object(retire, "inventory", return_value=[]):
                    with patch.object(retire, "ecr_inventory", return_value=({REPO: [image(1)]}, {(REPO, digest(1)): {}})):
                        retire.main()
        self.assertEqual(aws.call_count, 1)

    def test_run_command_does_not_disclose_secret_payload_on_failure(self):
        result = subprocess.CompletedProcess([], 1, "credential-value", "credential-value")
        with patch.object(retire.subprocess, "run", return_value=result):
            with self.assertRaises(RuntimeError) as error:
                retire.run(["aws", "secretsmanager"])
        self.assertNotIn("credential-value", str(error.exception))

    def test_runpod_errors_or_missing_templates_fail_closed(self):
        for result in [
            {"errors": [{"message": "upstream failed"}]},
            {"data": {"myself": {"pods": [], "podTemplates": []}}},
            {"data": {"myself": {"pods": [{"id": "pod", "imageName": "base", "templateId": "missing"}],
                                 "podTemplates": []}}},
        ]:
            with self.subTest(result=result), patch.object(retire.urllib.request, "urlopen") as urlopen:
                urlopen.return_value.__enter__.return_value = io.StringIO(json.dumps(result))
                with self.assertRaises(RuntimeError):
                    retire.runpod_images("private-test-key")


if __name__ == "__main__":
    unittest.main()
