from __future__ import annotations

import unittest

from kda_reference import KDAReference, TokenInputs, generate_tokens, saturate


class KDAReferenceTest(unittest.TestCase):
    def test_zero_key_only_decays_state(self) -> None:
        model = KDAReference(2)
        model.state = [[1 << 18, -(1 << 18)], [2 << 18, -(2 << 18)]]
        output = model.step(TokenInputs(q=[64, 0], k=[0, 0], v=[0, 0], alpha=[128, 128], beta=255))
        self.assertEqual(output, [1 << 17, -(1 << 17)])
        self.assertEqual(model.state[1][0], 1 << 18)

    def test_clear_restores_first_token_result(self) -> None:
        token = generate_tokens(8, 1, 7)[0]
        model = KDAReference(8)
        first = model.step(token)
        self.assertNotEqual(model.step(token), first)
        model.clear()
        self.assertEqual(model.step(token), first)

    def test_saturation_limits_are_exact(self) -> None:
        self.assertEqual(saturate(1 << 30, 24), (1 << 23) - 1)
        self.assertEqual(saturate(-(1 << 30), 24), -(1 << 23))


if __name__ == "__main__":
    unittest.main()
