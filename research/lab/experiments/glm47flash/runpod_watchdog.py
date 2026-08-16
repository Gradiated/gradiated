import datetime,json,os,sys,time,urllib.error,urllib.request

pod_id=sys.argv[1]
deadline=float(sys.argv[2])
cancel_path=sys.argv[3]
log_path=sys.argv[4]

def emit(event,**fields):
    row={'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),'event':event,**fields}
    with open(log_path,'a') as f:f.write(json.dumps(row,separators=(',',':'))+'\n')

while time.time() < deadline and not os.path.exists(cancel_path):
    time.sleep(min(10,max(0,deadline-time.time())))
if os.path.exists(cancel_path):
    emit('watchdog_cancelled')
    raise SystemExit(0)
h={'Authorization':'Bearer '+os.environ['RUNPOD_API_KEY']}
try:
    req=urllib.request.Request('https://rest.runpod.io/v1/pods/'+pod_id,headers=h,method='DELETE')
    with urllib.request.urlopen(req,timeout=30) as r: status=r.status
except urllib.error.HTTPError as e:
    status=e.code
emit('watchdog_delete',delete_http_status=status)
try:
    urllib.request.urlopen(urllib.request.Request('https://rest.runpod.io/v1/pods/'+pod_id,headers=h),timeout=30)
    verification='present'
except urllib.error.HTTPError as e:
    verification=f'http_{e.code}'
emit('watchdog_verify',verification=verification)
