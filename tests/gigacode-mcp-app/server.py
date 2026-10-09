#!/usr/bin/env python3
"""Isolated MCP App live GigaCode test; only app-only tool returns transcript."""
import sys, json, os, pathlib, importlib.util, traceback
ROOT=pathlib.Path(__file__).resolve().parents[1]
WORK=pathlib.Path.home()/"codex-desktop-test/workspace"
os.chdir(WORK)
spec=importlib.util.spec_from_file_location("harr_test_gigacode",str(ROOT/"common/mcp/gigacode_server.py"))
gc=importlib.util.module_from_spec(spec);spec.loader.exec_module(gc)
URI="ui://harr-gigacode/live.html"
STATE=pathlib.Path.home()/"codex-desktop-test/state"
STATE.mkdir(exist_ok=True,parents=True)
ACTIVE=STATE/"gigacode-ui-session.json"
LOG=STATE/"gigacode-ui-server.jsonl"
HTML=(ROOT/"tests/gigacode-mcp-app/panel.html").read_text()
def record(event,**data):
 with LOG.open("a") as f:f.write(json.dumps({"event":event,**data},ensure_ascii=False)+"\n")
def result(id,obj):
 print(json.dumps({"jsonrpc":"2.0","id":id,"result":obj},ensure_ascii=False),flush=True)
def err(id,msg):
 print(json.dumps({"jsonrpc":"2.0","id":id,"error":{"code":-32000,"message":str(msg)}},ensure_ascii=False),flush=True)
def unbox(r):
 return json.loads(r["content"][0]["text"])
def tools():
 return [
 {"name":"show_gigacode_live","description":"Start a read-only GigaCode test and show its live output in an embedded panel. Only session ID/status returned to the model; intermediate transcript is app-only.","inputSchema":{"type":"object","properties":{},"additionalProperties":False},"_meta":{"ui":{"resourceUri":URI,"visibility":["model","app"]},"ui/resourceUri":URI,"openai/outputTemplate":URI}},
 {"name":"poll_gigacode_ui","description":"UI only: read progress transcript using a cursor.","inputSchema":{"type":"object","properties":{"session_id":{"type":"string"},"after_revision":{"type":"integer"}},"required":["session_id"]},"_meta":{"ui":{"visibility":["app"]}}}]
record("started",cwd=str(WORK))
for line in sys.stdin:
 try:
  req=json.loads(line);id=req.get("id");method=req.get("method");p=req.get("params") or {}
  if id is None:continue
  record("request",method=method,name=p.get("name"))
  if method=="initialize":
   result(id,{"protocolVersion":"2025-06-18","capabilities":{"tools":{},"resources":{}},"serverInfo":{"name":"harr-gigacode-live-test","version":"0.1"}})
  elif method=="tools/list":result(id,{"tools":tools()})
  elif method=="tools/call":
   name=p.get("name")
   if name=="show_gigacode_live":
    task=("Прочитай README.md в текущем каталоге. Укажи, что это Harr, назови два раздела и верни структурированный DONE. Ничего не изменяй, не коммить, не запускай опасных команд. Перед финальным ответом коротко сообщи о выполненных шагах.")
    started=unbox(gc.start_tool({"action":"start","prompt":task,"timeout_sec":180}))
    sid=started.get("session_id","")
    ACTIVE.write_text(json.dumps({"session_id":sid,"status":started.get("status")}))
    record("launched",session_id=sid,status=started.get("status"))
    result(id,{"content":[{"type":"text","text":json.dumps({"session_id":sid,"status":started.get("status")})}],"structuredContent":{"session_id":sid,"status":started.get("status")},"_meta":{"ui":{"resourceUri":URI},"ui/resourceUri":URI,"openai/outputTemplate":URI}})
   elif name=="poll_gigacode_ui":
    args=p.get("arguments") or {}
    sid=args.get("session_id","")
    if sid!=json.loads(ACTIVE.read_text()).get("session_id"):raise ValueError("session mismatch")
    revision=max(0,int(args.get("after_revision",0)))
    msg=unbox(gc.messages_tool({"session_id":sid,"after_revision":revision,"message_limit":50}))
    status=unbox(gc.status_tool({"session_id":sid}))
    data={"messages":msg.get("messages",[]),"revision":msg.get("revision",revision),"has_more":msg.get("has_more",False),"status":status.get("status","UNKNOWN")}
    record("app_poll",session_id=sid,count=len(data["messages"]),revision=data["revision"],status=data["status"])
    result(id,{"content":[{"type":"text","text":"UI-only poll succeeded"}],"structuredContent":data})
   else:err(id,"unknown tool")
  elif method=="resources/read":
   record("resource_read",uri=p.get("uri"))
   result(id,{"contents":[{"uri":URI,"mimeType":"text/html;profile=mcp-app","text":HTML}]})
  elif method=="resources/list":result(id,{"resources":[{"uri":URI,"name":"GigaCode live","mimeType":"text/html;profile=mcp-app"}]})
  elif method=="resources/templates/list":result(id,{"resourceTemplates":[]})
  elif method=="ping":result(id,{})
  else:err(id,"unsupported method")
 except Exception as ex:
  record("error",message=str(ex),trace=traceback.format_exc()[-900:])
  if "id" in locals() and id is not None:err(id,str(ex))
