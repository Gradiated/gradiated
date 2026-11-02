import copy
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
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
            base = json.loads((renderer.GPU / 'pins.json').read_text())['hostBundle']['baseId']
            pins = {'image': '873716897517.dkr.ecr.us-east-1.amazonaws.com/gradiated/prod/inference:gpu-base-inputs-' + 'c' * 64,
                    'imageDigest': 'sha256:' + 'd' * 64,
                    'hostBundle': {'sha256': 'a' * 64, 'baseId': base}}
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

    def test_a_base_is_pinned_only_once_every_release_has_a_bundle_for_it(self):
        runtimes = json.loads(renderer.RUNTIMES.read_text())
        base = json.loads((renderer.GPU / 'pins.json').read_text())['hostBundle']['baseId']
        renderer.validate_bundles(runtimes, base)
        release = next(iter(runtimes))
        for bundles, message in (({key: value for key, value in runtimes[release]['bundles'].items() if key != base}, 'no bundle for the pinned base'),
                                 ({base: '../escape'}, 'needs a bundles map'), (None, 'needs a bundles map'), ({}, 'needs a bundles map')):
            with self.subTest(bundles=bundles), self.assertRaisesRegex(ValueError, message):
                renderer.validate_bundles({**runtimes, release: {**runtimes[release], 'bundles': bundles}}, base)
        with tempfile.TemporaryDirectory() as directory:
            catalogue = Path(directory) / 'runtimes.json'
            catalogue.write_text(json.dumps({**runtimes, release: {**runtimes[release], 'bundles': {'older-base': 'a' * 64}}}))
            with patch.object(renderer, 'RUNTIMES', catalogue), self.assertRaisesRegex(ValueError, 'no bundle for the pinned base'):
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
        self.assertEqual(template['ignoreDifferences'][0]['jqPathExpressions'],
                         ['select(.metadata.annotations["gradiated.com/paused-replicas"] == null) | .spec.replicas'])
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
            # Hosts being retired keep their keys after the listed hosts.
            self.assertIn({'secretKey': instance, 'remoteRef': entry['spec']['managementSecret']},
                          outputs[gpu / 'credentials.yaml'][1]['spec']['data'])
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
            self.assertEqual(document['spec']['strategy']['canary']['maxUnavailable'],
                             models[name].get('max_unavailable', 0))
            self.assertEqual(document['spec']['strategy']['canary']['steps'][1]['analysis']['templates'],
                             [{'templateName': 'sdk-qualification'}])
        with self.assertRaises(KeyError):
            renderer.rollout('unknown', {**models['kev'], 'runtime': '0' * 64}, runtimes)
        training = next(digest for digest, runtime in runtimes.items() if runtime.get('kind') == 'training')
        with self.assertRaises(ValueError):
            renderer.rollout('training', {**models['kev'], 'runtime': training}, runtimes)

    def test_explicit_canary_keeps_primary_and_pauses_after_qualification(self):
        runtimes = json.loads((renderer.ROOT / 'product/inference/gpu/runtimes.json').read_text())
        primary = json.loads((renderer.GPU / 'models.json').read_text())['glm-dealign']
        candidate = {**primary, 'replicas': 1, 'min_available': 1, 'max_unavailable': 0,
                     'max_surge': 1, 'canary_for': 'glm-dealign'}
        obj = renderer.rollout('glm-dealign-canary', candidate, runtimes)
        self.assertEqual(obj['spec']['replicas'], 1)
        self.assertEqual(obj['spec']['template']['metadata']['annotations']['gradiated.com/canary-of'],
                         'glm-dealign')
        steps = obj['spec']['strategy']['canary']['steps']
        self.assertIn('analysis', steps[1])
        self.assertEqual(steps[2], {'pause': {}})
        self.assertEqual(steps[3], {'setWeight': 100})
        self.assertNotIn('gradiated.com/canary-of',
                         renderer.rollout('glm-dealign', primary, runtimes)['spec']['template']['metadata']['annotations'])
        for parent in ('', '../bad', 'glm-dealign-canary', True, None):
            with self.subTest(parent=parent), self.assertRaisesRegex(ValueError, 'canary_for'):
                renderer.rollout('glm-dealign-canary', {**candidate, 'canary_for': parent}, runtimes)

    def test_isolated_canary_preserves_private_runtime_identity_and_public_mapping(self):
        runtimes = json.loads(renderer.RUNTIMES.read_text())
        primary = json.loads((renderer.GPU / 'models.json').read_text())['glm-dealign']
        private = copy.deepcopy(runtimes[primary['runtime']])
        public_id = private['model_id']
        private['model_id'] += '-sglang-canary'
        runtimes['private'] = private
        candidate = {**primary, 'runtime': 'private', 'canary_for': 'glm-dealign',
                     'serving_model_id': public_id, 'serving_mode': 'qualification'}
        renderer.validate_canaries({'glm-dealign': primary, 'candidate': candidate}, runtimes)
        for mode in ('qualification', 'production'):
            obj = renderer.rollout('candidate', {**candidate, 'serving_mode': mode}, runtimes)
            annotations = obj['spec']['template']['metadata']['annotations']
            self.assertEqual(annotations['gradiated.com/model-id'], private['model_id'])
            self.assertEqual(annotations['gradiated.com/serving-model-id'], public_id)
            self.assertEqual(annotations['gradiated.com/serving-mode'], mode)
        for unsafe in (
                {k: v for k, v in candidate.items() if k != 'serving_mode'},
                {k: v for k, v in candidate.items() if k != 'serving_model_id'},
                {**candidate, 'serving_model_id': private['model_id']}):
            with self.subTest(unsafe=unsafe), self.assertRaises(ValueError):
                renderer.rollout('candidate', unsafe, runtimes)
        for mode in ('invalid', None, True):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                renderer.rollout('candidate', {**candidate, 'serving_mode': mode}, runtimes)
        for field in ('gradiated.com/model-id', 'gradiated.com/serving-model-id',
                      'gradiated.com/serving-mode', 'gradiated.com/canary-of'):
            with self.subTest(field=field), self.assertRaises(ValueError):
                renderer.rollout('candidate', {**candidate, 'annotations': {field: 'spoof'}}, runtimes)
        for mapping in ('other/model', '', None):
            with self.subTest(mapping=mapping), self.assertRaises(ValueError):
                renderer.validate_canaries({'glm-dealign': primary, 'candidate': {
                    **candidate, 'serving_model_id': mapping}}, runtimes)
        with self.assertRaises(ValueError):
            renderer.rollout('primary', {**primary, 'serving_mode': 'qualification'}, runtimes)
        with self.assertRaises(ValueError):
            renderer.rollout('primary', {**primary, 'serving_model_id': public_id}, runtimes)
        self.assertNotIn('gradiated.com/serving-mode', renderer.rollout(
            'glm-dealign', primary, runtimes)['spec']['template']['metadata']['annotations'])

    def test_single_canary_replaces_itself_within_its_gpu_budget(self):
        runtimes = json.loads(renderer.RUNTIMES.read_text())
        model = json.loads((renderer.GPU / 'models.json').read_text())['glm-dealign']
        candidate = {**model, 'replicas': 1, 'max_surge': 0, 'max_unavailable': 1,
                     'canary_for': 'glm-dealign'}
        obj = renderer.rollout('candidate', candidate, runtimes)
        strategy = obj['spec']['strategy']['canary']
        self.assertEqual((strategy['maxSurge'], strategy['maxUnavailable']), (0, 1))
        self.assertEqual((obj['spec']['replicas'] + strategy['maxSurge']), 1)
        with self.assertRaisesRegex(ValueError, 'both be zero'):
            renderer.rollout('candidate', {**candidate, 'max_unavailable': 0}, runtimes)
        with self.assertRaisesRegex(ValueError, 'max_surge'):
            renderer.rollout('primary', {k: v for k, v in candidate.items() if k != 'canary_for'}, runtimes)

    def test_canary_catalogue_rejects_unknown_chained_and_different_models(self):
        runtimes = {'old': {'model_id': 'a/model'}, 'new': {'model_id': 'a/model'},
                    'other': {'model_id': 'a/other'}}
        primary = {'runtime': 'old'}
        candidate = {'runtime': 'new', 'canary_for': 'primary'}
        renderer.validate_canaries({'primary': primary, 'candidate': candidate}, runtimes)
        for models in (
                {'candidate': candidate},
                {'primary': primary, 'candidate': {**candidate, 'canary_for': 'candidate'}},
                {'primary': primary, 'candidate': {**candidate, 'runtime': 'other'}},
                {'primary': primary, 'candidate': candidate,
                 'nested': {'runtime': 'new', 'canary_for': 'candidate'}}):
            with self.subTest(models=models), self.assertRaises(ValueError):
                renderer.validate_canaries(models, runtimes)

    def test_model_disruption_budget_protects_all_revision_pods(self):
        model = json.loads((renderer.GPU / 'models.json').read_text())['glm-dealign']
        obj = renderer.disruption_budget('glm-dealign', model)
        self.assertEqual(obj['spec'], {'minAvailable': 8, 'selector': {
            'matchLabels': {'app.kubernetes.io/name': 'glm-dealign'}}})
        self.assertEqual(obj['metadata'], {'name': 'glm-dealign', 'namespace': 'gpu-inference'})
        generated = renderer.render()[renderer.MODELS / 'glm-dealign' / 'glm-dealign.yaml']
        self.assertEqual([doc for doc in generated if doc['kind'] == 'PodDisruptionBudget'], [obj])
        for invalid in (0, -1, True, 1.5, '8', '80%', None, 11):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, 'min_available'):
                renderer.disruption_budget('glm-dealign', {**model, 'min_available': invalid})

    def test_model_surge_limit_preserves_availability_and_qualification(self):
        runtimes = json.loads((renderer.ROOT / 'product/inference/gpu/runtimes.json').read_text())
        model = json.loads((renderer.GPU / 'models.json').read_text())['glm-dealign']
        default = renderer.rollout('glm-dealign', {k: v for k, v in model.items() if k != 'max_surge'}, runtimes)
        configured = renderer.rollout('glm-dealign', {**model, 'max_surge': 2}, runtimes)
        expected = default['spec']['strategy']['canary']
        self.assertEqual(expected['maxSurge'], 1)
        self.assertEqual(configured['spec']['strategy']['canary'], {**expected, 'maxSurge': 2})
        self.assertEqual(configured['spec']['template'], default['spec']['template'])
        for invalid in (0, -1, True, 1.5, '2', '20%', None):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, 'max_surge'):
                renderer.rollout('glm-dealign', {**model, 'max_surge': invalid}, runtimes)

    def test_packed_gpu_rollout_can_replace_one_replica_without_a_spare_gpu(self):
        runtimes = json.loads(renderer.RUNTIMES.read_text())
        model = json.loads((renderer.GPU / 'models.json').read_text())['glm-dealign']
        obj = renderer.rollout('glm-dealign', model, runtimes)
        self.assertEqual(obj['spec']['strategy']['canary']['maxUnavailable'], 1)
        resources = obj['spec']['template']['spec']['containers'][0]['resources']
        self.assertEqual(resources['requests']['memory'], '128Gi')
        self.assertEqual(resources['limits']['memory'], '224Gi')
        # Standard GLM plus two uncensored replicas fit the new four-GPU host.
        stock = json.loads((renderer.GPU / 'models.json').read_text())['glm']
        stock_runtime = runtimes[stock['runtime']]
        stock_memory = int(stock_runtime.get('request_memory', stock_runtime['memory'])[:-2])
        self.assertLessEqual(stock_memory + 2 * 128, 686)
        default = renderer.rollout('glm-dealign', {k: v for k, v in model.items()
                                                 if k != 'max_unavailable'}, runtimes)
        self.assertEqual(default['spec']['strategy']['canary']['maxUnavailable'], 0)
        for invalid in (-1, True, 1.5, '1', '10%', None, model['replicas']):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, 'max_unavailable'):
                renderer.rollout('glm-dealign', {**model, 'max_unavailable': invalid}, runtimes)

    def test_autoscaling_preserves_minimum_and_rejects_invalid_bounds(self):
        runtimes = json.loads((renderer.ROOT / 'product/inference/gpu/runtimes.json').read_text())
        models = json.loads((renderer.GPU / 'models.json').read_text())
        model = models['deepseek']
        obj = renderer.autoscaler('deepseek', model, runtimes[model['runtime']])
        self.assertEqual(obj['spec']['minReplicaCount'], model['replicas'])
        self.assertEqual(obj['spec']['maxReplicaCount'], model['autoscaling']['max_replicas'])
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

    def test_retired_model_can_pause_at_zero_without_losing_rollback_configuration(self):
        runtimes = json.loads(renderer.RUNTIMES.read_text())
        model = json.loads((renderer.GPU / 'models.json').read_text())['glm']
        model = {**model, 'autoscaling': {**model['autoscaling'], 'paused_replicas': 0}}
        obj = renderer.autoscaler('glm', model, runtimes[model['runtime']])
        self.assertEqual(obj['metadata']['annotations']['autoscaling.keda.sh/paused-replicas'], '0')
        self.assertEqual(obj['spec']['minReplicaCount'], model['replicas'])
        rollout = renderer.rollout('glm', model, runtimes)
        self.assertEqual(rollout['spec']['replicas'], 0)
        self.assertEqual(rollout['metadata']['annotations']['gradiated.com/paused-replicas'], '0')
        active = {**model, 'autoscaling': {key: value for key, value in model['autoscaling'].items()
                                        if key != 'paused_replicas'}}
        active_rollout = renderer.rollout('glm', active, runtimes)
        self.assertEqual(active_rollout['spec']['replicas'], model['replicas'])
        self.assertNotIn('annotations', active_rollout['metadata'])
        appset = yaml.safe_load(renderer.APPLICATIONS.read_text())
        expression = appset['spec']['template']['spec']['ignoreDifferences'][0]['jqPathExpressions'][0]
        for resource, expected in ((rollout, ''), (active_rollout, str(model['replicas']) + '\n')):
            selected = subprocess.check_output(['jq', '-r', expression], input=json.dumps(resource), text=True)
            self.assertEqual(selected, expected)
        for value in (-1, True, 0.5, model['autoscaling']['max_replicas'] + 1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                renderer.autoscaler('glm', {**model, 'autoscaling': {**model['autoscaling'], 'paused_replicas': value}}, runtimes[model['runtime']])

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
