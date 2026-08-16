import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from dashboard.watch_inbox import read_new_records


class DashboardInboxTests(unittest.TestCase):
    def test_reads_each_valid_prompt_once(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            inbox = root / "inbox.jsonl"
            cursor = root / "cursor"
            inbox.write_text(
                "\n".join(
                    [
                        json.dumps({"ts": "1", "text": "first"}),
                        "not-json",
                        json.dumps({"ts": "2", "text": "second"}),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            first = read_new_records(inbox, cursor)
            second = read_new_records(inbox, cursor)
            with inbox.open("a", encoding="utf-8") as target:
                target.write(json.dumps({"ts": "3", "text": "third"}) + "\n")
            third = read_new_records(inbox, cursor)

            self.assertEqual([record["text"] for record in first], ["first", "second"])
            self.assertEqual(second, [])
            self.assertEqual([record["text"] for record in third], ["third"])

    def test_recovers_from_a_cursor_past_a_truncated_inbox(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            inbox = root / "inbox.jsonl"
            cursor = root / "cursor"
            inbox.write_text(json.dumps({"text": "retained"}) + "\n", encoding="utf-8")
            cursor.write_text("10\n", encoding="utf-8")

            records = read_new_records(inbox, cursor)

            self.assertEqual([record["text"] for record in records], ["retained"])
            self.assertEqual(cursor.read_text(encoding="utf-8"), "1\n")


if __name__ == "__main__":
    unittest.main()
