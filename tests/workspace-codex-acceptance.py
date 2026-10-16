#!/usr/bin/env python3
import json, os, select, shlex, subprocess, tempfile, time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REAL=Path(os.environ['LEANCTX_TEST_BIN']).resolve()
CODEX=os.environ.get('CODEX_TEST_BIN') or subprocess.check_output(['bash','-lc','command -v codex'],text=True).strip()

with tempfile.TemporaryDirectory(prefix='harr-codex-workspace-',dir='/tmp') as td:
    base=Path(td); fix_home=base/'home'; fix_cfg=base/'config'; repo=base/'repo-a'; extra=base/'repo-b'
    for p in (fix_home,fix_cfg,repo,extra): p.mkdir(parents=True,exist_ok=True)
    (repo/'.git').mkdir(); (extra/'.git').mkdir(); (extra/'unique-b.txt').write_text('cobalt lantern walnut harr codex live 4815162342\n')
    wrapper=base/'leanctx-wrapper'
    wrapper.write_text(f'''#!/usr/bin/env bash
set -Eeuo pipefail
export HOME={shlex.quote(str(fix_home))}
export XDG_CONFIG_HOME={shlex.quote(str(fix_cfg))}
export HARR_CONFIG_DIR={shlex.quote(str(fix_cfg/'harr'))}
export HARR_LEANCTX_REAL={shlex.quote(str(REAL))}
export HARR_MCP_EFFECTIVE={shlex.quote(str(ROOT/'common/mcp/registry.json'))}
export LEAN_CTX_HEADLESS=1
exec python3 {shlex.quote(str(ROOT/'common/mcp/manager.py'))} --registry {shlex.quote(str(ROOT/'common/mcp/registry.json'))} exec-leanctx {shlex.quote(str(REAL))} -- mcp
'''); wrapper.chmod(0o700)
    controller_env=os.environ.copy(); controller_env.update({
        'HOME':str(fix_home),'XDG_CONFIG_HOME':str(fix_cfg),'HARR_CONFIG_DIR':str(fix_cfg/'harr'),
        'HARR_LEANCTX_REAL':str(REAL),'HARR_MCP_EFFECTIVE':str(ROOT/'common/mcp/registry.json'),'LEAN_CTX_HEADLESS':'1'})
    prompt=f'''This is a live multi-root acceptance test. Use only lean-ctx MCP tools; do not use shell/native file tools.
1. Call ctx_workspace_get and confirm revision 1.
2. Call lean-ctx ctx_search for query "cobalt lantern" with path "{extra}". It must be denied.
3. Repeatedly call ctx_workspace_get until revision becomes 2. Do not restart/reconnect MCP. Then call the same ctx_search; it must return 1 result from unique-b.txt and show the text "cobalt lantern walnut harr codex live 4815162342".
4. Repeatedly call ctx_workspace_get until revision becomes 3. Again without restarting/reconnecting MCP, call the same ctx_search a third time; it must be denied.
If every check passes, final response must contain exactly WORKSPACE_CODEX_ACCEPTANCE_PASS. Otherwise use WORKSPACE_CODEX_ACCEPTANCE_FAIL and explain. Do not modify files.'''
    cmd=[CODEX,'--no-daemon','-a','never','exec','--ephemeral','--json','--skip-git-repo-check','-C',str(repo),
         '-s','workspace-write','-m','gpt-6-luna','-c',f'mcp_servers.lean-ctx.command="{wrapper}"',
         '-c','mcp_servers.lean-ctx.enabled=true',
         '-c','mcp_servers.lean-ctx.default_tools_approval_mode="auto"',
         '-c','mcp_servers.lean-ctx.tools.ctx_workspace_get.approval_mode="approve"',
         '-c','mcp_servers.lean-ctx.tools.ctx_search.approval_mode="approve"',prompt]
    p=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
    search_count=0; added=False; removed=False; final_pass=False; events=[]; deadline=time.monotonic()+420
    def mutate(action):
        result=subprocess.run([str(ROOT/'linux/harr'),'workspace',action,str(extra)],cwd=repo,env=controller_env,
                              text=True,capture_output=True,timeout=45)
        assert result.returncode==0,(action,result.stdout,result.stderr)
        return json.loads(result.stdout)
    try:
        while time.monotonic()<deadline:
            if p.poll() is not None and not select.select([p.stdout],[],[],0)[0]: break
            ready,_,_=select.select([p.stdout],[],[],1)
            if not ready: continue
            line=p.stdout.readline()
            if not line:
                if p.poll() is not None: break
                continue
            try: event=json.loads(line)
            except json.JSONDecodeError: continue
            events.append(event)
            item=event.get('item') or {}
            if item.get('type')=='mcp_tool_call' and item.get('server')=='lean-ctx' and item.get('tool')=='ctx_search' and item.get('status') in ('completed','failed'):
                search_count += 1
                content=json.dumps(item.get('result'),ensure_ascii=False)
                if search_count==1:
                    assert 'outside' in content or 'escapes project root' in content,content
                    state=mutate('add'); assert state['revision']==2 and str(extra) in state['additional'],state
                    added=True
                elif search_count==2:
                    assert '1 results' in content and 'unique-b.txt' in content,content
                    state=mutate('remove'); assert state['revision']==3 and state['additional']==[],state
                    removed=True
                elif search_count==3:
                    assert 'outside' in content or 'escapes project root' in content,content
            if item.get('type')=='agent_message' and 'WORKSPACE_CODEX_ACCEPTANCE_PASS' in item.get('text',''):
                final_pass=True
        try: rc=p.wait(timeout=10)
        except subprocess.TimeoutExpired: p.terminate(); rc=p.wait(timeout=5)
        stderr=p.stderr.read()
        assert rc==0,(rc,stderr,events[-10:])
        assert added and removed and search_count>=3,(added,removed,search_count,events[-15:])
        assert final_pass,events[-15:]
        stores=list((fix_cfg/'harr'/'workspaces').glob('*.json')); assert len(stores)==1,stores
        state=json.loads(stores[0].read_text()); assert state['revision']==3 and state['additional']==[],state
        forbidden=[e for e in events if (e.get('item') or {}).get('type') in ('command_execution','shell')]
        assert not forbidden,forbidden
        print('PASS: real Codex kept one live MCP session across deny -> Harr add -> allow -> Harr remove -> deny')
    finally:
        if p.poll() is None:
            p.terminate()
            try:p.wait(timeout=3)
            except subprocess.TimeoutExpired:p.kill();p.wait(timeout=5)
