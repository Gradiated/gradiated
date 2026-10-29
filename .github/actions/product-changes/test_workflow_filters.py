"""Guard trigger coverage for inputs shared by workflow selectors and jobs."""

import unittest
from fnmatch import fnmatchcase
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = ROOT / ".github/workflows"


def push_paths(workflow):
    lines = workflow.split("  push:\n", 1)[1].splitlines()
    paths = []
    collecting = False
    for line in lines:
        if line.startswith("  ") and len(line) > 2 and line[2] != " ":
            break
        if line == "    paths:":
            collecting = True
        elif collecting and line.startswith("      - "):
            paths.append(line[8:].strip('"\''))
    return paths


def triggers(workflow, path):
    return any(fnmatchcase(path, pattern) for pattern in push_paths(workflow))


class WorkflowFilterTest(unittest.TestCase):
    def test_shared_selector_changes_revalidate_every_caller(self):
        for workflow in WORKFLOWS.glob("*.yml"):
            text = workflow.read_text()
            if "uses: ./.github/actions/relevant\n" in text:
                with self.subTest(workflow=workflow.name):
                    self.assertTrue(
                        triggers(text, ".github/actions/relevant/relevant.sh")
                    )
                    self.assertTrue(
                        triggers(text, ".github/actions/relevant/action.yml")
                    )

    def test_product_script_configuration_reaches_the_push_planner(self):
        self.assertTrue(
            triggers((WORKFLOWS / "tests.yml").read_text(), "product/tsconfig.scripts.json")
        )

    def test_application_image_gpu_assets_reach_release_trigger(self):
        from plan import plan

        workflow = (WORKFLOWS / "tests.yml").read_text()
        for path in (
            "product/inference/gpu/host-agent.py",
            "product/inference/images/gpu-base/download-runtime.py",
            "product/inference/host/gradiated_host/enroll.py",
        ):
            with self.subTest(path=path):
                self.assertTrue(triggers(workflow, path))
                self.assertTrue(plan([path])["tooling"])
                self.assertFalse(plan([path])["inference_e2e"])

    def test_research_cargo_configuration_is_a_build_input(self):
        self.assertTrue(
            triggers((WORKFLOWS / "research-lab.yml").read_text(), ".cargo/config.toml")
        )

    def test_model_checks_revalidate_the_pinned_toolchain(self):
        self.assertTrue(
            triggers((WORKFLOWS / "model-deployment.yml").read_text(), "mise.toml")
        )

    def test_website_only_pushes_stay_out_of_application_deployment(self):
        self.assertFalse(
            triggers((WORKFLOWS / "tests.yml").read_text(), "product/website/src/main.tsx")
        )


if __name__ == "__main__":
    unittest.main()
