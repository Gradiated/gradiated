#!/usr/bin/env python3
import datetime as dt,json,subprocess,time
from pathlib import Path
p=Path(__file__).resolve().parent;tag=dt.datetime.now(dt.UTC).strftime('%Y%m%dt%H%M%sz');name='gemma-h200-paired-quality-'+tag;out=p/'artifacts'/name;deadline=time.time()+4200
r=subprocess.run(['systemd-run','--user','--collect',f'--unit={name}','--property=TimeoutStartSec=80min','/usr/bin/python3',str(p/'quality_owner.py'),'--output-dir',str(out),'--name',name,'--deadline-epoch',str(deadline)],capture_output=True,text=True,timeout=30)
print(json.dumps({'unit':name+'.service','unit_manager':'user','launch_returncode':r.returncode,'launch_stdout':r.stdout[-1000:],'launch_stderr':r.stderr[-1000:],'artifact_root':str(out),'deadline_epoch':deadline,'name':name},sort_keys=True));raise SystemExit(r.returncode)
