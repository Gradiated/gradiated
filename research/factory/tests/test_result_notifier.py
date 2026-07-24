from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from grad_research.result_notifier import (
    ResultNotifier,
    research_update,
    template_text_parameter,
    whatsapp_payload,
)


class FakeSender:
    def __init__(self):
        self.messages = []

    def send(self, text):
        self.messages.append(text)
        return "wamid.test"


class ResultNotifierTests(unittest.TestCase):
    def test_formats_project_status_as_a_compact_result(self):
        with tempfile.TemporaryDirectory() as directory:
            lab = Path(directory)
            project = lab / "projects" / "batching"
            project.mkdir(parents=True)
            (lab / "CAMPAIGN.md").write_text("# GLM economics\n")
            (project / "STATUS.json").write_text(
                json.dumps(
                    {
                        "status": "complete",
                        "summary": "c16 reduced cost by 8%.",
                        "next_action": "Promote c16.",
                        "last_experiment": "v32",
                    }
                )
            )

            text = research_update(lab, {"label": "batching"})

            self.assertIn("GLM economics", text)
            self.assertIn("Experiment: v32", text)
            self.assertIn("Result: c16 reduced cost by 8%.", text)

    def test_template_payload_uses_one_dynamic_result_parameter(self):
        payload = whatsapp_payload(
            "4912345",
            "measured result",
            template_name="research_result",
            template_language="en_US",
        )

        self.assertEqual("template", payload["type"])
        self.assertEqual(
            "measured result",
            payload["template"]["components"][0]["parameters"][0]["text"],
        )

    def test_template_text_parameter_removes_meta_forbidden_whitespace(self):
        self.assertEqual(
            "Project: kernel Status: complete Result: 8% faster",
            template_text_parameter(
                "Project: kernel\nStatus:\tcomplete     Result: 8% faster"
            ),
        )

    def test_template_payload_sanitizes_parameter_but_freeform_preserves_text(self):
        text = "Result:\n8% faster\t at c32"

        template = whatsapp_payload(
            "4912345",
            text,
            template_name="research_result",
            template_language="en",
        )
        freeform = whatsapp_payload(
            "4912345",
            text,
            template_name=None,
            template_language="en",
        )

        self.assertEqual(
            "Result: 8% faster at c32",
            template["template"]["components"][0]["parameters"][0]["text"],
        )
        self.assertEqual(text, freeform["text"]["body"])

    def test_new_researcher_completion_is_sent_once_and_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            lab = Path(directory) / "lab"
            runtime = lab / "runtime"
            project = lab / "projects" / "kernel"
            runtime.mkdir(parents=True)
            project.mkdir(parents=True)
            events = runtime / "events.jsonl"
            events.write_text("")
            (project / "STATUS.json").write_text(
                json.dumps({"status": "complete", "summary": "No useful gain.", "next_action": "Stop."})
            )
            sender = FakeSender()
            notifier = ResultNotifier(lab, Path(directory) / "state.json", sender)
            event = {
                "event": "agent_completed",
                "role": "researcher",
                "label": "kernel",
                "timestamp": "2026-07-15T00:00:00Z",
                "stdout_path": "trace.jsonl",
            }
            with events.open("a") as handle:
                handle.write(json.dumps(event) + "\n")

            notifier.read_new_events()
            notifier.deliver_pending(now=1)
            notifier.deliver_pending(now=2)

            self.assertEqual(1, len(sender.messages))
            delivery = json.loads((runtime / "notification_events.jsonl").read_text())
            self.assertEqual("notification_sent", delivery["event"])


if __name__ == "__main__":
    unittest.main()
