"""Exercise subcheck selection and its PR/push integration without network access."""

import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from test_workflow_filters import triggers

ROOT = Path(__file__).resolve().parents[3]
ACTION = ROOT / ".github/actions/relevant"
spec = importlib.util.spec_from_file_location("subchecks", ACTION / "select.py")
subchecks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(subchecks)


def selected(name, paths, force=False):
    return subchecks.select(
        paths, json.loads((ACTION / f"{name}.json").read_text()),
        ".github/workflows/virtual-kubelet.yml", force,
    )


class SubcheckSelectionTest(unittest.TestCase):
    def test_fleet_operator_changes_run_the_rejoin_test(self):
        for path in ("product/services/gpu-fleet/src/rollout.ts", "product/packages/gpu-hosts/src/tailscale.ts",
                     "product/packages/control/src/index.ts", "product/pnpm-lock.yaml",
                     "product/inference/host/gradiated_host/tailscale.py"):
            with self.subTest(path=path):
                self.assertTrue(selected("gpu", [path])["rejoin"])

    def test_model_catalog_changes_skip_the_rejoin_test(self):
        paths = ["product/packages/control/src/catalog/models/kimi-k31-pro.ts",
                 "product/packages/control/test/catalog-models.test.ts"]
        self.assertFalse(selected("gpu", paths)["rejoin"])
        self.assertTrue(selected("gpu", [*paths, "product/packages/control/src/index.ts"])["rejoin"])

    def test_controller_source_only_selects_controller_scope(self):
        self.assertEqual(
            selected("gpu", ["tools/virtual-kubelet/cmd/gpu-controller/main.go"]),
            {"controller": True, "image": False, "rejoin": False},
        )

    def test_host_bundle_inputs_select_the_gpu_base_image_checks(self):
        for path in ("product/inference/runtime-launcher/main.cpp", "product/inference/bundles/host/Dockerfile",
                     "product/inference/images/gpu-base/Dockerfile", "product/inference/gpu/host-agent.py"):
            self.assertTrue(selected("gpu", [path])["image"], path)
        self.assertFalse(selected("gpu", ["tools/virtual-kubelet/cmd/gpu-controller/main.go"])["image"])

    def test_shared_inputs_and_dispatch_run_every_subcheck(self):
        for path in ("mise.toml", ".github/actions/relevant/select.py", ".github/workflows/virtual-kubelet.yml"):
            self.assertTrue(all(selected("gpu", [path]).values()), path)
        self.assertTrue(all(selected("gpu", [], force=True).values()))

    def test_unrelated_changes_select_no_subchecks(self):
        self.assertFalse(any(selected("gpu", ["docs/ARCHITECTURE.md"]).values()))

    def test_declared_subcheck_inputs_are_covered_by_workflow_triggers(self):
        paths = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines()
        text = (ROOT / ".github/workflows/virtual-kubelet.yml").read_text()
        for path in paths:
            if any(selected("gpu", [path]).values()):
                self.assertTrue(triggers(text, path), path)


class RelevantActionIntegrationTest(unittest.TestCase):
    def run_action(self, event, changes="", fail_lookup=False, invalid_before=False, zero_before=False):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bin_path = root / "bin"
            bin_path.mkdir()
            for name, source in {
                "yq": "#!/bin/bash\nif [[ $1 == *'.on.push.paths'* ]]; then echo 'tools/virtual-kubelet/*'; else echo test; fi\n",
                "gh": "#!/bin/bash\nif [[ $FAIL_LOOKUP == true ]]; then exit 1; fi\nprintf '%s\\n' \"$CHANGES\"\n",
            }.items():
                path = bin_path / name
                path.write_text(source)
                path.chmod(0o755)

            def git(*args):
                return subprocess.check_output(["git", *args], cwd=root, text=True, stderr=subprocess.DEVNULL).strip()

            git("init")
            git("config", "user.name", "Test")
            git("config", "user.email", "test@example.com")
            (root / "initial").write_text("initial")
            git("add", ".")
            git("commit", "-m", "initial")
            before = git("rev-parse", "HEAD")
            path = root / "tools/virtual-kubelet/cmd/gpu-controller/main.go"
            path.parent.mkdir(parents=True)
            path.write_text("changed")
            git("add", ".")
            git("commit", "-m", "change")
            (root / "notes.md").write_text("a later documentation commit")
            git("add", ".")
            git("commit", "-m", "later docs")
            output = root / "output"
            env = {
                **os.environ, "PATH": str(bin_path) + os.pathsep + os.environ["PATH"],
                "EVENT": event, "WORKFLOW": ".github/workflows/virtual-kubelet.yml",
                "SCOPES": str(ACTION / "gpu.json"), "GITHUB_ACTION_PATH": str(ACTION),
                "GITHUB_OUTPUT": str(output), "REPOSITORY": "owner/repo", "PULL_REQUEST": "1",
                "BEFORE": "0" * 40 if zero_before else "missing" if invalid_before else before,
                "HEAD": git("rev-parse", "HEAD"),
                "CHANGES": changes, "FAIL_LOOKUP": str(fail_lookup).lower(),
            }
            result = subprocess.run(["bash", str(ACTION / "relevant.sh")], cwd=root, env=env, capture_output=True, text=True)
            values = dict(line.split("=", 1) for line in output.read_text().splitlines()) if output.exists() else {}
            return result, values

    def test_pr_previous_filename_selects_both_old_and_new_scopes(self):
        result, outputs = self.run_action("pull_request", "tools/virtual-kubelet/moved.py\nproduct/inference/bundles/host/Dockerfile")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(outputs["relevant"], "true")
        checks = json.loads(outputs["checks"])
        self.assertTrue(checks["controller"])
        self.assertTrue(checks["image"])

    def test_push_uses_git_range_without_pr_lookup(self):
        result, outputs = self.run_action("push", fail_lookup=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(outputs["checks"]), {"controller": True, "image": False, "rejoin": False})

    def test_manual_dispatch_selects_all(self):
        result, outputs = self.run_action("workflow_dispatch", fail_lookup=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(all(json.loads(outputs["checks"]).values()))

    def test_new_branch_push_without_base_selects_all(self):
        result, outputs = self.run_action("push", zero_before=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(all(json.loads(outputs["checks"]).values()))

    def test_irrelevant_pr_skips_every_subcheck(self):
        result, outputs = self.run_action("pull_request", "docs/ARCHITECTURE.md")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(outputs["relevant"], "false")
        self.assertFalse(any(json.loads(outputs["checks"]).values()))

    def test_failed_lookup_and_unavailable_push_base_fail_the_action(self):
        for event, options in (("pull_request", {"fail_lookup": True}), ("push", {"invalid_before": True})):
            result, _ = self.run_action(event, **options)
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
