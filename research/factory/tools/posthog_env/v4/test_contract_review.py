import unittest

from contract_review import select


class ContractSelection(unittest.TestCase):
    def setUp(self):
        self.tasks = [{"task_id": str(i), "synth": {"family": str(i % 4)},
                       "validation": {"verdict": "SOUND"}} for i in range(20)]

    def test_selection_is_order_and_score_independent_and_covers_families(self):
        chosen = select(self.tasks, 15, 7)
        changed = [{**t, "model_score": 100 - i} for i, t in enumerate(reversed(self.tasks))]
        self.assertEqual([t["task_id"] for t in chosen], [t["task_id"] for t in select(changed, 15, 7)])
        self.assertEqual(len(chosen), 15)
        self.assertEqual({t["synth"]["family"] for t in chosen}, {"0", "1", "2", "3"})

    def test_rejected_and_duplicate_tasks_cannot_inflate_review(self):
        tasks = [{**t, "exclude": True} for t in self.tasks[:6]] + self.tasks[6:]
        with self.assertRaises(ValueError):
            select(tasks, 15, 7)
        with self.assertRaises(ValueError):
            select(self.tasks + self.tasks[:1], 15, 7)


if __name__ == "__main__":
    unittest.main()
