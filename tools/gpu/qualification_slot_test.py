import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('slot', Path(__file__).with_name('qualification-slot.py'))
slot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(slot)
NAME = 'gpu-01a0f19d-1ff3-7613-8cbf-81b693c0f0d4'


def node():
    return {'metadata': {'name': NAME, 'uid': 'node-uid', 'resourceVersion': '12',
                         'annotations': {'existing': 'preserved'}}, 'spec': {},
            'status': {'allocatable': {'cpu': '64', 'memory': '896Gi', 'nvidia.com/gpu': '4'},
                       'conditions': [{'type': 'Ready', 'status': 'True'}]}}


def pod(**requests):
    return {'metadata': {'uid': 'pod-uid'}, 'spec': {'nodeName': NAME, 'containers': [{'resources': {'requests': requests}}]},
            'status': {'phase': 'Running'}}


class QualificationSlotTest(unittest.TestCase):
    def test_accounts_for_all_three_resource_limits(self):
        occupied = [pod(cpu='16', memory='224Gi', **{'nvidia.com/gpu': '1'})] * 3
        self.assertEqual(slot.check_capacity(node(), occupied)['cpu'], 16)
        for key, value in [('cpu', '1m'), ('memory', '1Mi'), ('nvidia.com/gpu', '1')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                slot.check_capacity(node(), occupied + [pod(**{key: value})])
        done = pod(cpu='64'); done['status']['phase'] = 'Succeeded'
        slot.check_capacity(node(), occupied + [done])
        pending = pod(cpu='1'); pending['status']['phase'] = 'Pending'
        with self.assertRaises(ValueError):
            slot.check_capacity(node(), occupied + [pending])

    def test_reservation_preserves_running_pods_and_annotations(self):
        n = node(); writes = []
        def api(*args):
            if args[:2] == ('get', 'node'):
                return copy.deepcopy(n)
            if args[:2] == ('get', 'pods'):
                return {'items': []}
            ops = __import__('json').loads(args[-1]); writes.append(ops)
            for op in ops:
                if op['op'] == 'add':
                    root, key = op['path'].strip('/').split('/')
                    n[root][key] = op['value']
            return n
        with tempfile.TemporaryDirectory() as directory, patch.object(slot, 'kubectl', side_effect=api), patch.object(slot, 'settle'):
            path = Path(directory) / 'nested' / 'runtime' / 'lease.json'
            lease = slot.acquire(NAME, path)
            self.assertTrue(n['spec']['unschedulable'])
            self.assertEqual(n['metadata']['annotations']['existing'], 'preserved')
            self.assertEqual(n['metadata']['annotations'][slot.OWNER], lease['owner'])
            slot.release(lease)
            self.assertFalse(n['spec']['unschedulable'])
            self.assertEqual(n['metadata']['annotations'], {'existing': 'preserved'})
        self.assertEqual(len(writes), 2)
        for ops in writes:
            self.assertEqual(ops[0], {'op': 'test', 'path': '/metadata/resourceVersion', 'value': '12'})

    def test_refuses_existing_cordons_and_unready_nodes(self):
        for kind in ('cordon', 'fleet', 'owner', 'unready'):
            n = node()
            if kind == 'cordon': n['spec']['unschedulable'] = True
            elif kind == 'unready': n['status']['conditions'] = []
            else: n['metadata']['annotations'][slot.FLEET if kind == 'fleet' else slot.OWNER] = 'other'
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                with patch.object(slot, 'kubectl', return_value=n) as api, self.assertRaises(ValueError):
                    slot.acquire(NAME, Path(directory) / 'lease.json')
                self.assertEqual(api.call_count, 1)

    def test_never_releases_someone_elses_cordon_or_replaced_node(self):
        lease = {'node': NAME, 'uid': 'node-uid', 'owner': 'ours'}
        for kind in ('owner', 'fleet', 'uid'):
            n = node(); n['metadata']['annotations'][slot.OWNER] = 'ours'
            if kind == 'owner': n['metadata']['annotations'][slot.OWNER] = 'other'
            elif kind == 'fleet': n['metadata']['annotations'][slot.FLEET] = 'gpu-fleet'
            else: n['metadata']['uid'] = 'new-node'
            with self.subTest(kind=kind), patch.object(slot, 'kubectl', return_value=n) as api:
                with self.assertRaises(ValueError): slot.release(lease)
                self.assertEqual(api.call_count, 1)

    def test_a_late_scheduled_pod_releases_the_reservation(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(slot, 'kubectl', side_effect=[node(), {'items': []}]), patch.object(slot, 'patch'), patch.object(slot, 'settle', side_effect=ValueError('late binding')), patch.object(slot, 'release') as release:
                with self.assertRaises(ValueError): slot.acquire(NAME, Path(directory) / 'lease.json')
                release.assert_called_once()
                self.assertFalse((Path(directory) / 'lease.json').exists())

    def test_settling_waits_for_stable_demand_after_a_late_binding(self):
        n = node(); n['spec']['unschedulable'] = True
        n['metadata']['annotations'][slot.OWNER] = 'ours'
        lease = {'node': NAME, 'uid': 'node-uid', 'owner': 'ours'}
        now = [0]
        def api(*args):
            if args[:2] == ('get', 'node'): return n
            return {'items': [] if now[0] < 10 else [pod(cpu='16')]}
        with patch.object(slot, 'kubectl', side_effect=api):
            slot.settle(lease, clock=lambda: now[0], sleep=lambda seconds: now.__setitem__(0, now[0] + seconds))
        self.assertEqual(now[0], 40)

    def test_settling_rejects_lost_ownership_and_times_out_changing_demand(self):
        n = node(); n['spec']['unschedulable'] = True
        n['metadata']['annotations'][slot.OWNER] = 'ours'
        lease = {'node': NAME, 'uid': 'node-uid', 'owner': 'ours'}
        now = [0]
        def api(*args):
            if args[:2] == ('get', 'node'): return n
            return {'items': [pod(cpu=str(1 + now[0] % 2))]}
        with patch.object(slot, 'kubectl', side_effect=api), self.assertRaises(TimeoutError):
            slot.settle(lease, clock=lambda: now[0], sleep=lambda seconds: now.__setitem__(0, now[0] + seconds))
        self.assertEqual(now[0], 120)
        n['metadata']['annotations'][slot.FLEET] = 'gpu-fleet'
        with patch.object(slot, 'kubectl', return_value=n), self.assertRaisesRegex(ValueError, 'ownership changed'):
            slot.settle(lease)

    def test_failed_rollback_preserves_recovery_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'lease.json'
            with patch.object(slot, 'kubectl', side_effect=[node(), {'items': []}]), patch.object(slot, 'patch'), patch.object(slot, 'settle', side_effect=ValueError('late binding')), patch.object(slot, 'release', side_effect=ValueError('ownership changed')):
                with self.assertRaisesRegex(ValueError, 'ownership changed'):
                    slot.acquire(NAME, path)
            self.assertTrue(path.exists())

    def test_reserved_workstream_host_is_never_touched(self):
        with patch.object(slot, 'kubectl') as api, self.assertRaises(ValueError):
            slot.acquire('gpu-01a0fbf8-06fc-7658-96e1-ae72f7dba135', Path('unused'))
        api.assert_not_called()

    def test_existing_recovery_file_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'lease.json'; path.write_text('existing')
            with patch.object(slot, 'kubectl', side_effect=[node(), {'items': []}]), patch.object(slot, 'patch') as write:
                with self.assertRaises(FileExistsError): slot.acquire(NAME, path)
                write.assert_not_called()
            self.assertEqual(path.read_text(), 'existing')


if __name__ == '__main__':
    unittest.main()
