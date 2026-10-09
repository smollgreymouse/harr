"""Deterministic unit tests: no real GigaCode or Codex required."""
import importlib.util
import json
import pathlib
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

MODULE=pathlib.Path(__file__).with_name("server.py")
spec=importlib.util.spec_from_file_location("harr_live_panel_test",MODULE)
srv=importlib.util.module_from_spec(spec)
spec.loader.exec_module(srv)

def boxed(d):return {"content":[{"type":"text","text":json.dumps(d)}]}

class TestLivePoll(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory()
  self.addCleanup(self.t.cleanup)
  self.stack=patch.object(srv,"ACTIVE",pathlib.Path(self.t.name)/"sessions.json")
  self.stack.start();self.addCleanup(self.stack.stop)
 def test_model_cannot_discover_poll(self):
  tools=srv.tools()
  self.assertEqual(tools[1]["_meta"]["ui"]["visibility"],["app"])
  self.assertEqual(tools[0]["_meta"]["ui"]["visibility"],["model","app"])
 def test_independent_cursors(self):
  data=[{"revision":1,"text":"first"},{"revision":2,"text":"second"},{"revision":3,"text":"third"}]
  def messages(args):
   selected=[x for x in data if x["revision"]>args["after_revision"]]
   return boxed({"messages":selected,"revision":selected[-1]["revision"] if selected else args["after_revision"],"has_more":False})
  with patch.object(srv.gc,"messages_tool",side_effect=messages),patch.object(srv.gc,"status_tool",return_value=boxed({"status":"RUNNING"})):
   a=srv.wait_events("fake",0,0)
   b=srv.wait_events("fake",1,0)
   self.assertEqual([x["text"] for x in a["messages"]],["first","second","third"])
   self.assertEqual([x["text"] for x in b["messages"]],["second","third"])
 def test_timeout_bounded_and_idle(self):
  with patch.object(srv.gc,"messages_tool",return_value=boxed({"messages":[],"revision":9,"has_more":False})),patch.object(srv.gc,"status_tool",return_value=boxed({"status":"RUNNING"})):
   t=time.monotonic();r=srv.wait_events("fake",9,130)
   self.assertLess(time.monotonic()-t,.6)
   self.assertEqual(r["messages"],[])
 def test_wakes_when_message_appears(self):
  count=[0]
  def messages(args):
   count[0]+=1
   if count[0]>=2:return boxed({"messages":[{"revision":1,"text":"ready"}],"revision":1,"has_more":False})
   return boxed({"messages":[],"revision":0,"has_more":False})
  with patch.object(srv.gc,"messages_tool",side_effect=messages),patch.object(srv.gc,"status_tool",return_value=boxed({"status":"RUNNING"})):
   r=srv.wait_events("fake",0,1800)
   self.assertEqual(r["messages"][0]["text"],"ready")
 def test_terminal_returns_without_wait(self):
  for state in ("DONE","FAILED","CANCELLED","ESCALATE","TIMEOUT"):
   with self.subTest(state=state),patch.object(srv.gc,"messages_tool",return_value=boxed({"messages":[],"revision":0,"has_more":False})),patch.object(srv.gc,"status_tool",return_value=boxed({"status":state})):
    t=time.monotonic();r=srv.wait_events("fake",0,5000)
    self.assertLess(time.monotonic()-t,.15)
    self.assertEqual(r["status"],state)
 def test_parallel_panels_not_serialized(self):
  gate=threading.Barrier(3)
  out={}
  def poll(k):
   gate.wait()
   out[k]=srv.wait_events(k,0,120)
  with patch.object(srv.gc,"messages_tool",return_value=boxed({"messages":[],"revision":0,"has_more":False})),patch.object(srv.gc,"status_tool",return_value=boxed({"status":"RUNNING"})):
   threads=[threading.Thread(target=poll,args=(str(k),)) for k in (1,2)]
   for th in threads:th.start()
   t=time.monotonic();gate.wait()
   for th in threads:th.join(2)
   self.assertEqual(len(out),2)
   self.assertLess(time.monotonic()-t,.38)
 def test_registry_keeps_multiple_sessions_and_deduplicates(self):
  ids=["11111111-1111-1111-1111-111111111111","22222222-2222-2222-2222-222222222222"]
  srv.register(ids[0]);srv.register(ids[1]);srv.register(ids[0])
  self.assertEqual(json.loads(srv.ACTIVE.read_text()),ids)
  self.assertTrue(srv.registered(ids[0]))
  self.assertTrue(srv.registered(ids[1]))
  self.assertFalse(srv.registered("33333333-3333-3333-3333-333333333333"))
 def test_start_does_not_return_intermediate_text_to_model(self):
  sid="11111111-1111-1111-1111-111111111111"
  captured=[]
  with patch.object(srv.gc,"start_tool",return_value=boxed({"session_id":sid,"status":"RUNNING","messages":[{"text":"SECRET-PROGRESS"}]})),patch.object(srv,"result",side_effect=lambda i,v:captured.append(v)),patch.object(srv,"record"):
   srv.dispatch({"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"show_gigacode_live","arguments":{}}})
  self.assertEqual(captured[0]["structuredContent"],{"session_id":sid,"status":"RUNNING"})
  self.assertNotIn("SECRET-PROGRESS",json.dumps(captured))
 def test_app_poll_text_only_in_app_result(self):
  sid="11111111-1111-1111-1111-111111111111"
  srv.register(sid)
  captured=[]
  with patch.object(srv,"wait_events",return_value={"messages":[{"revision":1,"text":"SECRET-PROGRESS"}],"revision":1,"has_more":False,"status":"RUNNING"}),patch.object(srv,"result",side_effect=lambda i,v:captured.append(v)),patch.object(srv,"record"):
   srv.dispatch({"id":7,"method":"tools/call","params":{"name":"poll_gigacode_ui","arguments":{"session_id":sid,"after_revision":0,"wait_ms":0}}})
  self.assertNotIn("SECRET-PROGRESS",json.dumps(captured[0]["content"]))
  self.assertIn("SECRET-PROGRESS",json.dumps(captured[0]["structuredContent"]))
 def test_attach_second_panel_does_not_launch_second_worker(self):
  sid="11111111-1111-1111-1111-111111111111"
  srv.register(sid)
  captured=[]
  with patch.object(srv.gc,"start_tool") as start,patch.object(srv.gc,"status_tool",return_value=boxed({"status":"RUNNING"})),patch.object(srv,"result",side_effect=lambda i,v:captured.append(v)),patch.object(srv,"record"):
   srv.dispatch({"id":11,"method":"tools/call","params":{"name":"show_gigacode_live","arguments":{"session_id":sid}}})
  start.assert_not_called()
  self.assertEqual(captured[0]["structuredContent"],{"session_id":sid,"status":"RUNNING"})
 def test_attach_unknown_session_rejected(self):
  errors=[]
  with patch.object(srv.gc,"start_tool") as start,patch.object(srv,"err",side_effect=lambda i,e:errors.append(str(e))),patch.object(srv,"record"):
   srv.dispatch({"id":12,"method":"tools/call","params":{"name":"show_gigacode_live","arguments":{"session_id":"11111111-1111-1111-1111-111111111111"}}})
  start.assert_not_called()
  self.assertTrue(errors)
 def test_worker_status_exception_is_mcp_error(self):
  sid="11111111-1111-1111-1111-111111111111"
  srv.register(sid)
  errors=[]
  with patch.object(srv.gc,"messages_tool",side_effect=OSError("transcript unavailable")),patch.object(srv,"err",side_effect=lambda i,e:errors.append(str(e))),patch.object(srv,"record"):
   srv.dispatch({"id":13,"method":"tools/call","params":{"name":"poll_gigacode_ui","arguments":{"session_id":sid,"wait_ms":100}}})
  self.assertEqual(len(errors),1)
  self.assertIn("unavailable",errors[0])
 def test_status_failure_is_exposed_to_panel(self):
  with patch.object(srv.gc,"messages_tool",return_value=boxed({"messages":[],"revision":0,"has_more":False})),patch.object(srv.gc,"status_tool",return_value=boxed({"status":"FAILED","summary":"worker stopped"})):
   r=srv.wait_events("fake",0,10000)
  self.assertEqual(r["status"],"FAILED")
 def test_persisted_session_survives_registry_reload(self):
  sid="11111111-1111-1111-1111-111111111111"
  srv.register(sid)
  self.assertEqual(json.loads(srv.ACTIVE.read_text()),[sid])
  self.assertTrue(srv.registered(sid))
 def test_lifecycle_event_logged_without_error(self):
  captured=[]
  with patch.object(srv,'record',side_effect=lambda event,**kwargs:captured.append((event,kwargs))),patch.object(srv,'result') as out:
   srv.dispatch({'id':99,'method':'tools/call','params':{'name':'panel_event_ui','arguments':{'panel_id':'p-1','event':'created','session_id':'sid-1'}}})
  self.assertTrue(any(e=='panel_lifecycle' and d['lifecycle_event']=='created' for e,d in captured))
  out.assert_called_once()
 def test_invalid_session_rejected(self):
  errors=[]
  with patch.object(srv,"err",side_effect=lambda i,e:errors.append(str(e))),patch.object(srv,"record"):
   srv.dispatch({"id":9,"method":"tools/call","params":{"name":"poll_gigacode_ui","arguments":{"session_id":"../../etc/passwd"}}})
  self.assertTrue(errors)

if __name__=="__main__":unittest.main(verbosity=2)
