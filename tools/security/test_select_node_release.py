from datetime import datetime, timedelta, timezone
import unittest

from select_node_release import select_release


class NodeReleaseTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 22, 18, tzinfo=timezone.utc)
        self.parameter = {
            "Name": "/aws/service/eks/optimized-ami/1.36/amazon-linux-2023/x86_64/standard/recommended/release_version",
            "Type": "String",
            "Value": "1.36.5-20261019",
            "LastModifiedDate": (self.now - timedelta(days=7)).isoformat(),
        }

    def select(self, current="1.36.4-20261012"):
        return select_release(self.parameter, current, "1.36", self.now)[0]

    def test_seven_full_days_is_eligible(self):
        self.assertEqual(self.select(), "1.36.5-20261019")

    def test_one_microsecond_under_seven_days_waits(self):
        self.parameter["LastModifiedDate"] = (self.now - timedelta(days=7) + timedelta(microseconds=1)).isoformat()
        self.assertIsNone(self.select())

    def test_old_release_name_does_not_bypass_recent_publication(self):
        self.parameter.update(Value="1.36.5-20261001", LastModifiedDate=self.now.isoformat())
        self.assertIsNone(self.select())

    def test_up_to_date_group_is_not_replaced(self):
        self.assertIsNone(self.select(current="1.36.5-20261019"))

    def test_recommendation_cannot_downgrade_patch_version(self):
        self.assertIsNone(self.select(current="1.36.6-20261012"))

    def test_same_patch_newer_build_can_be_selected(self):
        self.parameter["Value"] = "1.36.4-20261019"
        self.assertEqual(self.select(), "1.36.4-20261019")

    def test_older_build_cannot_replace_newer_build(self):
        self.assertIsNone(self.select(current="1.36.5-20261020"))

    def test_publication_timezone_is_respected(self):
        self.parameter["LastModifiedDate"] = "2026-10-15T20:00:00+02:00"
        self.assertEqual(self.select(), "1.36.5-20261019")

    def test_invalid_metadata_fails_instead_of_selecting(self):
        for field, value in [
            ("Value", "1.37.1-20261019"),
            ("Value", "1.36.5-20261301"),
            ("Value", "1.36.5-20261019\n"),
            ("Name", "/another/parameter"),
            ("Type", "SecureString"),
            ("LastModifiedDate", "2026-10-15T18:00:00"),
            ("LastModifiedDate", "2026-10-23T18:00:00Z"),
            ("LastModifiedDate", "unknown"),
        ]:
            with self.subTest(field=field, value=value):
                original = self.parameter[field]
                self.parameter[field] = value
                with self.assertRaises(ValueError):
                    self.select()
                self.parameter[field] = original

    def test_missing_publication_time_fails(self):
        del self.parameter["LastModifiedDate"]
        with self.assertRaises(KeyError):
            self.select()


if __name__ == "__main__":
    unittest.main()
