"""Stage, launch and recover one content-pinned DDR4 comparison via the existing KV260 console."""
import argparse
import base64
from datetime import datetime, timezone
import gzip
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import runpy
import shlex
import tarfile
import tempfile
import time
import uuid
import zlib

def sha(data):
    return sha256(data).hexdigest()

def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)

def packed_command(source, *args):
    compressed = base64.b64encode(zlib.compress(source.encode(), 9)).decode()
    return ['python3', '-I', '-B', '-c', f'import zlib,base64;exec(zlib.decompress(base64.b64decode({compressed!r})))', *args]

def write_json(path, data):
    with path.open('x') as stream:
        json.dump(data, stream, indent=2, sort_keys=True)
        stream.write('\n')

def prepare(stage, config, destination, uart, observer, reuse=None):
    require(not destination.exists(), 'Choose a fresh local evidence directory')
    cfg = json.loads(config.read_text())
    require(cfg['allow_module_load'] is True and cfg['pins'], 'Unexpected comparison configuration')
    require(cfg['boot'] == 'e09cc30e-0803-4dcc-ac24-60864ebd540e','Boot differs from admission')
    previous = json.loads(reuse.read_text()) if reuse else None
    retained = {}
    if previous:
        require(previous['boot'] == cfg['boot'] and re.fullmatch(
                '/var/tmp/gradiated-logits-ddr4-burst-[0-9TZ]+-[0-9a-f]{6}',previous['board']),
                'Reuse requires an authenticated directory on the same boot')
    archive = BytesIO()
    with tarfile.open(fileobj=archive, mode='w', format=tarfile.USTAR_FORMAT) as tar:
        members = [(name,stage/name,pin) for name,pin in cfg['pins'].items()]
        members.append(('configuration.json',config,None))
        for name,path,pin in sorted(members):
            require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]+',name) and not path.is_symlink(), 'Unexpected member')
            data=path.read_bytes()
            if pin:
                require(sha(data) == pin['sha256'] and len(data)==pin['bytes'],f'Packet pin differs for {name}')
            if previous and pin and previous['sources'].get(name)==pin:
                retained[name]=pin
                continue
            item=tarfile.TarInfo(name); item.mode=0o600; item.size=len(data)
            tar.addfile(item,BytesIO(data))
        if retained:
            data=json.dumps({'directory':previous['board'],'pins':retained},sort_keys=True).encode()
            item=tarfile.TarInfo('reuse.json');item.mode=0o600;item.size=len(data)
            tar.addfile(item,BytesIO(data))
    raw=archive.getvalue()
    # Compress before base64 encoding to keep the UART transfer small.
    inner=gzip.compress(raw,mtime=0)
    outer=gzip.compress(json.dumps({'packet.tar.gz':base64.b64encode(inner).decode()},separators=(',',':')).encode(),mtime=0)
    n = (len(base64.b64encode(outer))+639)//640
    require(len(outer)<=4900000 and n<=10209,'Packet exceeds paced transport budget')
    ts=datetime.now(timezone.utc)
    tag='KV_DDR16_'+uuid.uuid4().hex[:12]
    attempt=ts.strftime('logits-ddr4-burst-%Y%m%dT%H%M%SZ-')+tag[-6:]
    board='/var/tmp/gradiated-'+attempt
    pins=json.dumps({'packet.tar.gz':sha(inner)},separators=(',',':'))
    staging=' '+shlex.join(['sudo','-n','timeout','-k','2s','1500s',*packed_command(observer['paced_receiver'](uart['RECEIVER']),board,tag+'_STAGE',str(n),str(len(outer)),sha(outer),pins)])
    require(len(staging)<4094,'Receiver command too long')
    destination.mkdir(mode=0o700)
    (destination/'board-transfer.gz').write_bytes(outer)
    write_json(destination/'invocation.json',{'tag':tag,'attempt':attempt,'board':board,'boot':cfg['boot'],
               'staging':staging,'archive_sha256':sha(outer),'archive_bytes':len(outer),'chunks':n,
               'inner_sha256':sha(inner),'config_sha256':sha(config.read_bytes()),'created':ts.isoformat(),
               'sources':cfg['pins'],'reused_from':previous['board'] if retained else None,'reused_files':sorted(retained)})
    print(attempt,len(outer),n,flush=True)

