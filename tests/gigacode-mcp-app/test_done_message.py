#!/usr/bin/env python3
"""Contract: only one active MCP App may initiate a completion message."""
import contextlib
import importlib.util
import io
import json
import pathlib
import tempfile
import uuid

root = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('gigacode_done_test', root/'common/mcp/gigacode_app/server.py')
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

with tempfile.TemporaryDirectory() as td:
    app.STATE = pathlib.Path(td)
    sid = str(uuid.uuid4())
    scope = str(uuid.uuid4())
    other = str(uuid.uuid4())
    app.lookup_scope = lambda given, session: {'session_id': sid} if session == sid and given in (scope, other) else None
    current = 'RUNNING'
    app.gc.status_tool = lambda arguments: {'content':[{'type':'text','text':json.dumps({'status':current})}]}

    def call(action, scope_id, owner_token=None):
        arguments = {'session_id':sid,'scope_id':scope_id}
        if owner_token is not None:
            arguments['owner_token'] = owner_token
        capture = io.StringIO()
        with contextlib.redirect_stdout(capture):
            app.dispatch({'jsonrpc':'2.0','id':1,'method':'tools/call',
                          'params':{'name':action,'arguments':arguments}})
        payload = json.loads(capture.getvalue())
        assert 'error' not in payload, payload
        return payload['result']['structuredContent']

    assert call('claim_done_notification_ui', scope)['claimed'] is False
    current = 'DONE'
    claimed = call('claim_done_notification_ui', scope, 'panel-a')
    assert claimed['claimed'] is True
    assert claimed['handoff']['status'] == 'DONE'
    assert call('claim_done_notification_ui', scope, 'panel-a')['claimed'] is True
    assert call('claim_done_notification_ui', other, 'panel-b')['claimed'] is False
    call('release_done_notification_ui', other, 'panel-b')
    assert call('claim_done_notification_ui', other)['claimed'] is False
    call('release_done_notification_ui', scope, 'panel-a')
    assert call('claim_done_notification_ui', other)['claimed'] is True
    assert call('claim_done_notification_ui', scope)['claimed'] is False

names = {tool['name']:tool for tool in app.tools()}
for name in ('claim_done_notification_ui', 'release_done_notification_ui'):
    assert names[name]['_meta']['ui']['visibility'] == ['app']
html = (root/'common/mcp/gigacode_app/panel.html').read_text()
ein_html = (root/'common/mcp/ein_app/panel.html').read_text()
assert "request('ui/message',{role:'user'" in html
assert 'notifyEligible' in html
assert 'JSON.stringify(claim.handoff)' in html
assert 'do not call gigacode status/messages/wait' in html
assert "append('Вызов:" not in html
assert "append('— '+d.status" not in html
for panel in (html,):
    assert 'owner_token:panelId' in panel or 'const owner_token=panelId' in panel
    assert 'for(let attempt=0;attempt<3&&!stopped;attempt++)' in panel
    assert "release_done_notification_ui',args" in panel
    assert 'clearTimeout(p.timer)' in panel
    assert "pending.clear();lifecycle('pagehide')" in panel
assert 'claim_done_notification_ui' not in ein_html
assert 'release_done_notification_ui' not in ein_html
assert "request('ui/message'" not in ein_html  # Ein panel is monitor-only; the inline marker owns completion.
assert 'poll_ein_ui' in ein_html and "status.textContent=d.status||'RUNNING'" in ein_html
assert "— '+d.status+' —" in ein_html  # terminal status remains visible in the monitor panel
print('MCP App DONE notification contract: PASS')
