import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('reserve_pd', Path(__file__).with_name('reserve-glm-pd-host.py'))
reserve = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reserve)


def node():
    return {'metadata': {'name': reserve.NODE, 'uid': 'node-uid', 'resourceVersion': '1',
                         'labels': {'nvidia.com/gpu.product': 'B300', 'gradiated.com/provider': 'runpod'},
                         'annotations': {'existing': 'preserved'}}, 'spec': {},
            'status': {'allocatable': {'cpu': '48', 'memory': '452Gi', 'nvidia.com/gpu': '2'},
                       'conditions': [{'type': 'Ready', 'status': 'True'}]}}


def pod(index, target=False):
    incarnation = 'runpod://' + str(index)
    return {'metadata': {'name': 'glm-' + str(index), 'uid': 'uid-' + str(index),
                         'namespace': reserve.NAMESPACE,
                         'labels': {'app.kubernetes.io/name': reserve.APP, 'rollouts-pod-template-hash': 'hash'},
                         'ownerReferences': [{'controller': True, 'kind': 'ReplicaSet', 'name': 'glm-dealign-hash'}],
                         'annotations': {'gradiated.com/model-id': reserve.MODEL,
                                         'gradiated.com/qualified': 'true',
                                         'gradiated.com/qualified-runtime': incarnation,
                                         'gradiated.com/release': json.dumps({
                                             'runtime_revision': 'glm-dealign-b93c18df2a1c',
                                             'model_revision': '745aac2ff0f10acf961f396df3f9418598aa7327'})}},
            'spec': {'nodeName': reserve.NODE if target else 'other-node',
                     'terminationGracePeriodSeconds': 750,
                     'containers': [{'name': 'runtime', 'image': reserve.IMAGE, 'resources': {
                         'requests': {'cpu': '16', 'memory': '224Gi', 'nvidia.com/gpu': '1'}}}]},
            'status': {'phase': 'Running',
                       'conditions': [{'type': key, 'status': 'True'} for key in ['Ready', 'RuntimeReady']],
                       'containerStatuses': [{'image': reserve.IMAGE, 'ready': True, 'containerID': incarnation}]}}


def rollout():
    return {'metadata': {'name': reserve.APP, 'namespace': reserve.NAMESPACE, 'uid': 'rollout-uid', 'generation': 7},
            'spec': {'replicas': 10, 'template': {'spec': {'containers': [{'image': reserve.IMAGE}]}}},
            'status': {'phase': 'Healthy', 'observedGeneration': '7', 'currentPodHash': 'hash',
                       'stableRS': 'hash', 'availableReplicas': 10, 'readyReplicas': 10, 'updatedReplicas': 10}}


def budget():
    return {'apiVersion': 'policy/v1', 'kind': 'PodDisruptionBudget',
            'metadata': {'name': reserve.APP, 'namespace': reserve.NAMESPACE,
                         'uid': 'budget-uid', 'generation': 3},
            'spec': {'minAvailable': 8, 'selector': {
                'matchLabels': {'app.kubernetes.io/name': reserve.APP}}},
            'status': {'observedGeneration': 3, 'disruptionsAllowed': 2}}


class FakeClient:
    def __init__(self):
        self.node = node()
        self.pods = [pod(index, index < 2) for index in range(10)]
        self.rollout = rollout()
        self.pdb = budget()
        self.time = 0
        self.evicted = []
        self.patches = []
        self.drain_complete_at = 45
        self.hook = lambda: None
        self.deny = False
        self.budget_calls = 0
        self.budget_hook = lambda: None
        self.eviction_hook = lambda: None
        self.eviction_attempts = []

    def sleep(self, seconds):
        self.time += seconds

    def snapshot(self):
        self.hook()
        if len(self.evicted) == 2 and self.time >= self.drain_complete_at:
            self.pods = [p for p in self.pods if p['metadata']['uid'] not in self.evicted]
        return copy.deepcopy((self.node, self.pods, self.rollout))

    def budget(self):
        self.budget_calls += 1
        self.budget_hook()
        return copy.deepcopy(self.pdb)

    def evict(self, name, uid):
        self.eviction_attempts.append(uid)
        self.eviction_hook()
        if self.deny or self.pdb['status']['disruptionsAllowed'] <= 0:
            raise subprocess.CalledProcessError(1, 'kubectl', stderr='TooManyRequests: disruption budget')
        self.evicted.append(uid)
        target = next(p for p in self.pods if p['metadata']['name'] == name)
        target['metadata']['deletionTimestamp'] = 'now'
        target['status']['conditions'] = []
        self.rollout['status']['availableReplicas'] -= 1
        self.pdb['status']['disruptionsAllowed'] -= 1

    def kubectl(self, *args):
        if args[:2] == ('get', 'node'):
            return copy.deepcopy(self.node)
        self.assert_patch(args)
        operations = json.loads(args[-1])
        if operations[0]['value'] != self.node['metadata']['resourceVersion']:
            raise ValueError('resourceVersion conflict')
        self.patches.append(operations)
        for operation in operations[1:]:
            root, key = operation['path'].strip('/').split('/')
            self.node[root][key] = operation['value']
        self.node['metadata']['resourceVersion'] = str(int(self.node['metadata']['resourceVersion']) + 1)
        return copy.deepcopy(self.node)

    def assert_patch(self, args):
        assert args[:3] == ('patch', 'node', reserve.NODE)