UNPACK = """
import hashlib,json,os,re,sys,tarfile
from pathlib import Path as P
stage=P(sys.argv[1]); archive=stage/'packet.tar.gz'
assert os.geteuid()==0 and stage.stat().st_uid==0 and stage.stat().st_mode&0o077==0
assert hashlib.sha256(archive.read_bytes()).hexdigest()==sys.argv[2]
with tarfile.open(archive,'r:gz') as tar:
 members=tar.getmembers(); names=[m.name for m in members]
 assert len(names)==len(set(names)) and all(m.isfile() and m.size<16000000 and re.fullmatch('[a-zA-Z0-9][A-Za-z0-9_.-]+',m.name) for m in members)
 conf=tar.extractfile('configuration.json').read(); assert hashlib.sha256(conf).hexdigest()==sys.argv[3]
 pins=json.loads(conf)['pins']
 reuse=json.loads(tar.extractfile('reuse.json').read()) if 'reuse.json' in names else {'pins':{}}
 assert set(names)-{'reuse.json'}==set(pins)-set(reuse['pins'])|{'configuration.json'}
 if reuse['pins']:
  old=P(reuse['directory'])
  assert re.fullmatch('/var/tmp/gradiated-logits-ddr4-burst-[0-9TZ]+-[0-9a-f]{6}',str(old)) and old!=stage
  assert old.is_dir() and not old.is_symlink() and old.stat().st_uid==0 and old.stat().st_mode&0o077==0
  for n,pin in reuse['pins'].items():
   assert re.fullmatch('[a-zA-Z0-9][A-Za-z0-9_.-]+',n) and n in pins and pin==pins[n]
   source=old/n
   assert source.is_file() and not source.is_symlink() and source.stat().st_uid==0 and source.stat().st_size==pin['bytes']
   data=source.read_bytes()
   assert hashlib.sha256(data).hexdigest()==pin['sha256']
   with (stage/n).open('xb') as out:out.write(data)
 for m in members:
  data=tar.extractfile(m).read()
  if m.name in pins:assert hashlib.sha256(data).hexdigest()==pins[m.name]['sha256'] and len(data)==pins[m.name]['bytes']
  with (stage/m.name).open('xb') as out:out.write(data)
print('packet verified',flush=True)
"""

EXPORT = """
import base64,gzip,hashlib,io,os,sys,tarfile
from pathlib import Path as P
stage=P(sys.argv[1]);tag=sys.argv[2]; assert os.geteuid()==0 and stage.stat().st_uid==0 and stage.stat().st_mode&0o077==0
files=[p for p in (stage/'evidence').rglob('*') if p.is_file()]
files += [p for p in (stage/'supervisor.txt',) if p.is_file()]
assert 0<len(files)<=2048 and sum(p.stat().st_size for p in files)<90_000_000
buffer=io.BytesIO()
with tarfile.open(mode='w:gz',fileobj=buffer) as tar:
 for p in sorted(files):
  assert p.is_relative_to(stage) and not p.is_symlink()
  tar.add(p,arcname=str(p.relative_to(stage)),recursive=False)
data=buffer.getvalue(); print('',flush=True)
for i in range(0,len(data),288):print(tag,'ROW',i,base64.b64encode(data[i:i+288]).decode())
print(tag,'END',len(data),hashlib.sha256(data).hexdigest(),flush=True)
"""

