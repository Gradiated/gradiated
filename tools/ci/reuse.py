"""Reuse a successful PR check round only for identical material inputs and scope."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def input_key(entries, plan):
    material = []
    for entry in entries.split(b'\0'):
        if not entry:
            continue
        path = entry.split(b'\t', 1)[1].decode()
        if path.startswith(('docs/', 'product/services/console/screenshots/', 'product/website/screenshots/')) or Path(path).name in ('README.md', 'AGENTS.md'):
            continue
        material.append(entry)
    scope = {key: value for key, value in plan.items() if key != 'format'}
    return hashlib.sha256(b'\0'.join(material) + json.dumps(scope, sort_keys=True).encode()).hexdigest()


def trusted_run(run, repository):
    return (run.get('status') == 'completed' and run.get('conclusion') == 'success'
            and run.get('event') == 'pull_request' and run.get('path') == '.github/workflows/tests.yml'
            and run.get('head_repository', {}).get('full_name') == repository)


def main():
    plan = json.loads(os.environ['PLAN'])
    key = input_key(subprocess.check_output(['git', 'ls-tree', '-r', '-z', 'HEAD']), plan)
    artifact = 'product-inputs-' + key
    reused = False
    repository = os.environ['GITHUB_REPOSITORY']
    def api(path):
        request = Request(f'https://api.github.com/repos/{repository}/{path}', headers={
            'Authorization': 'Bearer ' + os.environ['GITHUB_TOKEN'], 'Accept': 'application/vnd.github+json'})
        with urlopen(request, timeout=20) as response:
            return json.load(response)
    if os.environ.get('EVENT') == 'pull_request':
        try:
            candidates = api('actions/artifacts?' + urlencode({'name': artifact, 'per_page': 100}))['artifacts']
            for candidate in candidates:
                if candidate['name'] != artifact or candidate['expired']:
                    continue
                run = api(f"actions/runs/{candidate['workflow_run']['id']}")
                if trusted_run(run, repository):
                    reused = True
                    break
        except (OSError, ValueError, KeyError):
            print('Prior CI proof unavailable; running all selected checks.')
    destination = Path('.agents/runtime/product-ci-inputs.json')
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps({'key': key, 'scope': plan}))
    with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
        output.write(f'artifact={artifact}\nreused={str(reused).lower()}\n')
    print('Identical selected checks already passed.' if reused else 'Running selected checks.')


if __name__ == '__main__':
    main()
