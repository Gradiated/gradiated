#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = 'product/inference/host/gradiated_host'
FILES = ('enroll.py', 'enrollment-result.schema.json')

REMOTE = r'''import json,os,pathlib,re,subprocess,sys,tempfile
document=json.load(sys.stdin)
if os.geteuid()!=0:
    raise SystemExit('Run as root over Tailscale SSH')
config=pathlib.Path('/etc/gradiated/tailscale.json')
if not config.is_file() or json.loads(config.read_text()).get('pod')!=document['pod']:
    raise SystemExit('Bootstrap pod identity does not match')
if pathlib.Path('/etc/gradiated/kubelet.json').exists():
    raise SystemExit('Host is already enrolled; refusing to replace its enrollment code')
names=subprocess.check_output(['nvidia-smi','--query-gpu=name','--format=csv,noheader'],text=True,timeout=30).splitlines()
busy=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True,timeout=30).strip()
if len(names)!=2 or any(not re.search(r'\bH200\b',name) for name in names) or busy:
    raise SystemExit('Requires an idle pair of H200 GPUs')
root=pathlib.Path('/opt/gradiated/lib/gradiated_host')
for name,content in document['files'].items():
    if name not in ('enroll.py','enrollment-result.schema.json'):
        raise SystemExit('Unexpected enrollment file')
    if name.endswith('.py'):
        compile(content,name,'exec')
    else:
        json.loads(content)
    target=root/name
    if target.read_text()==content:
        continue
    backup=root/(name+'.before-h200')
    if not backup.exists():
        backup.write_bytes(target.read_bytes())
        backup.chmod(0o644)
    descriptor,temporary=tempfile.mkstemp(dir=root,prefix=name+'.')
    try:
        with os.fdopen(descriptor,'w') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary,0o644)
        os.replace(temporary,target)
    finally:
        pathlib.Path(temporary).unlink(missing_ok=True)
print(json.dumps({'pod':document['pod'],'source':document['source'],'enrollment_code_prepared':True}))
'''


def payload(pod, source):
    if not re.fullmatch('[a-z0-9]{1,40}', pod) or not re.fullmatch('[0-9a-f]{40}', source):
        raise ValueError('Use a RunPod ID and full merged source SHA')
    subprocess.run(['git', 'merge-base', '--is-ancestor', source, 'origin/main'], cwd=ROOT,
                   check=True, timeout=10, capture_output=True)
    files = {name: subprocess.check_output(['git', 'show', f'{source}:{PACKAGE}/{name}'],
                                          cwd=ROOT, text=True, timeout=10) for name in FILES}
    if 'H200' not in json.loads(files['enrollment-result.schema.json'])['properties']['gpu_product']['enum']:
        raise ValueError('Selected merged source does not support H200 enrollment')
    return {'pod': pod, 'source': source, 'files': files}


def main():
    parser = argparse.ArgumentParser(description='Prepare idle H200 bootstrap enrollment in place over admin Tailscale SSH.')
    parser.add_argument('--pod', required=True)
    parser.add_argument('--source', required=True, help='full merged commit SHA; fetch origin/main first')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    document = payload(args.pod, args.source)
    target = f'root@gpu-bootstrap-{args.pod}'
    if not args.apply:
        print(json.dumps({'target': target, 'source': args.source, 'files': list(FILES), 'apply': False}))
        return
    import shlex
    subprocess.run(['tailscale', 'ssh', target, 'python3 -c ' + shlex.quote(REMOTE)],
                   input=json.dumps(document), text=True, check=True, timeout=300)


if __name__ == '__main__':
    main()
