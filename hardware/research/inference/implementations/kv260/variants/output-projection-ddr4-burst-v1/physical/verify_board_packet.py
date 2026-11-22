"""Offline checks for the physical run. Does not access the KV260."""
import json
from pathlib import Path
from itertools import pairwise
from collections import Counter
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import importlib

p=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(p))
l=importlib.import_module('lifecycle')
b=importlib.import_module('bench_fixture')
calls=[]
def capture(label,mode,group,watchdog,smoke,homogeneous=None):
    if smoke: 
        calls.append(('smoke',mode,group,3))
        return {'requests':[{'observed':{'header':{'done_ns':n+100_000_000,'admitted_ns':n}}} for n in (100,200,300)]}
    warm,measured=b.block_cases(group,homogeneous)
    assert warm[-1][0]==measured[-1][0] and watchdog['request_timeout_ns']==1_000_000_000
    calls.append((homogeneous or 'mixed',mode,group,len(warm),len(measured)))
with TemporaryDirectory() as t:
    l.Lifecycle.measure(SimpleNamespace(arm=capture,output=Path(t)))
modes={'bram','scalar','beat','row'}
assert {v[1] for v in calls[:4]}==modes and len(calls)==44
assert sum(x[4] for x in calls[4:])==400 and sum(x[3] for x in calls[4:])==72
mixed=calls[4:20]; groups=[[x[1] for x in mixed if x[2]==g] for g in range(1,5)]
assert all(set(g)==modes for g in groups)
assert set(Counter(pair for g in groups for pair in pairwise(g)).values())=={1}
print('Four smoke blocks, 16 mixed and 24 per-prompt blocks. All mixed ordered neighbours balanced.')
