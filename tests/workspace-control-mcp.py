#!/usr/bin/env python3
import json, os, select, subprocess, sys, tempfile, time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SERVER=ROOT/'common/mcp/workspace_control/server.py'

def rpc(proc, ident, method, params, timeout=12):
    proc.stdin.write(json.dumps({'jsonrpc':'2.0','id':ident,'method':method,'params':params})+'\n'); proc.stdin.flush()
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        ready,_,_=select.select([proc.stdout],[],[],1)
        if ready:
            line=proc.stdout.readline()
            if line:
                obj=json.loads(line)
                if obj.get('id')==ident:return obj
        if proc.poll() is not None: break
    raise AssertionError((method,'timeout',proc.stderr.read()))

with tempfile.TemporaryDirectory(prefix='harr-workspace-control-') as td:
    base=Path(td); home=base/'home'; work=base/'work'; repo=work/'repo'; extra=base/'extra'; state=base/'state.json'; log=base/'calls.jsonl'
    for p in (home,repo,extra): p.mkdir(parents=True,exist_ok=True)
    (repo/'.git').mkdir(); state.write_text(json.dumps({'id':'11111111-1111-4111-8111-111111111111','revision':1,'primary':str(repo),'additional':[]}))
    fake=base/'harr'
    fake.write_text(r'''#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
state=Path(os.environ['HARR_CONTROL_STATE']);log=Path(os.environ['HARR_CONTROL_LOG']);args=sys.argv[1:]
with log.open('a') as f:f.write(json.dumps({'cwd':os.getcwd(),'args':args})+'\n')
s=json.loads(state.read_text())
if args[:2]==['workspace','show']:
 print(json.dumps({'store':str(state),**s}));raise SystemExit
if args[:2]==['workspace','sync']:
 added=[];skipped=[]
 for raw in args[2:]:
  path=str(Path(raw).resolve())
  if path==s['primary']:skipped.append({'path':path,'reason':'primary'});continue
  if path in s['additional']:skipped.append({'path':path,'reason':'already-present'});continue
  s['additional'].append(path);s['revision']+=1;added.append(path)
 state.write_text(json.dumps(s));print(json.dumps({'store':str(state),**s,'sync':{'added':added,'skipped':skipped}}));raise SystemExit
raise SystemExit(2)
'''); fake.chmod(0o755)
    env=os.environ.copy();env.update({'HOME':str(home),'HARR_BIN':str(fake),'HARR_CONTROL_STATE':str(state),'HARR_CONTROL_LOG':str(log)})
    p=subprocess.Popen([sys.executable,str(SERVER)],cwd=repo,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
    try:
        assert 'result' in rpc(p,1,'initialize',{})
        tools=rpc(p,2,'tools/list',{})['result']['tools']; names={x['name'] for x in tools}; assert names=={'workspace_get','workspace_sync'},names
        got=rpc(p,3,'tools/call',{'name':'workspace_get','arguments':{'project':str(repo)}})['result']['structuredContent']; assert got['revision']==1 and got['primary']==str(repo)
        synced=rpc(p,4,'tools/call',{'name':'workspace_sync','arguments':{'project':str(repo),'paths':[str(repo),str(extra)]}})['result']['structuredContent']
        assert synced['beforeRevision']==1 and synced['revision']==2 and synced['sync']['added']==[str(extra)],synced
        for ident,bad in ((5,str(home)),(6,str(work)),(7,'/')):
            reply=rpc(p,ident,'tools/call',{'name':'workspace_sync','arguments':{'project':str(repo),'paths':[bad]}})
            assert 'error' in reply,(bad,reply)
        calls=[json.loads(x) for x in log.read_text().splitlines()]
        assert any(c['args'][:2]==['workspace','sync'] for c in calls),calls
        print('PASS: direct Workspace control MCP get/sync + broad-root guards')
    finally:
        p.terminate()
        try:p.wait(timeout=3)
        except subprocess.TimeoutExpired:p.kill();p.wait(timeout=3)
