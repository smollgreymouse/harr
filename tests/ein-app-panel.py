#!/usr/bin/env python3
"""MCP App panel migration: per-instance registration, authorization and isolation.

No Codex CLI, real host configuration, or model is invoked.
"""
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
from unittest.mock import patch
from jsonrpc_reader import join_jsonrpc_reader, read_jsonrpc_line

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'common/mcp/ein_app/server.py'
HOST=ROOT/'common/hosts/codex-config.py'

def rpc(process,number,method,params=None):
    process.stdin.write(json.dumps({'jsonrpc':'2.0','id':number,'method':method,'params':params or {}})+'\n')
    process.stdin.flush()
    value=json.loads(read_jsonrpc_line(process,6))
    assert value.get('id')==number,value
    return value

with tempfile.TemporaryDirectory(prefix='ein-ui-harness-') as tmp:
    base=Path(tmp)
    config_root=base/'harr'; (config_root/'einherjar').mkdir(parents=True)
    config={'schema':2,'instances':[{'id':'gigacode','adapter':'gigacode','enabled':True},{'id':'open-review','adapter':'opencode','enabled':True},{'id':'disabled','adapter':'opencode','enabled':False}]}
    (config_root/'einherjar/instances.json').write_text(json.dumps(config))
    home=base/'home'; home.mkdir()
    env={**os.environ,'HOME':str(home),'HARR_CONFIG_DIR':str(config_root),'XDG_CACHE_HOME':str(base/'cache'),'XDG_STATE_HOME':str(base/'state'),'PYTHONPATH':str(ROOT)}
    mod_spec=importlib.util.spec_from_file_location('test_codex_host_placement',HOST)
    host=importlib.util.module_from_spec(mod_spec)
    mod_spec.loader.exec_module(host)
    host.CONFIG=base/'codex-config.toml'
    host.CODEX_HOME=base
    host.CONFIG.write_text('[mcp_servers.user-owned]\ncommand="untouched"\n')
    old_app=ROOT/'common/mcp/gigacode_app/server.py'
    host.CONFIG.write_text('[mcp_servers.harr-gigacode-app]\ncommand="/old/python"\nargs=['+json.dumps(str(old_app), ensure_ascii=False)+']\n\n[mcp_servers.keep-user-app]\ncommand="custom"\n')
    host.retire_gigacode_app()
    retired=tomllib.loads(host.CONFIG.read_text())['mcp_servers']
    assert 'harr-gigacode-app' not in retired and 'keep-user-app' in retired
    # Same name with a different script is user-owned and must survive.
    host.CONFIG.write_text('[mcp_servers.harr-gigacode-app]\ncommand="custom"\nargs=["/user/app.py"]\n')
    host.retire_gigacode_app()
    assert 'harr-gigacode-app' in tomllib.loads(host.CONFIG.read_text())['mcp_servers']
    alias_root=base/'repo-alias'
    alias_root.symlink_to(ROOT,target_is_directory=True)
    alias_app=alias_root/'common/mcp/gigacode_app/server.py'
    host.CONFIG.write_text('[mcp_servers.harr-gigacode-app]\ncommand="/old/python"\nargs=['+json.dumps(str(alias_app), ensure_ascii=False)+']\n')
    host.retire_gigacode_app()
    assert 'harr-gigacode-app' not in tomllib.loads(host.CONFIG.read_text()).get('mcp_servers',{})
    host.CONFIG.write_text('[mcp_servers.user-owned]\ncommand="untouched"\n')
    prior=os.environ.get('HARR_CONFIG_DIR')
    os.environ['HARR_CONFIG_DIR']=str(config_root)
    try:
        host.apply_named_ein_apps()
        host.apply_named_ein_apps()  # idempotent; no duplicate namespace
        data=tomllib.loads(host.CONFIG.read_text())
        assert set(data['mcp_servers'])=={'user-owned','gigacode','open-review','harr-ein-ui'},data
        assert data['mcp_servers']['user-owned']['command']=='untouched'
        assert data['mcp_servers']['harr-ein-ui']['env']['HARR_CONFIG_DIR']==str(config_root)
        assert data['mcp_servers']['harr-ein-ui']['env']['HARR_EIN_UI_MANAGED']=='1'
        for direct_name in ('gigacode','open-review'):
            direct=data['mcp_servers'][direct_name]
            assert direct['args']==[str(ROOT/'common/mcp/ein_direct.py'),direct_name]
            assert direct['env']['HARR_CONFIG_DIR']==str(config_root)
            assert direct['env']['HARR_EIN_DIRECT_MANAGED']=='1'
            assert direct['tools']['ein']['approval_mode']=='auto'
        assert host.named_ein_apps_are_managed(data)

        # A source-to-package install changes the canonical path. The explicit
        # ownership marker lets Harr migrate its own panel without touching a
        # user server that happens to use the same reserved name.
        package_ui=base/'package/usr/lib/harr/common/mcp/ein_app/server.py'
        with patch.object(host, 'ein_ui_path', return_value=package_ui):
            host.apply_named_ein_apps()
        packaged=tomllib.loads(host.CONFIG.read_text())['mcp_servers']['harr-ein-ui']
        assert packaged['args']==[str(package_ui)]
        host.apply_named_ein_apps()
        managed_text=host.CONFIG.read_text()

        # A same-named user MCP must fail closed rather than be overwritten.
        collision='[mcp_servers.open-review]\ncommand="user-owned"\n'
        host.CONFIG.write_text(collision)
        try:
            host.apply_named_ein_apps()
        except RuntimeError as exc:
            assert 'collision' in str(exc).lower()
        else:
            raise AssertionError('expected direct Ein/user MCP name collision')
        assert host.CONFIG.read_text()==collision
        host.CONFIG.write_text(managed_text)

        # Reconcile removal and keep original third-party MCP.
        config['instances'][1]['enabled']=False
        (config_root/'einherjar/instances.json').write_text(json.dumps(config))
        host.apply_named_ein_apps()
        names=set(tomllib.loads(host.CONFIG.read_text())['mcp_servers'])
        assert names=={'user-owned','gigacode','harr-ein-ui'},names
        config['instances'][1]['enabled']=True
        (config_root/'einherjar/instances.json').write_text(json.dumps(config))
    finally:
        if prior is None:os.environ.pop('HARR_CONFIG_DIR',None)
        else:os.environ['HARR_CONFIG_DIR']=prior

    # Exercise the panel's actual lazy backend loader for the migrated
    # GigaCode instance; it must bind the private runtime and preserve its
    # configured instance cache namespace.
    app_spec=importlib.util.spec_from_file_location('test_ein_app_backend',SCRIPT)
    app_module=importlib.util.module_from_spec(app_spec)
    with patch.dict(os.environ,env):
        app_spec.loader.exec_module(app_module)
        gigacode_backend=app_module.backend('gigacode')
        assert callable(gigacode_backend._load_state)
        workspace_key=hashlib.sha256(str(ROOT.resolve()).encode()).hexdigest()[:12]
        assert gigacode_backend.CACHE_ROOT==base/'cache/gigacode-mcp'/workspace_key

    for instance in ('gigacode','open-review'):
        penv={**env}
        p=subprocess.Popen([sys.executable,str(SCRIPT)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,cwd=base,env=penv,bufsize=1)
        try:
            response=rpc(p,1,'tools/list')['result']['tools']
            tools={t['name']:t for t in response}
            assert {'show_ein_live','panel_event_ui','list_ein_ui','poll_ein_ui'}==set(tools)
            assert tools['show_ein_live']['_meta']['ui']['visibility']==['model','app']
            for hidden in ('panel_event_ui','list_ein_ui','poll_ein_ui'):
                assert tools[hidden]['_meta']['ui']['visibility']==['app']
            uri=tools['show_ein_live']['_meta']['ui']['resourceUri']
            assert uri=='ui://harr-ein-ui/live.html'
            html=rpc(p,2,'resources/read',{'uri':uri})['result']['contents'][0]['text']
            assert "Harr · Ein" in html and 'poll_ein_ui' in html and 'show_gigacode_live' not in html
            assert 'ui/message' not in html and 'claim_done_notification_ui' not in html
            unknown='11111111-1111-1111-1111-111111111111'
            reply=rpc(p,3,'tools/call',{'name':'show_ein_live','arguments':{'instance':instance,'session_id':unknown}})
            assert 'error' in reply  # Cannot attach to arbitrary or other-instance sessions.
            print(instance,'read-only isolated panel PASS')
        finally:
            p.terminate()
            try:p.wait(timeout=5)
            except subprocess.TimeoutExpired:p.kill();p.wait(timeout=5)
            join_jsonrpc_reader(p)
    # One real detached fake job, opened by the direct MCP App after start.
    fake=base/'fake_agent.py'
    fake.write_text('import json\nprint(json.dumps({"status":"DONE","summary":"panel-connected","changed":[],"verified":[{"criterion":"smoke","check":"fake","result":"PASS","evidence":"0"}],"self_review":{"criteria_complete":True,"diff_scope_clean":True,"unverified":[]},"escalation":None,"blockers":[]}))\n')
    config['instances'].append({'id':'fake-panel','adapter':'custom','enabled':True,'definition':{'adapter':'command-template','start':[sys.executable,str(fake),'{prompt}']}})
    (config_root/'einherjar/instances.json').write_text(json.dumps(config))
    import time
    mcp=ROOT/'common/mcp/einherjar_server.py'
    penv={**env,'HARR_EIN_INSTANCE':'fake-panel'}
    runtime=config_root/'einherjar/runtime/fake-panel';runtime.mkdir(parents=True)
    (runtime/'einherjar.json').write_text(json.dumps({'schema':1,'default_backend':'fake-panel','backends':{'fake-panel':config['instances'][-1]['definition']}}))
    penv['HARR_CONFIG_DIR']=str(runtime)
    engine=subprocess.Popen([sys.executable,str(mcp)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,cwd=base,env=penv,bufsize=1)
    try:
        response=rpc(engine,10,'tools/call',{'name':'ein','arguments':{'action':'start','prompt':'smoke'}})
        sid=response['result']['structuredContent']['session_id']
        for i in range(30):
            current=rpc(engine,20+i,'tools/call',{'name':'ein','arguments':{'action':'status','session_id':sid}})['result']['structuredContent']
            if current['status'] in ('DONE','FAILED','ESCALATE'):break
            time.sleep(.2)
        assert current['status']=='DONE',current
        # App uses original Harr config dir, but engine used instance-specific runtime config.
        appenv={**env}
        app=subprocess.Popen([sys.executable,str(SCRIPT)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,cwd=base,env=appenv,bufsize=1)
        try:
            attached=rpc(app,50,'tools/call',{'name':'show_ein_live','arguments':{'instance':'fake-panel','session_id':sid}})['result']['structuredContent']
            assert attached['status']=='DONE'
            polled=rpc(app,51,'tools/call',{'name':'poll_ein_ui','arguments':{'instance':'fake-panel','session_id':sid,'scope_id':attached['scope_id'],'after_revision':0,'wait_ms':0}})['result']['structuredContent']
            assert polled['status']=='DONE',polled
            denied=rpc(app,53,'tools/call',{'name':'poll_ein_ui','arguments':{'instance':'open-review','session_id':sid,'scope_id':attached['scope_id'],'wait_ms':0}})
            assert 'error' in denied, denied
            denied=rpc(app,54,'tools/call',{'name':'show_ein_live','arguments':{'instance':'open-review','session_id':sid}})
            assert 'error' in denied, denied
            listed=rpc(app,52,'tools/call',{'name':'list_ein_ui','arguments':{}})['result']['structuredContent']
            assert {'instance':'fake-panel','session_id':sid} in listed['sessions']

            print('fake-panel detached lifecycle + UI restore PASS')
        finally:
            app.terminate()
            try:app.wait(timeout=5)
            except subprocess.TimeoutExpired:app.kill();app.wait(timeout=5)
            join_jsonrpc_reader(app)
    finally:
        engine.terminate()
        try:engine.wait(timeout=5)
        except subprocess.TimeoutExpired:engine.kill();engine.wait(timeout=5)
        join_jsonrpc_reader(engine)
    print('Named Ein Desktop App panel: PASS')