def launch(destination, uart, observer, session, action):
    destination=destination.resolve(strict=True)
    pkt=json.loads((destination/'invocation.json').read_text())
    archive=(destination/'board-transfer.gz').read_bytes()
    require(sha(archive)==pkt['archive_sha256'],'Staged local archive changed')
    tag=pkt['tag']; board=pkt['board']
    require(re.fullmatch('/var/tmp/gradiated-logits-ddr4-burst-[0-9TZ]+-[0-9a-f]{6}',board),'Unexpected board evidence directory')
    serial_dir=Path(tempfile.mkdtemp(dir=destination,prefix=action+'-console-'))
    console=uart['Console'](serial_dir,tag,session)
    try:
        console.start()
        observer['check_boot'](console,tag,pkt['boot'])
        if action=='stage':
            observer['send_archive'](console,tag+'_STAGE',pkt,base64.b64encode(archive),time.monotonic())
            command=shlex.join(['sudo','-n',*packed_command(UNPACK,board,pkt['inner_sha256'],pkt['config_sha256'])])
            console.send(' '+command+" ; printf '\\n%s %s\\n' "+tag+'_UNPACK "$?"')
            mark=console.wait([tag+r'_UNPACK ([0-9]+)'],time.monotonic()+20)
            require(mark and mark[1]=='0','Unpack failed')
            write_json(destination/'staged.json',{'inner_sha256':pkt['inner_sha256'],'verified':True})
        if action=='run':
            require(json.loads((destination/'staged.json').read_text())['verified'],'Missing staging receipt')
            # Stage is root-private. Keep stdin free for the shell after the process ends.
            code="""import os,sys,subprocess
from pathlib import Path
p=Path(sys.argv[1]); assert p.stat().st_uid==0 and p.stat().st_mode&0o077==0
with (p/'supervisor.txt').open('xb',buffering=0) as log:
 with subprocess.Popen(['/usr/bin/python3','-E','-s','-B',str(p/'lifecycle.py'),str(p/'configuration.json'),str(p/'evidence')],cwd=p,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT) as child:
  for row in child.stdout:
   log.write(row)
   if row.endswith(b' passed\\n'):
    print(sys.argv[2],'PROGRESS',row.decode('ascii').strip(),flush=True)
  raise SystemExit(child.wait())"""
            cmd=shlex.join(['sudo','-n',*packed_command(code,board,tag)])
            write_json(destination/'dispatch.json',{'attempt':pkt['attempt'],'utc':datetime.now(timezone.utc).isoformat()})
            console.send(' '+cmd+" ; printf '\\n%s %s\\n' "+tag+'_RESULT "$?"')
            m=console.wait([tag+r'_RESULT ([0-9]+)'],time.monotonic()+2070)
            require(m,'Missing lifecycle exit receipt')
            write_json(destination/'exit.json',{'status':int(m[1])})
            print('Lifecycle exit',m[1],flush=True)
        if action=='collect':
            cmd=shlex.join(['sudo','-n',*packed_command(EXPORT,board,tag+'_EXPORT')])
            console.send(' '+cmd+" ; printf '\\n%s %s\\n' "+tag+'_EXPORT_EXIT "$?"')
            end=console.wait([tag+r'_EXPORT END ([0-9]+) ([0-9a-f]{64})',tag+r'_EXPORT_EXIT ([0-9]+)'],time.monotonic()+900)
            require(end and end.lastindex==2,'Missing board archive')
            data=bytearray()
            for line in console.lines:
                v=line.split()
                if v[:2]==[tag+'_EXPORT','ROW']:
                    require(int(v[2])==len(data),'Board evidence frame gap')
                    data.extend(base64.b64decode(v[3],validate=True))
            require(len(data)==int(end[1]) and sha(data)==end[2],'Evidence return digest differs')
            with (destination/'board-evidence.tar.gz').open('xb') as f:f.write(data)
            with tarfile.open(fileobj=BytesIO(data),mode='r:gz') as tar:
                for f in tar.getmembers():
                    path=Path(f.name)
                    require(f.isfile() and not path.is_absolute() and '..' not in path.parts and
                            (path.parts[0]=='evidence' or f.name=='supervisor.txt'),'Unsafe evidence file')
                    dest=destination/path;dest.parent.mkdir(parents=True,exist_ok=True)
                    with dest.open('xb') as out:out.write(tar.extractfile(f).read())
            write_json(destination/'recovered.json',{'bytes':len(data),'sha256':sha(data)})
            print('Recovered',len(data),'bytes',flush=True)
    finally:
        console.stop()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','stage','run','collect'])
    parser.add_argument('directory',type=Path); parser.add_argument('--input',type=Path)
    parser.add_argument('--reuse',type=Path); parser.add_argument('--config',type=Path); parser.add_argument('--prior',type=Path,required=True)
    parser.add_argument('--session',default='95921.gradiated-kv260')
    args=parser.parse_args(); uart=runpy.run_path(str(args.prior/'uart_transport.py')); obs=runpy.run_path(str(args.prior/'observer_host.py'))
    obs['send_archive'].__globals__['TRANSFER_SECONDS'] = 1500
    if args.action=='prepare':prepare(args.input,args.config,args.directory,uart,obs,args.reuse)
    else:launch(args.directory,uart,obs,args.session,args.action)
