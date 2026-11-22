"""Stage independent UART slices and reconstruct the sealed Experiment 17 packet."""
import argparse
import base64
import gzip
import hashlib
import json
from pathlib import Path
import runpy
import shlex
import tempfile
import time
import uuid
import zlib

from transport import UNPACK, packed_command, require, write_json


def sha(data):
    return hashlib.sha256(data).hexdigest()


JOIN = """\
import base64,gzip,hashlib,json,os,re,sys,tempfile,zlib
from pathlib import Path
target=Path(sys.argv[1]); manifest=json.loads(zlib.decompress(base64.b64decode(sys.argv[2],validate=True)))
assert os.geteuid()==0 and not target.is_symlink()
assert re.fullmatch(r'/var/tmp/gradiated-logits-ddr4-prefetch-[0-9TZ]+-[a-f0-9]{6}',str(target))
parts=[]
for path,expected,size in manifest['parts']:
 p=Path(path)
 assert re.fullmatch(re.escape(str(target))+r'-part[0-9]{2}-[0-9a-f]{6}',path)
 assert p.is_dir() and not p.is_symlink() and p.stat().st_uid==0 and p.stat().st_mode&0o077==0
 f=p/'slice.bin'
 assert f.is_file() and not f.is_symlink() and f.stat().st_uid==0 and f.stat().st_size==size
 data=f.read_bytes(); assert len(data)==size and hashlib.sha256(data).hexdigest()==expected
 parts.append(data)
outer=b''.join(parts); assert hashlib.sha256(outer).hexdigest()==manifest['outer']
files=json.loads(gzip.decompress(outer)); assert set(files)=={'packet.tar.gz'}
inner=base64.b64decode(files['packet.tar.gz'],validate=True)
assert hashlib.sha256(inner).hexdigest()==manifest['inner']
target.mkdir(mode=0o700,exist_ok=True)
assert target.is_dir() and target.stat().st_uid==0 and target.stat().st_mode&0o077==0
f=target/'packet.tar.gz'
if f.exists():
 assert f.is_file() and not f.is_symlink() and f.stat().st_uid==0 and f.read_bytes()==inner
else:
 with tempfile.NamedTemporaryFile(dir=target,delete=False) as out: out.write(inner)
 os.replace(out.name,f)
"""


def stage(root, historic, session):
    invocation = json.loads((root / "invocation.json").read_text())
    if (root / "staged.json").exists():
        receipt = json.loads((root / "staged.json").read_text())
        require(receipt["inner_sha256"] == invocation["inner_sha256"] and receipt["verified"],
                "Existing transport receipt differs")
        print("Sealed packet already staged", flush=True)
        return
    archive = (root / "board-transfer.gz").read_bytes()
    require(sha(archive) == invocation["archive_sha256"], "Sealed outer packet differs")
    uart = runpy.run_path(str(historic / "uart_transport.py"))
    observer = runpy.run_path(str(historic / "observer_host.py"))
    observer["send_archive"].__globals__["TRANSFER_SECONDS"] = 240
    tag = invocation["tag"]
    board = invocation["board"]
    manifest = {"outer": sha(archive), "inner": invocation["inner_sha256"], "parts": []}
    console = uart["Console"](Path(tempfile.mkdtemp(dir=root, prefix="parts-console-")), tag, session)
    try:
        console.start()
        observer["check_boot"](console, tag, invocation["boot"])
        for index, offset in enumerate(range(0, len(archive), 240_000)):
            part = archive[offset:offset+240_000]
            receipt = root / f"slice-{index:02}.json"
            if receipt.is_file():
                saved = json.loads(receipt.read_text())
                require(saved["index"] == index and saved["sha256"] == sha(part)
                        and saved["bytes"] == len(part), "Slice receipt differs")
            else:
                outer = gzip.compress(json.dumps({"slice.bin": base64.b64encode(part).decode()},
                                                 separators=(",", ":")).encode(), mtime=0)
                encoded = base64.b64encode(outer)
                chunks = (len(encoded) + 639) // 640
                for attempt in range(1, 4):
                    suffix = uuid.uuid4().hex[:6]
                    path = f"{board}-part{index:02}-{suffix}"
                    alias = f"{tag}_P{index:02}_{suffix}"
                    line = " " + shlex.join([
                        "sudo", "-n", "timeout", "-k", "2s", "230s",
                        *packed_command(observer["paced_receiver"](uart["RECEIVER"]), path, alias,
                                        str(chunks), str(len(outer)), sha(outer),
                                        json.dumps({"slice.bin": sha(part)}, separators=(",", ":"))),
                    ])
                    packet = {"staging": line, "archive_sha256": sha(outer), "chunks": chunks,
                              "archive_bytes": len(outer)}
                    try:
                        observer["send_archive"](console, alias, packet, encoded, time.monotonic())
                    except (RuntimeError, ValueError) as exc:
                        print(f"Slice {index + 1} attempt {attempt} stopped: {exc}", flush=True)
                        if attempt == 3:
                            raise
                        observer["check_boot"](console, tag, invocation["boot"])
                    else:
                        saved = {"index": index, "board": path, "sha256": sha(part), "bytes": len(part)}
                        write_json(receipt, saved)
                        print(f"Verified slice {index + 1}: {len(part):,} bytes", flush=True)
                        break
            manifest["parts"].append([saved["board"], saved["sha256"], saved["bytes"]])
        packed_manifest = base64.b64encode(zlib.compress(json.dumps(manifest, separators=(",", ":")).encode(),9)).decode()
        setup = (
            (f"{tag}_JOIN", packed_command(JOIN, board, packed_manifest)),
            (f"{tag}_UNPACK", packed_command(UNPACK, board, invocation["inner_sha256"], invocation["config_sha256"])),
        )
        for alias, command in setup:
            line = " " + shlex.join(["sudo", "-n", *command]) + " ; printf '\\n%s %s\\n' " + alias + ' "$?"'
            console.send(line)
            result = console.wait([alias + r" ([0-9]+)"], time.monotonic()+30)
            require(result and result[1] == "0", f"{alias} rejected")
        write_json(root / "staged.json", {"inner_sha256": invocation["inner_sha256"], "verified": True,
                                         "slices": len(manifest["parts"])})
        print("Complete packet and configuration verified", flush=True)
    finally:
        console.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("historic", type=Path)
    parser.add_argument("--session", default="95921.gradiated-kv260")
    args = parser.parse_args()
    stage(args.run, args.historic, args.session)
