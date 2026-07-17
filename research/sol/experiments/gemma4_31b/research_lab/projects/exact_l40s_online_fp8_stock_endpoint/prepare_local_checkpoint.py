#!/usr/bin/env python3
"""Create a zero-copy flat staging view and checksum manifest from the verified terminal."""
from __future__ import annotations
import argparse, json, os
from pathlib import Path

def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument('--terminal',type=Path,required=True); p.add_argument('--output',type=Path,required=True); a=p.parse_args()
    terminal=json.loads(a.terminal.read_text())
    if terminal.get('pass') is not True: raise SystemExit('checkpoint terminal is not passing')
    source=Path(terminal['checkpoint_root']); a.output.mkdir(parents=True,exist_ok=False)
    lines=[]
    for row in terminal['files']:
        src=source/row['path']; dst=a.output/row['path']
        if src.stat().st_size != row['bytes']: raise SystemExit(f"size mismatch: {src}")
        os.link(src,dst); lines.append(f"{row['sha256']}  {row['path']}")
    (a.output/'model-files.sha256').write_text('\n'.join(lines)+'\n')
    manifest={'repository':'google/gemma-4-31B-it','revision':terminal['revision'],'shard_count':2,'weight_bytes':sum(r['bytes'] for r in terminal['files'] if r['path'].endswith('.safetensors')),'files':terminal['files']}
    (a.output/'model-files-manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    return 0
if __name__=='__main__': raise SystemExit(main())
