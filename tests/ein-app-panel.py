#!/usr/bin/env python3
"""MCP App panel migration: per-instance registration, authorization and isolation.

No Codex CLI, real host configuration, or model is invoked.
"""
import importlib.util
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import tomllib

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'common/mcp/ein_app/server.py'
HOST=ROOT/'common/hosts/codex-config.py'

def rpc(process,number,method,params=None):
    process.stdin.write(json.dumps({'jsonrpc':'2.0','id':number,'method':method,'params':params or {}})+'\n')
    process.stdin.flush()
    assert select.select([process.stdout],[],[],6)[0], 'panel server did not reply'
    raw=process.stdout.readline()
    assert raw,process.stderr.read()
    value=json.loads(raw)
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
    prior=os.environ.get('HARR_CONFIG_DIR')
    os.environ['HARR_CONFIG_DIR']=str(config_root)
    try:
        host.apply_named_ein_apps()
        host.apply_named_ein_apps()  # idempotent; no duplicate namespace
        data=tomllib.loads(host.CONFIG.read_text())
        assert set(data['mcp_servers'])=={'user-owned','harr-ein-ui'},data
        assert data['mcp_servers']['user-owned']['command']=='untouched'
        assert data['mcp_servers']['harr-ein-ui']['env']['HARR_CONFIG_DIR']==str(config_root)
        # Reconcile removal and keep original third-party MCP.
        config['instances'][1]['enabled']=False
        (config_root/'einherjar/instances.json').write_text(json.dumps(config))
        host.apply_named_ein_apps()
        names=set(tomllib.loads(host.CONFIG.read_text())['mcp_servers'])
        assert names=={'user-owned','harr-ein-ui'},names
        config['instances'][1]['enabled']=True
        (config_root/'einherjar/instances.json').write_text(json.dumps(config))
    finally:
        if prior is None:os.environ.pop('HARR_CONFIG_DIR',None)
        else:os.environ['HARR_CONFIG_DIR']=prior

    for instance in ('gigacode','open-review'):
        penv={**env}
        p=subprocess.Popen([sys.executable,str(SCRIPT)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,cwd=base,env=penv,bufsize=1)
        try:
            response=rpc(p,1,'tools/list')['result']['tools']
            tools={t['name']:t for t in response}
            assert {'show_ein_live','panel_event_ui','list_ein_ui','poll_ein_ui','claim_done_notification_ui','release_done_notification_ui'}==set(tools)
            assert tools['show_ein_live']['_meta']['ui']['visibility']==['model','app']
            for hidden in ('panel_event_ui','list_ein_ui','poll_ein_ui','claim_done_notification_ui','release_done_notification_ui'):
                assert tools[hidden]['_meta']['ui']['visibility']==['app']
            uri=tools['show_ein_live']['_meta']['ui']['resourceUri']
            assert uri=='ui://harr-ein-ui/live.html'
            html=rpc(p,2,'resources/read',{'uri':uri})['result']['contents'][0]['text']
            assert "Harr · Ein" in html and 'poll_ein_ui' in html and 'show_gigacode_live' not in html
            unknown='11111111-1111-1111-1111-111111111111'
            reply=rpc(p,3,'tools/call',{'name':'show_ein_live','arguments':{'instance':instance,'session_id':unknown}})
            assert 'error' in reply  # Cannot attach to arbitrary or other-instance sessions.
            print(instance,'read-only isolated panel PASS')
        finally:
            p.terminate()
            try:p.communicate(timeout=5)
            except subprocess.TimeoutExpired:p.kill();p.communicate()
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
            args={'instance':'fake-panel','session_id':sid,'scope_id':attached['scope_id']}
            claim=rpc(app,55,'tools/call',{'name':'claim_done_notification_ui','arguments':args})['result']['structuredContent']
            assert claim['claimed'] and claim['handoff']['status']=='DONE'
            again=rpc(app,56,'tools/call',{'name':'claim_done_notification_ui','arguments':args})['result']['structuredContent']
            assert not again['claimed']
            wrong=rpc(app,57,'tools/call',{'name':'release_done_notification_ui','arguments':{**args,'instance':'open-review'}})
            assert 'error' in wrong
            release=rpc(app,58,'tools/call',{'name':'release_done_notification_ui','arguments':args})['result']['structuredContent']
            assert release['ok']
            reclaimed=rpc(app,59,'tools/call',{'name':'claim_done_notification_ui','arguments':args})['result']['structuredContent']
            assert reclaimed['claimed']

            print('fake-panel detached lifecycle + UI restore PASS')
        finally:
            app.terminate();app.communicate(timeout=5)
    finally:
        engine.terminate();engine.communicate(timeout=5)
    print('Named Ein Desktop App panel: PASS')
