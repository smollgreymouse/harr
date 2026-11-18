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
state=Path(os.environ['HARR_CONTROL_STATE']);log=Path(os.environ['HARR_CONTROL_LOG']);owners=Path(os.environ['HARR_CONTROL_OWNERS']);args=sys.argv[1:]
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
if args[:3]==['workspace','owner','get'] or args[:3]==['workspace','owner','claim'] or args[:3]==['workspace','owner','release']:
 op=args[2];root=str(Path(args[3]).resolve());flags={};i=4
 while i<len(args):
  if args[i].startswith('--') and i+1<len(args):flags[args[i][2:]]=args[i+1];i+=2
  else:i+=1
 reg=json.loads(owners.read_text()) if owners.exists() else {}
 cur=reg.get(root)
 def save():owners.write_text(json.dumps(reg))
 if op=='get':
  print(json.dumps({'root':root,'owner':cur}));raise SystemExit
 oid=flags.get('owner-id')
 if op=='claim':
  if cur is None:
   cur={'owner_id':oid,'owner_label':flags.get('owner-label') or oid,'last_seen_at':'2026-11-17T00:00:00+00:00'}
   reg[root]=cur;save();print(json.dumps({'status':'claimed','root':root,'owner':cur}));raise SystemExit
  if cur.get('owner_id')==oid:
   cur={'owner_id':oid,'owner_label':flags.get('owner-label') or oid,'last_seen_at':'2026-11-17T00:00:00+00:00'}
   reg[root]=cur;save();print(json.dumps({'status':'reclaimed','root':root,'owner':cur}));raise SystemExit
  take=flags.get('take-over-from')
  if not take:
   print(json.dumps({'status':'confirmation_required','root':root,'owner':cur}));raise SystemExit
  if take==cur.get('owner_id'):
   prev=cur
   cur={'owner_id':oid,'owner_label':flags.get('owner-label') or oid,'last_seen_at':'2026-11-17T00:00:00+00:00'}
   reg[root]=cur;save();print(json.dumps({'status':'transferred','root':root,'owner':cur,'previousOwner':prev,'note':'Worktree ранее был отмечен за задачей. С вашего согласия отметка передана текущей задаче.'}));raise SystemExit
  print(json.dumps({'status':'owner_changed','root':root,'owner':cur}));raise SystemExit
 if op=='release':
  if cur is None:
   print(json.dumps({'status':'absent','root':root,'owner':None}));raise SystemExit
  if cur.get('owner_id')!=oid:
   print(json.dumps({'status':'not_owner','root':root,'owner':cur}));raise SystemExit
  del reg[root];save();print(json.dumps({'status':'released','root':root,'owner':None}));raise SystemExit
