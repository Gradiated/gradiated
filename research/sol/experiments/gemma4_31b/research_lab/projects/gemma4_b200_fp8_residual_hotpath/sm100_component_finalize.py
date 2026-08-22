#!/usr/bin/env python3
import hashlib,json,os,pathlib,sys,tempfile
out,pre=map(pathlib.Path,sys.argv[1:])
stock=json.loads((out/'stock/TERMINAL.json').read_text())
patched=json.loads((out/'patched/TERMINAL.json').read_text())
assert stock['custom_extension_sha256'] != patched['custom_extension_sha256']
assert stock['candidate_science_started'] and patched['candidate_science_started']
s={x['name']:x for x in stock['rows']}
p={x['name']:x for x in patched['rows']}
rows=[]
for name in s:
    a,c=s[name],p[name]
    rows.append({'name':name,'stock_p50_ms':a['quant_and_gemm_p50_ms'],'patched_p50_ms':c['quant_and_gemm_p50_ms'],'multiplicity_per_decode_step':a['multiplicity_per_decode_step'],'regression_fraction':c['quant_and_gemm_p50_ms']/a['quant_and_gemm_p50_ms']-1,'correctness':c['numeric']})
ws=sum(x['multiplicity_per_decode_step']*x['stock_p50_ms'] for x in rows)
wp=sum(x['multiplicity_per_decode_step']*x['patched_p50_ms'] for x in rows)
gain=1-wp/ws
saving=358*(ws-wp)/1000/32
correct=all(x['correctness']['finite'] and x['correctness']['cosine']>=.99999 and x['correctness']['normalized_rmse']<=.005 and x['correctness']['max_abs']<=.01 for x in rows)
shape_ok=all(x['regression_fraction']<=.05 for x in rows)
cls='component_positive_endpoint_conditional' if correct and shape_ok and gain>=.10 and saving>=.005 else 'component_negative_stop'
v={'schema_version':1,'classification':cls,'science_consumed':True,'stock_terminal_sha256':hashlib.sha256((out/'stock/TERMINAL.json').read_bytes()).hexdigest(),'patched_terminal_sha256':hashlib.sha256((out/'patched/TERMINAL.json').read_bytes()).hexdigest(),'preclaim_sha256':hashlib.sha256(pre.read_bytes()).hexdigest(),'rows':rows,'weighted_stock_quant_and_gemm_p50_ms':ws,'weighted_patched_quant_and_gemm_p50_ms':wp,'weighted_gain_fraction':gain,'projected_endpoint_saving_seconds_per_request':saving,'gates':{'correctness':correct,'shape_regression':shape_ok,'weighted_gain':gain>=.10,'endpoint_projection':saving>=.005},'stop_conditions':json.loads(pre.read_text())['stop_conditions'],'next_action':'retain claim for director promotion' if cls.startswith('component_positive') else 'release maintenance without endpoint replay'}
path=out/'SM100_TERMINAL.json'
fd,tmp=tempfile.mkstemp(prefix='.SM100_TERMINAL.',dir=out)
os.close(fd)
pathlib.Path(tmp).write_text(json.dumps(v,indent=2,sort_keys=True)+'\n')
os.replace(tmp,path)
