#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import pathlib
import urllib.request

ROOT = pathlib.Path('/home/glmrunner/gemma4-h200-ngram-sequential-validation/artifacts')
MODEL = 'google/gemma-4-31B-it'


def post(body: dict) -> dict:
    encoded = json.dumps(body, separators=(',', ':'), ensure_ascii=False).encode()
    request = urllib.request.Request('http://127.0.0.1:30000/v1/chat/completions', data=encoded, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read())


def main() -> None:
    tool = {'type':'function','function':{'name':'lookup_user','description':'Look up a user by id.','parameters':{'type':'object','properties':{'user_id':{'type':'string'}},'required':['user_id']}}}
    cases = [
        {'id':'gpqa_minimal','request':{'model':MODEL,'messages':[{'role':'user','content':'A closed system absorbs 100 J of heat and does 40 J of work on its surroundings. What is the change in internal energy in joules? Reply with only the number.'}],'temperature':0,'seed':20260718,'max_tokens':32}},
        {'id':'taubench_minimal','request':{'model':MODEL,'messages':[{'role':'user','content':'Use lookup_user to look up user_id demo_user.'}],'tools':[tool],'tool_choice':'required','temperature':0,'seed':20260718,'max_tokens':128}},
    ]
    rows=[]
    for case in cases:
        response=post(case['request'])
        choice=(response.get('choices') or [{}])[0]
        message=choice.get('message') or {}
        rows.append({'id':case['id'],'request':case['request'],'response':response,'raw_sha256':hashlib.sha256(json.dumps(response,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),'finish_reason':choice.get('finish_reason'),'content':message.get('content'),'tool_calls':message.get('tool_calls'),'usage':response.get('usage')})
    result={'schema_version':1,'classification':'bounded_candidate_side_gpqa_taubench_discriminator','count':len(rows),'rows':rows}
    (ROOT/'CANDIDATE_QUALITY_DISCRIMINATOR.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')


if __name__ == '__main__':
    main()
