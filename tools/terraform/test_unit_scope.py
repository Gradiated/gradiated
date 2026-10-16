import unittest

from unit_scope import last_apply, scope

BASE = "a" * 40
HEAD = "b" * 40


class UnitScopeTests(unittest.TestCase):
    def test_bootstrap_and_workflow_changes_do_not_expand_to_all_production(self):
        for changed in [["infra/bootstrap/security-audit/recovery.tf"],
                        [".github/workflows/terraform.yml", "tools/terraform/unit_scope.py"],
                        ["product/packages/control/package.json"]]:
            self.assertEqual(scope(BASE, HEAD, changed), f"...[{BASE}...{HEAD}]")

    def test_module_changes_keep_native_dependency_selection(self):
        self.assertEqual(scope(BASE, HEAD, ["infra/modules/monitoring/main.tf"]), f"...[{BASE}...{HEAD}]")

    def test_shared_provider_and_backend_inputs_require_full_scope(self):
        for path in ["mise.toml", "infra/environments/prod/us-east-1/terraform/root.hcl"]:
            self.assertEqual(scope(BASE, HEAD, [path]), "")

    def test_manual_full_apply_is_explicit(self):
        self.assertEqual(scope(None, HEAD, [], force_all=True), "")

    def test_missing_or_invalid_baseline_does_not_silently_apply_everything(self):
        for base in [None, "", "not-a-commit"]:
            with self.assertRaises(ValueError):
                scope(base, HEAD, [])

    def test_selects_actual_apply_not_a_newer_skipped_workflow(self):
        runs = [{"databaseId": 3, "headSha": "c" * 40, "event": "push"},
                {"databaseId": 2, "headSha": "d" * 40, "event": "push"},
                {"databaseId": 1, "headSha": BASE, "event": "push"}]
        jobs = {3: [{"name": "Production apply", "conclusion": "skipped"}],
                2: [{"name": "Format and validate", "conclusion": "success"}],
                1: [{"name": "Production apply", "conclusion": "success"}]}
        self.assertEqual(last_apply(runs, jobs.__getitem__), BASE)

    def test_pull_request_runs_cannot_be_apply_baselines(self):
        runs = [{"databaseId": 2, "headSha": HEAD, "event": "pull_request"},
                {"databaseId": 1, "headSha": BASE, "event": "workflow_dispatch"}]
        self.assertEqual(last_apply(runs, lambda _: [{"name": "Production apply", "conclusion": "success"}]), BASE)

    def test_missing_apply_history_fails_closed(self):
        with self.assertRaises(ValueError):
            last_apply([], lambda _: [])


if __name__ == "__main__":
    unittest.main()
