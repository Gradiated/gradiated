import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('migration', Path(__file__).with_name('migrate-control.py'))
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)

FIXTURE = r'''
import contextlib,http.client,json,os,pathlib,shutil,subprocess,sys,threading,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
class Api(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*args):pass
    def do_GET(self):
        if self.path=='/health/ready':data=b'ok'
        elif self.path.startswith('/api/internal/v1/runtime-bundles/'):
            data=json.dumps({'url':'http://127.0.0.1:4444/archive'}).encode()
        elif self.path=='/archive':
            data=b'x'*32;self.send_response(206);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return
        else:raise AssertionError(self.path)
        self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
server=ThreadingHTTPServer(('127.0.0.1',4444),Api)
threading.Thread(target=server.serve_forever,daemon=True).start()
root=Path('/var/lib/gradiated-kubelet');base=Path('/opt/gradiated/kubelet')
version=root/'host'/('a'*64)
for path in (version,base/'recovery',Path('/etc/gradiated'),Path('/opt/gradiated/bin'),Path('/opt/gradiated/tailscale')):path.mkdir(parents=True,exist_ok=True)
(version/'control-listener.py').write_text(Path('/tests/control-listener.py').read_text())
(version/'forward-control.py').write_text(Path('/tests/forward-control.py').read_text())
(root/'control-program').symlink_to(version/'forward-control.py')
(version/'.bundle-sha256').write_text('a'*64)
(root/'host/status.json').write_text(json.dumps({'current':'a'*64,'trial':False}))
(base/'supervise.py').write_text('def verified(*args):return True\n')
(base/'recovery/legacy').write_text('preserve this recovery fixture')
Path('/etc/gradiated/base-id').write_text('test-base')
Path('/etc/gradiated/kubelet.json').write_text(json.dumps({'instance_id':'test-instance'}))
Path('/etc/gradiated/tailscale-control.json').write_text(json.dumps({'api':'100.64.0.1'}))
installed=Path('/opt/gradiated/bin/forward-control')
installed.write_text((version/'control-listener.py').read_text()+'\n# legacy fixture\n')
os.chown(installed,10005,10005)
shutil.copy('/tests/run-control.sh','/opt/gradiated/bin/run-control')
client=Path('/opt/gradiated/tailscale/tailscale')
client.write_text("""#!/usr/local/bin/python3
import os,selectors,socket
remote=socket.create_connection(('127.0.0.1',4444))
selector=selectors.DefaultSelector();selector.register(0,selectors.EVENT_READ,remote);selector.register(remote,selectors.EVENT_READ,1)
while True:
 for key,_ in selector.select():
  data=os.read(key.fd,65536)
  if not data:raise SystemExit
  if key.data==1:os.write(1,data)
  else:key.data.sendall(data)
""")
client.chmod(0o755)
subprocess.Popen(['runuser','-u','tailscale','--','bash','/opt/gradiated/bin/run-control'])
deadline=time.monotonic()+10
while True:
    try:
        with contextlib.closing(http.client.HTTPConnection('127.0.0.1',3004,timeout=2)) as conn:
            conn.request('GET','/health/ready');response=conn.getresponse();assert response.status==200;response.read()
        break
    except OSError:
        if time.monotonic()>deadline:raise
        time.sleep(.1)
payload=json.dumps({'instance_id':'test-instance','sha256':'a'*64})
def migrate():
    result=subprocess.run([sys.executable,'-B','-c',Path('/tests/remote.py').read_text()],input=payload,text=True,capture_output=True,timeout=30)
    if result.returncode:raise RuntimeError(result.stderr)
    return json.loads(result.stdout)
(installed.parent/'.forward-control.new').write_text('interrupted write')
(base/'recovery.legacy').mkdir()
(base/'recovery.legacy/earlier').write_text('earlier recovery')
first=migrate()
assert first['dispatcher_updated'] and first['existing_connection_preserved'] and first['private_artifact_grant_verified']
assert (base/'recovery.legacy/earlier').read_text()=='earlier recovery'
assert any((path/'legacy').read_text()=='preserve this recovery fixture' for path in base.glob('recovery.legacy.*'))
assert (base/'recovery/control-listener.py').is_file()
second=migrate()
assert not second['dispatcher_updated']
print(json.dumps({'connection_preserving_migration':True,'recovery_installed':True,'repeat_is_idempotent':True}))
'''


class MigrationTests(unittest.TestCase):
    def test_dispatcher_handoff_preserves_live_http_and_installs_recovery(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.agents/runtime') as temporary:
            path = Path(temporary)
            for name in ('control-listener.py', 'forward-control.py', 'run-control.sh'):
                (path / name).write_text((ROOT / 'product/inference/tailscale' / name).read_text())
            (path / 'remote.py').write_text(migration.REMOTE)
            (path / 'fixture.py').write_text(FIXTURE)
            result = subprocess.run(['docker', 'run', '--rm', '--cpus=1', '--memory=512m',
                                     '-v', str(path) + ':/tests:ro', 'gradiated-tailscale-supervisor-test',
                                     'python3', '-B', '/tests/fixture.py'], capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(result.stdout)['connection_preserving_migration'])


if __name__ == '__main__':unittest.main()
