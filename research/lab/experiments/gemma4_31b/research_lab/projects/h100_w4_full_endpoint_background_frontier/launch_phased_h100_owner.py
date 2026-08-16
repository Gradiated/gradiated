#!/usr/bin/env python3
import datetime as dt,json,subprocess,time
from pathlib import Path
p=Path(__file__).resolve().parent;tag=dt.datetime.now(dt.UTC).strftime('%Y%m%dt%H%M%sz');name=f'gemma-h100-w4-phased-{tag}';out=p/'artifacts'/name;deadline=time.time()+3000
r=subprocess.run(['systemd-run','--user','--collect',f'--unit={name}','--property=TimeoutStartSec=100min','/usr/bin/python3',str(p/'phased_h100_owner.py'),'--output-dir',str(out),'--name',name,'--deadline-epoch',str(deadline)],capture_output=True,text=True,timeout=30)
print(json.dumps({'unit':f'{name}.service','unit_manager':'systemd --user','launch_returncode':r.returncode,'artifact_root':str(out),'deadline_epoch':deadline,'name':name,'stderr':r.stderr[-1000:]},sort_keys=True));raise SystemExit(r.returncode)
