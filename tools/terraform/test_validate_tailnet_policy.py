import json
import re
import unittest

import validate_tailnet_policy as checker


class TailnetPolicyTests(unittest.TestCase):
    def test_policy_parses_as_hujson_and_keeps_the_gpu_ssh_rules(self):
        text = '\n'.join(line for line in checker.POLICY.read_text().splitlines()
                         if not line.lstrip().startswith('//'))
        policy = json.loads(re.sub(r',(\s*[}\]])', r'\1', text))
        rules = {(rule['action'], tuple(rule['src'])): rule for rule in policy['ssh']}
        admin = rules[('check', ('autogroup:admin',))]
        self.assertEqual((admin['dst'], admin['users'], admin['checkPeriod']),
                         (['tag:gpu-inference', 'tag:gpu-bootstrap'], ['root'], '12h'))
        self.assertEqual(rules[('accept', ('tag:ops-mcp', 'tag:gpu-fleet'))]['dst'], ['tag:gpu-bootstrap'])
        gpu_destinations = [rule for rule in policy['ssh'] if {'tag:gpu-inference', 'tag:gpu-bootstrap'} & set(rule['dst'])]
        self.assertEqual(len(gpu_destinations), 2)
        self.assertTrue(policy['sshTests'])
        port_22 = sorted((tuple(grant['src']), tuple(grant['dst'])) for grant in policy['grants']
                         if 'tcp:22' in grant.get('ip', []) or '*' in grant.get('ip', []))
        self.assertEqual(port_22, [(('autogroup:admin',), ('tag:gpu-inference', 'tag:gpu-bootstrap')),
                                   (('autogroup:member',), ('autogroup:self',)),
                                   (('tag:ops-mcp', 'tag:gpu-fleet'), ('tag:gpu-bootstrap',))])

    def test_reports_failed_policy_tests(self):
        self.assertEqual(checker.failures({}), [])
        response = {'message': 'test(s) failed', 'data': [
            {'user': 'tag:ops-mcp', 'errors': ['[ssh test error]: want: "deny" got: "accept"']}]}
        self.assertEqual(checker.failures(response),
                         ['test(s) failed', 'tag:ops-mcp: [ssh test error]: want: "deny" got: "accept"'])


if __name__ == '__main__':
    unittest.main()
