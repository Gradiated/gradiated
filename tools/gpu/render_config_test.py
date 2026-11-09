import copy
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

spec = importlib.util.spec_from_file_location('render_config', Path(__file__).with_name('render-config.py'))
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


class RenderTests(unittest.TestCase):
    def test_host_agent_accepts_every_catalogued_runtime_environment(self):
        root = renderer.ROOT / 'product/inference/gpu'
        with patch.object(sys, 'path', [str(root), *sys.path]):
            spec = importlib.util.spec_from_file_location('catalog_host_agent', root / 'host-agent.py')
            host_agent = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(host_agent)
        runtimes = json.loads((root / 'runtimes.json').read_text())
        for digest, profile in runtimes.items():
            with self.subTest(runtime=digest):
                pod = {'metadata': {'annotations': {}},
                       'spec': {'containers': [{'image': profile['image']}]}}
                selected, _ = host_agent.runtime_profile({'runtimes': runtimes}, pod)
                self.assertEqual(selected, digest)

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
        pools = sorted(name for model in json.loads((renderer.GPU / 'models.json').read_text()).values()
                       for name in model['pools'])
        self.assertEqual(models['spec']['generators'], [{'list': {'elements': [{'model': name} for name in pools]}}])
        # Deleting a model's application must not delete its serving Rollout.
        self.assertTrue(models['spec']['syncPolicy']['preserveResourcesOnDeletion'])
        template = models['spec']['template']['spec']
        self.assertEqual(template['source']['path'],
                         str(renderer.MODELS.relative_to(renderer.ROOT)) + '/{{ .model }}')
        self.assertIn('RespectIgnoreDifferences=true', template['syncPolicy']['syncOptions'])
        self.assertEqual(template['ignoreDifferences'][0]['jqPathExpressions'],
                         ['select(.metadata.annotations["gradiated.com/paused-replicas"] == null) | .spec.replicas'])
        self.assertEqual(template['ignoreDifferences'][0]['jsonPointers'], ['/spec/paused'])
        for name in pools:
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

    def test_host_reservation_taints_are_projected_only_when_declared(self):
        document = self.host()
        baseline, _ = renderer.inventory([document])
        self.assertNotIn('extra_taints', baseline[0])
        taint = {'key': 'gradiated.com/kimi-k31', 'value': 'reserved', 'effect': 'NoSchedule'}
        document['spec']['extraTaints'] = [taint]
        configured, _ = renderer.inventory([document])
        self.assertEqual(configured, [{**baseline[0], 'extra_taints': [taint]}])
        document['spec']['extraTaints'] = []
        self.assertEqual(renderer.inventory([document])[0], baseline)
        invalid = [None, {}, True, 'bad', [None], [{**taint, 'operator': 'Equal'}], [taint, taint],
                   [{**taint, 'key': 'gradiated.com/gpu'}], [{**taint, 'key': ''}],
                   [{**taint, 'key': 'node.kubernetes.io/not-ready'}],
                   [{**taint, 'key': 'node.cloudprovider.kubernetes.io/uninitialized'}],
                   [{**taint, 'effect': 'NoExecute'}], [{**taint, 'value': None}],
                   [{k: v for k, v in taint.items() if k != 'value'}],
                   [{**taint, 'key': 'a/b/c'}], [{**taint, 'key': 'x' * 64}],
                   [{**taint, 'value': 'bad value'}], [{**taint, 'value': 'x' * 64}],
                   [{**taint, 'key': f'example.com/reservation-{i}'} for i in range(17)]]
        for extra in invalid:
            with self.subTest(extra=extra), self.assertRaisesRegex(ValueError, 'extraTaints'):
                renderer.inventory([{**document, 'spec': {**document['spec'], 'extraTaints': extra}}])
        schema = self.definition['spec']['versions'][0]['schema']['openAPIV3Schema']['properties']['spec']['properties']['extraTaints']
        self.assertEqual(schema['x-kubernetes-list-type'], 'map')
        self.assertEqual(schema['maxItems'], 16)
        self.assertEqual(schema['x-kubernetes-list-map-keys'], ['key'])
        self.assertEqual(schema['items']['required'], ['key', 'value', 'effect'])
        self.assertEqual(schema['items']['properties']['effect']['enum'], ['NoSchedule'])

    def test_node_reservation_reconciliation_retains_named_controller_access(self):
        resources = list(yaml.safe_load_all((renderer.GPU / 'rbac.yaml').read_text()))
        role = next(d for d in resources if d['kind'] == 'ClusterRole' and d['metadata']['name'] == 'gpu-controller-nodes')
        updates = [rule for rule in role['rules'] if 'nodes' in rule['resources'] and 'update' in rule['verbs']]
        self.assertEqual(len(updates), 1)
        # Hosts being retired keep their node access until --retire drops it with their key.
        listed = {host['metadata']['name'] for host in self.hosts}
        credentials = list(yaml.safe_load_all((renderer.GPU / 'credentials.yaml').read_text()))
        retained = {'gpu-' + entry['secretKey'] for entry in credentials[1]['spec']['data']}
        self.assertLessEqual(listed, set(updates[0]['resourceNames']))
        self.assertLessEqual(set(updates[0]['resourceNames']) - listed, retained)
        policies = list(yaml.safe_load_all((renderer.GPU / 'gpu-fleet.yaml').read_text()))
        restricted = next(d for d in policies if d['kind'] == 'ValidatingAdmissionPolicy'
                          and d['metadata']['name'] == 'gpu-fleet-node-updates')
        self.assertEqual(restricted['spec']['matchConditions'], [{'name': 'gpu-fleet',
            'expression': "request.userInfo.username == 'system:serviceaccount:gpu-inference:gpu-fleet'"}])

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
            models.pop('jaredpalmer/kev-9b')
            (gpu / 'models.json').write_text(json.dumps(models))
            stock = models['z-ai/glm-5.3-flash']
            with patch.multiple(renderer, ROOT=root, KUBE=kube, GPU=gpu, MODELS=gpu / 'models'):
                self.assertEqual(renderer.retired_outputs(renderer.render()), {gpu / 'models/kev/kev.yaml'})
                with patch('sys.argv', ['render-config.py', '--check']), \
                        self.assertRaisesRegex(SystemExit, 'kubectl -n gpu-inference delete rollout,scaledobject kev'):
                    renderer.main()
                for invalid in ('../escape', 'a/b', 'Upper', 'x' * 54, ''):
                    renamed = {**stock, 'pools': {invalid: stock['pools']['glm']}}
                    (gpu / 'models.json').write_text(json.dumps({**models, 'z-ai/glm-5.3-flash': renamed}))
                    with self.assertRaisesRegex(ValueError, 'DNS label'):
                        renderer.render()
                # A pool is written to its own directory, so its name cannot
                # collide with a platform or fleet manifest.
                renamed = {**stock, 'pools': {'controller': stock['pools']['glm']}}
                (gpu / 'models.json').write_text(json.dumps({**models, 'z-ai/glm-5.3-flash': renamed}))
                outputs = renderer.render()
                self.assertIn(gpu / 'models/controller/controller.yaml', outputs)
                self.assertEqual(outputs[gpu / 'controller.yaml'][1]['kind'], 'Deployment')

    # Pools and scaling: models.json lists each public model's minimum slots and its pools.
    def fleet(self):
        models = json.loads((renderer.GPU / 'models.json').read_text())
        runtimes = json.loads(renderer.RUNTIMES.read_text())
        hosts, _ = renderer.inventory(self.hosts)
        return models, runtimes, hosts

    def synthetic(self, pools, min_slots=0, hosts=(), **runtimes):
        """Plan one test model from runtime slot counts named in the pools."""
        catalogue = {name: {'model_id': 'test/model', 'release': {}, 'image': 'test@sha256:' + name,
                            'cpu': '8', 'memory': '64Gi', 'gpus': 1, **runtime}
                     for name, runtime in runtimes.items()}
        return renderer.plan({'test/model': {'min_slots': min_slots, 'pools': pools}}, catalogue, list(hosts)), catalogue

    def test_current_fleet_floors_come_from_slots(self):
        models, runtimes, hosts = self.fleet()
        pools = renderer.plan(models, runtimes, hosts)
        floors = {name: (pool['floor'], pool['maximum'], pool['slots']) for name, pool in pools.items()}
        # Sixty uncensored slots fill the five B300 replicas of twelve slots;
        # the B200 and H200 pools are switched off.
        self.assertEqual(floors['glm-dealign-sglang'], (2, 5, 12))
        self.assertEqual(floors['glm-dealign-sglang-b200'][:2], (0, 0))
        self.assertEqual(floors['glm-dealign-sglang-h200'][:2], (0, 0))
        self.assertEqual(floors['kev'], (2, 2, 1))
        for name in ('glm', 'deepseek'):
            self.assertEqual(floors[name][:2], (0, 0))
        for model in ('dealignai/glm-5.3-flash-uncensored', 'jaredpalmer/kev-9b'):
            self.assertGreater(models[model]['min_slots'], 0)
        # Models never name hosts; reservations on hosts.yaml place pools instead.
        self.assertNotIn('instance-id', (renderer.GPU / 'models.json').read_text())
        self.assertNotIn('canary', (renderer.GPU / 'models.json').read_text())

    def test_the_floor_fills_pools_in_order_and_must_fit(self):
        pools, _ = self.synthetic({'large': {'runtime': 'twelve', 'max_replicas': 2},
                                   'off': {'runtime': 'three', 'max_replicas': 0},
                                   'small': {'runtime': 'three', 'max_replicas': 4}},
                                  min_slots=30, twelve={'active_requests': 12}, three={'active_requests': 3})
        self.assertEqual([(p['floor'], p['maximum']) for p in pools.values()], [(2, 2), (0, 0), (2, 4)])
        # A switched-off pool takes no place in the fill order.
        self.assertEqual(pools['small']['ahead'], [('large', 2, 12)])
        self.assertEqual(pools['large']['ahead'], [])
        # A floor rounds up to whole replicas.
        pools, _ = self.synthetic({'large': {'runtime': 'twelve', 'max_replicas': 3}}, min_slots=13,
                                  twelve={'active_requests': 12})
        self.assertEqual(pools['large']['floor'], 2)
        with self.assertRaisesRegex(ValueError, 'min_slots exceeds'):
            self.synthetic({'large': {'runtime': 'twelve', 'max_replicas': 2}}, min_slots=25, twelve={'active_requests': 12})
        for floor in (-1, 1.5, True, '2'):
            with self.subTest(floor=floor), self.assertRaisesRegex(ValueError, 'min_slots'):
                self.synthetic({'large': {'runtime': 'twelve', 'max_replicas': 2}}, min_slots=floor,
                               twelve={'active_requests': 12})

    def test_slots_come_from_the_enforced_runtime_limit(self):
        pools, _ = self.synthetic({'pool': {'runtime': 'free', 'slots': 4, 'max_replicas': 1}}, free={})
        self.assertEqual(pools['pool']['slots'], 4)
        for pool, runtime, message in [
                ({'runtime': 'free', 'max_replicas': 1}, {}, 'needs slots'),
                ({'runtime': 'free', 'slots': 0, 'max_replicas': 1}, {}, 'needs slots'),
                ({'runtime': 'free', 'slots': 1.5, 'max_replicas': 1}, {}, 'needs slots'),
                ({'runtime': 'free', 'slots': 4, 'max_replicas': 1}, {'active_requests': 12}, 'takes its slots')]:
            with self.subTest(pool=pool, runtime=runtime), self.assertRaisesRegex(ValueError, message):
                self.synthetic({'pool': pool}, free=runtime)

    def test_pool_fields_are_closed_so_models_cannot_pin_hosts(self):
        base = {'runtime': 'twelve', 'gpu': 'B300', 'max_replicas': 1, 'progress_deadline_seconds': 60}
        for field in ('affinity', 'node_selector', 'extra_tolerations', 'canary_for', 'serving_model_id',
                      'min_available', 'autoscaling', 'paused_replicas'):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'unknown fields'):
                self.synthetic({'pool': {**base, field: {}}}, twelve={'active_requests': 12})
        catalogue = {'twelve': {'model_id': 'test/model', 'active_requests': 12, 'release': {}}}
        for model in ({'pools': {'pool': base}}, {'min_slots': 0}, {'min_slots': 0, 'pools': {}},
                      {'min_slots': 0, 'pools': {'pool': base}, 'max_slots': 1}):
            with self.subTest(model=model), self.assertRaises(ValueError):
                renderer.plan({'test/model': model}, catalogue, [])
        two = {'test/model': {'min_slots': 0, 'pools': {'pool': base}},
               'test/other': {'min_slots': 0, 'pools': {'pool': base}}}
        with self.assertRaisesRegex(ValueError, 'two models'):
            renderer.plan(two, catalogue, [])

    def test_a_pool_cannot_serve_another_public_model_or_train(self):
        catalogue = {'other': {'model_id': 'test/other', 'active_requests': 1, 'release': {}},
                     'training': {'model_id': 'training', 'kind': 'training', 'release': {}}}
        models = {'test/other': {'min_slots': 0, 'pools': {'other': {'runtime': 'other', 'max_replicas': 0}}}}
        with self.assertRaisesRegex(ValueError, 'another public model'):
            renderer.plan({**models, 'test/model': {'min_slots': 0, 'pools': {
                'pool': {'runtime': 'other', 'max_replicas': 1}}}}, catalogue, [])
        with self.assertRaisesRegex(ValueError, 'training runtime'):
            renderer.plan({'test/model': {'min_slots': 0, 'pools': {
                'pool': {'runtime': 'training', 'max_replicas': 1}}}}, catalogue, [])

    def test_systemone_models_keep_capacity_because_openrouter_cannot_serve_them(self):
        pool = {'pool': {'runtime': 'kev', 'slots': 1, 'max_replicas': 1}}
        with self.assertRaisesRegex(ValueError, 'SystemOne'):
            self.synthetic(pool, kev={'release': {'protocol': 'system_one'}})
        self.synthetic(pool, min_slots=1, kev={'release': {'protocol': 'system_one'}})
        # A chat model may idle at zero: OpenRouter serves it meanwhile.
        self.synthetic(pool, kev={})

    def test_qualification_pool_is_fixed_isolated_and_uncounted(self):
        specs = {'serving': {'runtime': 'public', 'gpu': 'B300', 'max_replicas': 2, 'progress_deadline_seconds': 60},
                 'staged': {'runtime': 'private', 'gpu': 'H200', 'mode': 'qualification', 'replicas': 1,
                            'progress_deadline_seconds': 60}}
        pools, catalogue = self.synthetic(specs, min_slots=12, public={'active_requests': 12},
                                          private={'active_requests': 3, 'model_id': 'test/model-staged'})
        staged = pools['staged']
        self.assertEqual((staged['floor'], staged['maximum']), (1, 1))
        # Staged capacity takes no place in the fill order.
        self.assertEqual(pools['serving']['ahead'], [])
        with patch.object(renderer, 'glm_sglang_profiles', return_value={}):
            _, outputs = renderer.model_outputs({'test/model': {'min_slots': 12, 'pools': specs}}, catalogue, [])
        documents = {doc['kind']: doc for doc in outputs[renderer.MODELS / 'staged' / 'staged.yaml']}
        annotations = documents['Rollout']['spec']['template']['metadata']['annotations']
        # The worker routes a private identity only in production mode.
        self.assertEqual(annotations['gradiated.com/model-id'], 'test/model-staged')
        self.assertEqual(annotations['gradiated.com/serving-model-id'], 'test/model')
        self.assertEqual(annotations['gradiated.com/serving-mode'], 'qualification')
        # A fixed autoscaler lets the fleet operator surge it during a host re-image.
        scaled = documents['ScaledObject']['spec']
        self.assertEqual((scaled['minReplicaCount'], scaled['maxReplicaCount']), (1, 1))
        self.assertNotIn('PodDisruptionBudget', documents)
        rules = outputs[renderer.REPLICA_RULES][0]['spec']['groups'][0]['rules']
        staged_rules = [rule['expr'] for rule in rules if rule['labels']['rollout'] == 'staged']
        self.assertEqual(staged_rules, ['vector(0)', 'vector(0)'])
        serving = renderer.rollout('serving', pools['serving'], catalogue)['spec']['template']['metadata']['annotations']
        self.assertNotIn('gradiated.com/serving-mode', serving)
        for pool, message in [
                ({'runtime': 'public', 'mode': 'qualification', 'replicas': 1}, 'private runtime model ID'),
                ({'runtime': 'private', 'mode': 'qualification', 'max_replicas': 1}, 'fixed replicas'),
                ({'runtime': 'private', 'mode': 'qualification', 'replicas': 0}, 'fixed replicas'),
                ({'runtime': 'private', 'max_replicas': 1, 'replicas': 1}, 'min_slots sets its floor'),
                ({'runtime': 'private'}, 'min_slots sets its floor'),
                ({'runtime': 'private', 'mode': 'canary', 'max_replicas': 1}, 'mode must be')]:
            with self.subTest(pool=pool), self.assertRaisesRegex(ValueError, message):
                self.synthetic({'pool': pool}, public={'active_requests': 12},
                               private={'active_requests': 3, 'model_id': 'test/model-staged'})

    def test_a_reservation_admits_a_pool_to_its_hosts_and_keeps_it_there(self):
        reserved = self.host()
        reserved['spec']['extraTaints'] = [{'key': 'gradiated.com/reserved', 'value': 'kimi-k31', 'effect': 'NoSchedule'}]
        other = self.host('019d5a4a-0000-7000-8000-000000000002', 'newpod2')
        hosts, _ = renderer.inventory([reserved, other])
        pool = {'runtime': 'kimi', 'gpu': 'B300', 'gpu_count': 8, 'reservation': 'kimi-k31', 'max_replicas': 1,
                'progress_deadline_seconds': 60}
        pools, catalogue = self.synthetic({'kimi': pool}, hosts=hosts, kimi={'active_requests': 5})
        spec = renderer.rollout('kimi', pools['kimi'], catalogue)['spec']['template']['spec']
        self.assertEqual(spec['nodeSelector'], {'gradiated.com/provider': 'runpod', 'nvidia.com/gpu.product': 'B300',
                                                'nvidia.com/gpu.count': '8'})
        self.assertIn({'key': 'gradiated.com/reserved', 'operator': 'Equal', 'value': 'kimi-k31', 'effect': 'NoSchedule'},
                      spec['tolerations'])
        terms = spec['affinity']['nodeAffinity']['requiredDuringSchedulingIgnoredDuringExecution']['nodeSelectorTerms']
        self.assertEqual(terms, [{'matchExpressions': [{'key': 'gradiated.com/instance-id', 'operator': 'In',
                                                        'values': [reserved['spec']['instanceId']]}]}])
        with self.assertRaisesRegex(ValueError, 'reserved for'):
            self.synthetic({'kimi': {**pool, 'reservation': 'training'}}, hosts=hosts, kimi={'active_requests': 5})
        # An unreserved pool neither tolerates reservations nor names hosts.
        plain, _ = self.synthetic({'plain': {k: v for k, v in pool.items() if k != 'reservation'}}, hosts=hosts,
                                  kimi={'active_requests': 5})
        spec = renderer.rollout('plain', plain['plain'], catalogue)['spec']['template']['spec']
        self.assertEqual(spec['tolerations'], [{'key': 'gradiated.com/gpu', 'operator': 'Equal', 'value': 'true',
                                                'effect': 'NoSchedule'}])
        self.assertNotIn('affinity', spec)

    def test_hosts_reserve_training_and_kimi_capacity(self):
        hosts, _ = renderer.inventory(self.hosts)
        reserved = {}
        for host in hosts:
            for taint in host.get('extra_taints', []):
                reserved.setdefault((taint['key'], taint['value']), []).append(host['instance_id'])
        self.assertEqual(reserved, {
            ('gradiated.com/reserved', 'training'): ['01a0f19d-1ff3-7613-8cbf-81b693c0f0d4'],
            ('gradiated.com/reserved', 'kimi-k31'): ['01a0fbf7-5276-700b-903b-7e04da150ed6',
                                                     '01a0fbf8-06fc-7658-96e1-ae72f7dba135']})
        # Training Jobs tolerate their reservation.
        trainer = (renderer.ROOT / 'product/services/temporal-worker/src/training/kubernetes-host.ts').read_text()
        self.assertIn('key: "gradiated.com/reserved"', trainer)
        self.assertIn('value: "training"', trainer)

    def test_spread_places_replicas_on_separate_hosts(self):
        pools, catalogue = self.synthetic({'pool': {'runtime': 'r', 'gpu': 'B300', 'max_replicas': 2,
                                                    'progress_deadline_seconds': 60}}, r={'active_requests': 1})
        pool = pools['pool']
        term = {'topologyKey': 'kubernetes.io/hostname',
                'labelSelector': {'matchLabels': {'app.kubernetes.io/name': 'pool'}}}
        required = renderer.rollout('pool', {**pool, 'spread': 'required'}, catalogue)['spec']['template']['spec']
        self.assertEqual(required['affinity'], {'podAntiAffinity': {'requiredDuringSchedulingIgnoredDuringExecution': [term]}})
        preferred = renderer.rollout('pool', {**pool, 'spread': 'preferred'}, catalogue)['spec']['template']['spec']
        self.assertEqual(preferred['affinity'], {'podAntiAffinity': {'preferredDuringSchedulingIgnoredDuringExecution': [
            {'weight': 100, 'podAffinityTerm': term}]}})
        with self.assertRaisesRegex(ValueError, 'spread'):
            renderer.rollout('pool', {**pool, 'spread': 'always'}, catalogue)

    def test_rollout_uses_catalogue_resources_and_qualification(self):
        models, runtimes, hosts = self.fleet()
        for name, pool in renderer.plan(models, runtimes, hosts).items():
            document = renderer.rollout(name, pool, runtimes)
            runtime = runtimes[pool['runtime']]
            pod = document['spec']['template']
            self.assertEqual(pod['spec']['containers'][0]['image'], runtime['image'])
            self.assertEqual(json.loads(pod['metadata']['annotations']['gradiated.com/release']), runtime['release'])
            self.assertFalse(pod['spec']['automountServiceAccountToken'])
            self.assertEqual(document['spec']['replicas'], pool['floor'])
            self.assertEqual(document['spec']['strategy']['canary']['maxUnavailable'], pool.get('max_unavailable', 0))
            self.assertEqual(document['spec']['strategy']['canary']['steps'][1]['analysis']['templates'],
                             [{'templateName': 'sdk-qualification'}])
            self.assertNotIn('gradiated.com/canary-of', pod['metadata']['annotations'])

    def test_rollout_strategy_bounds(self):
        models, runtimes, hosts = self.fleet()
        pool = renderer.plan(models, runtimes, hosts)['glm-dealign-sglang-h200']
        default = renderer.rollout('glm-dealign-sglang-h200', {**pool, 'rolling_update': False}, runtimes)
        self.assertEqual(default['spec']['strategy']['canary']['steps'][0], {'setWeight': 50})
        rolling = renderer.rollout('glm-dealign-sglang-h200', pool, runtimes)['spec']['strategy']['canary']
        self.assertEqual(rolling['steps'], [{'setWeight': 100}, default['spec']['strategy']['canary']['steps'][1]])
        self.assertEqual((rolling['maxSurge'], rolling['maxUnavailable']), (0, 1))
        kev = renderer.plan(models, runtimes, hosts)['kev']
        self.assertEqual({k: v for k, v in renderer.rollout('kev', kev, runtimes)['spec']['strategy']['canary'].items()
                          if k != 'steps'}, {'maxSurge': 1, 'maxUnavailable': 0})
        for change, message in [({'rolling_update': 1}, 'rolling_update'), ({'max_surge': 0, 'max_unavailable': 0}, 'both zero'),
                                ({'max_surge': -1}, 'max_surge'), ({'max_unavailable': '1'}, 'max_unavailable'),
                                ({'progress_deadline_seconds': 0}, 'progress_deadline_seconds'),
                                ({'gpu': ''}, 'gpu'), ({'gpu_count': 0}, 'gpu_count'),
                                ({'labels': {'app.kubernetes.io/name': 'other'}}, 'identity label is reserved'),
                                ({'annotations': {'gradiated.com/serving-mode': 'production'}}, 'reserved')]:
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, message):
                renderer.rollout('kev', {**kev, **change}, runtimes)

    def test_glm_sglang_runtimes_declare_their_launcher_active_request_limit(self):
        models, runtimes, hosts = self.fleet()
        pools = renderer.plan(models, runtimes, hosts)
        profiles = renderer.glm_sglang_profiles()
        renderer.validate_active_requests(pools, runtimes, profiles)
        h200, b300 = pools['glm-dealign-sglang-h200']['runtime'], pools['glm-dealign-sglang']['runtime']
        self.assertEqual((runtimes[b300]['active_requests'], runtimes[h200]['active_requests']), (12, 3))
        for runtime, change, message in [
                (h200, 4, 'equal its launcher profile, 3'),
                (b300, 16, 'equal its launcher profile, 12'),
                (b300, None, 'equal its launcher profile, 12'),
                (b300, 0, 'integer from 1 to 4096'),
                (b300, '16', 'integer from 1 to 4096'),
                (b300, True, 'integer from 1 to 4096')]:
            changed = copy.deepcopy(runtimes)
            if change is None:
                del changed[runtime]['active_requests']
            else:
                changed[runtime]['active_requests'] = change
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, message):
                renderer.validate_active_requests(pools, changed, profiles)
        # Without an explicit profile, the GPU the pool runs on selects it.
        changed = copy.deepcopy(runtimes)
        del changed[h200]['environment']['GLM_SGLANG_PROFILE']
        renderer.validate_active_requests(pools, changed, profiles)
        placed = copy.deepcopy(pools)
        placed['glm-dealign-sglang-h200']['gpu'] = 'A100'
        with self.assertRaisesRegex(ValueError, 'no single GLM SGLang profile'):
            renderer.validate_active_requests(placed, changed, profiles)

    def test_b300_sglang_pool_keeps_its_compact_memory_request(self):
        models, runtimes, hosts = self.fleet()
        pool = renderer.plan(models, runtimes, hosts)['glm-dealign-sglang']
        compact = runtimes[pool['runtime']]
        container = renderer.rollout('glm-dealign-sglang', pool, runtimes)['spec']['template']['spec']['containers'][0]
        self.assertEqual(container['resources']['requests'], {'cpu': '32', 'memory': '256Gi', 'nvidia.com/gpu': '2'})
        self.assertEqual(container['resources']['limits']['memory'], '400Gi')
        # Two replicas fit one four-GPU B300 host (85 CPU, 686 GiB allocatable).
        self.assertLessEqual(2 * int(compact['cpu']), 85)
        self.assertLessEqual(2 * int(compact['request_memory'][:-2]), 686)

    def test_switched_off_pool_keeps_its_rollout_at_zero_without_an_autoscaler(self):
        models, runtimes, hosts = self.fleet()
        _, outputs = renderer.model_outputs(models, runtimes, hosts)
        documents = outputs[renderer.MODELS / 'glm-dealign-sglang-h200' / 'glm-dealign-sglang-h200.yaml']
        self.assertEqual([doc['kind'] for doc in documents], ['Rollout'])
        self.assertEqual(documents[0]['spec']['replicas'], 0)
        # Argo holds it at zero; restoring max_replicas hands replicas back to KEDA.
        self.assertEqual(documents[0]['metadata']['annotations'], {'gradiated.com/paused-replicas': '0'})
        serving = outputs[renderer.MODELS / 'glm-dealign-sglang' / 'glm-dealign-sglang.yaml']
        self.assertEqual([doc['kind'] for doc in serving], ['Rollout', 'PodDisruptionBudget', 'ScaledObject'])
        self.assertNotIn('annotations', serving[0]['metadata'])
        # A host drain takes a pool at most one replica below its floor.
        self.assertEqual(serving[1]['spec']['minAvailable'], 1)

    def test_every_pool_scales_on_utilization_and_refusals_in_its_own_slots(self):
        self.assertEqual((renderer.UTILIZATION, renderer.REFUSAL_SHARE), (0.7, 0.05))
        pools, catalogue = self.synthetic({'first': {'runtime': 'twelve', 'gpu': 'B300', 'max_replicas': 2,
                                                     'progress_deadline_seconds': 60},
                                           'second': {'runtime': 'three', 'gpu': 'H200', 'max_replicas': 4,
                                                      'progress_deadline_seconds': 60}},
                                          min_slots=0, twelve={'active_requests': 12}, three={'active_requests': 3})
        first, second = (renderer.scaling_queries(name, pools[name]) for name in ('first', 'second'))
        self.assertEqual(set(first), {'utilization', 'refusals'})
        model = 'model="test/model"'
        # One sample: the per-model rule's label must not survive beside the idle zero.
        self.assertIn(f'max(gradiated:model_busy_slots{{{model}}})', first['utilization'])
        self.assertTrue(first['utilization'].endswith('/ 0.7, 0)'))
        # The second pool supplies what the first cannot serve: its maximum while
        # it grows, its ready replicas once it requests its maximum.
        self.assertTrue(second['utilization'].endswith(
            '/ 0.7 - ((max(rollout_info_replicas_available{namespace="gpu-inference",name="first"}) * 12 and on() '
            '(max(rollout_info_replicas_desired{namespace="gpu-inference",name="first"}) >= 2)) or vector(24)), 0)'))
        self.assertIn(f'gradiated:model_capacity_refusal_ratio{{{model}}} > 0.05', first['refusals'])
        self.assertNotIn('name="first"} >=', first['refusals'])
        # One replica more than are ready, so capacity grows as replicas finish loading.
        ready = 'max(rollout_info_replicas_available{namespace="gpu-inference",name="first"})'
        self.assertIn(f'({ready} + 1 + floor({ready} / 10)) * 12', first['refusals'])
        self.assertIn('max(rollout_info_replicas_desired{namespace="gpu-inference",name="first"}) >= 2', second['refusals'])
        scaled = renderer.autoscaler('second', pools['second'])['spec']
        self.assertEqual((scaled['minReplicaCount'], scaled['maxReplicaCount'], scaled['cooldownPeriod']), (0, 4, 1800))
        self.assertEqual({t['metadata']['threshold'] for t in scaled['triggers']}, {'3'})
        for trigger in scaled['triggers']:
            self.assertTrue(trigger['metadata']['query'].endswith('> time() - 45))'))

    def test_replica_rules_follow_rollout_targets_and_floors(self):
        models, runtimes, hosts = self.fleet()
        pools = renderer.plan(models, runtimes, hosts)
        rules = renderer.replica_rules(pools)['spec']['groups'][0]['rules']
        by_rollout = {}
        for rule in rules:
            by_rollout.setdefault(rule['labels']['rollout'], {})[rule['record']] = rule['expr']
        self.assertEqual(set(by_rollout), set(pools))
        self.assertEqual(by_rollout['glm-dealign-sglang'], {
            'gradiated_model_desired_replicas':
                'max(rollout_info_replicas_desired{namespace="gpu-inference",name="glm-dealign-sglang"}) or vector(2)',
            # A one-at-a-time rollout of the five-replica floor keeps four serving.
            'gradiated_model_minimum_replicas': 'vector(1)'})
        self.assertEqual(by_rollout['kev']['gradiated_model_minimum_replicas'], 'vector(2)')
        # One replica of a single-replica floor must stay, even if a rollout may take it down.
        single = renderer.replica_rules({'pool': {**pools['glm-dealign-sglang'], 'floor': 1, 'max_unavailable': 1}})
        self.assertEqual(single['spec']['groups'][0]['rules'][1]['expr'], 'vector(1)')
        self.assertEqual(by_rollout['glm-dealign-sglang-h200'], {
            'gradiated_model_desired_replicas': 'vector(0)', 'gradiated_model_minimum_replicas': 'vector(0)'})
        rendered = yaml.safe_load(renderer.REPLICA_RULES.read_text().split('\n', 1)[1])
        self.assertEqual(rendered, renderer.replica_rules(pools))

    def test_rejects_invalid_pool_names(self):
        for name in ('model-', 'a' * 54, '../model', 'Model'):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'DNS label'):
                self.synthetic({name: {'runtime': 'r', 'max_replicas': 1}}, r={'active_requests': 1})

if __name__ == '__main__':
    unittest.main()
