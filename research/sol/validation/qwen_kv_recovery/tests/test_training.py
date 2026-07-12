import unittest

import torch

from validation.qwen_kv_recovery.training import distillation_objective, should_promote


class DistillationTests(unittest.TestCase):
    def test_identical_logits_have_zero_teacher_kl(self) -> None:
        logits = torch.tensor([[[2.0, 0.0, -1.0], [0.0, 1.0, 2.0]]])
        targets = torch.tensor([[0, 2]])

        objective = distillation_objective(
            logits,
            logits,
            targets,
            temperature=2.0,
            teacher_kl_weight=0.7,
            next_token_weight=0.3,
        )

        self.assertAlmostEqual(float(objective.teacher_kl), 0.0, places=6)
        self.assertAlmostEqual(
            float(objective.total),
            0.3 * float(objective.next_token_cross_entropy),
            places=6,
        )

    def test_promotion_requires_every_quality_gate(self) -> None:
        self.assertTrue(should_promote({"passed": True}))
        self.assertFalse(should_promote({"passed": False}))
        self.assertFalse(should_promote({}))


if __name__ == "__main__":
    unittest.main()
