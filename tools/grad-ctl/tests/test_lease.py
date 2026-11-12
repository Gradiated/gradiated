from datetime import datetime, timezone
import json
import unittest

import _path  # noqa: F401
from grad_ctl import lease

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)


def host(annotation=None, status=None, taints=None):
    return {'metadata': {'name': 'gpu-01a0f19d-1ff3-7613-8cbf-81b693c0f0d4',
                         'annotations': {lease.ANNOTATION: json.dumps(annotation)} if annotation else {}},
            'spec': {'instanceId': '01a0f19d-1ff3-7613-8cbf-81b693c0f0d4',
                     'inventory': {'gpuCount': 4, 'gpuProduct': 'B300'},
                     **({'extraTaints': taints} if taints else {})},
            'status': status or {}}


class HostLeaseTests(unittest.TestCase):
    def test_request_matches_the_operator_schema(self):
        request = lease.build_request('agent', 'SFT sweep', 6, NOW)
        self.assertEqual(request, {'holder': 'agent', 'purpose': 'SFT sweep', 'until': '2026-11-06T18:00:00Z',
                                   'preemptible': True})
        self.assertEqual(lease.build_request('agent', 'SFT sweep', 6, NOW, False)['preemptible'], False)
        for hours in (0, -1, lease.MAX_HOURS + 1):
            with self.subTest(hours=hours), self.assertRaises(SystemExit):
                lease.build_request('agent', 'x', hours, NOW)
        for holder, purpose in (('', 'x'), ('x' * 101, 'x'), ('agent', ''), ('agent', 'x' * 501)):
            with self.subTest(holder=holder[:5], purpose=purpose[:5]), self.assertRaises(SystemExit):
                lease.build_request(holder, purpose, 1, NOW)

    def test_state_follows_the_operator_through_a_lease(self):
        request = lease.build_request('agent', 'sweep', 6, NOW)
        # An older request, as written before preemptible was always set.
        legacy = {key: value for key, value in request.items() if key != 'preemptible'}
        held = {'holder': 'agent', 'purpose': 'sweep', 'since': '2026-11-06T12:10:00Z'}
        cases = [
            (host(), 'in pool'),
            (host(request), 'requested'),
            (host(request, {'rollout': {'kind': 'lease', 'result': 'Running', 'step': 'Surge', 'lease': request}}),
             'leasing (Surge)'),
            (host(request, {'lease': held, 'rollout': {'kind': 'lease', 'result': 'Succeeded'}}), 'leased'),
            (host({**request, 'holder': 'other'}, {'lease': held}), 'given to other, waiting for its return'),
            # Past its deadline, so it cannot be extended before the return.
            (host(lease.build_request('agent', 'sweep', 6, datetime(2020, 1, 1, tzinfo=timezone.utc)),
                  {'lease': held}), 'expired, waiting for its return'),
            (host(None, {'lease': held, 'rollout': {'kind': 'lease', 'result': 'Succeeded'}}),
             'handed back, waiting for its return'),
            (host(None, {'lease': held, 'rollout': {'kind': 'return', 'result': 'Running', 'step': 'Reimage'}}),
             'returning (Reimage)'),
            (host(None, {'lease': held, 'rollout': {'kind': 'return', 'result': 'Failed', 'lastError': 'boom'}}),
             'return failed: boom'),
            (host(legacy, {'rollout': {'kind': 'lease', 'result': 'Failed', 'lastError': 'No capacity',
                                       'lease': request}}),
             'lease failed: No capacity'),
            (host(request, {'rollout': {'kind': 'return', 'result': 'Succeeded', 'startedAt': '2026-11-06T13:00:00Z',
                                        'lease': request}}), 'lease preempted'),
            (host(request, {'rollout': {'kind': 'return', 'result': 'Succeeded', 'startedAt': '2026-11-06T18:00:30Z',
                                        'lease': request}}), 'lease expired'),
            # Same second, with milliseconds, and an offset: compared as times, not strings.
            (host(request, {'rollout': {'kind': 'return', 'result': 'Succeeded', 'startedAt': '2026-11-06T18:00:00.500Z',
                                        'lease': request}}), 'lease expired'),
            (host({**request, 'until': '2026-11-06T19:00:00+01:00'},
                  {'rollout': {'kind': 'return', 'result': 'Succeeded', 'startedAt': '2026-11-06T18:30:00Z',
                               'lease': {**request, 'until': '2026-11-06T19:00:00+01:00'}}}), 'lease expired'),
            # A new request after an old outcome is a new request.
            (host(lease.build_request('agent', 'sweep', 7, NOW),
                  {'rollout': {'kind': 'lease', 'result': 'Failed', 'lease': request}}), 'requested'),
        ]
        for item, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(lease.state(item, NOW), expected)
        failed_legacy = next(item for item, expected in cases if expected == 'lease failed: No capacity')
        self.assertTrue(lease.ended(failed_legacy))
        self.assertFalse(lease.ended(cases[-1][0]))

    def test_only_the_holder_hands_a_lease_back_without_force(self):
        leased = host(lease.build_request('agent', 'sweep', 6, NOW))
        self.assertEqual(lease.own(leased, 'agent', False)['holder'], 'agent')
        with self.assertRaises(SystemExit):
            lease.own(leased, 'someone-else', False)
        self.assertEqual(lease.own(leased, 'someone-else', True)['holder'], 'agent')

    def test_hosts_are_found_by_a_unique_instance_prefix(self):
        items = [host(), {**host(), 'spec': {**host()['spec'], 'instanceId': '01a0fbf7-5276-700b-903b-7e04da150ed6'}}]
        self.assertEqual(lease.find(items, '01a0f19d')['spec']['instanceId'][:8], '01a0f19d')
        self.assertEqual(lease.find(items, 'gpu-01a0fbf7')['spec']['instanceId'][:8], '01a0fbf7')
        with self.assertRaises(SystemExit):
            lease.find(items, '01a0f')

    def test_writes_are_conditional_and_retried_on_a_conflict(self):
        calls, items = [], [{**host(), 'metadata': {**host()['metadata'], 'resourceVersion': '7'}}]

        def kubectl(*args, capture=True):
            calls.append(args)
            if args[0] == 'get':
                return json.dumps({'items': items})
            if len(calls) == 2:
                raise lease.Conflict()
            return ''

        original, sleep = lease.kubectl, lease.time.sleep
        lease.kubectl, lease.time.sleep = kubectl, lambda _: None
        try:
            lease.change('01a0f19d', lambda item: lease.annotate(item, lease.build_request('agent', 'x', 1, NOW)))
        finally:
            lease.kubectl, lease.time.sleep = original, sleep
        writes = [args for args in calls if args[0] == 'annotate']
        self.assertEqual(len(writes), 2)
        self.assertTrue(all('--resource-version=7' in args for args in writes))


if __name__ == '__main__':
    unittest.main()
