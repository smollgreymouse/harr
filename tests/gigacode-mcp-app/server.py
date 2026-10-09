#!/usr/bin/env python3
"""Isolated MCP App live GigaCode test; only app-only tool returns transcript."""
import sys, json, os, pathlib, importlib.util, traceback, threading, time, uuid
ROOT=pathlib.Path(__file__).resolve().parents[2]
WORK=pathlib.Path.home()/"codex-desktop-test/workspace"
os.chdir(WORK)
spec=importlib.util.spec_from_file_location("harr_test_gigacode",str(ROOT/"common/mcp/gigacode_server.py"))
gc=importlib.util.module_from_spec(spec);spec.loader.exec_module(gc)
URI="ui://harr-gigacode/live.html"
STATIC_URI="ui://harr-gigacode/static-ab.html"
STATE=pathlib.Path.home()/"codex-desktop-test/state"
STATE.mkdir(exist_ok=True,parents=True)
ACTIVE=STATE/"gigacode-ui-sessions.json"
OUTPUT_LOCK=threading.Lock()
REGISTRY_LOCK=threading.Lock()
TERMINAL={"DONE","FAILED","CANCELLED","ESCALATE","TIMEOUT"}
MAX_RESTORED_ACTIVE=8
MAX_RESTORED_FINISHED=3
LOG=STATE/"gigacode-ui-server.jsonl"
HTML=(ROOT/"tests/gigacode-mcp-app/panel.html").read_text()
STATIC_HTML=(ROOT/"tests/gigacode-mcp-app/static-ab.html").read_text()
def record(event,**data):
 with LOG.open("a") as f:f.write(json.dumps({"event":event,**data},ensure_ascii=False)+"\n")
def result(id,obj):
 with OUTPUT_LOCK: print(json.dumps({"jsonrpc":"2.0","id":id,"result":obj},ensure_ascii=False),flush=True)
def err(id,msg):
 with OUTPUT_LOCK: print(json.dumps({"jsonrpc":"2.0","id":id,"error":{"code":-32000,"message":str(msg)}},ensure_ascii=False),flush=True)
def unbox(r):
 return json.loads(r["content"][0]["text"])
def tools():
 return [
 {"name":"show_static_ab","description":"Render a completely static MCP App for A/B layout diagnosis; no worker, scripts or polling.","inputSchema":{"type":"object","properties":{},"additionalProperties":False},"_meta":{"ui":{"resourceUri":STATIC_URI,"visibility":["model","app"]},"ui/resourceUri":STATIC_URI,"openai/outputTemplate":STATIC_URI}},
 {"name":"show_gigacode_live","description":"Start a read-only GigaCode test and show its live output in an embedded panel. Only session ID/status returned to the model; intermediate transcript is app-only.","inputSchema":{"type":"object","properties":{"session_id":{"type":"string","description":"Attach another panel to an existing test session; omit to start new."},"scenario":{"type":"string","enum":["short","long_readonly"]}},"additionalProperties":False},"_meta":{"ui":{"resourceUri":URI,"visibility":["model","app"]},"ui/resourceUri":URI,"openai/outputTemplate":URI}},
 {"name":"panel_event_ui","description":"App-only panel lifecycle diagnostics.","inputSchema":{"type":"object","properties":{"panel_id":{"type":"string"},"event":{"type":"string"},"session_id":{"type":"string"}},"required":["panel_id","event"]},"_meta":{"ui":{"visibility":["app"]}}},
 {"name":"list_gigacode_ui","description":"App-only list of isolated test sessions.","inputSchema":{"type":"object","properties":{}},"_meta":{"ui":{"visibility":["app"]}}},
 {"name":"poll_gigacode_ui","description":"UI only: read progress transcript using a cursor.","inputSchema":{"type":"object","properties":{"session_id":{"type":"string"},"after_revision":{"type":"integer"},"wait_ms":{"type":"integer","minimum":0,"maximum":15000}},"required":["session_id"]},"_meta":{"ui":{"visibility":["app"]}}}]
