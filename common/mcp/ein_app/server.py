#!/usr/bin/env python3
"""Harr named Ein live panel. Read-only MCP App, per-instance session namespace."""
import sys, json, os, pathlib, importlib.util, traceback, threading, time, uuid
ROOT=pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from common.mcp.ein_instances import config_for_instance
import re
URI="ui://harr-ein-ui/live.html"
CONFIG_ROOT=pathlib.Path(os.environ.get("HARR_CONFIG_DIR",pathlib.Path.home()/".config/harr"))
STATE=pathlib.Path(os.environ.get("XDG_STATE_HOME", pathlib.Path.home()/".local/state"))/"harr/ein-ui"
STATE.mkdir(exist_ok=True,parents=True)
ACTIVE=STATE/"sessions.json"
SCOPES=STATE/"scopes.json"
LOG=STATE/"server.jsonl"
HTML=(pathlib.Path(__file__).with_name("panel.html")).read_text()
BACKENDS={}
IMPORT_LOCK=threading.RLock()

def backend(instance):
 item=config_for_instance(instance)
 with IMPORT_LOCK:
  if instance not in BACKENDS:
   old_id=os.environ.get("HARR_EIN_INSTANCE")
   old_root=os.environ.get("HARR_CONFIG_DIR")
   try:
    os.environ["HARR_EIN_INSTANCE"]=instance
    os.environ["HARR_CONFIG_DIR"]=str(CONFIG_ROOT/"einherjar/runtime"/instance)
    script=(ROOT/"common/executor/gigacode_runtime.py" if item["adapter"]=="gigacode"
            else ROOT/"common/mcp/einherjar_server.py")
    spec=importlib.util.spec_from_file_location("harr_ein_panel_backend_"+instance.replace("-","_"),str(script))
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    BACKENDS[instance]=mod
   finally:
    if old_id is None:os.environ.pop("HARR_EIN_INSTANCE",None)
    else:os.environ["HARR_EIN_INSTANCE"]=old_id
    if old_root is None:os.environ.pop("HARR_CONFIG_DIR",None)
    else:os.environ["HARR_CONFIG_DIR"]=old_root
  return BACKENDS[instance]

def instance_id(value):
 if not isinstance(value,str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,62}",value):
  raise ValueError("valid instance name required")
 config_for_instance(value)
 return value

def session_state(instance,sid):
 mod=backend(instance)
 if not mod._validate_session_id(sid):raise ValueError("invalid session UUID")
 state=mod._load_state(sid)
 if not isinstance(state,dict):raise ValueError("Ein session not found for instance")
 return mod,state

OUTPUT_LOCK=threading.Lock()
REGISTRY_LOCK=threading.Lock()
TERMINAL={"DONE","FAILED","CANCELLED","ESCALATE","TIMEOUT"}
MAX_RESTORED_ACTIVE=8
MAX_RESTORED_FINISHED=3
LOG=STATE/"server.jsonl"
# Registry bounds: the app server is long-lived; without these the scope
# registry, claim directories, and event log grow for the life of the process.
SCOPE_TTL_SEC=24*3600
MAX_SCOPES=64
LOG_ROTATE_BYTES=5*1024*1024
MAX_TRANSCRIPT_CURSORS=256
POLL_LOCK=threading.Lock()
# (instance,sid) -> [byte offset, revision] into the append-only chat
# transcript; lets the panel long-poll read only the tail instead of
# re-parsing the whole JSONL on every 0.75s poll step. Only backends that
# expose an offset reader (gigacode adapter) use the fast path.
_TRANSCRIPT_CURSOR={}

def _get_transcript_cursor(key):
 with POLL_LOCK:
  cursor=_TRANSCRIPT_CURSOR.pop(key,None)
  if cursor is not None:_TRANSCRIPT_CURSOR[key]=cursor
  return cursor

