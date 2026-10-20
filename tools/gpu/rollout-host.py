#!/usr/bin/env python3
import argparse
import base64
import json
from pathlib import Path
import re
import shlex
import subprocess

import tailnet_ssh

ROOT = Path(__file__).resolve().parents[2]
REMOTE = '''
import json,pathlib,sys,time,urllib.request,importlib.util
payload=json.load(sys.stdin)
root=pathlib.Path('/var/lib/gradiated-kubelet')
config=json.loads(pathlib.Path('/etc/gradiated/kubelet.json').read_text())
if config['instance_id']!=payload['instance_id']:raise ValueError('Host identity mismatch')
payload['config']=config
payload['management_token']=pathlib.Path(config['token_file']).read_text()
def ping():
    request=urllib.request.Request('http://127.0.0.1:8887/_kubelet',data=b'{"operation":"ping"}',headers={'Authorization':'Bearer '+payload['management_token'],'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=5) as response:return json.load(response)
def agent_identity():
    matches=[]
    for path in pathlib.Path('/proc').glob('[0-9]*/cmdline'):
        try:
            arguments=[value for value in path.read_bytes().split(bytes([0])) if value]
            if arguments and arguments[-1].endswith(b'/host-agent.py'):
                state=(path.parent/'stat').read_text().rsplit(')',1)[1].split()
                if state[0]!='Z':matches.append({'pid':int(path.parent.name),'birth':state[19]})
        except (OSError,ValueError,IndexError):pass
    return matches[0] if len(matches)==1 else None
def snapshot():
    result={}
    for path in (root/'pods').glob('*/runtime.json'):
        state=json.loads(path.read_text())
        for key in ('runtime','task','reporter'):
            owner=state.get(key)
            if owner and owner.get('birth'):
                proc=pathlib.Path(f"/proc/{owner['pid']}/stat")
                if proc.exists() and proc.read_text().rsplit(')',1)[1].split()[19]==owner['birth']:
                    result[f'{path.parent.name}/{key}']=owner
    for path in (root/'pods').glob('*/state.json'):
        owner=json.loads(path.read_text()).get('task')
        if owner and owner.get('birth'):
            proc=pathlib.Path(f"/proc/{owner['pid']}/stat")
            if proc.exists() and proc.read_text().rsplit(')',1)[1].split()[19]==owner['birth']:
                result[f'{path.parent.name}/task']=owner
    proxy=root/'proxy/nginx.pid'
    if proxy.exists():
        pid=int(proxy.read_text())
        birth=pathlib.Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[19]
        result['proxy']={'pid':pid,'birth':birth}
    return result
before=snapshot()
before_agent=agent_identity()
if before_agent is None:raise RuntimeError('Cannot identify a single management agent before migration')
if ping()['instance_id']!=config['instance_id']:raise ValueError('Agent identity mismatch')
module={}
exec(compile(payload.pop('installer'),'install-host.py','exec'),module)
import contextlib,io
with contextlib.redirect_stdout(io.StringIO()):module['install'](payload)
deadline=time.monotonic()+120
while True:
    try:
        current_agent=agent_identity()
        result=ping()
        if result.get('host_launcher') and current_agent and current_agent!=before_agent and agent_identity()==current_agent:
            if snapshot()!=before:raise RuntimeError('Serving process identities changed')
            print(json.dumps({'instance_id':config['instance_id'],'host_launcher':True,'preserved_processes':len(before)}))
            break
    except OSError:pass
    if time.monotonic()>=deadline:raise TimeoutError('Host launcher did not become healthy')
    time.sleep(2)
'''


def rollout(targets, binary, base_id, run=subprocess.run, resolve=tailnet_ssh.resolve):
    if not re.fullmatch("[A-Za-z0-9._-]+", base_id):
        raise ValueError("An explicitly confirmed base ID is required")
    hosts = []
    for target in targets:
        if set(target) - {'instance_id', 'tailscale_ip'}:
            raise ValueError('Targets name an enrolled instance and, optionally, its Tailscale address')
        instance, address = resolve(target['instance_id'])
        if target.get('tailscale_ip') not in (None, address):
            raise ValueError('Target address differs from hosts.json')
        hosts.append((instance, address))
    for instance, address in hosts:
        payload = {'base_id': base_id, 'instance_id': instance, 'desmondd': base64.b64encode(binary).decode(),
                   'installer': (ROOT / 'tools/gpu/install-host.py').read_text()}
        for name in ('host_state.py', 'host_bundle.py', 'host-agent.py', 'supervise.py'):
            payload[name] = (ROOT / 'product/inference/gpu' / name).read_text()
        run(tailnet_ssh.command(address, 'python3 -c ' + shlex.quote(REMOTE)),
            input=json.dumps(payload), text=True, check=True, timeout=180)


def main():
    parser = argparse.ArgumentParser(description='Install the launcher and agent on enrolled hosts over Tailscale SSH, one host at a time.')
    parser.add_argument('--targets', type=Path, required=True, help='JSON list of {"instance_id": ...} entries from hosts.json')
    parser.add_argument('--desmondd', type=Path, required=True)
    parser.add_argument('--base-id', required=True, help='Confirmed compatibility ID of the retained hosts')
    args = parser.parse_args()
    rollout(json.loads(args.targets.read_text()), args.desmondd.read_bytes(), args.base_id)


if __name__ == '__main__':
    main()