def registered(sid):
 with REGISTRY_LOCK:
  try: return sid in json.loads(ACTIVE.read_text())
  except (OSError,ValueError): return False

def register(sid):
 with REGISTRY_LOCK:
  try: ids=json.loads(ACTIVE.read_text())
  except (OSError,ValueError): ids=[]
  if sid not in ids:ids.append(sid)
  tmp=ACTIVE.with_suffix(".tmp")
  tmp.write_text(json.dumps(ids))
  tmp.replace(ACTIVE)

def restored_sessions():
 """Only this workspace's live jobs plus recent finished jobs; do not delete history."""
 with REGISTRY_LOCK:
  try: ids=json.loads(ACTIVE.read_text())
  except (OSError,ValueError): ids=[]
 if not isinstance(ids,list): return []
 active=[]
 finished=[]
 for sid in dict.fromkeys(x for x in ids if isinstance(x,str)):
  if not gc._validate_session_id(sid): continue
  state=gc._load_state(sid)
  # gc._load_state resolves under WORKSPACE_KEY, never in another workspace.
  if not isinstance(state,dict): continue
  state_path=gc._state_path(sid)
  try: modified=state_path.stat().st_mtime
  except OSError: continue
  status=(state.get("handoff") or {}).get("status") if state.get("phase")=="finished" else "RUNNING"
  entry=(modified,sid)
  (finished if status in TERMINAL else active).append(entry)
 active.sort(reverse=True)
 finished.sort(reverse=True)
 return [sid for _,sid in active[:MAX_RESTORED_ACTIVE]+finished[:MAX_RESTORED_FINISHED]]


def wait_events(sid,revision,wait_ms):
 """Bounded server-side long poll. Independent cursor and deadline per panel."""
 deadline=time.monotonic()+wait_ms/1000
 while True:
  msg=unbox(gc.messages_tool({"session_id":sid,"after_revision":revision,"message_limit":50}))
  status=unbox(gc.status_tool({"session_id":sid}))
  value=status.get("status","UNKNOWN")
  data={"messages":msg.get("messages",[]),"revision":msg.get("revision",revision),
        "has_more":msg.get("has_more",False),"status":value}
  if data["messages"] or data["has_more"] or value in TERMINAL or value not in ("RUNNING","STARTING","PENDING"):
   return data
  remaining=deadline-time.monotonic()
  if remaining<=0:return data
  time.sleep(min(0.75,remaining))