def _remember_transcript_cursor(key,cursor):
 with POLL_LOCK:
  _TRANSCRIPT_CURSOR.pop(key,None)
  _TRANSCRIPT_CURSOR[key]=cursor
  while len(_TRANSCRIPT_CURSOR)>MAX_TRANSCRIPT_CURSORS:
   _TRANSCRIPT_CURSOR.pop(next(iter(_TRANSCRIPT_CURSOR)))

def _forget_transcript_cursor(key):
 with POLL_LOCK:_TRANSCRIPT_CURSOR.pop(key,None)

def record(event,**data):
 with REGISTRY_LOCK:
  try:
   if LOG.exists() and LOG.stat().st_size>LOG_ROTATE_BYTES:
    LOG.replace(LOG.with_name(LOG.name+".1"))
  except OSError:pass
 with LOG.open("a") as f:f.write(json.dumps({"event":event,**data},ensure_ascii=False)+"\n")
def result(id,obj):
 with OUTPUT_LOCK: print(json.dumps({"jsonrpc":"2.0","id":id,"result":obj},ensure_ascii=False),flush=True)
def err(id,msg):
 with OUTPUT_LOCK: print(json.dumps({"jsonrpc":"2.0","id":id,"error":{"code":-32000,"message":str(msg)}},ensure_ascii=False),flush=True)
def unbox(r):
 return json.loads(r["content"][0]["text"])
def tools():
 return [
 {"name":"show_ein_live","description":"Read-only: display an existing Ein session in an HTML panel; no job is started or modified. The transcript is app-only and is not returned to the model.","annotations":{"readOnlyHint":True,"destructiveHint":False,"idempotentHint":True,"openWorldHint":False},"inputSchema":{"type":"object","properties":{"instance":{"type":"string","description":"User-configured Ein MCP name."},"session_id":{"type":"string","description":"Existing Ein session UUID to display."}},"required":["instance","session_id"],"additionalProperties":False},"_meta":{"ui":{"resourceUri":URI,"visibility":["model","app"]},"ui/resourceUri":URI,"openai/outputTemplate":URI}},
 {"name":"panel_event_ui","description":"App-only panel lifecycle diagnostics.","inputSchema":{"type":"object","properties":{"panel_id":{"type":"string"},"event":{"type":"string"},"session_id":{"type":"string"}},"required":["panel_id","event"]},"_meta":{"ui":{"visibility":["app"]}}},
 {"name":"list_ein_ui","description":"App-only list of displayed Ein sessions.","inputSchema":{"type":"object","properties":{}},"_meta":{"ui":{"visibility":["app"]}}},
 {"name":"poll_ein_ui","description":"UI only: read progress transcript using a cursor.","inputSchema":{"type":"object","properties":{"instance":{"type":"string"},"session_id":{"type":"string"},"after_revision":{"type":"integer"},"scope_id":{"type":"string"},"wait_ms":{"type":"integer","minimum":0,"maximum":15000}},"required":["instance","session_id","scope_id"]},"_meta":{"ui":{"visibility":["app"]}}}]
def registered(instance,sid):
 with REGISTRY_LOCK:
  try:return {"instance":instance,"session_id":sid} in json.loads(ACTIVE.read_text())
  except (OSError,ValueError):return False

def register(instance,sid):
 with REGISTRY_LOCK:
  try: entries=json.loads(ACTIVE.read_text())
  except (OSError,ValueError):entries=[]
  value={"instance":instance,"session_id":sid}
  if value not in entries:entries.append(value)
  tmp=ACTIVE.with_suffix(".tmp");tmp.write_text(json.dumps(entries));tmp.replace(ACTIVE)

def register_scope(instance,session_id,after_revision):
 scope_id=str(uuid.uuid4())
 now=time.time()
 with REGISTRY_LOCK:
  try: scopes=json.loads(SCOPES.read_text())
  except (OSError,ValueError):scopes={}
  if not isinstance(scopes,dict):scopes={}
  # Drop scopes past their TTL; entries without a timestamp (older server
  # versions) survive the TTL sweep but are evicted first by the cap.
  scopes={k:v for k,v in scopes.items()
          if isinstance(v,dict) and now-float(v.get("created") or now)<=SCOPE_TTL_SEC}
  while len(scopes)>=MAX_SCOPES:
   scopes.pop(next(iter(scopes)))
  scopes[scope_id]={"instance":instance,"session_id":session_id,"initial_revision":after_revision,"created":now}
  temp=SCOPES.with_suffix(".tmp");temp.write_text(json.dumps(scopes));temp.replace(SCOPES)
 return scope_id

