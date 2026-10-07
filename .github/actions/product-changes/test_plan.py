import os
import subprocess
import unittest
from unittest.mock import patch

from plan import changed_paths, plan


class ProductChangesTest(unittest.TestCase):
    def test_credentials_change_installs_rust_components(self):
        result = plan(["product/packages/credentials/src/index.ts"])
        self.assertIn("@gradiated/credentials", result["packages"])
        self.assertTrue(result["unit"])
        self.assertTrue(result["rust"])

    def test_website_does_not_run_backend_or_inference_checks(self):
        result = plan(["product/website/src/pages/TrainingPage.tsx"])
        self.assertTrue(result["website"])
        self.assertEqual(result["packages"], [])
        self.assertEqual(
            [key for key, value in result.items() if value is True], ["website"]
        )

    def test_email_change_checks_api_and_browser_without_rust(self):
        result = plan(["product/services/api/src/email/waitlist-welcome.ts"])
        self.assertEqual(result["packages"], ["@gradiated/api"])
        self.assertTrue(result["playwright"])
        self.assertFalse(result["gateway_contract"])
        self.assertFalse(result["inference_e2e"])
        self.assertFalse(result["inference_native"])
        self.assertFalse(result["backend_storage"])

    def test_shared_contracts_include_dependents_and_rust(self):
        result = plan(["product/packages/contracts/src/index.ts"])
        for package in (
            "@gradiated/api",
            "@gradiated/console",
            "@gradiated/gateway",
            "@gradiated/collector",
            "@gradiated/proxy",
        ):
            self.assertIn(package, result["packages"])
        self.assertTrue(result["website"])
        self.assertTrue(result["integration"])
        self.assertTrue(result["playwright"])
        self.assertFalse(result["inference_native"])

    def test_console_change_does_not_run_inference(self):
        result = plan(["product/services/console/src/pages/models-page.tsx"])
        self.assertEqual(result["packages"], ["@gradiated/console"])
        self.assertTrue(result["playwright"])
        self.assertFalse(result["inference_e2e"])

    def test_gateway_change_checks_runtime_and_relay_boundaries(self):
        result = plan(["product/services/gateway/src/main.rs"])
        for key in (
            "unit",
            "integration",
            "gateway_contract",
            "proxy_e2e",
            "backend_storage",
            "inference_e2e",
        ):
            self.assertTrue(result[key], key)
        self.assertFalse(result["playwright"])
        self.assertFalse(result["inference_native"])

    def test_runtime_change_runs_runtime_checks_without_backend_unit_tests(self):
        result = plan(["product/inference/runtimes/kev/app.py"])
        self.assertTrue(result["native_kev"])
        self.assertTrue(result["inference_e2e"])
        self.assertTrue(result["gateway_contract"])
        self.assertFalse(result["unit"])
        self.assertFalse(result["native_cpp"])
        self.assertFalse(result["native_vllm"])

    def test_root_dependency_and_workflow_changes_run_all_checks(self):
        for path in (
            "product/pnpm-lock.yaml",
            ".github/workflows/tests.yml",
            ".github/actions/product-changes/plan.py",
            "mise.toml",
        ):
            result = plan([path])
            self.assertTrue(all(value for value in result.values()), path)
            self.assertNotIn("@gradiated/wizard", result["packages"])

    def test_manual_dispatch_runs_all_checks(self):
        self.assertTrue(all(plan([], force=True).values()))

    def test_documentation_research_and_screenshot_changes_skip_product_checks(self):
        for paths in (
            ["docs/DEPLOYMENT.md"],
            ["research/lab/src/lib.rs"],
            ["product/website/README.md"],
            ["product/services/console/screenshots/login.png"],
            ["product/website/screenshots/training.png"],
        ):
            self.assertFalse(any(plan(paths).values()), paths)

    def test_local_launcher_change_runs_tooling_validation(self):
        result = plan(["product/mprocs.yaml"])
        self.assertTrue(result["tooling"])
        self.assertFalse(result["unit"])
        self.assertFalse(result["inference_e2e"])

    def test_tooling_changes_run_script_checks(self):
        self.assertTrue(plan(["tools/deployment/update-release.mjs"])["tooling"])
        self.assertFalse(plan(["tools/deployment/update-release.mjs"])["unit"])

    def test_gateway_fixtures_and_ingress_run_api_contract_tests(self):
        for path in (
            "product/services/gateway/src/http.rs",
            "product/services/gateway/test/fixtures/systemone-request.accepted.json",
            "infra/environments/prod/us-east-1/kubernetes/workloads/public-api.yaml",
        ):
            self.assertIn("@gradiated/api", plan([path])["packages"])

    def test_pr_lookup_paginates_and_includes_previous_names(self):
        with (
            patch.dict(
                os.environ,
                {
                    "EVENT": "pull_request",
                    "REPOSITORY": "owner/repo",
                    "PULL_REQUEST": "12",
                },
            ),
            patch(
                "plan.subprocess.check_output",
                return_value="product/website/src/new.tsx\nproduct/services/api/src/old.ts\n",
            ) as lookup,
        ):
            paths, force = changed_paths()
        command = lookup.call_args.args[0]
        self.assertIn("--paginate", command)
        self.assertIn(".[] | .filename, (.previous_filename // empty)", command)
        self.assertFalse(force)
        self.assertTrue(plan(paths)["unit"])
        self.assertTrue(plan(paths)["website"])

    def test_push_uses_full_commit_range_and_deleted_paths(self):
        with (
            patch.dict(
                os.environ, {"EVENT": "push", "BEFORE": "a" * 40, "HEAD": "b" * 40}
            ),
            patch(
                "plan.subprocess.check_output",
                return_value="product/services/console/src/deleted.tsx\n",
            ) as lookup,
        ):
            paths, force = changed_paths()
        self.assertEqual(
            lookup.call_args.args[0],
            ["git", "diff", "--name-only", "--no-renames", "a" * 40, "b" * 40],
        )
        self.assertFalse(force)
        self.assertTrue(plan(paths)["playwright"])

    def test_failed_lookup_is_not_treated_as_no_changes(self):
        with (
            patch.dict(
                os.environ,
                {
                    "EVENT": "pull_request",
                    "REPOSITORY": "owner/repo",
                    "PULL_REQUEST": "12",
                },
            ),
            patch(
                "plan.subprocess.check_output",
                side_effect=subprocess.CalledProcessError(1, "gh"),
            ),
        ):
            with self.assertRaises(subprocess.CalledProcessError):
                changed_paths()

    def test_generated_schema_rebuilds_website(self):
        self.assertTrue(
            plan(["product/services/api/generated/openapi.json"])["website"]
        )


if __name__ == "__main__":
    unittest.main()
