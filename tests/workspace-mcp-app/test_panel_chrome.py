#!/usr/bin/env python3
from __future__ import annotations
import html, json, shutil, subprocess, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PANEL = (ROOT / 'common/mcp/workspace_app/panel.html').read_text(encoding='utf-8')
CHROME = shutil.which('google-chrome') or shutil.which('chromium') or shutil.which('chromium-browser')
if not CHROME:
    print('SKIP: Chrome/Chromium not installed')
    raise SystemExit(0)

initial = {
    'workspaceId':'11111111-1111-4111-8111-111111111111',
    'name':'repo-a','project':'/work/repo-a','primary':'/work/repo-a','revision':1,
    'additional':['/work/shared','/work/missing'],
    'roots':[
        {'path':'/work/repo-a','kind':'primary','status':'OK'},
        {'path':'/work/shared','kind':'additional','status':'OK'},
        {'path':'/work/missing','kind':'additional','status':'missing'},
    ],
    'notice':'LeanCTX root inclusion does not grant Codex filesystem read/write permission.'
}
# srcdoc keeps the test host and app frame same-origin so the host can drive clicks.
srcdoc = html.escape(PANEL, quote=True)
host = f'''<!doctype html><html><body style="margin:0;background:#202124;color:#e8eaed;width:860px">
<iframe id="app" style="width:820px;height:560px;border:0" srcdoc="{srcdoc}"></iframe>
<div id="result" data-test="RUNNING"></div>
<script>
const frame=document.getElementById('app'), result=document.getElementById('result');
let state={json.dumps(initial)};
function snapshot(){{return JSON.parse(JSON.stringify(state))}}
function send(o){{frame.contentWindow.postMessage(o,'*')}}
function ok(id,value){{send({{jsonrpc:'2.0',id,result:value}})}}
function err(id,message){{send({{jsonrpc:'2.0',id,error:{{code:-32000,message}}}})}}
function toolResult(payload){{return {{content:[{{type:'text',text:'ok'}}],structuredContent:payload}}}}
window.addEventListener('message',e=>{{
  if(e.source!==frame.contentWindow)return; const o=e.data||{{}};
  if(o.method==='ui/initialize'){{ok(o.id,{{protocolVersion:'2026-01-26',capabilities:{{}}}});return}}
  if(o.method==='ui/notifications/initialized'){{setTimeout(()=>send({{jsonrpc:'2.0',method:'ui/notifications/tool-result',params:{{result:toolResult(snapshot())}}}}),20);setTimeout(run,100);return}}
  if(o.method==='tools/call'){{const name=o.params?.name,a=o.params?.arguments||{{}};
    if(name==='workspace_ui_get'){{ok(o.id,toolResult(snapshot()));return}}
    if(name==='workspace_ui_add_root'){{if(a.expected_revision!==state.revision){{err(o.id,'revision conflict: expected '+a.expected_revision+', current '+state.revision);return}}
      state.revision++;state.additional.push(a.path);state.roots.push({{path:a.path,kind:'additional',status:'OK'}});ok(o.id,toolResult(snapshot()));return}}
    if(name==='workspace_ui_remove_root'){{if(a.expected_revision!==state.revision){{err(o.id,'revision conflict: expected '+a.expected_revision+', current '+state.revision);return}}
      state.revision++;state.additional=state.additional.filter(x=>x!==a.path);state.roots=state.roots.filter(x=>x.path!==a.path);ok(o.id,toolResult(snapshot()));return}}
    err(o.id,'unknown tool');
  }}
}});
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function waitFor(fn,label){{for(let i=0;i<80;i++){{if(fn())return;await sleep(25)}}throw Error('timeout '+label)}}
async function run(){{try{{const d=frame.contentDocument;await waitFor(()=>d.getElementById('revision')?.textContent==='rev 1','initial');
  const input=d.getElementById('path');input.value='/work/new-root';input.dispatchEvent(new Event('input',{{bubbles:true}}));d.getElementById('add').click();
  await waitFor(()=>d.getElementById('revision').textContent==='rev 2'&&d.getElementById('message').textContent.includes('добавлен'),'add');
  // External writer advances revision. The panel must surface conflict and reload rev 3 rather than erase the error.
  state.revision=3;input.value='/work/stale-add';input.dispatchEvent(new Event('input',{{bubbles:true}}));d.getElementById('add').click();
  await waitFor(()=>d.getElementById('revision').textContent==='rev 3'&&d.getElementById('message').textContent.includes('другом окне'),'conflict');
  const buttons=[...d.querySelectorAll('[data-remove]')];const target=buttons.find(b=>b.parentElement.querySelector('.path')?.textContent==='/work/new-root');if(!target)throw Error('remove target missing');
  target.click();if(target.textContent!=='Подтвердить')throw Error('remove did not require confirmation');target.click();
  await waitFor(()=>d.getElementById('revision').textContent==='rev 4'&&d.getElementById('message').textContent.includes('удалён'),'remove');
  result.dataset.test='PASS';result.textContent='PASS';document.body.dataset.test='PASS';
}}catch(e){{result.dataset.test='FAIL';result.textContent='FAIL '+e.message;document.body.dataset.test='FAIL';}}}}
</script></body></html>'''

with tempfile.TemporaryDirectory(prefix='harr-workspace-panel-') as td:
    base=Path(td); host_path=base/'host.html'; shot=base/'panel.png'; host_path.write_text(host,encoding='utf-8')
    proc=subprocess.run([CHROME,'--headless=new','--disable-gpu','--no-sandbox','--allow-file-access-from-files','--window-size=860,620','--virtual-time-budget=7000',f'--screenshot={shot}','--dump-dom',host_path.as_uri()],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=30,check=False)
    if proc.returncode != 0:
        raise SystemExit('Chrome failed:\n'+proc.stderr[-4000:])
    if 'data-test="PASS"' not in proc.stdout:
        raise AssertionError('Panel browser acceptance failed:\n'+proc.stdout[-5000:]+'\n'+proc.stderr[-3000:])
    out=Path('/tmp/harr-workspace-panel.png'); shutil.copy2(shot,out)
    print(f'PASS: browser Add/conflict-refresh/two-step Remove UI acceptance; screenshot={out}')
