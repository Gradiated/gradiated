#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, pathlib, subprocess, sys

def sha256(path: pathlib.Path) -> str:
    digest=hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda:handle.read(1024*1024),b""): digest.update(block)
    return digest.hexdigest()

def matches(root: pathlib.Path, row: dict) -> bool:
    path=root/row["path"]
    return path.is_file() and path.stat().st_size==row["bytes"] and sha256(path)==row["sha256"]

def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--manifest",type=pathlib.Path,required=True)
    parser.add_argument("--checkpoint",type=pathlib.Path,required=True)
    parser.add_argument("--revision",required=True)
    args=parser.parse_args()
    manifest=json.loads(args.manifest.read_text())
    rows=manifest["checkpoint_files"]
    if all(matches(args.checkpoint,row) for row in rows): return 0
    temporary=args.checkpoint.with_name(args.checkpoint.name+".staging")
    temporary.mkdir(exist_ok=True)
    result=subprocess.run(["huggingface-cli","download","google/gemma-4-31B-it","--revision",args.revision,"--local-dir",str(temporary),"--local-dir-use-symlinks","False"],text=True,capture_output=True)
    if result.returncode:
        sys.stderr.write(result.stderr[-4000:])
        return result.returncode
    if not all(matches(temporary,row) or matches(args.checkpoint,row) for row in rows):
        raise RuntimeError("downloaded checkpoint does not match immutable manifest")
    args.checkpoint.mkdir(exist_ok=True)
    for row in rows:
        final=args.checkpoint/row["path"]
        if matches(args.checkpoint,row): continue
        source=temporary/row["path"]
        if not matches(temporary,row): raise RuntimeError(f"missing staged file: {row['path']}")
        source.replace(final)
    if not all(matches(args.checkpoint,row) for row in rows):
        raise RuntimeError("immutable checkpoint finalization mismatch")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
