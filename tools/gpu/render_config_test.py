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

    def test_pins_reach_the_operator_and_invalid_pins_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            gpu = Path(directory)
            shutil.copytree(renderer.GPU, gpu, dirs_exist_ok=True)
            pins = {'image': '873716897517.dkr.ecr.us-east-1.amazonaws.com/gradiated/prod/inference:gpu-base-inputs-' + 'c' * 64,
                    'imageDigest': 'sha256:' + 'd' * 64,
                    'hostBundle': {'sha256': 'a' * 64, 'baseId': 'test-base'}}
            (gpu / 'pins.json').write_text(json.dumps(pins))
            with patch.object(renderer, 'GPU', gpu):
                outputs = renderer.render()
                self.assertEqual(json.loads(outputs[gpu / 'gpu-fleet-pins.yaml'][0]['data']['pins.json']), pins)
                # The controller applies whatever bundle the operator chose for each host.
                self.assertNotIn('host_bundle', json.loads(outputs[gpu / 'controller.yaml'][0]['data']['hosts.json']))
                for invalid in ({**pins, 'hostBundle': {**pins['hostBundle'], 'sha256': '../escape'}},
                                {**pins, 'image': pins['image'] + '@' + pins['imageDigest']},
                                {**pins, 'image': 'docker.io/library/ubuntu:latest'},
                                {**pins, 'imageDigest': 'latest'},
                                {**pins, 'extra': True}):
                    (gpu / 'pins.json').write_text(json.dumps(invalid))
                    with self.assertRaises(ValueError):
                        renderer.render()

    def test_template_and_ops_mcp_take_the_pinned_image_and_bundle(self):
        pins = {'image': '873716897517.dkr.ecr.us-east-1.amazonaws.com/gradiated/prod/inference:gpu-base-inputs-' + 'c' * 64,
                'imageDigest': 'sha256:' + 'd' * 64,
                'hostBundle': {'sha256': 'a' * 64, 'baseId': 'test-base'}}
        copies = renderer.pinned_copies(pins)
        self.assertEqual(json.loads(copies[renderer.TEMPLATES])['image'], pins['image'])
        workload = copies[renderer.OPS_MCP]
        for name, value in (('GPU_BASE_IMAGE', pins['image']), ('GPU_HOST_BOOTSTRAP_SHA256', 'a' * 64),
                            ('GPU_HOST_BOOTSTRAP_BASE_ID', 'test-base')):
            self.assertRegex(workload, rf'- name: {name}\n\s+value: {re.escape(value)}\n')
        # Everything else in the workload is left as written.
        current = renderer.OPS_MCP.read_text().splitlines()
        self.assertEqual(len(workload.splitlines()), len(current))

    def test_each_model_fleet_and_platform_sync_as_separate_argo_applications(self):
        platform = renderer.KUBE / 'platform'
        self.assertFalse((platform / 'gpu-inference.yaml').exists())
        models = yaml.safe_load((platform / 'gpu-models.yaml').read_text())
        # A list generator: a git directory generator makes Argo check out the
        # repository's private submodule, which fails.
        self.assertEqual(models['spec']['generators'],
                         [{'list': {'elements': [{'model': name} for name in
                                                 sorted(json.loads((renderer.GPU / 'models.json').read_text()))]}}])
        # Deleting a model's application must not delete its serving Rollout.
        self.assertTrue(models['spec']['syncPolicy']['preserveResourcesOnDeletion'])
        template = models['spec']['template']['spec']
        self.assertEqual(template['source']['path'],
                         str(renderer.MODELS.relative_to(renderer.ROOT)) + '/{{ .model }}')
        self.assertIn('RespectIgnoreDifferences=true', template['syncPolicy']['syncOptions'])
        self.assertEqual(template['ignoreDifferences'][0]['jsonPointers'], ['/spec/replicas'])
        for name in json.loads((renderer.GPU / 'models.json').read_text()):
            self.assertTrue((renderer.MODELS / name / f'{name}.yaml').exists(), name)
        # Each application prunes what leaves its files: a setting carried over
        # from the handoff would keep removed resources running.
        fleet_app = yaml.safe_load((platform / 'gpu-fleet.yaml').read_text())['spec']
        shared_app = yaml.safe_load((platform / 'gpu-platform.yaml').read_text())['spec']
        for spec in (template, fleet_app, shared_app):
            self.assertEqual(spec['syncPolicy']['automated'], {'prune': True, 'selfHeal': True})
            # A fresh cluster syncs in any order: namespaces are created and syncs retry.
            self.assertIn('CreateNamespace=true', spec['syncPolicy']['syncOptions'])
            self.assertGreaterEqual(spec['syncPolicy']['retry']['limit'], 1)
        # Every manifest in gpu-inference/ belongs to exactly one of the fleet
        # and platform applications.
        fleet = fleet_app['source']
        shared = shared_app['source']
        for source in (fleet, shared):
            self.assertEqual(source['path'], str(renderer.GPU.relative_to(renderer.ROOT)))
        listed = set(fleet['directory']['include'].strip('{}').split(','))
        self.assertEqual(shared['directory']['exclude'], fleet['directory']['include'])
        self.assertEqual(shared['directory']['include'], '*.yaml')
        root = {path.name for path in renderer.GPU.glob('*.yaml')}
        self.assertLessEqual(listed, root)
        self.assertIn('hosts.yaml', listed)
        self.assertIn('controller.yaml', root - listed)
        # No sync waves on model resources: one model's health must never
        # hold back another model's changes.
        for path in renderer.MODELS.glob('*/*.yaml'):
            for document in yaml.safe_load_all(path.read_text()):
                self.assertNotIn('argocd.argoproj.io/sync-wave', document['metadata'].get('annotations', {}))

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
            with patch.multiple(renderer, ROOT=root, KUBE=kube, GPU=gpu, MODELS=gpu / 'models'):
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
            with patch.multiple(renderer, ROOT=root, KUBE=kube, GPU=gpu, MODELS=gpu / 'models'):
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
            with patch.multiple(renderer, ROOT=root, KUBE=kube, GPU=gpu, MODELS=gpu / 'models'):
                self.assertEqual(renderer.retired_outputs(renderer.render()), {gpu / 'models/kev/kev.yaml'})
                with patch('sys.argv', ['render-config.py', '--check']), \
                        self.assertRaisesRegex(SystemExit, 'kubectl -n gpu-inference delete rollout,scaledobject kev'):
                    renderer.main()
                for invalid in ('../escape', 'a/b', 'Upper', 'x' * 54, ''):
                    (gpu / 'models.json').write_text(json.dumps({**models, invalid: models['glm']}))
                    with self.assertRaisesRegex(ValueError, 'DNS label'):
                        renderer.render()
                # A model is written to its own directory, so its name cannot
                # collide with a platform or fleet manifest.
                (gpu / 'models.json').write_text(json.dumps({**models, 'controller': models['glm']}))
                outputs = renderer.render()
                self.assertIn(gpu / 'models/controller/controller.yaml', outputs)
                self.assertEqual(outputs[gpu / 'controller.yaml'][1]['kind'], 'Deployment')

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
