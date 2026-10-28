#!/usr/bin/env python3
"""Redash registry, CLI integration, and strict tool-list/call isolation tests."""
import importlib.util
import json
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
assert redash['secrets'][0]['target']['name'] == 'REDASH_API_KEY'
assert redash['secrets'][0]['memento_id'] == 'mcp/redash/default'
assert redash['transport'] == 'stdio'

with tempfile.TemporaryDirectory() as tmp:
    backend = Path(tmp) / 'backend.py'
    backend.write_text('''import json,sys
for line in sys.stdin:
 q=json.loads(line)
 if q.get('method')=='tools/list':
  r={'tools':[{'name':n} for n in ('get_query','execute_adhoc_query','update_query','delete_visualization')]}
 else:
  r={'content':[{'type':'text','text':'backend reached'}]}
 print(json.dumps({'jsonrpc':'2.0','id':q.get('id'),'result':r}),flush=True)
''')
    p = subprocess.Popen([sys.executable, str(ROOT/'common/mcp/redash_readonly_proxy.py'), sys.executable, str(backend)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    def send(req):
        p.stdin.write(json.dumps(req)+'\n');p.stdin.flush()
        return json.loads(p.stdout.readline())
    try:
        listed=send({'jsonrpc':'2.0','id':1,'method':'tools/list'})
        assert [t['name'] for t in listed['result']['tools']] == ['get_query']
        for method,name in [('tools/call','update_query'),('tools/call','execute_adhoc_query'),('tools/call','list_unknown'),('resources/read',None)]:
            result=send({'jsonrpc':'2.0','id':2,'method':method,'params':{'name':name}})
            assert result['error']['code']==-32601, result
        ok=send({'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'get_query'}})
        assert ok['result']['content'][0]['text']=='backend reached'
    finally:
        p.stdin.close();p.wait(timeout=5)
print('Redash read-only proxy + registry: PASS')
