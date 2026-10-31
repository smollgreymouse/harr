#!/usr/bin/env python3
"""Named Ein CLI/registry/MCP flow without any real external models."""
import json
import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
PYTHON=sys.executable
with tempfile.TemporaryDirectory(prefix='harr-ein-named-') as tmp:
    base=Path(tmp)
    env={**os.environ, 'HOME':str(base/'home'),'XDG_CONFIG_HOME':str(base/'home/.config'),'XDG_CACHE_HOME':str(base/'home/.cache'),'HARR_CONFIG_DIR':str(base/'home/.config/harr'),'PYTHONPATH':str(ROOT)}
    work=base/'workspace';work.mkdir()
    # A migrated named instance named "gigacode" must keep reading its old
    # standalone cache namespace; other ids receive isolated namespaces.
    workspace_key=hashlib.sha256(str(work.resolve()).encode()).hexdigest()[:12]
    legacy_cache=base/'home/.cache/gigacode-mcp'/workspace_key
    legacy_cache.mkdir(parents=True)
    with patch.dict(os.environ,env):
        ein_spec=importlib.util.spec_from_file_location('ein_state_writer',ROOT/'common/mcp/einherjar_server.py')
        ein_state_writer=importlib.util.module_from_spec(ein_spec)
        ein_spec.loader.exec_module(ein_state_writer)
    ein_state_writer.CACHE_ROOT=base/'ein-atomic-state';ein_state_writer.CACHE_ROOT.mkdir()
    concurrent_sid='22222222-2222-4222-8222-222222222222'
    replace_barrier=threading.Barrier(2)
    first_replace_lock=threading.Lock()
    first_replace_sources=set()
    original_replace=os.replace
    def synchronized_replace(source,destination):
        source_key=os.fspath(source)
        with first_replace_lock:
            first_attempt=source_key not in first_replace_sources
            first_replace_sources.add(source_key)
        if first_attempt:
            replace_barrier.wait(timeout=5)
        return original_replace(source,destination)
    concurrent_payloads=[{'phase':'running','writer':'worker'},{'phase':'queued','writer':'launcher'}]
    with patch.object(os,'replace',side_effect=synchronized_replace):
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(ein_state_writer._write_state,concurrent_sid,payload) for payload in concurrent_payloads]
            for future in futures:future.result(timeout=10)
    persisted=ein_state_writer._load_state(concurrent_sid)
    temp_files=list(ein_state_writer.CACHE_ROOT.glob(f'.{concurrent_sid}.state.json.*.tmp'))
    assert persisted in concurrent_payloads and not temp_files,(persisted,temp_files)
    transient_sid='33333333-3333-4333-8333-333333333333'
    original_replace=os.replace
    replace_attempts=[]
    def transient_permission_error(source,destination):
        replace_attempts.append((source,destination))
        if len(replace_attempts)==1:raise PermissionError('simulated transient Windows sharing violation')
        return original_replace(source,destination)
    with patch.object(os,'replace',side_effect=transient_permission_error), patch.object(ein_state_writer.time,'sleep'):
        ein_state_writer._write_state(transient_sid,{'phase':'finished','writer':'retry'})
    assert ein_state_writer._load_state(transient_sid)=={'phase':'finished','writer':'retry'}
    assert len(replace_attempts)==2
    print('Ein concurrent atomic state writes PASS')
    legacy_sid='11111111-1111-4111-8111-111111111111'
    legacy_handoff={'status':'DONE','summary':'existing history','changed':[],'verified':[{'criterion':'old','check':'state','result':'PASS','evidence':'preserved'}],'escalation':None,'blockers':[]}
    (legacy_cache/f'{legacy_sid}.state.json').write_text(json.dumps({'phase':'finished','session_id':legacy_sid,'handoff':legacy_handoff}))
    previous_cwd=Path.cwd()
    previous_instance=os.environ.get('HARR_EIN_INSTANCE')
    os.chdir(work)
    try:
        runtime_path=ROOT/'common/executor/gigacode_runtime.py'
        with patch.dict(os.environ,env):
            for instance_id in ('gigacode','fake-one','fake-two'):
                os.environ['HARR_EIN_INSTANCE']=instance_id
                runtime_spec=importlib.util.spec_from_file_location(f'ein_cache_{instance_id}',runtime_path)
                runtime=importlib.util.module_from_spec(runtime_spec)
                runtime_spec.loader.exec_module(runtime)
                if instance_id=='gigacode':
                    assert runtime.CACHE_ROOT==legacy_cache
                    preserved=runtime.status_tool({'session_id':legacy_sid})['structuredContent']
                    assert preserved['summary']=='existing history' and preserved['verified']==legacy_handoff['verified']
                else:
                    assert runtime.CACHE_ROOT==base/f'home/.cache/harr/einherjar/{instance_id}'/workspace_key
    finally:
        os.chdir(previous_cwd)
        if previous_instance is None:os.environ.pop('HARR_EIN_INSTANCE',None)
        else:os.environ['HARR_EIN_INSTANCE']=previous_instance
    fake=work/'fake.py'
    fake.write_text('''import json
print(json.dumps({"status":"DONE","summary":"named fake worker done","changed":[],"verified":[{"criterion":"fake","check":"fake run","result":"PASS","evidence":"exit 0"}],"self_review":{"criteria_complete":True,"diff_scope_clean":True,"unverified":[]},"escalation":None,"blockers":[]}))
''')
    definition=base/'definition.json'
    definition.write_text(json.dumps({'adapter':'command-template','start':[PYTHON,str(fake),'{prompt}']}))
    cli=[PYTHON,str(ROOT/'common/mcp/ein_instances.py')]
    def run(*args,ok=True):
        p=subprocess.run([*cli,*args],env=env,cwd=work,text=True,encoding='utf-8',capture_output=True)
        if ok:assert p.returncode==0,(args,p.stdout,p.stderr)
        else:assert p.returncode!=0,args
        return p.stdout
    # Direct Codex frontdoors reserve Harr-owned host namespaces.
    run('add','--id','harr-ein-ui','--adapter','opencode',ok=False)

    def failure_evidence(instance_id,session_id):
        cache=(legacy_cache if instance_id=='gigacode' else
               base/'home/.cache/harr/einherjar'/instance_id/workspace_key)
        state_path=cache/f'{session_id}.state.json'
        try:state=json.loads(state_path.read_text())
        except (OSError,ValueError) as exc:return f'state unavailable: {exc}'
        evidence=[f'state={json.dumps(state,ensure_ascii=False)[:2000]}']
        paths=[state.get('worker_log'),state.get('stdout_path'),state.get('stderr_path'),cache/f'{session_id}.runtime.log']
        for raw_path in paths:
            if not raw_path:continue
            path=Path(raw_path)
            try:tail=path.read_bytes()[-4000:].decode('utf-8',errors='replace')
            except OSError:continue
            if tail:evidence.append(f'{path.name} tail (<=4000 bytes):\n{tail}')
        return '\n'.join(evidence)[:12000]
    run('add','--id','fake-one','--adapter','custom','--definition-file',str(definition))
    run('add','--id','fake-two','--adapter','custom','--definition-file',str(definition))
    run('add','--id','gigacode','--adapter','gigacode')
    fake_gigacode=work/'fake-gigacode'
    completion=work/'fake-gigacode-complete'
    ready=work/'fake-gigacode-ready'
    handoff={'status':'DONE','summary':'fake GigaCode completed','changed':['fake.py'],'verified':[{'criterion':'wire','check':'fake CLI','result':'PASS','evidence':'exit 0'}],'self_review':{'criteria_complete':True,'diff_scope_clean':True,'unverified':[]},'escalation':None,'blockers':[]}
    fake_gigacode.write_text(
        f'#!{PYTHON}\nimport json,time\nfrom pathlib import Path\n'
        f'Path({str(ready)!r}).write_text("ready")\n'
        f'while not Path({str(completion)!r}).exists(): time.sleep(0.02)\n'
        f'print(json.dumps({handoff!r}))\n'
    )
    fake_gigacode.chmod(0o755)
    run('edit','gigacode','--executable',str(fake_gigacode))
    codex_home=base/'profiles/codex'
    codex_home.mkdir(parents=True)
    (codex_home/'config.toml').write_text('model = "synthetic"\n')
    run('add','--id','codex-worker','--adapter','codex','--codex-home',str(codex_home))
    assert json.loads(run('show','codex-worker'))['codex_home']==str(codex_home)
    run('add','--id','zcode-worker','--adapter','zcode','--executable',PYTHON)
    assert json.loads(run('show','zcode-worker'))['adapter']=='zcode'
    assert 'found (no model calls)' in run('test','zcode-worker')
    run('add','--id','bad-profile','--adapter','opencode','--codex-home',str(codex_home),ok=False)
    run('add','--id','bad-relative','--adapter','codex','--codex-home','relative/path',ok=False)
    run('add','--id','bad-missing','--adapter','codex',ok=False)
    run('add','--id','fake-one','--adapter','custom','--definition-file',str(definition),ok=False)
    run('add','--id','codegraph','--adapter','opencode',ok=False)
    assert 'fake-one' in run('list') and 'fake-two' in run('list')
    run('edit','fake-two','--display-name','Second worker')
    assert json.loads(run('show','fake-two'))['display_name']=='Second worker'
    selection=base/'home/.config/harr/mcp-selection.json'
    effective=base/'home/.config/harr/mcp-registry.json'
    select=[PYTHON,str(ROOT/'common/mcp/selector.py'),'--catalog',str(ROOT/'common/mcp/registry.json'),'--selection',str(selection),'--effective',str(effective),'--spec','none']
    subprocess.run(select,env=env,check=True,capture_output=True)
    data=json.loads(effective.read_text())
    servers={s['name']:s for s in data['servers']}
    assert {'fake-one','fake-two','gigacode','codex-worker','zcode-worker'} <= set(servers)
    assert servers['zcode-worker']['ein_instance']=='zcode-worker'
    assert servers['zcode-worker']['runtime']['script']=='einherjar_server.py'
    assert 'einherjar' not in servers and 'gigacode' not in {s['name'] for s in json.loads((ROOT/'common/mcp/registry.json').read_text())['servers']}
    assert servers['gigacode']['ein_instance']=='gigacode'
    assert servers['gigacode']['runtime']['script']=='einherjar_server.py'
    assert servers['fake-one']['runtime']['script']=='einherjar_server.py'
    assert len([x for x in data['servers'] if x['name']=='gigacode'])==1
    assets=ROOT/'common/mcp/assets.py'
    rendered=base/'generated-policy.md'
    subprocess.run([PYTHON,str(assets),'filter-text','--catalog',str(ROOT/'common/mcp/registry.json'),'--registry',str(effective),'--input',str(ROOT/'common/policy/tool-routing.template.md'),'--output',str(rendered)],check=True,env=env)
    assert 'fake-one::ein' in rendered.read_text() and 'fake-two::ein' in rendered.read_text()
    assert 'gigacode::ein' in rendered.read_text()
    assert 'gigacode::gigacode' not in rendered.read_text()
    assert 'only after the user directly instructs you to delegate' in rendered.read_text()
    # Legacy GigaCode's *entire* argument schema is shared, not only action names.
    legacy_source = ROOT/'common/mcp/ein_tool_schema.json'
    canonical_schema = json.loads(legacy_source.read_text())['inputSchema']
    skill_dir = base/'rendered-skill'
    subprocess.run([PYTHON,str(assets),'filter-skill','--catalog',str(ROOT/'common/mcp/registry.json'),'--registry',str(effective),'--source',str(ROOT/'common/skills/harr'),'--output',str(skill_dir)],check=True,env=env)
    assert 'fake-one::ein' in (skill_dir/'SKILL.md').read_text()
    assert (skill_dir/'references/einherjar.md').exists()
    leanctx=base/'leanctx.toml'
    subprocess.run([PYTHON,str(ROOT/'common/mcp/manager.py'),'--registry',str(effective),'render-leanctx','--base',str(ROOT/'common/leanctx/config.base.toml'),'--output',str(leanctx),'--platform','linux','--runner-command','harr-mcp-run'],check=True,env=env)
    for tool_name in ('fake-one','fake-two','gigacode','zcode-worker'):
        assert f'name = "{tool_name}"' in leanctx.read_text()

    manager=[PYTHON,str(ROOT/'common/mcp/manager.py'),'--registry',str(effective),'run']
    if os.name != 'nt': env['HARR_EIN_EXECUTABLE']=str(fake_gigacode)
    for name in ('fake-one','fake-two','gigacode','codex-worker','zcode-worker'):
        proc=subprocess.Popen([*manager,name],env=env,cwd=work,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',bufsize=1)
        def call(i,method,params=None):
            proc.stdin.write(json.dumps({'jsonrpc':'2.0','id':i,'method':method,'params':params or {}})+'\n');proc.stdin.flush()
            raw=proc.stdout.readline();assert raw,proc.stderr.read()
            return json.loads(raw)['result']
        try:
            tools=call(1,'tools/list')['tools']
            assert len(tools)==1 and tools[0]['name']=='ein',(name,tools)
            schema=tools[0]['inputSchema']
            assert schema['properties']['action']['enum']==['start','resume','status','messages','wait','cancel']
            assert 'backend' not in schema['properties']
            assert schema == canonical_schema, name
            if name == 'zcode-worker':
                runtime_config=Path(env['HARR_CONFIG_DIR'])/'einherjar/runtime/zcode-worker/einherjar.json'
                assert json.loads(runtime_config.read_text())=={'schema':1,'default_backend':'zcode','backends':{}}
            if name in {'codex-worker','zcode-worker'} or (name == 'gigacode' and os.name == 'nt'):continue # NEVER invoke a real backend; this fake executable uses a POSIX script.
            rejected=call(2,'tools/call',{'name':'ein','arguments':{'action':'start','backend':'gigacode','prompt':'test'}})
            assert rejected.get('isError')
            started=call(3,'tools/call',{'name':'ein','arguments':{'action':'start','prompt':'fake task'}})['structuredContent']
            assert 'session_id' in started,(name,started)
            sid=started['session_id']
            if name=='gigacode':
                for _ in range(100):
                    status=call(9,'tools/call',{'name':'ein','arguments':{'action':'status','session_id':sid}})['structuredContent']
                    if status['status']=='RUNNING':break
                    time.sleep(.02)
                assert status['status']=='RUNNING',(name,status,failure_evidence(name,sid))
                for _ in range(100):
                    if ready.exists():break
                    time.sleep(.02)
                assert ready.exists(),'fake GigaCode CLI did not start'
                completion.touch()
            for i in range(30):
                status=call(10+i,'tools/call',{'name':'ein','arguments':{'action':'status','session_id':sid}})['structuredContent']
                if status['status']!='RUNNING':break
                time.sleep(.2)
            assert status['status']=='DONE',(name,status,failure_evidence(name,sid))
            assert status['summary']==('fake GigaCode completed' if name=='gigacode' else 'named fake worker done')
            print(name,'MCP tools + lifecycle PASS')
        finally:
            proc.terminate()
            try:proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:proc.kill();proc.communicate()
    run('disable','fake-one')
    data=json.loads(effective.read_text())
    assert 'fake-one' not in {s['name'] for s in data['servers']}
    assert 'fake-two' in {s['name'] for s in data['servers']}
    run('enable','fake-one')
    assert 'fake-one' in {s['name'] for s in json.loads(effective.read_text())['servers']}
    run('remove','fake-two')
    assert 'fake-two' not in {s['name'] for s in json.loads(effective.read_text())['servers']}
    print('Named Ein integration: PASS')
