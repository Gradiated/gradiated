from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parity  # noqa: E402


class ParityTests(unittest.TestCase):
    def test_list_criteria_become_gateway_choices(self):
        case = {'state': 's', 'question': {'type': 'choice', 'instructions': 'i', 'criteria': ['a', 'b']}}
        self.assertEqual(parity.request('posthog/jevk5', case)['questions']['q']['criteria'], {'a': None, 'b': None})

    def test_served_probabilities_follow_the_fixture_order_whatever_the_key_order(self):
        score = {'type': 'score', 'criteria': [f'l{i}' for i in range(11)]}
        answer = {'type': 'score', 'probabilities': {str(i): i / 55 for i in sorted(range(11), key=str)}}
        self.assertEqual(parity.served(answer, score), [i / 55 for i in range(11)])
        self.assertEqual(parity.served({'type': 'noul', 'noul': 0.75}, {'type': 'noul'}), [0.75, 0.25])

    def test_gate(self):
        cases = [{'probabilities': [0.9, 0.1], 'input_tokens': 1}, {'probabilities': [0.55, 0.45], 'input_tokens': 1}]
        _, bad = parity.compare(cases, [[0.85, 0.15], [0.49, 0.51]], 0.08)
        self.assertEqual(bad, 0)  # a flip of a near tie within the tolerance is reported, not failed
        _, bad = parity.compare(cases, [[0.7, 0.3], [0.55, 0.45]], 0.08)
        self.assertEqual(bad, 1)

    def test_fixtures_have_46_cases_each(self):
        import json

        for model, (fixture, _) in parity.FIXTURES.items():
            self.assertEqual(len(json.loads(fixture.read_text())['cases']), 46, model)


if __name__ == '__main__':
    unittest.main()
