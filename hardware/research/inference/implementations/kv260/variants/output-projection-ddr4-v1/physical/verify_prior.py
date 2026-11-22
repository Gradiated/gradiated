"""Replay actual baseline cycle counters and synthetic DDR accounting failures."""
import json
from pathlib import Path
from measurement import verify_counters
from copy import deepcopy
from argparse import ArgumentParser

parser=ArgumentParser(description=__doc__)
parser.add_argument('capture',type=Path)
args=parser.parse_args()
rows=[row for number in range(1,4) for row in json.loads((args.capture/f'p{number}-candidate/block.json').read_text())['requests']]
assert len(rows)==18
rejects=0
def reject(case,header,counts,ddr):
    global rejects
    try:verify_counters(case,header,counts,ddr)
    except ValueError:rejects+=1
    else:raise AssertionError("Accepted inconsistent counters")
for row in rows:
    header=row['observed']['header']
    n=header['context_count']
    base={'projections':n,'useful_bytes':0,'reads':0,'beats':0,'faults':0,'projection_clocks':2112*n,
          'extra_clocks':0,'ar_stalls':0,'response_waits':0}
    verify_counters(row['case'],header,base,False)
    reads=1024*n
    for waits,stalls in ((0,0),(7*reads,reads//5)):
        added=2*reads+waits+stalls
        ext={**base,'reads':reads,'beats':reads,'useful_bytes':2*reads,'extra_clocks':added,
             'projection_clocks':base['projection_clocks']+added,'ar_stalls':stalls,'response_waits':waits}
        changed=deepcopy(header)
        for name,increment in [('first',1),('last',added-1),('done',added)]:
            changed['request_cycles'][name]+=increment
        verify_counters(row['case'],changed,ext,True)
        for key in ext:
            reject(row['case'],changed,{**ext,key:ext[key]+1},True)
        reject(row['case'],header,ext,True)
    reject(row['case'],header,{**base,'faults':1},False)
print('Replayed',len(rows),'board baseline records, 36 synthetic DDR cases and',rejects,'rejections.')
