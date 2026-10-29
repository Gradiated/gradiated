import unittest
from rule_tests import fixture_rules


class RuleClosureTest(unittest.TestCase):
    def setUp(self):
        self.groups = [{'name': 'records', 'rules': [
            {'record': 'service:base', 'expr': 'source'},
            {'record': 'service:derived', 'expr': 'service:base + 1'},
            {'record': 'unrelated', 'expr': 'sum(other)'}]},
            {'name': 'alerts', 'rules': [
                {'alert': 'Expected', 'expr': 'service:derived > 1'},
                {'alert': 'Other', 'expr': 'unrelated > 1'}]}]

    def test_alert_fixture_retains_transitive_records_and_all_assertions(self):
        test = {'alert_rule_test': [{'alertname': 'Expected', 'exp_alerts': []}]}
        selected = fixture_rules(self.groups, test)
        self.assertEqual([r.get('record', r.get('alert')) for g in selected for r in g['rules']],
                         ['service:base', 'service:derived', 'Expected'])
        self.assertEqual(test['alert_rule_test'][0]['exp_alerts'], [])

    def test_expression_fixture_retains_its_record_dependencies(self):
        selected = fixture_rules(self.groups, {'promql_expr_test': [{'expr': 'service:derived'}]})
        self.assertEqual(len(selected), 1)
        self.assertEqual(len(selected[0]['rules']), 2)

    def test_similar_names_do_not_create_dependencies(self):
        selected = fixture_rules(self.groups, {'promql_expr_test': [{'expr': 'service:derived_suffix'}]})
        self.assertEqual(selected, [])

    def test_unknown_alert_is_not_silently_dropped(self):
        with self.assertRaises(AssertionError):
            fixture_rules(self.groups, {'alert_rule_test': [{'alertname': 'Typo'}]})
