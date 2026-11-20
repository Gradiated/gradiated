import unittest

from train import validate_resume_arguments


class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.saved = {
            "batch_size": 16,
            "accumulation": 2,
            "max_length": 2048,
            "learning_rate": 1e-4,
            "brier_weight": 1.0,
            "rank": 32,
            "steps": 1500,
            "run_dir": "/old-vm",
            "seconds": 9000,
        }

    def test_continuation_rejects_every_changed_training_setting(self):
        for key in [
            "batch_size",
            "accumulation",
            "max_length",
            "learning_rate",
            "brier_weight",
            "rank",
            "steps",
        ]:
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, key):
                validate_resume_arguments(
                    self.saved, {**self.saved, key: self.saved[key] * 2}
                )

    def test_new_host_and_deadline_do_not_change_training_sequence(self):
        validate_resume_arguments(
            self.saved, {**self.saved, "run_dir": "/new-vm", "seconds": 6000}
        )


if __name__ == "__main__":
    unittest.main()
