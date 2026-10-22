import copy
import importlib.util
import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest
from unittest.mock import patch

import yaml

spec = importlib.util.spec_from_file_location('render_config', Path(__file__).with_name('render-config.py'))
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.definition = yaml.safe_load((renderer.GPU / 'gpuhost-crd.yaml').read_text())
        self.hosts = [item for item in yaml.safe_load_all((renderer.GPU / 'hosts.yaml').read_text()) if item]

    def host(self, instance='019d5a4a-0000-7000-8000-000000000001', pod='newpod1'):
        document = copy.deepcopy(self.hosts[0])
        document['metadata']['name'] = 'gpu-' + instance
        document['spec']['instanceId'] = instance
        document['spec']['provider']['podId'] = pod
        document['spec']['managementSecret'] = {'key': 'gradiated/prod/platform/gpu-host/' + instance}
        return document

    def test_host_pin_is_projected_and_invalid_digests_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            gpu = Path(directory)
            shutil.copytree(renderer.GPU, gpu, dirs_exist_ok=True)
            pin = {'sha256': 'a' * 64, 'base_id': 'test-base'}
            (gpu / 'host.json').write_text(json.dumps(pin))
            with patch.object(renderer, 'GPU', gpu):
                outputs = renderer.render()
                self.assertEqual(json.loads(outputs[gpu / 'controller.yaml'][0]['data']['hosts.json'])['host_bundle'], pin)
                (gpu / 'host.json').write_text(json.dumps({**pin, 'sha256': '../escape'}))
                with self.assertRaises(ValueError):
                    renderer.render()

    def test_argo_only_reads_generated_manifests(self):
        app = yaml.safe_load((renderer.KUBE / 'platform/gpu-inference.yaml').read_text())
        self.assertEqual(app['spec']['source']['directory']['include'], '*.yaml')

    def test_host_services_belong_to_the_fleet_operator_not_git(self):
        self.assertFalse((renderer.KUBE / 'platform/inference-hosts.yaml').exists())
        self.assertFalse((renderer.KUBE / 'tailscale-inference/hosts').exists())
        network = yaml.safe_load((renderer.KUBE / 'platform/inference-network.yaml').read_text())['spec']
        self.assertNotIn('automated', network['syncPolicy'])
        self.assertEqual(network['source']['directory'], {'include': 'proxies.yaml'})

    def test_new_host_projects_secret_and_private_endpoint(self):
        document = self.host()
        hosts, secrets = renderer.inventory([document])
        instance = document['spec']['instanceId']
        self.assertEqual(hosts[0]['token_file'], '/var/run/gradiated-host-keys/' + instance)
        self.assertEqual(hosts[0]['endpoint'], f'http://gpu-{instance}.tailscale-inference.svc.cluster.local:8888/_kubelet')
        self.assertEqual(hosts[0]['gpu_count'], document['spec']['inventory']['gpuCount'])
        self.assertEqual(secrets, [{'secretKey': instance, 'remoteRef': document['spec']['managementSecret']}])

    def test_rejects_duplicates_misnamed_other_kinds_and_empty_inventory(self):
        first = self.host()
        renamed = self.host()
        renamed['metadata']['name'] = 'gpu-other'
        shared_pod = self.host('019d5a4a-0000-7000-8000-000000000002', first['spec']['provider']['podId'])
        wrong_kind = {**self.host(), 'kind': 'Service'}
        for documents in ([first, self.host()], [first, shared_pod], [renamed], [wrong_kind], []):
            with self.subTest(documents=documents), self.assertRaises(ValueError):
                renderer.inventory(documents)

    def test_argo_never_deletes_the_crd_or_a_gpuhost(self):
        options = self.definition['metadata']['annotations']['argocd.argoproj.io/sync-options'].split(',')
        self.assertIn('Delete=false', options)
        self.assertIn('Prune=false', options)
        for host in self.hosts:
            with self.subTest(host=host['metadata']['name']):
                self.assertIn('Prune=false', host['metadata']['annotations']['argocd.argoproj.io/sync-options'].split(','))
                # Declared, so a host deleted before the operator's first pass is still held.
                self.assertIn('fleet.gradiated.com/drain', host['metadata']['finalizers'])

    def test_fleet_operator_manages_every_host_account(self):
        documents = yaml.safe_load_all((renderer.GPU / 'gpu-fleet.yaml').read_text())
        deployment = next(item for item in documents if item and item['kind'] == 'Deployment')
        env = {item['name']: item.get('value') for item in deployment['spec']['template']['spec']['containers'][0]['env']}
        managed = set(env['FLEET_ACCOUNTS'].split(','))
        for host in self.hosts:
            provider = host['spec']['provider']
            self.assertIn(f"{provider['name']}/{provider['accountId']}", managed)

    def test_a_removed_host_keeps_its_access_until_retired(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            kube = root / renderer.KUBE.relative_to(renderer.ROOT)
            gpu = kube / 'gpu-inference'
            shutil.copytree(renderer.GPU, gpu)
            runtime_path = root / 'product/inference/gpu/runtimes.json'
            runtime_path.parent.mkdir(parents=True)
            shutil.copyfile(renderer.ROOT / 'product/inference/gpu/runtimes.json', runtime_path)
            removed = self.hosts[-1]['spec']['instanceId']
            (gpu / 'hosts.yaml').write_text(yaml.safe_dump_all(self.hosts[:-1]))
            with patch.multiple(renderer, ROOT=root, KUBE=kube, GPU=gpu):
                # Step one: out of hosts.yaml, so Argo stops wanting the GpuHost,
                # but still drainable.
                with patch('sys.argv', ['render-config.py']):
                    renderer.main()
                self.assertIn('gpu-' + removed, (gpu / 'rbac.yaml').read_text())
                self.assertIn(removed, (gpu / 'credentials.yaml').read_text())
                with patch('sys.argv', ['render-config.py', '--check']):
                    renderer.main()

                # Step two, once the GpuHost is gone.
                with patch('sys.argv', ['render-config.py', '--retire', removed]):
                    renderer.main()
                self.assertNotIn('gpu-' + removed, (gpu / 'rbac.yaml').read_text())
                self.assertNotIn(removed, (gpu / 'credentials.yaml').read_text())
                with patch('sys.argv', ['render-config.py', '--check']):
                    renderer.main()

    def test_capacity_bounds_match_the_controller(self):
        bounds = self.definition['spec']['versions'][0]['schema']['openAPIV3Schema']['properties']['spec']['properties']['inventory']['properties']
        controller = (renderer.ROOT / 'tools/virtual-kubelet/cmd/gpu-controller/hosts.go').read_text()
        for field, go in (('gpuCount', 'GPUCount'), ('cpu', 'CPU'), ('memoryGiB', 'MemoryGiB')):
            match = re.search(rf'h\.{go} < (\d+) \|\| h\.{go} > (\d+)', controller)
            self.assertEqual((int(match.group(1)), int(match.group(2))),
                             (bounds[field]['minimum'], bounds[field]['maximum']), field)

    def test_added_host_updates_all_enrollment_resources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            kube = root / renderer.KUBE.relative_to(renderer.ROOT)
            gpu = kube / 'gpu-inference'
            shutil.copytree(renderer.GPU, gpu)
            runtime_path = root / 'product/inference/gpu/runtimes.json'
            runtime_path.parent.mkdir(parents=True)
            shutil.copyfile(renderer.ROOT / 'product/inference/gpu/runtimes.json', runtime_path)
            entry = self.host()
            (gpu / 'hosts.yaml').write_text(yaml.safe_dump_all([*self.hosts, entry]))
            with patch.multiple(renderer, ROOT=root, KUBE=kube, GPU=gpu):
                outputs = renderer.render()
            instance = entry['spec']['instanceId']
            controller = outputs[gpu / 'controller.yaml']
            self.assertEqual(json.loads(controller[0]['data']['hosts.json'])['hosts'][-1]['instance_id'], instance)
            for resource in outputs[gpu / 'rbac.yaml']:
                if resource['metadata']['name'] in ('gpu-controller-nodes', 'gpu-controller-leases', 'gpu-fleet-nodes'):
                    for rule in resource.get('rules', []):
                        if 'resourceNames' in rule:
                            self.assertIn('gpu-' + instance, rule['resourceNames'])
            self.assertEqual(outputs[gpu / 'credentials.yaml'][1]['spec']['data'][-1],
                             {'secretKey': instance, 'remoteRef': entry['spec']['managementSecret']})
            models = json.loads((gpu / 'models.json').read_text())
            models.pop('kev')
            (gpu / 'models.json').write_text(json.dumps(models))
            with patch.multiple(renderer, ROOT=root, KUBE=kube, GPU=gpu):
                self.assertEqual(renderer.retired_outputs(renderer.render()), {gpu / 'kev.yaml'})
                for name in ('controller', 'rbac', 'credentials', 'namespace', 'qualification'):
                    (gpu / 'models.json').write_text(json.dumps({**models, name: models['glm']}))
                    with self.assertRaisesRegex(ValueError, 'collides with a static manifest'):
                        renderer.render()

    def test_rollout_uses_catalogue_resources_and_qualification(self):
        runtimes = json.loads((renderer.ROOT / 'product/inference/gpu/runtimes.json').read_text())
        models = json.loads((renderer.GPU / 'models.json').read_text())
        for name, model in models.items():
            document = renderer.rollout(name, model, runtimes)
            runtime = runtimes[model['runtime']]
            pod = document['spec']['template']
            self.assertEqual(pod['spec']['containers'][0]['image'], runtime['image'])
            self.assertEqual(json.loads(pod['metadata']['annotations']['gradiated.com/release']), runtime['release'])
            self.assertFalse(pod['spec']['automountServiceAccountToken'])
            self.assertEqual(document['spec']['strategy']['canary']['maxUnavailable'], 0)
            self.assertEqual(document['spec']['strategy']['canary']['steps'][1]['analysis']['templates'],
                             [{'templateName': 'sdk-qualification'}])
        with self.assertRaises(KeyError):
            renderer.rollout('unknown', {**models['kev'], 'runtime': '0' * 64}, runtimes)
        training = next(digest for digest, runtime in runtimes.items() if runtime.get('kind') == 'training')
        with self.assertRaises(ValueError):
            renderer.rollout('training', {**models['kev'], 'runtime': training}, runtimes)

    def test_autoscaling_preserves_minimum_and_rejects_invalid_bounds(self):
        runtimes = json.loads((renderer.ROOT / 'product/inference/gpu/runtimes.json').read_text())
        models = json.loads((renderer.GPU / 'models.json').read_text())
        model = models['deepseek']
        obj = renderer.autoscaler('deepseek', model, runtimes[model['runtime']])
        self.assertEqual(obj['spec']['minReplicaCount'], model['replicas'])
        self.assertEqual(obj['spec']['maxReplicaCount'], 2)
        # A later sync wave would make every model's scaling wait for all
        # Rollouts in the app to become healthy.
        self.assertNotIn('argocd.argoproj.io/sync-wave', obj['metadata']['annotations'])
        for invalid in ({'max_replicas': 0, 'target_concurrency': 1},
                        {'max_replicas': 2.5, 'target_concurrency': 1},
                        {'max_replicas': 2, 'target_concurrency': 0},
                        {'max_replicas': 2, 'target_concurrency': float('nan')},
                        {'max_replicas': 2, 'target_concurrency': float('inf')}):
            with self.assertRaises(ValueError):
                renderer.autoscaler('deepseek', {**model, 'autoscaling': invalid}, runtimes[model['runtime']])

    def test_rejects_invalid_names_and_overridden_qualification_identity(self):
        runtimes = json.loads((renderer.ROOT / 'product/inference/gpu/runtimes.json').read_text())
        model = json.loads((renderer.GPU / 'models.json').read_text())['kev']
        for name in ('model-', 'a' * 64, '../model', 'Model'):
            with self.assertRaises(ValueError):
                renderer.rollout(name, model, runtimes)
        with self.assertRaisesRegex(ValueError, 'identity label is reserved'):
            renderer.rollout('kev', {**model, 'labels': {'app.kubernetes.io/name': 'other'}}, runtimes)


if __name__ == '__main__':
    unittest.main()