def dispatch(req):
 id=req.get("id")
 if id is None:return
 method=req.get("method");p=req.get("params") or {}
 try:
  record("request",method=method,name=p.get("name"),id=id)
  if method=="initialize":
   result(id,{"protocolVersion":"2025-06-18","capabilities":{"tools":{},"resources":{}},"serverInfo":{"name":"harr-gigacode-live-test","version":"0.2"}})
  elif method=="tools/list":result(id,{"tools":tools()})
  elif method=="tools/call":
   name=p.get("name")
   if name=="show_static_ab":
    record("static_ab_opened")
    result(id,{"content":[{"type":"text","text":"Static A/B panel opened; no GigaCode worker."}],"structuredContent":{"variant":"static","status":"READY"},"_meta":{"ui":{"resourceUri":STATIC_URI},"ui/resourceUri":STATIC_URI,"openai/outputTemplate":STATIC_URI}})
   elif name=="show_gigacode_live":
    task=("Прочитай README.md в текущем каталоге. Укажи, что это Harr, назови два раздела и верни структурированный DONE. Ничего не изменяй, не коммить, не запускай опасных команд. Перед финальным ответом коротко сообщи о выполненных шагах.")
    args=p.get("arguments") or {}
    scenario=args.get("scenario","short")
    if scenario not in ("short","long_readonly"):raise ValueError("invalid test scenario")
    if scenario=="long_readonly":
     task=("Выполни подробный аудит README.md без изменений файлов. "
           "Последовательно проверь заголовок, архитектуру, MCP-конфигурацию, Quickstart, "
           "описание установки и troubleshooting. Для каждого пункта приводи короткое наблюдение "
           "и проверяй соответствующие разделы README через read_file; в конце дай структурированный DONE. "
           "Ничего не записывай и не меняй. Сделай не менее 6 отдельных шагов проверки.")
    requested=args.get("session_id")
    if requested:
     if not isinstance(requested,str) or not gc._validate_session_id(requested) or not registered(requested):
      raise ValueError("cannot attach unrecognized test session")
     sid=requested
     started={"status":unbox(gc.status_tool({"session_id":sid})).get("status","UNKNOWN")}
     record("attached",session_id=sid,status=started.get("status"))
    else:
     started=unbox(gc.start_tool({"action":"start","prompt":task,"timeout_sec":180}))
     sid=started.get("session_id","")
     if not gc._validate_session_id(sid):raise ValueError("GigaCode returned invalid session")
     register(sid)
     record("launched",session_id=sid,status=started.get("status"))
    result(id,{"content":[{"type":"text","text":json.dumps({"session_id":sid,"status":started.get("status")})}],"structuredContent":{"session_id":sid,"status":started.get("status")},"_meta":{"ui":{"resourceUri":URI},"ui/resourceUri":URI,"openai/outputTemplate":URI}})
   elif name=="panel_event_ui":
    args=p.get("arguments") or {}
    event=str(args.get("event",""))[:48]
    pid=str(args.get("panel_id",""))[:80]
    record("panel_lifecycle",panel_id=pid,lifecycle_event=event,session_id=str(args.get("session_id",""))[:80])
    result(id,{"content":[{"type":"text","text":"ok"}],"structuredContent":{"ok":True}})
   elif name=="list_gigacode_ui":
    ids=restored_sessions()
    record("restored_list",sessions=len(ids))
    result(id,{"content":[{"type":"text","text":"UI-only list"}],"structuredContent":{"sessions":ids}})
   elif name=="poll_gigacode_ui":
    args=p.get("arguments") or {}
    sid=args.get("session_id","")
    if not isinstance(sid,str) or not gc._validate_session_id(sid) or not registered(sid):
     raise ValueError("unrecognized test session")
    revision=max(0,int(args.get("after_revision",0)))
    wait_ms=min(15000,max(0,int(args.get("wait_ms",10000))))
    data=wait_events(sid,revision,wait_ms)
    record("app_poll",session_id=sid,count=len(data["messages"]),revision=data["revision"],status=data["status"],wait_ms=wait_ms)
    result(id,{"content":[{"type":"text","text":"UI-only poll succeeded"}],"structuredContent":data})
   else:err(id,"unknown tool")
  elif method=="resources/read":
   record("resource_read",uri=p.get("uri"))
   uri=p.get("uri")
   if uri not in (URI,STATIC_URI):raise ValueError("unknown resource")
   result(id,{"contents":[{"uri":uri,"mimeType":"text/html;profile=mcp-app","text":STATIC_HTML if uri==STATIC_URI else HTML}]})
  elif method=="resources/list":result(id,{"resources":[{"uri":URI,"name":"GigaCode live","mimeType":"text/html;profile=mcp-app"},{"uri":STATIC_URI,"name":"Static A/B probe","mimeType":"text/html;profile=mcp-app"}]})
  elif method=="resources/templates/list":result(id,{"resourceTemplates":[]})
  elif method=="ping":result(id,{})
  else:err(id,"unsupported method")
 except Exception as ex:
  record("error",message=str(ex),trace=traceback.format_exc()[-900:])
  err(id,str(ex))

def main():
 record("started",cwd=str(WORK))
 for line in sys.stdin:
  try:
   req=json.loads(line)
   threading.Thread(target=dispatch,args=(req,),daemon=True).start()
  except Exception as ex:record("protocol_error",message=str(ex))

if __name__ == "__main__":
 main()
