#!/usr/bin/env python3
from __future__ import annotations
import json, os, pathlib, sys, threading, time, traceback, uuid
from datetime import datetime, timezone

BASE=pathlib.Path(__file__).resolve().parent
STATE=pathlib.Path(os.environ.get("XDG_STATE_HOME", pathlib.Path.home()/".local/state"))/"harr-async-notify-probe"
STATE.mkdir(parents=True,exist_ok=True)
WORKSPACE_URI="ui://async-notify-probe/workspace.html"
MARKER_URI="ui://async-notify-probe/marker.html"
HTML={WORKSPACE_URI:(BASE/"workspace.html").read_text(),MARKER_URI:(BASE/"marker.html").read_text()}
LOG=STATE/"events.jsonl"; STARTED=time.time(); OUTPUT_LOCK=threading.Lock(); COND=threading.Condition()
SEQ=0; EVENTS=[]; JOBS={}; CLAIMS={}

def now_iso(): return datetime.now(timezone.utc).isoformat()
def record(kind,**fields):
    try:
        with LOG.open("a") as f:f.write(json.dumps({"ts":now_iso(),"kind":kind,"pid":os.getpid(),**fields},ensure_ascii=False)+"\n")
    except Exception: pass
def emit_result(i,v):
    with OUTPUT_LOCK: print(json.dumps({"jsonrpc":"2.0","id":i,"result":v},ensure_ascii=False),flush=True)
def emit_error(i,m,c=-32000):
    with OUTPUT_LOCK: print(json.dumps({"jsonrpc":"2.0","id":i,"error":{"code":c,"message":str(m)}},ensure_ascii=False),flush=True)

def arm_job(delay_sec,message):
    delay=max(1.0,min(float(delay_sec),120.0)); job_id=str(uuid.uuid4()); due=time.time()+delay
    job={"job_id":job_id,"status":"RUNNING","message":message,"created_at":now_iso(),"due_at":datetime.fromtimestamp(due,timezone.utc).isoformat(),"completed_at":None,"event_id":None,"seq":None}
    with COND:JOBS[job_id]=job
    record("job_started",job_id=job_id,delay_sec=delay,message=message)
    def fire():
        global SEQ
        with COND:
            j=JOBS.get(job_id)
            if not j or j["status"]!="RUNNING":return
            SEQ+=1
            ev={"seq":SEQ,"event_id":str(uuid.uuid4()),"job_id":job_id,"message":message,"source":"server_timer","completed_at":now_iso()}
            j.update(status="DONE",completed_at=ev["completed_at"],event_id=ev["event_id"],seq=ev["seq"])
            EVENTS.append(ev)
            if len(EVENTS)>128:del EVENTS[:-128]
            COND.notify_all()
        record("engine_completed",**ev)
    t=threading.Timer(delay,fire);t.daemon=True;t.start();return dict(job)

def app_only():return {"ui":{"visibility":["app"]}}
def ui_meta(uri,fullscreen=False):
    m={"ui":{"resourceUri":uri,"visibility":["model","app"]},"ui/resourceUri":uri,"openai/outputTemplate":uri}
    if fullscreen:m["openai/ui"]={"preferredModelDisplayMode":"fullscreen"}
    return m