raise SystemExit(2)
'''); fake.chmod(0o755)
    env=os.environ.copy();env.update({'HOME':str(home),'HARR_BIN':str(fake),'HARR_CONTROL_STATE':str(state),'HARR_CONTROL_LOG':str(log),'HARR_CONTROL_OWNERS':str(base/'owners.json')})
    p=subprocess.Popen([sys.executable,str(SERVER)],cwd=repo,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
    try:
        assert 'result' in rpc(p,1,'initialize',{})
        tools=rpc(p,2,'tools/list',{})['result']['tools']; names={x['name'] for x in tools}
        assert names=={'workspace_get','workspace_sync','workspace_owner_get','workspace_owner_claim','workspace_owner_release'},names
        sync_description=next(x['description'] for x in tools if x['name']=='workspace_sync')
        assert 'default auto mode binds that project' in sync_description and 'No explicit HARR_WORKSPACE_ROOT is needed' in sync_description
        got=rpc(p,3,'tools/call',{'name':'workspace_get','arguments':{'project':str(repo)}})['result']['structuredContent']; assert got['revision']==1 and got['primary']==str(repo)
        synced=rpc(p,4,'tools/call',{'name':'workspace_sync','arguments':{'project':str(repo),'paths':[str(repo),str(extra)]}})['result']['structuredContent']
        assert synced['beforeRevision']==1 and synced['revision']==2 and synced['sync']['added']==[str(extra)],synced
        # Exact duplicate paths inside one request are refused before any write.
        dup=rpc(p,12,'tools/call',{'name':'workspace_sync','arguments':{'project':str(repo),'paths':[str(extra),str(extra)]}})
        assert 'error' in dup and 'duplicate' in dup['error']['message'],dup
        # A checkout created during a running session is a newly known root.
        # Reuse the existing add-only MCP rather than changing the primary root.
        checkout=base/'new-checkout'; checkout.mkdir()
        registered=rpc(p,9,'tools/call',{'name':'workspace_sync','arguments':{'project':str(repo),'paths':[str(checkout)]}})['result']['structuredContent']
        assert registered['sync']['added']==[str(checkout)] and registered['primary']==str(repo),registered
        reread=rpc(p,10,'tools/call',{'name':'workspace_get','arguments':{'project':str(repo)}})['result']['structuredContent']
        assert str(checkout) in reread['additional'] and str(extra) in reread['additional'],reread
        repeated=rpc(p,11,'tools/call',{'name':'workspace_sync','arguments':{'project':str(repo),'paths':[str(checkout)]}})['result']['structuredContent']
        assert repeated['sync']['added']==[] and repeated['revision']==reread['revision'],repeated
        current=json.loads(state.read_text()); current['warnings']=[{'code':'workspace-root-missing','path':'/gone','state':'missing','message':'Configured Workspace root is missing and inactive.','remove_command':'harr workspace remove /gone'}]; state.write_text(json.dumps(current))
        warned=rpc(p,8,'tools/call',{'name':'workspace_get','arguments':{'project':str(repo)}})['result']
        assert warned['structuredContent']['warnings'][0]['code']=='workspace-root-missing',warned
        assert 'WARNING:' in warned['content'][0]['text'] and 'harr workspace remove /gone' in warned['content'][0]['text'],warned
        for ident,bad in ((5,str(home)),(6,str(work)),(7,'/')):
            reply=rpc(p,ident,'tools/call',{'name':'workspace_sync','arguments':{'project':str(repo),'paths':[bad]}})
            assert 'error' in reply,(bad,reply)
        # Cooperative owner note: get -> claim -> conflict -> transfer -> release.
        root=str(repo)
        nobody=rpc(p,20,'tools/call',{'name':'workspace_owner_get','arguments':{'project':str(repo),'root':root}})['result']['structuredContent']
        assert nobody['owner'] is None,nobody
        claimed=rpc(p,21,'tools/call',{'name':'workspace_owner_claim','arguments':{'project':str(repo),'root':root,'owner_id':'task-a','owner_label':'Task A'}})['result']['structuredContent']
        assert claimed['status']=='claimed' and claimed['owner']['owner_id']=='task-a',claimed
        updated=rpc(p,22,'tools/call',{'name':'workspace_owner_claim','arguments':{'project':str(repo),'root':root,'owner_id':'task-a'}})['result']['structuredContent']
        assert updated['status']=='reclaimed',updated
        conflict=rpc(p,23,'tools/call',{'name':'workspace_owner_claim','arguments':{'project':str(repo),'root':root,'owner_id':'task-b'}})['result']
        assert conflict['structuredContent']['status']=='confirmation_required',conflict
        assert 'task-a' in conflict['content'][0]['text'] and 'take_over_from=task-a' in conflict['content'][0]['text'],conflict
        stale=rpc(p,24,'tools/call',{'name':'workspace_owner_claim','arguments':{'project':str(repo),'root':root,'owner_id':'task-b','take_over_from':'task-z'}})['result']['structuredContent']
        assert stale['status']=='owner_changed' and stale['owner']['owner_id']=='task-a',stale
        transferred=rpc(p,25,'tools/call',{'name':'workspace_owner_claim','arguments':{'project':str(repo),'root':root,'owner_id':'task-b','take_over_from':'task-a'}})['result']['structuredContent']
        assert transferred['status']=='transferred' and transferred['previousOwner']['owner_id']=='task-a',transferred
        wrong=rpc(p,26,'tools/call',{'name':'workspace_owner_release','arguments':{'project':str(repo),'root':root,'owner_id':'task-a'}})['result']['structuredContent']
        assert wrong['status']=='not_owner',wrong
        released=rpc(p,27,'tools/call',{'name':'workspace_owner_release','arguments':{'project':str(repo),'root':root,'owner_id':'task-b'}})['result']['structuredContent']
        assert released['status']=='released',released
        calls=[json.loads(x) for x in log.read_text().splitlines()]
        assert any(c['args'][:2]==['workspace','sync'] for c in calls),calls
        assert any(c['args'][:3]==['workspace','owner','claim'] for c in calls),calls
        print('PASS: direct Workspace control MCP get/sync/owner + broad-root and duplicate guards')
    finally:
        p.terminate()
        try:p.wait(timeout=3)
        except subprocess.TimeoutExpired:p.kill();p.wait(timeout=3)
