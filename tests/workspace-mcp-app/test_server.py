#!/usr/bin/env python3
import json, os, select, subprocess, sys, tempfile, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; SERVER=ROOT/'common/mcp/workspace_app/server.py'
def rpc(proc,ident,method,params):
 proc.stdin.write(json.dumps({'jsonrpc':'2.0','id':ident,'method':method,'params':params})+'\n');proc.stdin.flush();end=time.monotonic()+10
 while time.monotonic()<end:
  ready,_,_=select.select([proc.stdout],[],[],1)
  if ready:
   line=proc.stdout.readline()
   if line:
    obj=json.loads(line)
    if obj.get('id')==ident:return obj
 raise AssertionError((method,'timeout',proc.stderr.read()))
with tempfile.TemporaryDirectory(prefix='harr-workspace-app-') as td:
 base=Path(td);repo=base/'repo';wrong=base/'wrong-cwd';extra=base/'extra';extra2=base/'extra2';state=base/'state.json';log=base/'calls.jsonl'
 for p in (repo,wrong,extra,extra2):p.mkdir();(p/'.git').mkdir()
 state.write_text(json.dumps({'id':'11111111-1111-4111-8111-111111111111','revision':1,'primary':str(repo),'additional':[]}))
 fake=base/'harr';fake.write_text(r'''#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
state=Path(sys.argv[0]).with_name('state.json');log=Path(sys.argv[0]).with_name('calls.jsonl');a=sys.argv[1:];assert a[:1]==['workspace'],a;a=a[1:];s=json.loads(state.read_text())
with log.open('a') as f:f.write(json.dumps({'cwd':os.getcwd(),'args':a})+'\n')
if a[0]=='show': print(json.dumps({'store':str(state),**s}));raise SystemExit
if a[0] in ('add','remove'):
 path=str(Path(a[1]).resolve());expected=int(a[a.index('--expected-revision')+1])
 if expected!=s['revision']: print(f'Workspace admin failed: revision conflict: expected {expected}, current {s["revision"]}',file=sys.stderr);raise SystemExit(1)
 if a[0]=='add':
  if path not in s['additional']:s['additional'].append(path)
 elif path in s['additional']:s['additional'].remove(path)
 s['revision']+=1;state.write_text(json.dumps(s));print(json.dumps({'store':str(state),**s}));raise SystemExit
raise SystemExit(2)
''');fake.chmod(0o755)
 env=os.environ.copy();env['HARR_BIN']=str(fake)
 p=subprocess.Popen([sys.executable,str(SERVER)],cwd=wrong,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
 try:
  assert 'result' in rpc(p,1,'initialize',{})
  tools=rpc(p,2,'tools/list',{})['result']['tools'];names={t['name']:t for t in tools}
  assert names['show_harr_workspace']['_meta']['ui']['visibility']==['model','app']
  assert names['show_harr_workspace']['inputSchema']['required']==['project']
  for n in ('workspace_ui_get','workspace_ui_add_root','workspace_ui_remove_root'):assert names[n]['_meta']['ui']['visibility']==['app']
  missing=rpc(p,3,'tools/call',{'name':'show_harr_workspace','arguments':{}});assert 'error' in missing and 'project is required' in missing['error']['message']
  shown=rpc(p,4,'tools/call',{'name':'show_harr_workspace','arguments':{'project':str(repo)}})['result'];snap=shown['structuredContent'];assert snap['revision']==1 and snap['project']==str(repo)
  resource=rpc(p,5,'resources/read',{'uri':'ui://harr-workspace/panel.html'})['result']['contents'][0];assert resource['mimeType']=='text/html;profile=mcp-app'
  html=resource['text'];assert 'workspace_ui_add_root' in html and 'workspace_ui_remove_root' in html and 'Подтвердить' in html and 'aria-live' in html
  add=rpc(p,6,'tools/call',{'name':'workspace_ui_add_root','arguments':{'project':str(repo),'path':str(extra),'expected_revision':1}})['result']['structuredContent'];assert add['revision']==2 and str(extra) in add['additional']
  stale=rpc(p,7,'tools/call',{'name':'workspace_ui_add_root','arguments':{'project':str(repo),'path':str(extra2),'expected_revision':1}});assert 'error' in stale and 'revision conflict' in stale['error']['message']
  broad=rpc(p,8,'tools/call',{'name':'workspace_ui_add_root','arguments':{'project':str(repo),'path':str(base),'expected_revision':2}});assert 'error' in broad and 'broad parent' in broad['error']['message']
  fsroot=rpc(p,9,'tools/call',{'name':'workspace_ui_add_root','arguments':{'project':str(repo),'path':'/','expected_revision':2}});assert 'error' in fsroot and 'filesystem root' in fsroot['error']['message']
  rem=rpc(p,10,'tools/call',{'name':'workspace_ui_remove_root','arguments':{'project':str(repo),'path':str(extra),'expected_revision':2}})['result']['structuredContent'];assert rem['revision']==3 and rem['additional']==[]
  calls=[json.loads(x) for x in log.read_text().splitlines()];assert calls and all(Path(c['cwd'])==repo for c in calls),calls
  print('PASS: Workspace MCP App explicit-project binding, resource, CAS add/remove and app-only mutations')
 finally:
  p.terminate()
  try:p.wait(timeout=3)
  except subprocess.TimeoutExpired:p.kill();p.wait(timeout=3)
