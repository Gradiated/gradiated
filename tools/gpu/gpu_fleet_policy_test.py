"""The gpu-fleet admission policies, checked by a real Kubernetes API server.

Starts k3s in Docker, installs the policies from gpu-fleet.yaml, and patches a
pod, a node and a KEDA ScaledObject as the operator's service account. Needs
Docker and kubectl.
"""

import json
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
FLEET = ROOT / 'infra/environments/prod/us-east-1/kubernetes/gpu-inference/gpu-fleet.yaml'
# Matches the EKS minor version in infra/environments/prod/us-east-1/terraform/eks.
IMAGE = 'rancher/k3s:v1.36.3-k3s1@sha256:d0f79175794edd9694b4a12bafc5c52ae1977369a2f7cf256264e7bd2dae0be9'
OPERATOR = 'system:serviceaccount:gpu-inference:gpu-fleet'
COST = 'controller.kubernetes.io/pod-deletion-cost'
PAUSED = 'autoscaling.keda.sh/paused-replicas'
CORDONED_BY = 'fleet.gradiated.com/cordoned-by'

# Lets the impersonated operator reach the API; the policies under test then
# decide what it may change.
ACCESS = [
    {'apiVersion': 'v1', 'kind': 'Namespace', 'metadata': {'name': 'gpu-inference'}},
    {'apiVersion': 'rbac.authorization.k8s.io/v1', 'kind': 'ClusterRole', 'metadata': {'name': 'test-gpu-fleet'},
     'rules': [{'apiGroups': [''], 'resources': ['pods', 'nodes'], 'verbs': ['get', 'patch']},
               {'apiGroups': ['keda.sh'], 'resources': ['scaledobjects'], 'verbs': ['get', 'patch']}]},
    {'apiVersion': 'rbac.authorization.k8s.io/v1', 'kind': 'ClusterRoleBinding', 'metadata': {'name': 'test-gpu-fleet'},
     'subjects': [{'kind': 'User', 'name': OPERATOR}],
     'roleRef': {'kind': 'ClusterRole', 'name': 'test-gpu-fleet', 'apiGroup': 'rbac.authorization.k8s.io'}},
]
# Enough of KEDA's CRD to store a ScaledObject.
SCALED_OBJECTS = {
    'apiVersion': 'apiextensions.k8s.io/v1', 'kind': 'CustomResourceDefinition',
    'metadata': {'name': 'scaledobjects.keda.sh'},
    'spec': {'group': 'keda.sh', 'scope': 'Namespaced',
             'names': {'plural': 'scaledobjects', 'singular': 'scaledobject', 'kind': 'ScaledObject'},
             'versions': [{'name': 'v1alpha1', 'served': True, 'storage': True,
                           'schema': {'openAPIV3Schema': {'type': 'object',
                                                          'x-kubernetes-preserve-unknown-fields': True}}}]},
}


class GpuFleetPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.kubeconfig = Path(cls.directory.name) / 'kubeconfig'
        cls.container = subprocess.check_output(
            ['docker', 'run', '-d', '--privileged', '-p', '127.0.0.1::6443', IMAGE, 'server',
             '--disable=traefik,servicelb,metrics-server,local-storage,coredns', '--disable-agent'],
            text=True).strip()
        try:
            port = subprocess.check_output(['docker', 'port', cls.container, '6443/tcp'], text=True).split(':')[-1].strip()
            deadline = time.monotonic() + 120
            while True:
                result = subprocess.run(['docker', 'exec', cls.container, 'cat', '/etc/rancher/k3s/k3s.yaml'],
                                        capture_output=True, text=True)
                if result.returncode == 0:
                    cls.kubeconfig.write_text(result.stdout.replace('127.0.0.1:6443', f'127.0.0.1:{port}'))
                    if cls.kubectl('get', '--raw', '/readyz', check=False).returncode == 0:
                        break
                if time.monotonic() > deadline:
                    raise RuntimeError('k3s did not become ready')
                time.sleep(1)
            policies = [document for document in yaml.safe_load_all(FLEET.read_text())
                        if document and document['kind'].startswith('ValidatingAdmissionPolicy')]
            cls.apply(*ACCESS, SCALED_OBJECTS, *policies)
            cls.apply(
                {'apiVersion': 'v1', 'kind': 'Node',
                 'metadata': {'name': 'gpu-test', 'labels': {'a': 'b'}, 'annotations': {'a': 'b'}}},
                {'apiVersion': 'v1', 'kind': 'Pod',
                 'metadata': {'name': 'kev-1', 'namespace': 'gpu-inference', 'labels': {'app.kubernetes.io/name': 'kev'},
                              'annotations': {'gradiated.com/qualified-runtime': 'kev-1:1'}},
                 'spec': {'nodeName': 'gpu-test', 'containers': [{'name': 'kev', 'image': 'kev'}]}},
                {'apiVersion': 'keda.sh/v1alpha1', 'kind': 'ScaledObject',
                 'metadata': {'name': 'kev', 'namespace': 'gpu-inference', 'annotations': {'a': 'b'}},
                 'spec': {'minReplicaCount': 1, 'scaleTargetRef': {'name': 'kev'}}})
            # Policies take effect once the API server has loaded them.
            deadline = time.monotonic() + 60
            while cls.patch('pod', 'kev-1', {'metadata': {'labels': {'x': 'y'}}}).returncode == 0:
                cls.patch('pod', 'kev-1', {'metadata': {'labels': {'x': None}}}, user=None)
                if time.monotonic() > deadline:
                    raise RuntimeError('the gpu-fleet policies never took effect')
                time.sleep(1)
        except BaseException:
            subprocess.run(['docker', 'rm', '-f', cls.container], capture_output=True)
            raise

    @classmethod
    def tearDownClass(cls):
        subprocess.run(['docker', 'rm', '-f', cls.container], capture_output=True)
        cls.directory.cleanup()

    @classmethod
    def kubectl(cls, *args, stdin=None, check=True):
        return subprocess.run(['kubectl', '--kubeconfig', str(cls.kubeconfig), *args],
                              input=stdin, capture_output=True, text=True, check=check)

    # A new namespace has no default service account for a few seconds, and a
    # pod cannot be created until it does.
    @classmethod
    def apply(cls, *documents):
        deadline = time.monotonic() + 60
        while True:
            result = cls.kubectl('apply', '-f', '-', check=False,
                                 stdin='\n---\n'.join(json.dumps(document) for document in documents))
            if result.returncode == 0:
                return
            if time.monotonic() > deadline:
                raise RuntimeError(result.stderr)
            time.sleep(1)

    @classmethod
    def patch(cls, kind, name, body, user=OPERATOR):
        args = ['patch', kind, name, '--type=merge', '-p', json.dumps(body)]
        if kind in ('pod', 'scaledobject'):
            args += ['-n', 'gpu-inference']
        if user:
            args += ['--as', user]
        return cls.kubectl(*args, check=False)

    NAMES = {'pod': 'kev-1', 'node': 'gpu-test', 'scaledobject': 'kev'}

    def assertAllowed(self, kind, body):
        name = self.NAMES[kind]
        result = self.patch(kind, name, body)
        self.assertEqual(result.returncode, 0, result.stderr)

    def assertRefused(self, kind, body, message):
        name = self.NAMES[kind]
        result = self.patch(kind, name, body)
        self.assertNotEqual(result.returncode, 0, f'admitted: {body}')
        self.assertIn(message, result.stderr)

    def test_operator_may_only_set_a_pods_deletion_cost(self):
        self.assertAllowed('pod', {'metadata': {'annotations': {COST: '-10000'}}})
        self.assertAllowed('pod', {'metadata': {'annotations': {COST: None}}})
        message = "may change only a pod's controller.kubernetes.io/pod-deletion-cost annotation"
        for body in ({'metadata': {'labels': {'app.kubernetes.io/name': 'other'}}},
                     {'metadata': {'annotations': {'gradiated.com/qualified-runtime': 'forged'}}},
                     {'metadata': {'annotations': {'gradiated.com/qualified-runtime': None}}},
                     {'metadata': {'finalizers': ['example.com/hold']}},
                     {'metadata': {'ownerReferences': [{'apiVersion': 'v1', 'kind': 'Node', 'name': 'x', 'uid': '00000000-0000-0000-0000-000000000000'}]}},
                     {'spec': {'activeDeadlineSeconds': 1}}):
            with self.subTest(body=body):
                self.assertRefused('pod', body, message)

    def test_operator_may_only_cordon_a_node_and_mark_its_cordon(self):
        for value in ('gpu-fleet', 'gpu-fleet-rollout'):
            with self.subTest(value=value):
                self.assertAllowed('node', {'metadata': {'annotations': {CORDONED_BY: value}},
                                            'spec': {'unschedulable': True}})
                self.assertAllowed('node', {'metadata': {'annotations': {CORDONED_BY: None}},
                                            'spec': {'unschedulable': False}})
        message = "may change only a node's spec.unschedulable and its fleet.gradiated.com/cordoned-by marker"
        for body in ({'metadata': {'labels': {'gradiated.com/fault-domain': 'forged'}}},
                     {'metadata': {'annotations': {'example.com/x': 'y'}}},
                     {'metadata': {'annotations': {'a': None}}},
                     {'metadata': {'annotations': {CORDONED_BY: 'someone-else'}}},
                     {'metadata': {'finalizers': ['example.com/hold']}},
                     {'metadata': {'ownerReferences': [{'apiVersion': 'v1', 'kind': 'Node', 'name': 'x', 'uid': '00000000-0000-0000-0000-000000000000'}]}},
                     {'spec': {'taints': [{'key': 'x', 'effect': 'NoSchedule'}]}},
                     {'spec': {'providerID': 'runpod://forged'}}):
            with self.subTest(body=body):
                self.assertRefused('node', body, message)

    def test_operator_may_only_pause_a_scaledobject(self):
        self.assertAllowed('scaledobject', {'metadata': {'annotations': {PAUSED: '3'}}})
        self.assertAllowed('scaledobject', {'metadata': {'annotations': {PAUSED: None}}})
        message = "may change only a ScaledObject's autoscaling.keda.sh/paused-replicas annotation"
        owner = {'apiVersion': 'v1', 'kind': 'ConfigMap', 'name': 'x',
                 'uid': '00000000-0000-0000-0000-000000000000'}
        for body in ({'metadata': {'annotations': {PAUSED: 'many'}}},
                     {'metadata': {'annotations': {'a': None}}},
                     {'metadata': {'ownerReferences': [owner]}},
                     {'metadata': {'labels': {'x': 'y'}}},
                     {'spec': {'minReplicaCount': 0}}):
            with self.subTest(body=body):
                self.assertRefused('scaledobject', body, message)

    def test_other_users_are_not_limited(self):
        result = self.patch('pod', 'kev-1', {'metadata': {'labels': {'team': 'inference'}}}, user=None)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
