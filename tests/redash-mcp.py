#!/usr/bin/env python3
"""Redash registry, CLI integration, and tool-list/call isolation tests."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('manager', ROOT / 'common/mcp/manager.py')
manager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manager)
registry = manager.load_registry(ROOT / 'common/mcp/registry.json')
redash = next(s for s in registry['servers'] if s['name'] == 'redash')
assert redash['runtime']['package'] == '@suthio/redash-mcp'
assert redash['runtime']['version'] == '0.1.1'
assert redash['runtime']['readonly_proxy'] == 'redash_readonly_proxy.py'
assert redash['doctor']['required_tools'] == ['get_query','execute_query','execute_adhoc_query']
assert redash['secrets'][0]['target']['name'] == 'REDASH_API_KEY'
assert redash['secrets'][0]['memento_id'] == 'mcp/redash/default'
assert redash['transport'] == 'stdio'

with tempfile.TemporaryDirectory() as tmp:
    backend = Path(tmp) / 'backend.py'
    backend.write_text('''import json,sys,os
for line in sys.stdin:
 q=json.loads(line)
 if q.get('method')=='tools/list':
  r={'tools':[{'name':n,'description':'upstream description','inputSchema':{'type':'object','properties':{'query':{'type':'string'},'dataSourceId':{'type':'integer'},'applyAutoLimit':{'type':'boolean'}}}} for n in ('get_query','execute_query','execute_parameterized_query','execute_adhoc_query','update_query','delete_visualization')]}
 else:
  with open(os.environ['HARR_TEST_BACKEND_LOG'],'a') as f: f.write(json.dumps(q)+chr(10))
  r={'content':[{'type':'text','text':'backend reached'}]}
 print(json.dumps({'jsonrpc':'2.0','id':q.get('id'),'result':r}),flush=True)
''')
    call_log = Path(tmp) / 'calls.jsonl'
    env = os.environ.copy(); env['HARR_TEST_BACKEND_LOG'] = str(call_log)
    p = subprocess.Popen([sys.executable, str(ROOT/'common/mcp/redash_readonly_proxy.py'), sys.executable, str(backend)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
    def send(req):
        p.stdin.write(json.dumps(req)+'\n');p.stdin.flush()
        return json.loads(p.stdout.readline())
    try:
        listed=send({'jsonrpc':'2.0','id':1,'method':'tools/list'})
        names = [t['name'] for t in listed['result']['tools']]
        assert names == ['get_query','execute_query','execute_parameterized_query','execute_adhoc_query']
        adhoc = next(t for t in listed['result']['tools'] if t['name']=='execute_adhoc_query')
        assert adhoc['inputSchema']['properties']['dataSourceId']['enum'] == [20]
        for method,name in [('tools/call','update_query'),('tools/call','list_unknown'),('resources/read',None)]:
            result=send({'jsonrpc':'2.0','id':2,'method':method,'params':{'name':name}})
            assert result['error']['code']==-32601, result
        ok=send({'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'get_query'}})
        assert ok['result']['content'][0]['text']=='backend reached'
        denied=send({'jsonrpc':'2.0','id':4,'method':'tools/call','params':{'name':'execute_adhoc_query','arguments':{'query':'SELECT 1','dataSourceId':10}}})
        assert denied['error']['code']==-32602, denied
        ok=send({'jsonrpc':'2.0','id':5,'method':'tools/call','params':{'name':'execute_adhoc_query','arguments':{'query':'SELECT start_date FROM campaign','dataSourceId':20,'applyAutoLimit':False}}})
        assert ok['result']['content'][0]['text']=='backend reached'
        forwarded=json.loads(call_log.read_text().splitlines()[-1])
        assert forwarded['params']['name']=='execute_adhoc_query'
        assert forwarded['params']['arguments']['dataSourceId']==20
        assert forwarded['params']['arguments']['applyAutoLimit'] is True
    finally:
        p.stdin.close();p.wait(timeout=5)
print('Redash read-only proxy + registry: PASS')
