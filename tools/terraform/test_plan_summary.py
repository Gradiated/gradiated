import json
from pathlib import Path
import tempfile
import unittest

from plan_summary import summarize


class PlanSummaryTests(unittest.TestCase):
    def render(self, **plan):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            unit = directory / "database"
            unit.mkdir()
            (unit / "tfplan.json").write_text(json.dumps({"format_version": "1.2", **plan}))
            return summarize(directory)

    def test_replacement_and_changed_fields_without_values(self):
        summary = self.render(resource_changes=[{
            "address": "aws_db_instance.primary",
            "change": {"actions": ["delete", "create"],
                       "before": {"password": "old-secret", "port": 5432},
                       "after": {"password": "new-secret", "port": 5432},
                       "after_unknown": {"id": True}},
        }], output_changes={"password": {
            "actions": ["update"], "before": "old-secret", "after": "new-secret",
        }})
        self.assertIn("1 REPLACE", summary)
        self.assertIn("`aws_db_instance.primary`", summary)
        self.assertIn("`id`, `password`", summary)
        self.assertNotIn("`port`", summary)
        self.assertNotIn("old-secret", summary)
        self.assertNotIn("new-secret", summary)

    def test_no_changes(self):
        self.assertIn("No planned changes", self.render(resource_changes=[{
            "address": "terraform_data.example", "change": {"actions": ["no-op"]},
        }]))

    def test_move_import_and_drift_are_not_reported_as_no_changes(self):
        summary = self.render(resource_drift=[{
            "address": "aws_db_instance.primary",
            "change": {"actions": ["update"],
                       "before": {"password": "old-secret", "port": 5432},
                       "after": {"password": "new-secret", "port": 5432}},
        }], resource_changes=[
            {"address": "terraform_data.new", "previous_address": "terraform_data.old",
             "change": {"actions": ["no-op"]}},
            {"address": "terraform_data.imported",
             "change": {"actions": ["no-op"], "importing": {"id": "hidden-import-id"}}},
        ])
        self.assertIn("1 MOVE", summary)
        self.assertIn("1 IMPORT", summary)
        self.assertIn("drift in 1 resources", summary)
        self.assertIn("refresh update | `aws_db_instance.primary` | `password`", summary)
        self.assertNotIn("1 update", summary)
        self.assertNotIn("old-secret", summary)
        self.assertNotIn("new-secret", summary)
        self.assertNotIn("hidden-import-id", summary)

    def test_missing_or_incomplete_plans_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                summarize(Path(temporary))
        for flags in ({"complete": False}, {"errored": True}, {"format_version": "2.0"}):
            with self.assertRaises(ValueError):
                self.render(**flags)

    def test_large_drift_cannot_hide_a_planned_replacement(self):
        drift = {"address": "terraform_data.refresh_only",
                 "change": {"actions": ["update"],
                            "before": {"input": "old"}, "after": {"input": "new"}}}
        replacement = {
            "address": "aws_db_instance.primary",
            "change": {"actions": ["delete", "create"]},
        }
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for name, changes in [("a-drift", {"resource_drift": [drift] * 1_000}),
                                  ("z-database", {"resource_changes": [replacement]})]:
                unit = directory / name
                unit.mkdir()
                (unit / "tfplan.json").write_text(json.dumps({"format_version": "1.2", **changes}))
            summary = summarize(directory)
        self.assertIn("1 REPLACE", summary)
        self.assertLess(summary.index("REPLACE | `aws_db_instance.primary`"),
                        summary.index("refresh update"))
        self.assertIn("Preview truncated", summary)
        self.assertLess(len(summary), 51_000)

    def test_markdown_escaping_and_length_limit(self):
        resource = {"address": "terraform_data.`bad|<tag>\n",
                    "change": {"actions": ["create"], "after": {"id": "not-for-comments"}}}
        summary = self.render(resource_changes=[resource] * 1_000)
        self.assertNotIn("<tag>", summary)
        self.assertNotIn("not-for-comments", summary)
        self.assertIn("Preview truncated", summary)
        self.assertLess(len(summary), 51_000)


if __name__ == "__main__":
    unittest.main()