def lookup_scope(scope_id,instance,sid):
 with REGISTRY_LOCK:
  try: scope=json.loads(SCOPES.read_text()).get(scope_id)
  except (OSError,ValueError,TypeError):return None
 if not isinstance(scope,dict) or scope.get("instance")!=instance or scope.get("session_id")!=sid:return None
 return scope

def restored_sessions():
 with REGISTRY_LOCK:
  try:entries=json.loads(ACTIVE.read_text())
  except (OSError,ValueError):entries=[]
 if not isinstance(entries,list):return []
 active=[];finished=[]
 for entry in entries:
  if not isinstance(entry,dict):continue
  try:
   instance=instance_id(entry.get("instance"));sid=entry.get("session_id")
   mod,state=session_state(instance,sid)
   modified=mod._state_path(sid).stat().st_mtime
  except (ValueError,OSError,TypeError):continue
  status=(state.get("handoff") or {}).get("status") if state.get("phase")=="finished" else "RUNNING"
  ((finished if status in TERMINAL else active)).append((modified,{"instance":instance,"session_id":sid}))
 active.sort(key=lambda x:x[0],reverse=True);finished.sort(key=lambda x:x[0],reverse=True)
 return [v for _,v in active[:MAX_RESTORED_ACTIVE]+finished[:MAX_RESTORED_FINISHED]]

def _anchor_transcript_cursor(mod,instance,sid):
 """Full-parse anchor for the incremental poll cursor (gigacode adapter)."""
 offset,messages=mod._assistant_messages_after_offset(sid,0)
 revision=len(messages)
 _remember_transcript_cursor((instance,sid),[offset,revision])
 return revision

def _messages_paged(mod,instance,sid,revision):
 """messages_tool(after_revision=revision) with an incremental fast path.

 Only backends exposing a byte-offset transcript reader (gigacode adapter)
 take the fast path; response shape is identical to messages_tool either way.
 """
 incremental=hasattr(mod,"_assistant_messages_after_offset")
 cursor=_get_transcript_cursor((instance,sid)) if incremental else None
 if incremental and cursor is None:
  latest=_anchor_transcript_cursor(mod,instance,sid)
  cursor=_get_transcript_cursor((instance,sid))
  if cursor is None: cursor=[0,latest]
 if incremental and revision==cursor[1]:
  offset,new_messages=mod._assistant_messages_after_offset(sid,cursor[0])
  if offset>=cursor[0]:
   new_revision=cursor[1]+len(new_messages)
   with POLL_LOCK:
    known=_TRANSCRIPT_CURSOR.get((instance,sid))
    if known is None or known[0]<=offset:
     _TRANSCRIPT_CURSOR.pop((instance,sid),None)
     _TRANSCRIPT_CURSOR[(instance,sid)]=[offset,new_revision]
     while len(_TRANSCRIPT_CURSOR)>MAX_TRANSCRIPT_CURSORS:
      _TRANSCRIPT_CURSOR.pop(next(iter(_TRANSCRIPT_CURSOR)))
   selected=new_messages[:50]
   next_revision=cursor[1]+len(selected) if selected else cursor[1]
   return {"revision":next_revision,"latest_revision":new_revision,
           "has_more":new_revision>next_revision,"messages":selected}
  # Transcript was truncated or replaced; drop the stale cursor.
  _forget_transcript_cursor((instance,sid))
 return unbox(mod.messages_tool({"session_id":sid,"after_revision":revision,"message_limit":50}))

