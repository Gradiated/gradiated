import json, sys, torch
from pathlib import Path
from transformers import AutoModelForCausalLM, AutoTokenizer
work=Path(sys.argv[1]); suite=Path(sys.argv[2]); out=Path(sys.argv[3]); cases=[json.loads(x) for x in (suite/'cases.jsonl').read_text().splitlines()]
c=next(x for x in cases if x['case_id']=='teacher_nll'); tok=AutoTokenizer.from_pretrained(work/'checkpoint'); ids=tok(c['prompt'],return_tensors='pt').input_ids.cuda(); model=AutoModelForCausalLM.from_pretrained(work/'checkpoint',torch_dtype=torch.bfloat16).cuda().eval()
with torch.no_grad(): logits=model(ids).logits[0,:-1]; targets=ids[0,1:]; lp=torch.log_softmax(logits.float(),-1).gather(1,targets[:,None]).squeeze(1); top=logits[-1].argmax().item()
out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps({'prompt_sha256':__import__('hashlib').sha256(c['prompt'].encode()).hexdigest(),'input_ids':ids[0].tolist(),'mean_nll':float(-lp.mean()),'scored_tokens':int(lp.numel()),'greedy_top_token_id':top},sort_keys=True)+'\n')
