import json,subprocess,select,time,threading,queue
cmd=['python3','tests/gigacode-mcp-app/server.py']
p=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
results={}
cv=threading.Condition()
def reader():
 for line in p.stdout:
  r=json.loads(line)
  with cv:
   results[r.get('id')]=r;cv.notify_all()
threading.Thread(target=reader,daemon=True).start()
def request(id,method,params=None,timeout=30):
 p.stdin.write(json.dumps({'jsonrpc':'2.0','id':id,'method':method,'params':params or {}})+'\n');p.stdin.flush()
 with cv:
  ok=cv.wait_for(lambda:id in results,timeout)
  if not ok:raise RuntimeError('timeout '+str(id))
  return results.pop(id)
assert request(1,'initialize')['result']['serverInfo']['version']=='0.2'
s=request(2,'tools/call',{'name':'show_gigacode_live','arguments':{}},timeout=45)['result']['structuredContent']['session_id']
print('session',s,flush=True)
# Two concurrent requests same session; their cursors must be independent.
for n in (3,4):
 p.stdin.write(json.dumps({'jsonrpc':'2.0','id':n,'method':'tools/call','params':{'name':'poll_gigacode_ui','arguments':{'session_id':s,'after_revision':99999,'wait_ms':3500}}})+'\n');p.stdin.flush()
t=time.monotonic()
with cv:
 assert cv.wait_for(lambda:3 in results and 4 in results,12), 'parallel long-poll timed out'
 a=results.pop(3);b=results.pop(4)
assert 'result' in a and 'result' in b,(a,b)
elapsed=round(time.monotonic()-t,2)
print('parallel polls',a['result']['structuredContent']['status'],b['result']['structuredContent']['status'],'elapsed',elapsed,flush=True)
assert elapsed<6
deadline=time.monotonic()+28
while True:
 x=request(5,'tools/call',{'name':'poll_gigacode_ui','arguments':{'session_id':s,'after_revision':0,'wait_ms':3000}},timeout=10)
 d=x['result']['structuredContent']
 if d['messages'] or d['status'] not in ('RUNNING','STARTING','PENDING') or time.monotonic()>deadline:break
print('replay count',len(d['messages']),'revision',d['revision'],'status',d['status'])
assert len(d['messages'])>0,d
p.terminate()
