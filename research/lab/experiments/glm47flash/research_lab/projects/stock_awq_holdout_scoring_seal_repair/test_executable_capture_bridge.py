#!/usr/bin/env python3
import importlib.util,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent; RUNNER=ROOT.parents[2]/'campaign_100'/'nebius'/'vllm_v2_quality_runner.py'
spec=importlib.util.spec_from_file_location('runner',RUNNER); runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
def main():
 ids=[1,2,3]; assert runner.token_sequence_sha256(ids)==runner.token_sequence_sha256(json.loads(json.dumps(ids)))
 request=runner.capture_request({'category':'teacher_forced_loss','teacher_forced_text':'x'});assert request['endpoint']=='/v1/completions' and request['payload']['return_token_ids'] is True
 p=subprocess.run([sys.executable,str(ROOT/'executable_capture_bridge.py')],capture_output=True,text=True,timeout=180);assert p.returncode==0,p.stderr
 out=json.loads(p.stdout);assert out['status']=='HOLDOUT_EXECUTABLE_BRIDGE_PASS' and len(out['fresh_api_server_pids'])==3
 print(json.dumps({'pass':True,'json_round_trip':True,'real_r4_ingested':True},sort_keys=True))
if __name__=='__main__':main()
