#!/usr/bin/env python3
import json, os, select, subprocess, sys, tempfile, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
REAL=Path(os.environ['LEANCTX_TEST_BIN']).resolve()
APP=ROOT/'common/mcp/workspace_app/server.py'; MANAGER=ROOT/'common/mcp/manager.py'; REGISTRY=ROOT/'common/mcp/registry.json'; HARR=ROOT/'linux/harr'
def rpc(proc, ident, method, params, timeout=35):
 proc.stdin.write(json.dumps({'jsonrpc':'2.0','id':ident,'method':method,'params':params})+'\n');proc.stdin.flush();end=time.monotonic()+timeout
 while time.monotonic()<end:
  if proc.poll() is not None: raise AssertionError(('process exited',proc.returncode,proc.stderr.read()))
  ready,_,_=select.select([proc.stdout],[],[],1)
  if ready:
   line=proc.stdout.readline()
   if line:
    obj=json.loads(line)
    if obj.get('id')==ident:return obj
 raise AssertionError((method,'timeout'))
def text_result(reply):
 if 'error' in reply:return json.dumps(reply['error'])
 return '\n'.join(x.get('text','') for x in reply['result'].get('content',[]) if x.get('type')=='text')
with tempfile.TemporaryDirectory(prefix='harr-workspace-app-live-') as td:
 base=Path(td);home=base/'home';cfg=base/'config';repo=base/'repo-a';wrong=base/'wrong-app-cwd';extra=base/'repo-b'
 for p in (home,cfg,repo,wrong,extra):p.mkdir(parents=True,exist_ok=True)
 (repo/'.git').mkdir();(wrong/'.git').mkdir();(extra/'.git').mkdir();target=extra/'marker.txt';target.write_text('workspace_ui_live_marker_723\n')
 env=os.environ.copy();env.update({'HOME':str(home),'XDG_CONFIG_HOME':str(cfg),'HARR_BIN':str(HARR),'HARR_LEANCTX_REAL':str(REAL),'HARR_MCP_EFFECTIVE':str(REGISTRY),'LEAN_CTX_HEADLESS':'1'})
 app=subprocess.Popen([sys.executable,str(APP)],cwd=wrong,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
 mcp=subprocess.Popen([sys.executable,str(MANAGER),'--registry',str(REGISTRY),'exec-leanctx',str(REAL),'--','mcp'],cwd=repo,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
 try:
  assert 'result' in rpc(mcp,1,'initialize',{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'workspace-ui-live','version':'1'}})
  mcp.stdin.write(json.dumps({'jsonrpc':'2.0','method':'notifications/initialized','params':{}})+'\n');mcp.stdin.flush()
  before=rpc(mcp,2,'tools/call',{'name':'ctx_read','arguments':{'path':str(target)}});assert 'outside' in text_result(before) or 'escapes project root' in text_result(before)
  shown=rpc(app,10,'tools/call',{'name':'show_harr_workspace','arguments':{'project':str(repo)}})['result']['structuredContent'];assert shown['revision']==1 and shown['project']==str(repo)
  added=rpc(app,11,'tools/call',{'name':'workspace_ui_add_root','arguments':{'project':str(repo),'path':str(extra),'expected_revision':1}})['result']['structuredContent'];assert added['revision']==2
  allowed=rpc(mcp,3,'tools/call',{'name':'ctx_read','arguments':{'path':str(target)}});assert 'workspace_ui_live_marker_723' in text_result(allowed),allowed
  removed=rpc(app,12,'tools/call',{'name':'workspace_ui_remove_root','arguments':{'project':str(repo),'path':str(extra),'expected_revision':2}})['result']['structuredContent'];assert removed['revision']==3
  after=rpc(mcp,4,'tools/call',{'name':'ctx_read','arguments':{'path':str(target)}});assert 'outside' in text_result(after) or 'escapes project root' in text_result(after)
  print('PASS: explicit-project Workspace App add/remove updates one live LeanCTX MCP session without restart')
 finally:
  for proc in (app,mcp):
   proc.terminate()
   try:proc.wait(timeout=3)
   except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=3)
