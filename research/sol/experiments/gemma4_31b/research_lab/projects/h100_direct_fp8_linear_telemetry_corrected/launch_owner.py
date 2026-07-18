#!/usr/bin/env python3
import datetime as dt,json,subprocess,time
from pathlib import Path
p=Path(__file__).resolve().parent; tag=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dt%H%M%sz'); name=f'gemma-h100-direct-fp8-corrected-{tag}'; output=p/'artifacts'/name; deadline=time.time()+1080
cmd=['systemd-run','--user',f'--unit={name}','--collect','--property=TimeoutStartSec=23min','/usr/bin/python3',str(p/'h100_direct_fp8_owner.py'),'--output-dir',str(output),'--name',name,'--deadline-epoch',str(deadline),'--identity',str(p/'artifacts'/'DIRECTOR_IDENTITY_ASSERTION.json')]
r=subprocess.run(cmd,capture_output=True,text=True,timeout=30);print(json.dumps({'unit':f'{name}.service','unit_manager':'systemd --user','launch_returncode':r.returncode,'launch_stdout':r.stdout[-1000:],'launch_stderr':r.stderr[-1000:],'artifact_root':str(output),'deadline_epoch':deadline,'name':name},sort_keys=True));raise SystemExit(r.returncode)
