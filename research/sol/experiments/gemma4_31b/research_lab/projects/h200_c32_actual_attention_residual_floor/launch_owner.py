#!/usr/bin/env python3
import argparse, datetime as dt, json, os, subprocess, time
from pathlib import Path
P=Path(__file__).resolve().parent
def main():
 p=argparse.ArgumentParser(); p.add_argument('--audit',type=Path,required=True); p.add_argument('--identity',type=Path,required=True); a=p.parse_args(); stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dt%H%M%sz'); name=f'gemma-h200-c32-attn-{stamp}'; out=P/'artifacts'/name; deadline=time.time()+3900; unit=f'{name}.service'
 cmd=['systemd-run','--user','--unit',name,'--collect','--property=TimeoutStartSec=65min','/usr/bin/python3',str(P/'attention_owner.py'),'--output-dir',str(out),'--name',name,'--deadline-epoch',str(deadline),'--audit',str(a.audit.resolve()),'--identity',str(a.identity.resolve())]
 r=subprocess.run(cmd,capture_output=True,text=True,timeout=30); payload={'unit':unit,'unit_manager':'systemd --user','launch_returncode':r.returncode,'launch_stdout':r.stdout[-1000:],'launch_stderr':r.stderr[-1000:],'artifact_root':str(out),'deadline_epoch':deadline,'name':name}; print(json.dumps(payload,sort_keys=True)); return r.returncode
if __name__=='__main__': raise SystemExit(main())
