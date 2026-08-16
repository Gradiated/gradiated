#!/usr/bin/env python3
from __future__ import annotations
import hashlib,importlib.util,json,time
from pathlib import Path
P=Path(__file__).resolve().parent;S=P.parent/'h200_w4_full_endpoint_background_frontier/h200_endpoint_owner.py'
s=importlib.util.spec_from_file_location('phased_source',S);m=importlib.util.module_from_spec(s);assert s.loader;s.loader.exec_module(m)
m.P=P;m.CK=P/'artifacts/w4-checkpoint-owner-20260717T223754Z/checkpoint-repair-2';m.RATE=2.15;m.DISK=.01215275
old=m.build_create_command
def create(**kw):
 kw.update(platform='gpu-h100-sxm',preset='1gpu-16vcpu-200gb',disk_gib=250);return old(**kw)
m.build_create_command=create
def h(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def bound(name:str,deadline:float)->dict:
 from session_staging import checkpoint_files,transfer_timeout_seconds
 f=checkpoint_files(m.CK);total=sum(x.bytes for x in f);st=json.loads((P/'STATUS.json').read_text());prior=float(st.get('derived_provider_spend_usd',0));spent=float(st.get('provider_exposure_seconds',0));requested=deadline-time.time();checks={'bindings':json.loads((P/'BINDINGS.json').read_text()).get('pass') is True,'terminal':json.loads((P/'W4_CHECKPOINT_TERMINAL.json').read_text()).get('pass') is True,'manifest':(m.CK/'model-files.sha256').is_file(),'runner':(P/'endpoint_runner.py').is_file(),'inventory':not m.list_items('instance') and not m.list_items('disk'),'keys':m.KEY.is_file() and m.PUB.is_file(),'budget':prior+(m.RATE+m.DISK)*requested/3600<=6.0 and spent+requested<=7800,'deadline':1800<requested<=3680}
 return {'type':'h100_w4_phased_precreate','checks':checks,'pass':all(checks.values()),'prior_provider_seconds':spent,'prior_spend_usd_derived':prior,'requested_provider_seconds':requested,'transfer_files_total':len(f),'transfer_bytes':total,'transfer_timeout_seconds':transfer_timeout_seconds(total),'source_hashes':{'runner':h(P/'endpoint_runner.py'),'owner_source':h(S)}}
m.bindings_check=bound
raise SystemExit(m.main())