class ReserveGlmPdHostTest(unittest.TestCase):
    def run_reservation(self, client, path, apply=True):
        return reserve.reserve(path, apply=apply, client=client,
                               clock=lambda: client.time, sleep=client.sleep)

    def test_dry_run_does_not_write_or_evict(self):
        client = FakeClient()
        with tempfile.TemporaryDirectory() as directory, patch.object(reserve.slot, 'kubectl') as api:
            path = Path(directory) / 'lease.json'
            plan = self.run_reservation(client, path, apply=False)
            self.assertEqual(len(plan['pods']), 2)
            self.assertEqual(plan['budget'], {'name': reserve.APP, 'namespace': reserve.NAMESPACE,
                                              'uid': 'budget-uid', 'minAvailable': 8,
                                              'selector': {'matchLabels': {
                                                  'app.kubernetes.io/name': reserve.APP}}})
            self.assertFalse(path.exists())
            api.assert_not_called()
        self.assertEqual(client.evicted, [])

    def test_missing_mismatched_or_unobserved_budget_never_cordons(self):
        cases = []
        cases.append(('missing', None))
        for field, value in [('apiVersion', 'policy/v1beta1'), ('kind', 'Other')]:
            resource = budget(); resource[field] = value; cases.append((field, resource))
        for field, value in [('name', 'other'), ('namespace', 'other'), ('uid', ''),
                             ('generation', 4), ('deletionTimestamp', 'now')]:
            resource = budget(); resource['metadata'][field] = value; cases.append((field, resource))
        for minimum in ['8', '80%', 7, 9]:
            resource = budget(); resource['spec']['minAvailable'] = minimum
            cases.append(('minimum-' + str(minimum), resource))
        resource = budget(); resource['spec']['maxUnavailable'] = 0
        cases.append(('maxUnavailable', resource))
        for selector in [{}, {'matchLabels': {'app.kubernetes.io/name': 'other'}},
                         {'matchLabels': {'app.kubernetes.io/name': reserve.APP, 'extra': 'narrow'}},
                         {'matchLabels': {'app.kubernetes.io/name': reserve.APP},
                          'matchExpressions': [{'key': 'extra', 'operator': 'Exists'}]}]:
            resource = budget(); resource['spec']['selector'] = selector
            cases.append(('selector-' + str(selector), resource))
        for status in [{}, {'observedGeneration': 2, 'disruptionsAllowed': 2},
                       {'observedGeneration': 3, 'disruptionsAllowed': None},
                       {'observedGeneration': 3, 'disruptionsAllowed': True},
                       {'observedGeneration': 3, 'disruptionsAllowed': -1}]:
            resource = budget(); resource['status'] = status; cases.append(('status-' + str(status), resource))
        for name, resource in cases:
            for apply in [False, True]:
                client = FakeClient(); client.pdb = resource
                with self.subTest(case=name, apply=apply), tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / 'lease.json'
                    with patch.object(reserve.slot, 'kubectl') as api, self.assertRaises(ValueError):
                        self.run_reservation(client, path, apply=apply)
                    api.assert_not_called()
                    self.assertFalse(path.exists())
                    self.assertEqual(client.eviction_attempts, [])

    def test_budget_rechecked_immediately_before_cordon(self):
        client = FakeClient()
        def replace():
            if client.budget_calls == 2:
                client.pdb['metadata']['uid'] = 'replacement-budget'
        client.budget_hook = replace
        with tempfile.TemporaryDirectory() as directory, patch.object(reserve.slot, 'kubectl', side_effect=client.kubectl):
            path = Path(directory) / 'lease.json'
            with self.assertRaisesRegex(ValueError, 'budget UID changed'):
                self.run_reservation(client, path)
            self.assertEqual(client.patches, [])
            self.assertFalse(path.exists())
            self.assertEqual(client.eviction_attempts, [])

    def test_zero_initial_budget_never_cordons_or_releases_a_foreign_cordon(self):
        client = FakeClient(); client.pdb['status']['disruptionsAllowed'] = 0
        with tempfile.TemporaryDirectory() as directory, patch.object(reserve.slot, 'kubectl') as api:
            path = Path(directory) / 'lease.json'
            with self.assertRaisesRegex(ValueError, 'permits no further eviction'):
                self.run_reservation(client, path)
            api.assert_not_called()
            self.assertFalse(path.exists())
            self.assertEqual(client.eviction_attempts, [])

    def test_budget_must_remain_present_during_normal_drain(self):
        client = FakeClient()
        def remove():
            if len(client.evicted) == 2: client.pdb = None
        client.budget_hook = remove
        with tempfile.TemporaryDirectory() as directory, patch.object(reserve.slot, 'kubectl', side_effect=client.kubectl):
            path = Path(directory) / 'lease.json'
            with self.assertRaisesRegex(ValueError, 'budget is missing'):
                self.run_reservation(client, path)
            self.assertEqual(client.evicted, ['uid-0', 'uid-1'])
            self.assertFalse(client.node['spec']['unschedulable'])
            self.assertFalse(path.exists())

    def test_budget_replacement_or_staleness_stops_second_eviction(self):
        for kind in ['uid', 'generation', 'selector']:
            client = FakeClient()
            def change():
                if client.evicted:
                    if kind == 'uid': client.pdb['metadata']['uid'] = 'new-budget'
                    elif kind == 'generation': client.pdb['metadata']['generation'] += 1
                    else: client.pdb['spec']['selector'] = {}
            client.budget_hook = change
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                with patch.object(reserve.slot, 'kubectl', side_effect=client.kubectl):
                    path = Path(directory) / 'lease.json'
                    with self.assertRaises(ValueError): self.run_reservation(client, path)
                    self.assertEqual(client.evicted, ['uid-0'])
                    self.assertEqual(client.eviction_attempts, ['uid-0'])
                    self.assertFalse(client.node['spec']['unschedulable'])
                    self.assertFalse(path.exists())

    def test_exhausted_budget_stops_second_eviction(self):
        client = FakeClient()
        def exhaust():
            if client.evicted: client.pdb['status']['disruptionsAllowed'] = 0
        client.budget_hook = exhaust
        with tempfile.TemporaryDirectory() as directory, patch.object(reserve.slot, 'kubectl', side_effect=client.kubectl):
            path = Path(directory) / 'lease.json'
            with self.assertRaisesRegex(ValueError, 'permits no further eviction'):
                self.run_reservation(client, path)
            self.assertEqual(client.eviction_attempts, ['uid-0'])
            self.assertEqual(client.evicted, ['uid-0'])
            self.assertFalse(client.node['spec']['unschedulable'])
            self.assertFalse(path.exists())

    def test_api_denial_after_positive_budget_check_is_not_bypassed(self):
        client = FakeClient()
        def race():
            if client.evicted: client.pdb['status']['disruptionsAllowed'] = 0
        client.eviction_hook = race
        with tempfile.TemporaryDirectory() as directory, patch.object(reserve.slot, 'kubectl', side_effect=client.kubectl):
            path = Path(directory) / 'lease.json'
            with self.assertRaises(subprocess.CalledProcessError):
                self.run_reservation(client, path)
            self.assertEqual(client.eviction_attempts, ['uid-0', 'uid-1'])
            self.assertEqual(client.evicted, ['uid-0'])
            self.assertFalse(client.node['spec']['unschedulable'])
            self.assertFalse(path.exists())

    def test_success_waits_for_stable_cordon_and_complete_normal_drain(self):
        client = FakeClient()
        with tempfile.TemporaryDirectory() as directory, patch.object(reserve.slot, 'kubectl', side_effect=client.kubectl):
            path = Path(directory) / 'lease.json'
            original_patch = reserve.slot.patch
            def persisted_before_cordon(*args):
                self.assertTrue(path.exists())
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                return original_patch(*args)
            with patch.object(reserve.slot, 'patch', side_effect=persisted_before_cordon):
                lease = self.run_reservation(client, path)
            self.assertEqual(client.time, 45)
            self.assertEqual(client.evicted, ['uid-0', 'uid-1'])
            self.assertEqual(len(client.pods), 8)
            self.assertTrue(client.node['spec']['unschedulable'])
            self.assertEqual(client.node['metadata']['annotations']['existing'], 'preserved')
            self.assertEqual(json.loads(path.read_text())['owner'], lease['owner'])
            reserve.slot.release(lease)
            self.assertFalse(client.node['spec']['unschedulable'])
        self.assertEqual(client.patches[0][0], {'op': 'test', 'path': '/metadata/resourceVersion', 'value': '1'})

    def test_invalid_initial_state_never_mutates(self):
        for kind in ['foreign-pod', 'wrong-image', 'stale-qualification', 'foreign-node', 'cordon',
                     'fleet-owner', 'qualification-owner', 'insufficient-memory', 'other-replica-unready',
                     'rollout-progressing', 'rollout-new-hash', 'rollout-unobserved']:
            client = FakeClient()
            if kind == 'foreign-pod': client.pods[0]['metadata']['annotations']['gradiated.com/model-id'] = 'other'
            elif kind == 'wrong-image': client.pods[0]['spec']['containers'][0]['image'] = 'new'
            elif kind == 'stale-qualification': client.pods[0]['metadata']['annotations']['gradiated.com/qualified-runtime'] = 'old'
            elif kind == 'foreign-node': client.node['metadata']['name'] = 'another-node'
            elif kind == 'cordon': client.node['spec']['unschedulable'] = True
            elif kind == 'fleet-owner': client.node['metadata']['annotations'][reserve.slot.FLEET] = 'gpu-fleet'
            elif kind == 'qualification-owner': client.node['metadata']['annotations'][reserve.slot.OWNER] = 'other'
            elif kind == 'insufficient-memory': client.node['status']['allocatable']['memory'] = '399Gi'
            elif kind == 'other-replica-unready': client.pods[2]['status']['conditions'] = []
            elif kind == 'rollout-progressing': client.rollout['status']['phase'] = 'Progressing'
            elif kind == 'rollout-new-hash': client.rollout['status']['currentPodHash'] = 'new'
            elif kind == 'rollout-unobserved': client.rollout['metadata']['generation'] = 8
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                with patch.object(reserve.slot, 'kubectl') as api, self.assertRaises(ValueError):
                    self.run_reservation(client, Path(directory) / 'lease.json')
                api.assert_not_called()
                self.assertEqual(client.evicted, [])

    def test_replacement_uid_before_second_eviction_is_never_deleted(self):
        client = FakeClient()
        def replace():
            if client.evicted:
                client.pods[1]['metadata']['uid'] = 'replacement-uid'
        client.hook = replace
        with tempfile.TemporaryDirectory() as directory, patch.object(reserve.slot, 'kubectl', side_effect=client.kubectl):
            path = Path(directory) / 'lease.json'
            with self.assertRaisesRegex(ValueError, 'replacement UID'):
                self.run_reservation(client, path)
            self.assertEqual(client.evicted, ['uid-0'])
            self.assertFalse(client.node['spec']['unschedulable'])
            self.assertFalse(path.exists())

    def test_late_pod_binding_during_settle_aborts_before_any_eviction(self):
        client = FakeClient()
        def bind():
            if client.time >= 10 and len(client.pods) == 10:
                client.pods.append(pod(99, target=True))
        client.hook = bind
        with tempfile.TemporaryDirectory() as directory, patch.object(reserve.slot, 'kubectl', side_effect=client.kubectl):
            path = Path(directory) / 'lease.json'
            with self.assertRaisesRegex(ValueError, 'foreign pod'):
                self.run_reservation(client, path)
            self.assertEqual(client.evicted, [])
            self.assertEqual(client.time, 10)
            self.assertFalse(client.node['spec']['unschedulable'])
            self.assertFalse(path.exists())

    def test_owner_changes_preserve_the_recovery_lease_and_foreign_cordon(self):
        for owner in ['qualification', 'fleet']:
            client = FakeClient()
            def change_owner():
                if client.evicted:
                    key = reserve.slot.OWNER if owner == 'qualification' else reserve.slot.FLEET
                    client.node['metadata']['annotations'][key] = 'another-owner'
            client.hook = change_owner
            with self.subTest(owner=owner), tempfile.TemporaryDirectory() as directory:
                with patch.object(reserve.slot, 'kubectl', side_effect=client.kubectl):
                    path = Path(directory) / 'lease.json'
                    with self.assertRaisesRegex(RuntimeError, 'preserve'):
                        self.run_reservation(client, path)
                    self.assertEqual(client.evicted, ['uid-0'])
                    self.assertTrue(client.node['spec']['unschedulable'])
                    self.assertTrue(path.exists())

    def test_pdb_rejection_releases_only_the_owned_cordon(self):
        client = FakeClient(); client.deny = True
        with tempfile.TemporaryDirectory() as directory, patch.object(reserve.slot, 'kubectl', side_effect=client.kubectl):
            path = Path(directory) / 'lease.json'
            with self.assertRaises(subprocess.CalledProcessError):
                self.run_reservation(client, path)
            self.assertEqual(client.time, 30)
            self.assertEqual(client.evicted, [])
            self.assertFalse(path.exists())
            self.assertFalse(client.node['spec']['unschedulable'])

    def test_failed_pods_still_wait_for_uid_removal_until_deadline(self):
        client = FakeClient(); client.drain_complete_at = float('inf')
        def fail_pods():
            for p in client.pods:
                if p['metadata']['uid'] in client.evicted:
                    p['status']['phase'] = 'Failed'
        client.hook = fail_pods
        with tempfile.TemporaryDirectory() as directory, patch.object(reserve.slot, 'kubectl', side_effect=client.kubectl):
            with self.assertRaisesRegex(TimeoutError, 'normal pod grace'):
                self.run_reservation(client, Path(directory) / 'lease.json')
            self.assertEqual(client.time, 900)
            self.assertEqual(len(client.pods), 10)
            self.assertTrue(all(p['spec']['terminationGracePeriodSeconds'] == 750 for p in client.pods))
            self.assertFalse(client.node['spec']['unschedulable'])

    def test_a_new_rollout_or_capacity_loss_stops_before_second_eviction(self):
        for kind in ['rollout', 'capacity']:
            client = FakeClient()
            def change():
                if client.evicted:
                    if kind == 'rollout': client.rollout['metadata']['generation'] += 1
                    else: client.pods[2]['status']['conditions'] = []
            client.hook = change
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                with patch.object(reserve.slot, 'kubectl', side_effect=client.kubectl), self.assertRaises(ValueError):
                    self.run_reservation(client, Path(directory) / 'lease.json')
                self.assertEqual(client.evicted, ['uid-0'])

    def test_final_free_capacity_is_checked(self):
        client = FakeClient()
        with tempfile.TemporaryDirectory() as directory, patch.object(reserve.slot, 'kubectl', side_effect=client.kubectl):
            with patch.object(reserve.slot, 'check_capacity', return_value={'cpu': 48, 'memory': 452*1024**3, 'nvidia.com/gpu': 1}):
                with self.assertRaisesRegex(ValueError, 'insufficient free'):
                    self.run_reservation(client, Path(directory) / 'lease.json')
            self.assertFalse(client.node['spec']['unschedulable'])

    def test_existing_lease_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(reserve.slot, 'kubectl') as api:
            path = Path(directory) / 'lease.json'; path.write_text('existing')
            with self.assertRaises(FileExistsError): self.run_reservation(FakeClient(), path)
            self.assertEqual(path.read_text(), 'existing')
            api.assert_not_called()

    def test_eviction_uses_uid_precondition_without_overriding_grace(self):
        client = reserve.Client(100, clock=lambda: 0)
        with patch.object(client, 'run') as run:
            client.evict('pod-name', 'original-uid')
        args, payload = run.call_args.args
        self.assertEqual(args[2], '/api/v1/namespaces/gpu-inference/pods/pod-name/eviction')
        self.assertEqual(payload['apiVersion'], 'policy/v1')
        self.assertEqual(payload['deleteOptions'], {'preconditions': {'uid': 'original-uid'}})
        self.assertNotIn('gracePeriodSeconds', payload['deleteOptions'])

    def test_budget_client_reads_only_the_named_production_budget(self):
        client = reserve.Client(100, clock=lambda: 0)
        with patch.object(client, 'run', return_value=budget()) as run:
            self.assertEqual(client.budget()['metadata']['uid'], 'budget-uid')
        run.assert_called_once_with(['get', 'poddisruptionbudget', 'glm-dealign',
                                     '-n', 'gpu-inference', '-o', 'json'])

    def test_expired_client_deadline_never_invokes_kubectl(self):
        client = reserve.Client(10, clock=lambda: 11)
        with patch.object(reserve.subprocess, 'run') as run, self.assertRaises(TimeoutError):
            client.snapshot()
        run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