def tools():
    return [
      {"name":"show_async_workspace_probe","description":"Open the persistent Workspace-like async monitor in the Codex side panel. It observes jobs but does not wake the chat.","annotations":{"readOnlyHint":True,"destructiveHint":False,"idempotentHint":True,"openWorldHint":False},"inputSchema":{"type":"object","properties":{},"additionalProperties":False},"_meta":ui_meta(WORKSPACE_URI,True)},
      {"name":"start_async_marker_probe","description":"Start a simulated async worker and leave a compact inline completion marker in the transcript. The marker changes RUNNING to DONE and wakes the chat via ui/message.","annotations":{"readOnlyHint":False,"destructiveHint":False,"idempotentHint":False,"openWorldHint":False},"inputSchema":{"type":"object","properties":{"delay_sec":{"type":"number","minimum":1,"maximum":120,"default":15},"message":{"type":"string","maxLength":500}},"additionalProperties":False},"_meta":ui_meta(MARKER_URI)},
      {"name":"probe_attach_ui","description":"App-only lifecycle/heartbeat event.","inputSchema":{"type":"object","properties":{"panel_id":{"type":"string"},"surface":{"type":"string"},"event":{"type":"string"},"job_id":{"type":"string"}},"required":["panel_id","surface","event"],"additionalProperties":False},"_meta":app_only()},
      {"name":"probe_wait_job_ui","description":"App-only bounded wait for one simulated job.","inputSchema":{"type":"object","properties":{"panel_id":{"type":"string"},"job_id":{"type":"string"},"timeout_ms":{"type":"integer","minimum":100,"maximum":15000}},"required":["panel_id","job_id","timeout_ms"],"additionalProperties":False},"_meta":app_only()},
      {"name":"probe_wait_events_ui","description":"App-only bounded wait for workspace completion events.","inputSchema":{"type":"object","properties":{"panel_id":{"type":"string"},"after_seq":{"type":"integer","minimum":0},"timeout_ms":{"type":"integer","minimum":100,"maximum":15000}},"required":["panel_id","after_seq","timeout_ms"],"additionalProperties":False},"_meta":app_only()},
      {"name":"probe_list_jobs_ui","description":"App-only snapshot of recent simulated jobs.","inputSchema":{"type":"object","properties":{},"additionalProperties":False},"_meta":app_only()},
      {"name":"probe_claim_ui","description":"App-only atomic completion delivery claim.","inputSchema":{"type":"object","properties":{"panel_id":{"type":"string"},"event_id":{"type":"string"}},"required":["panel_id","event_id"],"additionalProperties":False},"_meta":app_only()},
      {"name":"probe_release_ui","description":"App-only release a completion delivery claim after failed ui/message.","inputSchema":{"type":"object","properties":{"panel_id":{"type":"string"},"event_id":{"type":"string"}},"required":["panel_id","event_id"],"additionalProperties":False},"_meta":app_only()}
    ]
def tool_result(payload,text,uri=None,fullscreen=False):
    out={"content":[{"type":"text","text":text}],"structuredContent":payload}
    if uri:out["_meta"]=ui_meta(uri,fullscreen)
    return out

