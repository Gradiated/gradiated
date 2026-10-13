#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[2]
path = root / 'infra/environments/prod/us-east-1/kubernetes/gpu-inference/controller.yaml'
source = path.read_text()
line = next(line for line in source.splitlines() if line.startswith('    {"namespace"'))
config = json.loads(line.strip())
config['runtimes'] = json.loads((root / 'product/inference/gpu/runtimes.json').read_text())
encoded = json.dumps(config, separators=(',', ':'))
updated = source.replace(line, '    ' + encoded)
updated = re.sub(r'(gradiated.com/host-inventory: )[0-9a-f]+', lambda match: match[1] + hashlib.sha256(encoded.encode()).hexdigest(), updated)
if '--check' in sys.argv:
    if updated != source:
        raise SystemExit('Runtime catalogue is stale; run python3 tools/gpu/render-runtimes.py')
else:
    path.write_text(updated)
