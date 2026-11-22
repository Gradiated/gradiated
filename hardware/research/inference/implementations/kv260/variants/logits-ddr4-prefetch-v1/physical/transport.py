"""Stage, launch and recover one content-pinned DDR4 comparison via the existing KV260 console."""
import argparse
import base64
from datetime import datetime, timezone
import gzip
from hashlib import sha256
from io import BytesIO
import json
import os
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
    with tempfile.NamedTemporaryFile(dir=path.parent, mode="w") as stream:
        json.dump(data, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.link(stream.name, path)

def prepare(stage, config, destination, reuse=None):
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
    tag='KV_DDR17_'+uuid.uuid4().hex[:12]
    attempt=ts.strftime('logits-ddr4-prefetch-%Y%m%dT%H%M%SZ-')+tag[-6:]
    board='/var/tmp/gradiated-'+attempt
    destination.mkdir(mode=0o700)
    (destination/'board-transfer.gz').write_bytes(outer)
    write_json(destination/'invocation.json',{'tag':tag,'attempt':attempt,'board':board,'boot':cfg['boot'],
               'archive_sha256':sha(outer),'archive_bytes':len(outer),'chunks':n,
               'inner_sha256':sha(inner),'config_sha256':sha(config.read_bytes()),'created':ts.isoformat(),
               'sources':cfg['pins'],'qualification':cfg['qualification'],'reused_from':previous['board'] if retained else None,'reused_files':sorted(retained)})
    print(attempt,len(outer),n,flush=True)

UNPACK = """
import hashlib,json,os,re,sys,tarfile,tempfile
from pathlib import Path as P
stage=P(sys.argv[1]); archive=stage/'packet.tar.gz'
assert os.geteuid()==0 and stage.stat().st_uid==0 and stage.stat().st_mode&0o077==0
assert hashlib.sha256(archive.read_bytes()).hexdigest()==sys.argv[2]
def save(path,data):
 if path.exists():
  assert path.is_file() and not path.is_symlink() and path.stat().st_uid==0 and path.read_bytes()==data
 else:
  with tempfile.NamedTemporaryFile(dir=stage,delete=False) as out: out.write(data)
  os.replace(out.name,path)
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
   save(stage/n,data)
 for m in members:
  data=tar.extractfile(m).read()
  if m.name in pins:assert hashlib.sha256(data).hexdigest()==pins[m.name]['sha256'] and len(data)==pins[m.name]['bytes']
  save(stage/m.name,data)
print('packet verified',flush=True)
"""

BOARD_PATH = r"/var/tmp/gradiated-logits-ddr4-prefetch-[0-9TZ]+-[0-9a-f]{6}"
PART_BYTES = 156_000

START = """
import hashlib,json,os,subprocess,sys
from pathlib import Path as P
stage=P(sys.argv[1]); check=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert os.geteuid()==0 and stage.stat().st_uid==0 and stage.stat().st_mode&0o077==0 and not stage.is_symlink()
config,source=stage/'configuration.json',stage/'lifecycle.py'
for p,expected in ((config,sys.argv[2]),(source,sys.argv[3])):
 assert p.is_file() and not p.is_symlink() and p.stat().st_uid==0 and check(p)==expected
pins=json.loads(config.read_bytes())['pins']
for name,pin in pins.items():
 p=stage/name
 assert p.parent==stage and p.is_file() and not p.is_symlink() and p.stat().st_uid==0
 assert p.stat().st_size==pin['bytes'] and check(p)==pin['sha256']
assert not (stage/'evidence').exists()
with (stage/'supervisor.txt').open('xb',buffering=0) as log:
 p=subprocess.Popen(['/usr/bin/python3','-E','-s','-B',str(source),str(config),str(stage/'evidence')],
     cwd=stage,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 with (stage/'supervisor-pid.json').open('x') as f:json.dump({'pid':p.pid},f)
print('',flush=True)
print(sys.argv[4],'PID',p.pid,flush=True)
"""

STATUS = """
import base64,hashlib,json,os,sys
from pathlib import Path as P
p=P(sys.argv[1]); assert os.geteuid()==0 and p.stat().st_uid==0 and p.stat().st_mode&0o077==0 and not p.is_symlink()
status=p/'supervisor-pid.json'
proc=json.loads(status.read_text())['pid'] if status.exists() else None
try:
 active=bool(proc and str(p/'lifecycle.py').encode() in (P('/proc')/str(proc)/'cmdline').read_bytes())
except FileNotFoundError:
 active=False
log=p/'supervisor.txt'; lines=log.read_text(errors='replace').splitlines() if log.exists() else []
result=p/'evidence/outcome.json'
try: result_value=json.loads(result.read_text()) if result.exists() else None
except json.JSONDecodeError:
 assert active
 result_value=None
data=json.dumps({'pid':proc,'running':active,'last_passed':next((v for v in reversed(lines) if v.endswith(' passed')),None),
 'outcome':result_value,'log_tail':lines[-2:] if not active else []},sort_keys=True,separators=(',',':')).encode()
print('',flush=True)
print(sys.argv[2],'STATUS',base64.b64encode(data).decode(),hashlib.sha256(data).hexdigest(),flush=True)
"""

ARCHIVE = """
import hashlib,os,sys,tarfile,tempfile
from pathlib import Path as P
p=P(sys.argv[1]); tag=sys.argv[2]
assert os.geteuid()==0 and p.stat().st_uid==0 and p.stat().st_mode&0o077==0 and not p.is_symlink()
dest=p/'board-evidence.tar.gz'
if not dest.exists():
 files=sorted(f for f in (p/'evidence').rglob('*') if f.is_file())+[p/'supervisor.txt',p/'supervisor-pid.json']
 assert 0<len(files)<=2048 and sum(f.stat().st_size for f in files)<90_000_000
 with tempfile.NamedTemporaryFile(dir=p,delete=False) as stream:
  with tarfile.open(fileobj=stream,mode='w:gz') as bundle:
   for f in files:
    assert f.is_file() and not f.is_symlink() and f.is_relative_to(p)
    bundle.add(f,arcname=str(f.relative_to(p)),recursive=False)
 os.replace(stream.name,dest)
assert dest.is_file() and not dest.is_symlink() and dest.stat().st_uid==0
data=dest.read_bytes()
print('',flush=True)
print(tag,'ARCHIVE',len(data),hashlib.sha256(data).hexdigest(),flush=True)
"""

SLICE = """
import base64,hashlib,os,sys
from pathlib import Path as P
p=P(sys.argv[1]); tag=sys.argv[2]; off,size=map(int,sys.argv[3:])
assert os.geteuid()==0 and p.stat().st_uid==0 and p.stat().st_mode&0o077==0 and not p.is_symlink()
with (p/'board-evidence.tar.gz').open('rb') as stream:
 stream.seek(off)
 data=stream.read(size)
assert len(data)==size
print('',flush=True)
for i in range(0,len(data),288):print(tag,'ROW',off+i,base64.b64encode(data[i:i+288]).decode())
print(tag,'END',off,len(data),hashlib.sha256(data).hexdigest(),flush=True)
"""


def packet(directory):
    invocation = json.loads((directory / "invocation.json").read_text())
    require(re.fullmatch(BOARD_PATH, invocation["board"]), "Unexpected board directory")
    return invocation


def remote(console, code, prefix, board, *args):
    shell = shlex.join(["sudo", "-n", *packed_command(code, board, *args)])
    console.send(" " + shell + " ; printf '\\n%s %s\\n' " + prefix + '_EXIT "$?"')


def read_status(console, invocation):
    tag = invocation["tag"] + "_BOARD"
    remote(console, STATUS, tag, invocation["board"], tag)
    response = console.wait([tag + r" STATUS ([0-9A-Za-z+/=]+) ([0-9a-f]{64})"], time.monotonic() + 15)
    require(response, "Missing board status")
    payload = base64.b64decode(response[1], validate=True)
    require(sha(payload) == response[2], "Board status digest differs")
    return json.loads(payload)


def dispatch(directory, console, invocation):
    staged = json.loads((directory / "staged.json").read_text())
    require(staged["verified"] is True and staged["inner_sha256"] == invocation["inner_sha256"],
            "Missing matching staging receipt")
    state = read_status(console, invocation)
    require(state["pid"] is None and state["outcome"] is None, "Board lifecycle was already launched")
    tag = invocation["tag"]
    attempt = {"attempt": invocation["attempt"], "utc": datetime.now(timezone.utc).isoformat(),
               "configuration_sha256": invocation["config_sha256"]}
    write_json(directory / "dispatch.json", attempt)
    remote(console, START, tag, invocation["board"], invocation["config_sha256"],
           invocation["sources"]["lifecycle.py"]["sha256"], tag)
    response = console.wait([tag + r" PID ([0-9]+)", tag + r"_EXIT ([0-9]+)"], time.monotonic() + 18)
    if response and " PID " in response[0]:
        print("Board lifecycle started", response[1], flush=True)
    else:
        state = read_status(console, invocation)
        require(state["pid"] is not None, "Board lifecycle launch is unverified")
        print("Board lifecycle launch recovered", state["pid"], flush=True)


def recover(directory, console, invocation):
    state = read_status(console, invocation)
    require(state["outcome"] is not None and not state["running"], "No sealed completed outcome")
    tag = invocation["tag"] + "_COLLECT"
    board = invocation["board"]
    remote(console, ARCHIVE, tag, board, tag)
    reply = console.wait([tag + r" ARCHIVE ([0-9]+) ([0-9a-f]{64})"], time.monotonic() + 30)
    require(reply, "Evidence archive receipt missing")
    total, expected = int(reply[1]), reply[2]
    require(0 < total < 90_000_000, "Evidence archive size outside the agreed limit")
    parts = directory / "recovery-parts"
    parts.mkdir(mode=0o700, exist_ok=True)
    archive = bytearray()
    for off in range(0, total, PART_BYTES):
        path = parts / f"{expected}-{off:09}.slice"
        size = min(PART_BYTES, total - off)
        receipt_path = path.with_suffix(".json")
        if path.exists() and receipt_path.exists():
            data = path.read_bytes()
            receipt = json.loads(receipt_path.read_text())
            require(len(data) == size and receipt == {"bytes": size, "sha256": sha(data)},
                    "Previously recovered slice differs")
        else:
            alias = f"{tag}_{off:09}_{uuid.uuid4().hex[:6]}"
            begin = len(console.lines)
            remote(console, SLICE, alias, board, alias, str(off), str(size))
            reply = console.wait([alias + r" END ([0-9]+) ([0-9]+) ([0-9a-f]{64})"],
                                 time.monotonic() + 100)
            require(reply and (int(reply[1]), int(reply[2])) == (off, size), "Missing evidence slice")
            data = bytearray()
            for line in console.lines[begin:]:
                columns = line.split()
                if columns[:2] == [alias, "ROW"]:
                    require(len(columns) == 4 and int(columns[2]) == off + len(data), "Evidence frame gap")
                    data.extend(base64.b64decode(columns[3], validate=True))
            require(len(data) == size and sha(data) == reply[3], "Evidence slice checksum differs")
            preserve_bytes(path, data)
            receipt_bytes = (json.dumps({"bytes": size, "sha256": reply[3]}, sort_keys=True) + "\n").encode()
            preserve_bytes(receipt_path, receipt_bytes)
            print(f"Recovered {off + size:,} / {total:,} evidence bytes", flush=True)
        archive.extend(data)
    require(len(archive) == total and sha(archive) == expected, "Combined evidence archive checksum differs")
    preserve_bytes(directory / "board-evidence.tar.gz", archive)
    seen = set()
    with tarfile.open(fileobj=BytesIO(archive), mode="r:gz") as tar:
        for member in tar:
            path = Path(member.name)
            require(member.isfile() and path not in seen and not path.is_absolute() and ".." not in path.parts
                    and (path.parts[0] == "evidence" or member.name in ("supervisor.txt", "supervisor-pid.json")),
                    f"Unsafe evidence member: {path}")
            seen.add(path)
            destination = directory / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            preserve_bytes(destination, tar.extractfile(member).read())
    require(json.loads((directory / "evidence/outcome.json").read_text()) == state["outcome"],
            "Archived outcome differs from authenticated live receipt")
    record = directory / "recovered.json"
    receipt = {"bytes": total, "sha256": expected}
    if record.exists():
        require(json.loads(record.read_text()) == receipt, "Final archive receipt differs")
    else:
        write_json(record, receipt)


def preserve_bytes(path, data):
    if path.exists():
        require(path.is_file() and not path.is_symlink() and path.read_bytes() == data,
                f"Previously preserved file differs: {path}")
    else:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            stream.write(data)
        os.replace(stream.name, path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run", "status", "collect"))
    parser.add_argument("directory", type=Path)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--reuse", type=Path)
    parser.add_argument("--prior", type=Path)
    parser.add_argument("--session", default="95921.gradiated-kv260")
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args.input, args.input / "config.json", args.directory, args.reuse)
    else:
        invocation = packet(args.directory)
        uart = runpy.run_path(str(args.prior / "uart_transport.py"))
        observer = runpy.run_path(str(args.prior / "observer_host.py"))
        log = Path(tempfile.mkdtemp(dir=args.directory, prefix=args.action + "-console-"))
        console = uart["Console"](log, invocation["tag"], args.session)
        try:
            console.start()
            observer["check_boot"](console, invocation["tag"], invocation["boot"])
            if args.action == "run":
                dispatch(args.directory, console, invocation)
            elif args.action == "status":
                state = read_status(console, invocation)
                receipt = {"utc": datetime.now(timezone.utc).isoformat(), **state}
                write_json(log / "status.json", receipt)
                print(json.dumps(receipt, sort_keys=True), flush=True)
            elif args.action == "collect":
                recover(args.directory, console, invocation)
        finally:
            console.stop()