def dispatch(req):
    i=req.get("id"); method=req.get("method"); p=req.get("params") or {}
    if i is None:
        if method:record("notification",method=method)
        return
    try:
      if method=="initialize":
        record("server_initialize");emit_result(i,{"protocolVersion":"2025-06-18","capabilities":{"tools":{},"resources":{}},"serverInfo":{"name":"codex-mcp-async-probe","version":"0.2"}})
      elif method=="tools/list":emit_result(i,{"tools":tools()})
      elif method=="resources/list":emit_result(i,{"resources":[{"uri":WORKSPACE_URI,"name":"Async Workspace Probe","mimeType":"text/html;profile=mcp-app"},{"uri":MARKER_URI,"name":"Async Completion Marker","mimeType":"text/html;profile=mcp-app"}]})
      elif method=="resources/templates/list":emit_result(i,{"resourceTemplates":[]})
      elif method=="resources/read":
        uri=p.get("uri")
        if uri not in HTML:raise ValueError("unknown resource")
        content={"uri":uri,"mimeType":"text/html;profile=mcp-app","text":HTML[uri]}
        if uri==MARKER_URI:
            content["_meta"]={
                "openai/widgetHeightHint":44,
                "openai/widgetMinFrameHeight":40,
                "openai/widgetPrefersBorder":False,
                "openai/widgetShowCodexWidgetInline":True,
            }
        emit_result(i,{"contents":[content]})
      elif method=="tools/call":
        name=p.get("name");a=p.get("arguments") or {}
        if name=="show_async_workspace_probe":
            payload={"surface":"workspace","serverPid":os.getpid(),"serverStartedAt":datetime.fromtimestamp(STARTED,timezone.utc).isoformat(),"latestSeq":SEQ}
            record("show_workspace");emit_result(i,tool_result(payload,"Async workspace probe opened.",WORKSPACE_URI,True))
        elif name=="start_async_marker_probe":
            job=arm_job(a.get("delay_sec",15),str(a.get("message") or "simulated Ein completion"))
            payload={"surface":"marker","serverPid":os.getpid(),**job}
            record("show_marker",job_id=job["job_id"]);emit_result(i,tool_result(payload,"Async marker probe started.",MARKER_URI))
        elif name=="probe_attach_ui":
            panel=str(a.get("panel_id",""))[:120];surface=str(a.get("surface",""))[:32];event=str(a.get("event",""))[:120];job=str(a.get("job_id",""))[:80] or None
            record("panel_event",panel_id=panel,surface=surface,event=event,job_id=job);emit_result(i,tool_result({"latestSeq":SEQ,"serverPid":os.getpid()},"ok"))
        elif name=="probe_wait_job_ui":
            panel=str(a.get("panel_id",""))[:120];job_id=str(a.get("job_id",""));timeout=max(.1,min(int(a.get("timeout_ms",10000))/1000,15));deadline=time.monotonic()+timeout
            with COND:
                while True:
                    job=JOBS.get(job_id)
                    if job is None:raise ValueError("unknown job")
                    if job["status"]!="RUNNING":break
                    rem=deadline-time.monotonic()
                    if rem<=0:break
                    COND.wait(rem)
                snap=dict(JOBS[job_id])
            record("job_wait_return",panel_id=panel,job_id=job_id,status=snap["status"],event_id=snap.get("event_id"));emit_result(i,tool_result({"job":snap,"serverPid":os.getpid()},"ok"))
        elif name=="probe_wait_events_ui":
            panel=str(a.get("panel_id",""))[:120];after=int(a.get("after_seq",0));timeout=max(.1,min(int(a.get("timeout_ms",10000))/1000,15));deadline=time.monotonic()+timeout
            with COND:
                while True:
                    ev=next((x for x in EVENTS if x["seq"]>after),None)
                    if ev:break
                    rem=deadline-time.monotonic()
                    if rem<=0:break
                    COND.wait(rem)
                latest=SEQ
            record("workspace_wait_return",panel_id=panel,after_seq=after,event_seq=ev["seq"] if ev else None);emit_result(i,tool_result({"event":ev,"latestSeq":latest,"serverPid":os.getpid()},"ok"))
        elif name=="probe_list_jobs_ui":
            with COND:jobs=[dict(x) for x in list(JOBS.values())[-32:]]
            emit_result(i,tool_result({"jobs":jobs,"latestSeq":SEQ,"serverPid":os.getpid()},"ok"))
        elif name=="probe_claim_ui":
            panel=str(a.get("panel_id",""))[:120];event_id=str(a.get("event_id",""))
            with COND:
                owner=CLAIMS.get(event_id);claimed=owner is None or owner==panel
                if claimed:CLAIMS[event_id]=panel
            record("claim",panel_id=panel,event_id=event_id,claimed=claimed);emit_result(i,tool_result({"claimed":claimed,"owner":CLAIMS.get(event_id)},"ok"))
        elif name=="probe_release_ui":
            panel=str(a.get("panel_id",""))[:120];event_id=str(a.get("event_id",""))
            with COND:
                released=CLAIMS.get(event_id)==panel
                if released:CLAIMS.pop(event_id,None)
            record("release",panel_id=panel,event_id=event_id,released=released);emit_result(i,tool_result({"released":released},"ok"))
        else:emit_error(i,"unknown tool",-32601)
      elif method=="ping":emit_result(i,{})
      else:emit_error(i,"unsupported method",-32601)
    except Exception as ex:
      record("error",method=str(method),error=str(ex));emit_error(i,str(ex));print(traceback.format_exc(),file=sys.stderr,flush=True)

def main():
    record("server_start")
    for line in sys.stdin:
      try:threading.Thread(target=dispatch,args=(json.loads(line),),daemon=True).start()
      except Exception as ex:record("stdin_error",error=str(ex))
if __name__=="__main__":main()
