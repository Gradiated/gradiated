#!/usr/bin/env python3
"""Consumer repair: accept pinned SGLang's measured `accept len` telemetry."""
import ast, hashlib, json, pathlib, re
from evaluate_dflash_diagnostic import old_openai_text

VERIFY = re.compile(r"DFLASH verify completed\. num_correct_drafts_per_req=(\[[^\n]+\])")
ACCEPT = re.compile(r"Decode batch.*?accept len: ([0-9]+(?:\.[0-9]+)?)")

def main():
    import argparse
    p=argparse.ArgumentParser(); p.add_argument('--candidate',type=pathlib.Path,required=True); p.add_argument('--consumed-ar',type=pathlib.Path,required=True); p.add_argument('--server-log',type=pathlib.Path,required=True); p.add_argument('--output',type=pathlib.Path,required=True); a=p.parse_args()
    term=json.loads((a.candidate/'TERMINAL.json').read_text())
    rows=[json.loads(x.read_text()) for x in sorted(a.candidate.glob('request-*.json'))]
    cand=[x.read_text() for x in sorted(a.candidate.glob('response-*.txt'))]
    control=[old_openai_text(x) for x in sorted(a.consumed_ar.glob('response-*.sse'))]
    log=a.server_log.read_text(errors='replace'); accepted=[]
    for m in VERIFY.finditer(log): accepted.extend(ast.literal_eval(m.group(1)))
    if not accepted: accepted=[float(m.group(1)) for m in ACCEPT.finditer(log)]
    result={'schema_version':1,'classification':'diagnostic_pass','complete_requests':term.get('complete_requests'),'candidate_raw_token_ids_present':len(rows)==4 and all(r.get('returned_token_ids')==358 for r in rows),'prior_ar_decoded_text_equal':len(cand)==len(control)==4 and cand==control,'candidate_text_sha256':[hashlib.sha256(x.encode()).hexdigest() for x in cand],'consumed_ar_text_sha256':[hashlib.sha256(x.encode()).hexdigest() for x in control],'draft_runner_initialized':'Initialized DFLASH draft runner' in log,'verify_event_count':len(VERIFY.findall(log)),'accept_len_event_count':len(ACCEPT.findall(log)),'request_verification_count':len(accepted),'accepted_draft_tokens':sum(accepted),'mean_accepted_drafts_per_verification':sum(accepted)/len(accepted) if accepted else None,'terminal_pass':term.get('pass') is True}
    result['pass']=bool(result['terminal_pass'] and result['complete_requests']==4 and result['candidate_raw_token_ids_present'] and result['prior_ar_decoded_text_equal'] and result['draft_runner_initialized'] and result['request_verification_count']>0 and result['accepted_draft_tokens']>0)
    if not result['pass']: result['classification']='diagnostic_quality_or_integration_reject'
    a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n'); return 0 if result['pass'] else 72
if __name__=='__main__': raise SystemExit(main())
