#!/usr/bin/env python3
import json, os, select, subprocess, sys, tempfile, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REAL=Path(os.environ['LEANCTX_TEST_BIN']).resolve()
with tempfile.TemporaryDirectory(prefix='harr-live-workspace-') as td:
    base=Path(td); home=base/'home'; cfg=base/'config'; repo=base/'repo-a'; extra=base/'repo-b'
    for p in (home,cfg,repo,extra): p.mkdir(parents=True,exist_ok=True)
    (repo/'.git').mkdir(); (extra/'.git').mkdir(); (extra/'unique-b.txt').write_text('harr_live_cobalt_marker_991\n')
    env=os.environ.copy(); env.update({'HOME':str(home),'XDG_CONFIG_HOME':str(cfg),'HARR_LEANCTX_REAL':str(REAL),'HARR_MCP_EFFECTIVE':str(ROOT/'common/mcp/registry.json'),'LEAN_CTX_HEADLESS':'1'})
    cmd=[sys.executable,str(ROOT/'common/mcp/manager.py'),'--registry',str(ROOT/'common/mcp/registry.json'),'exec-leanctx',str(REAL),'--','mcp']
    p=subprocess.Popen(cmd,cwd=repo,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
    seq=0
    def rpc(method,params,timeout=35):
        global seq
        seq+=1; ident=seq
        p.stdin.write(json.dumps({'jsonrpc':'2.0','id':ident,'method':method,'params':params})+'\n'); p.stdin.flush()
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            if p.poll() is not None: raise AssertionError(('MCP exited',p.returncode,p.stderr.read()))
            ready,_,_=select.select([p.stdout],[],[],max(0,end-time.monotonic()))
            if not ready: break
            line=p.stdout.readline()
            if not line: break
            obj=json.loads(line)
            if obj.get('id')==ident: return obj
        raise AssertionError(('MCP timeout',method))
    def call(name,args=None):
        reply=rpc('tools/call',{'name':name,'arguments':args or {}})
        if 'error' in reply: return reply
        return '\n'.join(x.get('text','') for x in reply.get('result',{}).get('content',[]) if x.get('type')=='text')
    def workspace_get(): return json.loads(call('ctx_workspace_get'))
    def search_extra(): return call('ctx_search',{'query':'harr_live_cobalt_marker_991','path':str(extra)})
    def harr(*args):
        r=subprocess.run([str(ROOT/'linux/harr'),'workspace',*args],cwd=repo,env=env,text=True,capture_output=True,timeout=40)
        assert r.returncode==0,(args,r.stdout,r.stderr)
        return json.loads(r.stdout)
    try:
        init=rpc('initialize',{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'harr-live-test','version':'1'}})
        assert 'result' in init,init
        p.stdin.write(json.dumps({'jsonrpc':'2.0','method':'notifications/initialized','params':{}})+'\n');p.stdin.flush()
        before=workspace_get(); assert before['revision']==1 and before['additionalRoots']==[],before
        denied=search_extra(); assert 'outside' in denied or 'escapes project root' in denied,denied
        added=harr('add',str(extra)); assert added['revision']==2 and str(extra) in added['additional'],added
        live=workspace_get(); assert live['revision']==2 and str(extra) in live['additionalRoots'],live
        allowed=search_extra(); assert 'harr_live_cobalt_marker_991' in allowed,allowed
        removed=harr('remove',str(extra)); assert removed['revision']==3 and removed['additional']==[],removed
        after=workspace_get(); assert after['revision']==3 and after['additionalRoots']==[],after
        denied_again=search_extra(); assert 'outside' in denied_again or 'escapes project root' in denied_again,denied_again
        print('PASS: one Harr-managed MCP session observes add/search/remove/deny live without restart')
    finally:
        p.terminate()
        try:p.wait(timeout=3)
        except subprocess.TimeoutExpired:p.kill();p.wait(timeout=5)
