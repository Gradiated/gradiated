#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
import re
import shlex
import subprocess

REMOTE = r'''
import contextlib,http.client,importlib.util,json,os,pathlib,pwd,shutil,signal,sys,tempfile,time,urllib.request
sys.dont_write_bytecode=True
from pathlib import Path
payload=json.load(sys.stdin)
root=Path('/var/lib/gradiated-kubelet')
base=Path('/opt/gradiated/kubelet')
config=json.loads(Path('/etc/gradiated/kubelet.json').read_text())
if config['instance_id']!=payload['instance_id']:raise ValueError('Host identity mismatch')
state=json.loads((root/'host/status.json').read_text())
digest=payload['sha256']
if state.get('current')!=digest or state.get('trial'):raise ValueError('A healthy active host version is required')
spec=importlib.util.spec_from_file_location('launcher',base/'supervise.py')
launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)
if not launcher.verified(root/'host',digest,Path('/etc/gradiated/base-id').read_text().strip()):raise ValueError('Active host bundle verification failed')
version=root/'host'/digest
listener=version/'control-listener.py'
program=version/'forward-control.py'
if (root/'control-program').resolve(strict=True)!=program:raise ValueError('Active control helper is not selected')
account=pwd.getpwnam('tailscale')
installed=Path('/opt/gradiated/bin/forward-control')
def identity(pid):
    try:
        values=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
        return values[19] if values[0]!='Z' else None
    except OSError:return None
def listeners():
    result=[]
    for path in Path('/proc').glob('[0-9]*/cmdline'):
        try:
            args=[value for value in path.read_bytes().split(bytes([0])) if value]
            if (len(args)==2 and args[-1]==bytes(str(installed),'utf8') and
                    path.parent.stat().st_uid==account.pw_uid):
                pid=int(path.parent.name);birth=identity(pid)
                if birth:result.append((pid,birth))
        except OSError:pass
    return result
def replace(data):
    fd,name=tempfile.mkstemp(prefix='.forward-control-',dir=installed.parent)
    temporary=Path(name)
    try:
        with os.fdopen(fd,'wb') as output:
            os.fchown(output.fileno(),account.pw_uid,account.pw_gid)
            output.write(data);output.flush();os.fsync(output.fileno())
        temporary.replace(installed)
    finally:temporary.unlink(missing_ok=True)
def probe(connection):
    connection.request('GET','/health/ready')
    response=connection.getresponse();response.read()
    if response.status!=200 or connection.sock is None:raise ValueError('Private control readiness failed')
changed=installed.read_bytes()!=listener.read_bytes()
connection=http.client.HTTPConnection('127.0.0.1',3004,timeout=10)
probe(connection)
original_socket=connection.sock
try:
    if changed:
        old=installed.read_bytes()
        matches=listeners()
        if len(matches)!=1:raise ValueError('Cannot identify a single control listener')
        pid,birth=matches[0]
        replace(listener.read_bytes())
        try:
            if identity(pid)!=birth:raise ValueError('Control listener identity changed')
            # Killing only the acceptor leaves its nc children and their sockets alive.
            os.kill(pid,signal.SIGKILL)
            deadline=time.monotonic()+10
            while True:
                current=listeners()
                if len(current)==1 and current[0]!=(pid,birth):
                    try:
                        with contextlib.closing(http.client.HTTPConnection('127.0.0.1',3004,timeout=2)) as fresh:probe(fresh)
                        break
                    except OSError:pass
                if time.monotonic()>deadline:raise TimeoutError('Control dispatcher did not restart')
                time.sleep(.1)
            probe(connection)
            if connection.sock is not original_socket:raise ValueError('Existing control connection was replaced')
            with contextlib.closing(http.client.HTTPConnection('127.0.0.1',3004,timeout=10)) as fresh:probe(fresh)
        except Exception:
            replace(old)
            for current,birth in listeners():
                if identity(current)==birth:os.kill(current,signal.SIGKILL)
            raise
finally:connection.close()
recovery=base/'recovery'
if not (recovery/'control-listener.py').exists():
    with tempfile.TemporaryDirectory(prefix='.seed-',dir=base) as temporary:
        staging=Path(temporary)/'recovery'
        shutil.copytree(version,staging)
        (staging/'.bundle-sha256').unlink()
        for path in staging.iterdir():
            fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
            try:os.fsync(fd)
            finally:os.close(fd)
        if recovery.exists():
            import ctypes
            libc=ctypes.CDLL(None,use_errno=True)
            # Linux rename exchange keeps a recovery directory present throughout.
            if libc.renameat2(-100,os.fsencode(staging),-100,os.fsencode(recovery),2)!=0:
                error=ctypes.get_errno()
                raise OSError(error,os.strerror(error))
            staging.rename(base/f'recovery.legacy.{time.time_ns()}')
        else:staging.rename(recovery)
        fd=os.open(base,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
# Exercise short-lived artifact grants through the new helper without printing them.
url='http://127.0.0.1:3004/api/internal/v1/runtime-bundles/'+digest
with urllib.request.urlopen(url,timeout=10) as response:grant=json.load(response)
request=urllib.request.Request(grant['url'],headers={'Range':'bytes=0-31'})
with urllib.request.urlopen(request,timeout=20) as response:
    if response.status!=206 or len(response.read(33))!=32:raise ValueError('Private artifact grant verification failed')
print(json.dumps({'instance_id':config['instance_id'],'sha256':digest,'dispatcher_updated':changed,
                  'existing_connection_preserved':True,'new_connections_healthy':True,
                  'private_artifact_grant_verified':True,'recovery_seed_installed':True}))
'''


def main():
    parser = argparse.ArgumentParser(description='Migrate an enrolled host to bundle-owned forwarding without replacing GPU capacity.')
    parser.add_argument('targets', type=Path)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--identity-file', type=Path, required=True)
    parser.add_argument('--known-hosts', type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch('[0-9a-f]{64}', args.sha256):raise ValueError('A verified host digest is required')
    targets=json.loads(args.targets.read_text())
    if any(target['ssh'].endswith('@ssh.runpod.io') for target in targets):
        raise ValueError('This migration requires direct SSH; interactive RunPod gateways are not supported')
    for target in targets:
        if not re.fullmatch(r'(?:[a-z0-9_][a-z0-9_-]*@)?[a-zA-Z0-9][a-zA-Z0-9.-]*', target['ssh']):raise ValueError('Explicit SSH targets are required')
        command = ['ssh', '-i', str(args.identity_file), '-o', 'UserKnownHostsFile=' + str(args.known_hosts),
                   '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=10',
                   '-p', str(int(target.get('port', 22))), target['ssh'], 'python3 -B -c ' + shlex.quote(REMOTE)]
        subprocess.run(command, input=json.dumps({'instance_id': target['instance_id'], 'sha256': args.sha256}),
                       text=True, check=True, timeout=90)


if __name__ == '__main__':main()
