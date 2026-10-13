import importlib.util
import json
from pathlib import Path
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
        self.hosts = json.loads((renderer.GPU / 'hosts.json').read_text())

    def test_argo_only_reads_generated_manifests(self):
        app = yaml.safe_load((renderer.KUBE / 'platform/gpu-inference.yaml').read_text())
        self.assertEqual(app['spec']['source']['directory']['include'], '*.yaml')

    def test_new_host_projects_service_secret_and_private_endpoint(self):
        entry = {**self.hosts[0], 'instance_id': '019d5a4a-0000-7000-8000-000000000001',
                 'tailscale_ip': '100.64.0.1', 'management_secret': {'key': 'gradiated/prod/platform/gpu-host/test'}}
        hosts, services, secrets = renderer.inventory([entry])
        instance = entry['instance_id']
        self.assertEqual(services[instance]['metadata']['annotations']['tailscale.com/tailnet-ip'], '100.64.0.1')
        self.assertEqual(hosts[0]['token_file'], '/var/run/gradiated-host-keys/' + instance)
        self.assertEqual(hosts[0]['endpoint'], f'http://gpu-{instance}.tailscale-inference.svc.cluster.local:8888/_kubelet')
        self.assertEqual(secrets, [{'secretKey': instance, 'remoteRef': entry['management_secret']}])

    def test_rejects_duplicate_identity_or_address_and_public_address(self):
        for entries in ([self.hosts[0], self.hosts[0]],
                        [self.hosts[0], {**self.hosts[1], 'tailscale_ip': self.hosts[0]['tailscale_ip']}],
                        [{**self.hosts[0], 'tailscale_ip': '1.1.1.1'}], []):
            with self.assertRaises(ValueError):
                renderer.inventory(entries)

    def test_added_host_updates_all_enrollment_resources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            kube = root / renderer.KUBE.relative_to(renderer.ROOT)
            gpu = kube / 'gpu-inference'
            shutil.copytree(renderer.GPU, gpu)
            runtime_path = root / 'product/inference/gpu/runtimes.json'
            runtime_path.parent.mkdir(parents=True)
            shutil.copyfile(renderer.ROOT / 'product/inference/gpu/runtimes.json', runtime_path)
            entry = {**self.hosts[0], 'instance_id': '019d5a4a-0000-7000-8000-000000000001',
                     'tailscale_ip': '100.64.0.1',
                     'management_secret': {'key': 'gradiated/prod/platform/gpu-host/test'}}
            (gpu / 'hosts.json').write_text(json.dumps([*self.hosts, entry]))
            with patch.multiple(renderer, ROOT=root, KUBE=kube, GPU=gpu):
                outputs = renderer.render()
            instance = entry['instance_id']
            self.assertIn(kube / 'tailscale-inference/hosts' / f'{instance}.yaml', outputs)
            controller = outputs[gpu / 'controller.yaml']
            self.assertEqual(json.loads(controller[0]['data']['hosts.json'])['hosts'][-1]['instance_id'], instance)
            for resource in outputs[gpu / 'rbac.yaml']:
                if resource['metadata']['name'] in ('gpu-controller-nodes', 'gpu-controller-leases'):
                    for rule in resource.get('rules', []):
                        if 'resourceNames' in rule:
                            self.assertIn('gpu-' + instance, rule['resourceNames'])
            self.assertEqual(outputs[gpu / 'credentials.yaml'][1]['spec']['data'][-1],
                             {'secretKey': instance, 'remoteRef': entry['management_secret']})
            models = json.loads((gpu / 'models.json').read_text())
            models.pop('kev')
            (gpu / 'models.json').write_text(json.dumps(models))
            with patch.multiple(renderer, ROOT=root, KUBE=kube, GPU=gpu):
                self.assertEqual(renderer.retired_outputs(renderer.render()), {gpu / 'kev.yaml'})

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
