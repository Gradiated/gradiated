#!/usr/bin/env python3
"""Create one private RunPod template from the repository catalog, without allocating GPUs."""
import argparse
import json
import os
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[2]


def query(document, variables=None):
    request = urllib.request.Request(
        'https://api.runpod.io/graphql',
        data=json.dumps({'query': document, 'variables': variables or {}}).encode(),
        headers={'Authorization': 'Bearer ' + os.environ['RUNPOD_API_KEY'],
                 'Content-Type': 'application/json', 'User-Agent': 'Gradiated-ops/1.0'})
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)
    if result.get('errors'):
        raise RuntimeError('RunPod rejected the template operation')
    return result['data']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    catalog = json.loads((ROOT / 'infra/environments/prod/runpod/templates.json').read_text())
    selected, = [item for item in catalog['models'] if item['name'] == args.name]
    payload = {
        'name': selected['name'], 'imageName': catalog['image'],
        'containerDiskInGb': selected['diskGb'], 'volumeInGb': 0,
        'dockerArgs': '', 'ports': '', 'isPublic': False, 'isServerless': False,
        'startSsh': False, 'startJupyter': False,
        'env': [{'key': key, 'value': value} for key, value in catalog['env'].items()],
        'allowedCudaVersions': catalog['allowedCudaVersions'],
        'readme': (f"Gradiated GPU host for {selected['model']}. Select {selected['gpuCount']}x "
                   f"{selected['gpu']}; at least 16 vCPUs and 224 GiB RAM per GPU. "
                   'No network volume or exposed ports. Refresh the single-use Tailscale '
                   'bootstrap secret immediately before creation. Kubernetes installs the model after enrollment.'),
    }
    existing = query('{ myself { podTemplates { id name imageName containerDiskInGb volumeInGb ports isPublic isServerless } } }')['myself']['podTemplates']
    matches = [item for item in existing if item['name'] == args.name and not item['isPublic']]
    if matches:
        current, = matches
        if any(current.get(key) != payload[key] for key in ['imageName', 'containerDiskInGb', 'volumeInGb', 'isServerless']):
            raise SystemExit('Existing template differs; create a new version instead of mutating it')
        print(json.dumps({'existing': True, 'id': current['id'], 'name': args.name}))
    elif args.apply:
        created = query('mutation($input: SaveTemplateInput!) { saveTemplate(input: $input) { id name imageName isPublic } }', {'input': payload})['saveTemplate']
        print(json.dumps(created))
    else:
        print(json.dumps({'apply': False, 'template': payload}))


if __name__ == '__main__':
    main()
