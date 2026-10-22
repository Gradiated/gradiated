"""The GpuHost CRD's validation, checked by a real Kubernetes API server.

Starts a k3s server in Docker, installs the CRD and the committed hosts, then
checks what the API server admits and refuses. Needs Docker and kubectl.
"""

import copy
import json
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
import uuid

import yaml

ROOT = Path(__file__).resolve().parents[2]
GPU = ROOT / 'infra/environments/prod/us-east-1/kubernetes/gpu-inference'
# Matches the EKS minor version in infra/environments/prod/us-east-1/terraform/eks.
IMAGE = 'rancher/k3s:v1.36.3-k3s1@sha256:d0f79175794edd9694b4a12bafc5c52ae1977369a2f7cf256264e7bd2dae0be9'


class GpuHostCrdTest(unittest.TestCase):
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
            cls.kubectl('apply', '-f', str(GPU / 'gpuhost-crd.yaml'))
            cls.kubectl('wait', '--for=condition=Established', 'crd/gpuhosts.fleet.gradiated.com', '--timeout=60s')
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

    def apply(self, document, check=True):
        return self.kubectl('apply', '-f', '-', stdin=json.dumps(document), check=check)

    def host(self, **overrides):
        instance = str(uuid.uuid4())
        document = copy.deepcopy(next(item for item in yaml.safe_load_all((GPU / 'hosts.yaml').read_text()) if item))
        document['metadata'] = {'name': 'gpu-' + instance}
        document['spec']['instanceId'] = instance
        document['spec']['provider']['podId'] = instance.replace('-', '')[:14]
        document['spec']['managementSecret'] = {'key': 'gradiated/prod/platform/gpu-host/' + instance}
        for path, value in overrides.items():
            target = document['spec']
            *parents, leaf = path.split('.')
            for parent in parents:
                target = target[parent]
            target[leaf] = value
        return document

    def assertRefused(self, document, message):
        result = self.apply(document, check=False)
        self.assertNotEqual(result.returncode, 0, f'admitted: {json.dumps(document)}')
        self.assertIn(message, result.stderr)

    def test_committed_hosts_are_admitted(self):
        self.kubectl('apply', '--dry-run=server', '-f', str(GPU / 'hosts.yaml'))

    def test_name_must_match_the_instance(self):
        document = self.host()
        document['metadata']['name'] = 'gpu-' + str(uuid.uuid4())
        self.assertRefused(document, 'metadata.name must be gpu-<spec.instanceId>')

    def test_capacity_and_product_bounds(self):
        for field, value in (('inventory.gpuCount', 9), ('inventory.gpuCount', 0), ('inventory.cpu', 513),
                             ('inventory.memoryGiB', 4097), ('inventory.gpuProduct', 'H100'),
                             ('provider.podId', 'Not A Pod'), ('provider.machineId', 'Not A Machine'),
                             ('managementSecret', {'key': 'some/other/secret'})):
            with self.subTest(field=field, value=value):
                self.assertRefused(self.host(**{field: value}), 'spec.' + field.split('.')[0])

    def test_identity_is_immutable_but_inventory_and_machine_can_change(self):
        document = self.host()
        del document['spec']['provider']['machineId']
        self.apply(document)
        resized = copy.deepcopy(document)
        resized['spec']['inventory']['cpu'] = 48
        resized['spec']['provider']['machineId'] = 'machine1'
        self.apply(resized)

        moved = copy.deepcopy(resized)
        moved['spec']['provider']['podId'] = 'otherpod'
        self.assertRefused(moved, 'the pod ID is immutable')
        other_account = copy.deepcopy(resized)
        other_account['spec']['provider']['accountId'] = 'user_other'
        self.assertRefused(other_account, 'the provider account is immutable')
        renumbered = copy.deepcopy(document)
        renumbered['spec']['instanceId'] = str(uuid.uuid4())
        self.assertRefused(renumbered, 'instanceId is immutable')
        unmachined = copy.deepcopy(resized)
        del unmachined['spec']['provider']['machineId']
        self.assertRefused(unmachined, 'the machine ID can be changed but not removed')
        remachined = copy.deepcopy(resized)
        remachined['spec']['provider']['machineId'] = 'machine2'
        self.apply(remachined)

    def test_status_is_a_subresource(self):
        document = self.host()
        self.apply(document)
        name = document['metadata']['name']
        self.kubectl('patch', 'gpuhost', name, '--subresource=status', '--type=merge',
                     '-p', json.dumps({'status': {'phase': 'Ready', 'observed': {'reachable': True}}}))
        self.apply({**document, 'status': {'phase': 'Degraded'}})
        phase = self.kubectl('get', 'gpuhost', name, '-o', 'jsonpath={.status.phase}').stdout
        self.assertEqual(phase, 'Ready')


if __name__ == '__main__':
    unittest.main()
