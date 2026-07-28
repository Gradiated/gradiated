#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path
DENOMINATOR, TARGET = .625149101968745, .500119281574996
def main() -> int:
 p=argparse.ArgumentParser(); p.add_argument('--results',type=Path,required=True); p.add_argument('--server-log',type=Path,required=True); p.add_argument('--output',type=Path,required=True); a=p.parse_args()
 terms={k:json.loads((a.results/k/'TERMINAL.json').read_text()) for k in ('ar-c32','dflash-depth4-c32')}
 rows={k:[json.loads(x.read_text()) for x in sorted((a.results/k).glob('request-*.json'))] for k in terms}
 ar,df=rows['ar-c32'],rows['dflash-depth4-c32']
 complete=all(t['complete_requests']==32 and t['pass'] for t in terms.values())
 ownership=all(len({r['request_id'] for r in v})==32 and all(r['request_id'] for r in v) for v in rows.values())
 tokens=all(x['token_ids']==y['token_ids'] and len(x['token_ids'])==358 for x,y in zip(ar,df))
 accounting=all((x['prompt_tokens'],x['completion_tokens'],x['cached_tokens'])==(y['prompt_tokens'],y['completion_tokens'],y['cached_tokens']) for x,y in zip(ar,df))
 log=a.server_log.read_text(); accepted='accept len' in log or 'DFLASH verify completed' in log
 candidate=terms['dflash-depth4-c32']; control=terms['ar-c32']; passed=complete and ownership and tokens and accounting and accepted
 v={'schema_version':1,'classification':'endpoint_measured' if passed else 'quality_or_observer_reject','pass':passed,'complete_requests':{k:t['complete_requests'] for k,t in terms.items()},'output_tokens':358,'exact_request_ownership':ownership,'target_emitted_token_equivalence':tokens,'cache_accounting_equality':accounting,'accepted_prefix_telemetry_present':accepted,'failures':{k:32-t['complete_requests'] for k,t in terms.items()},'control':control,'candidate':candidate,'candidate_beats_paired_ar':candidate['service_seconds_per_request']<control['service_seconds_per_request'],'qualified_denominator_s_per_request':DENOMINATOR,'campaign_target_s_per_request':TARGET,'candidate_beats_denominator':candidate['service_seconds_per_request']<DENOMINATOR,'candidate_hits_campaign_target':candidate['service_seconds_per_request']<=TARGET}
 tmp=a.output.with_suffix('.part'); tmp.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n'); tmp.replace(a.output); return 0 if passed else 72
if __name__=='__main__': raise SystemExit(main())