def wait_events(instance,sid,revision,wait_ms):
 mod=backend(instance)
 deadline=time.monotonic()+wait_ms/1000
 while True:
  msg=_messages_paged(mod,instance,sid,revision)
  status=unbox(mod.status_tool({"session_id":sid}))
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
   result(id,{"protocolVersion":"2025-06-18","capabilities":{"tools":{},"resources":{}},"serverInfo":{"name":"harr-ein-ui","version":"0.2"}})
  elif method=="tools/list":result(id,{"tools":tools()})
  elif method=="tools/call":
   name=p.get("name")
   if name=="show_ein_live":
    args=p.get("arguments") or {}
    instance=instance_id(args.get("instance"))
    requested=args.get("session_id")
    if not isinstance(requested,str):
     raise ValueError("show_ein_live requires existing session_id UUID")
    sid=requested
    mod,state=session_state(instance,sid)
    started={"status":unbox(mod.status_tool({"session_id":sid})).get("status","UNKNOWN")}
    if started["status"]=="UNKNOWN":raise ValueError("Ein session not found")
    register(instance,sid)
    first_revision=0
    record("attached",session_id=sid,status=started["status"])
    scope_id=register_scope(instance,sid,first_revision)
    visible={"instance":instance,"session_id":sid,"scope_id":scope_id,"initial_revision":first_revision,"status":started.get("status")}
    result(id,{"content":[{"type":"text","text":json.dumps(visible)}],"structuredContent":visible,"_meta":{"ui":{"resourceUri":URI},"ui/resourceUri":URI,"openai/outputTemplate":URI}})
   elif name=="panel_event_ui":
    args=p.get("arguments") or {}
    event=str(args.get("event",""))[:48]
    pid=str(args.get("panel_id",""))[:80]
    record("panel_lifecycle",panel_id=pid,lifecycle_event=event,session_id=str(args.get("session_id",""))[:80])
    result(id,{"content":[{"type":"text","text":"ok"}],"structuredContent":{"ok":True}})
   elif name=="list_ein_ui":
    ids=restored_sessions()
    record("restored_list",sessions=len(ids))
    result(id,{"content":[{"type":"text","text":"UI-only list"}],"structuredContent":{"sessions":ids}})
   elif name=="poll_ein_ui":
    args=p.get("arguments") or {}
    sid=args.get("session_id","")
    instance=instance_id(args.get("instance"))
    if not isinstance(sid,str) or not registered(instance,sid):
     raise ValueError("unrecognized test session")
    scope=lookup_scope(args.get("scope_id"),instance,sid)
    if scope is None:raise ValueError("unrecognized invocation scope")
    revision=max(int(scope["initial_revision"]),int(args.get("after_revision",0)))
    wait_ms=min(15000,max(0,int(args.get("wait_ms",10000))))
    data=wait_events(instance,sid,revision,wait_ms)
    record("app_poll",session_id=sid,count=len(data["messages"]),revision=data["revision"],status=data["status"],wait_ms=wait_ms)
    result(id,{"content":[{"type":"text","text":"UI-only poll succeeded"}],"structuredContent":data})
   else:err(id,"unknown tool")
  elif method=="resources/read":
   record("resource_read",uri=p.get("uri"))
   uri=p.get("uri")
   if uri != URI:raise ValueError("unknown resource")
   result(id,{"contents":[{"uri":uri,"mimeType":"text/html;profile=mcp-app","text":HTML}]})
  elif method=="resources/list":result(id,{"resources":[{"uri":URI,"name":"Ein live","mimeType":"text/html;profile=mcp-app"}]})
  elif method=="resources/templates/list":result(id,{"resourceTemplates":[]})
  elif method=="ping":result(id,{})
  else:err(id,"unsupported method")
 except Exception as ex:
  record("error",message=str(ex),trace=traceback.format_exc()[-900:])
  err(id,str(ex))

def main():
 record("started",cwd=str(ROOT))
 for line in sys.stdin:
  try:
   req=json.loads(line)
   threading.Thread(target=dispatch,args=(req,),daemon=True).start()
  except Exception as ex:record("protocol_error",message=str(ex))

if __name__ == "__main__":
 main()
