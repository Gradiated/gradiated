#!/usr/bin/env python3
"""Resume normal draining for the two renamed GLM pods, without provider changes."""
import argparse
import json
from pathlib import Path
import urllib.request

HOSTS = {
    '01a0f19d-1ff3-7613-8cbf-81b693c0f0d4': 'ae016b3d-2ef4-4dac-b7be-b252601515cb',
    '01a0fbf7-5276-700b-903b-7e04da150ed6': 'c4530de2-509f-412e-88e5-9bb6d1799ba9',
}
LEGACY = 'dealignai/glm-5.3-flash-uncensored-nvfp4'
MODEL = 'dealignai/glm-5.3-flash-uncensored'
IMAGE = 'gradiated/glm-bundle@sha256:43cdd1187074c633a08bb41babd1298fe3bb85dd8850bb1964d89849a3b63919'
ROOT = Path('/var/lib/gradiated-kubelet')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    config = json.loads(Path('/etc/gradiated/kubelet.json').read_text())
    host = config['instance_id']
    if host not in HOSTS:
        raise SystemExit('This host is not authorized for this GLM drain recovery')
    uid = HOSTS[host]
    path = ROOT / 'pods' / uid / 'state.json'
    if not path.exists():
        print(json.dumps({'host': host, 'uid': uid, 'already_removed': True}))
        return
    state = json.loads(path.read_text())
    pod = state['pod']
    if (pod['metadata']['uid'] != uid or pod['spec']['nodeName'] != 'gpu-' + host
            or pod['metadata']['annotations'].get('gradiated.com/model-id') != LEGACY
            or pod['spec']['containers'][0]['image'] != IMAGE):
        raise SystemExit('Stored pod does not match the authorized legacy GLM allocation')
    replacements = [json.loads(p.read_text()) for p in (ROOT / 'pods').glob('*/state.json')]
    ready = any(not item.get('draining') and item.get('qualified_once')
                and item['pod']['metadata'].get('annotations', {}).get('gradiated.com/model-id') == MODEL
                for item in replacements)
    if not ready:
        raise SystemExit('No qualified replacement exists on this host')
    result = {'host': host, 'uid': uid, 'apply': args.apply,
              'already_draining': bool(state.get('draining'))}
    if args.apply:
        fence = json.loads((ROOT / 'fence.json').read_text())
        payload = {'operation': 'delete', 'uid': uid, 'epoch': fence['epoch'], 'term': fence['term']}
        token = Path(config['token_file']).read_text().strip()
        request = urllib.request.Request('http://127.0.0.1:8887/_kubelet',
                                         data=json.dumps(payload).encode(),
                                         headers={'Authorization': 'Bearer ' + token,
                                                  'Content-Type': 'application/json'})
        # UID-only deletion uses the existing owned allocation and preserves the agent's full drain.
        with urllib.request.urlopen(request, timeout=20) as response:
            result['deleted'] = bool(json.load(response)['deleted'])
    print(json.dumps(result))


if __name__ == '__main__':
    main()
