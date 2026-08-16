#!/usr/bin/env python3
import argparse,datetime as dt,json,subprocess,time
from pathlib import Path
PROJECT=Path(__file__).resolve().parent
def main():
 p=argparse.ArgumentParser(); p.add_argument('--audit',type=Path,required=True); p.add_argument('--identity',type=Path,required=True); a=p.parse_args()
 tag=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dt%H%M%sz'); name=f'gemma-h100-paged-fp8-{tag}'; out=PROJECT/'artifacts'/name; deadline=time.time()+1500
 cmd=['systemd-run','--user',f'--unit={name}','--collect','--property=TimeoutStartSec=40min','/usr/bin/python3',str(PROJECT/'h100_owner.py'),'--output-dir',str(out),'--name',name,'--deadline-epoch',str(deadline),'--audit',str(a.audit.resolve()),'--identity',str(a.identity.resolve())]
 run=subprocess.run(cmd,capture_output=True,text=True,timeout=30)
 print(json.dumps({'unit':f'{name}.service','unit_manager':'systemd --user','launch_returncode':run.returncode,'launch_stdout':run.stdout[-1000:],'launch_stderr':run.stderr[-1000:],'artifact_root':str(out),'deadline_epoch':deadline,'name':name},sort_keys=True)); return run.returncode
if __name__=='__main__': raise SystemExit(main())
