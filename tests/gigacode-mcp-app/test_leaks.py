#!/usr/bin/env python3
"""Leak-regression tests for the live panel app servers.

Imports the REAL common/mcp/gigacode_app/server.py (and ein_app/server.py)
with HOME/XDG sandboxed, then verifies the registry bounds that keep the
long-lived panel process from growing forever: scope registry TTL+cap,
delivered-completions cap, event-log rotation, and the incremental
transcript fast path used by the panel long-poll.
"""
import importlib.util
import json
import os
import pathlib
import tempfile
import time
import unittest
from unittest.mock import patch

_TMP=tempfile.TemporaryDirectory(prefix="panel-leaks-")
SANDBOX=pathlib.Path(_TMP.name)
os.environ["HOME"]=str(SANDBOX/"home")
os.environ["XDG_CACHE_HOME"]=str(SANDBOX/"cache")
os.environ["XDG_STATE_HOME"]=str(SANDBOX/"state")

REPO=pathlib.Path(__file__).resolve().parents[2]

def _load(rel,name):
 spec=importlib.util.spec_from_file_location(name,REPO/rel)
 assert spec and spec.loader
 module=importlib.util.module_from_spec(spec)
 spec.loader.exec_module(module)
 return module

srv=_load("common/mcp/gigacode_app/server.py","panel_leaks_gigacode_app")
ein_srv=_load("common/mcp/ein_app/server.py","panel_leaks_ein_app")

SID="11111111-1111-1111-1111-111111111111"
SID2="22222222-2222-2222-2222-222222222222"

def boxed(d):return {"content":[{"type":"text","text":json.dumps(d)}]}

class GigacodePanelLeaks(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup)
  base=pathlib.Path(self.t.name)
  for attr in ("STATE","ACTIVE","SCOPES","LOG"):
   value=base/attr.lower()
   if attr in ("STATE","ACTIVE","SCOPES","LOG") and attr!="STATE":
    value.parent.mkdir(parents=True,exist_ok=True)
   p=patch.object(srv,attr,value);p.start();self.addCleanup(p.stop)
  srv.STATE.mkdir(parents=True,exist_ok=True)
  claims=patch.object(srv,"MAX_CLAIM_FILES",128)
  claims.start();self.addCleanup(claims.stop)

 def test_scope_registry_capped(self):
  # Newest scopes survive; the registry never exceeds the cap.
  for _ in range(srv.MAX_SCOPES+20):
   srv.register_scope(SID,0)
  scopes=json.loads(srv.SCOPES.read_text())
  self.assertEqual(len(scopes),srv.MAX_SCOPES)

 def test_scope_ttl_prunes_stale_and_keeps_legacy(self):
  now=time.time()
  srv.SCOPES.write_text(json.dumps({
   "stale-old":{"session_id":SID,"initial_revision":1,"created":now-2*srv.SCOPE_TTL_SEC},
   "fresh":{"session_id":SID,"initial_revision":2,"created":now},
   "legacy-no-timestamp":{"session_id":SID2,"initial_revision":3},
  }))
  srv.register_scope(SID,0)
  scopes=json.loads(srv.SCOPES.read_text())
  self.assertNotIn("stale-old",scopes)
  self.assertIn("fresh",scopes)
  self.assertIn("legacy-no-timestamp",scopes)  # unknown age survives the TTL sweep
  self.assertIn("created",scopes[next(iter(scopes))])  # new entries are timestamped

 def test_claims_capped_oldest_removed(self):
  claim_dir=srv.STATE/"delivered-completions";claim_dir.mkdir(parents=True,exist_ok=True)
  total=srv.MAX_CLAIM_FILES+10
  for i in range(total):
   claim=claim_dir/f"{SID}.{i}.claimed"
   claim.write_text(f"scope-{i}")
   stamp=time.time()-total+i
   os.utime(claim,(stamp,stamp))
  srv.prune_claims()
  remaining=sorted(p.name for p in claim_dir.glob("*.claimed"))
  self.assertEqual(len(remaining),srv.MAX_CLAIM_FILES)
  self.assertNotIn(f"{SID}.0.claimed",remaining)   # oldest gone
  self.assertIn(f"{SID}.{total-1}.claimed",remaining)  # newest kept

 def test_claim_handler_invokes_prune(self):
  with patch.object(srv,"prune_claims") as prune,patch.object(srv.gc,"status_tool",return_value=boxed({"status":"DONE"})),patch.object(srv,"result"),patch.object(srv,"record"):
   srv.register(SID)
   scope=srv.register_scope(SID,0)
   srv.dispatch({"id":5,"method":"tools/call","params":{"name":"claim_done_notification_ui","arguments":{"session_id":SID,"scope_id":scope}}})
  prune.assert_called_once()

 def test_server_log_rotates(self):
  log=pathlib.Path(self.t.name)/"log"/"server.jsonl"
  log.parent.mkdir(parents=True,exist_ok=True)
  with patch.object(srv,"LOG",log),patch.object(srv,"LOG_ROTATE_BYTES",400):
   for i in range(50):
    srv.record("app_poll",session_id=SID,padding="x"*60,count=i)
  self.assertTrue(log.with_name(log.name+".1").exists())
  self.assertLess(log.stat().st_size,400*3)

 def test_incremental_poll_matches_full_parse(self):
  chat_dir=SANDBOX/"home"/".gigacode"/"projects"/"ws"/"chats"
  chat_dir.mkdir(parents=True,exist_ok=True)
  chat=chat_dir/f"{SID}.jsonl"
  def append(texts):
   with chat.open("a") as handle:
    for text in texts:
     handle.write(json.dumps({"type":"assistant","timestamp":"t","message":{"parts":[{"text":text}]}})+"\n")
  append(["first","second","third"])
  with patch.dict(srv._TRANSCRIPT_CURSOR,{},clear=True):
   # First call with the caller behind the cursor: full-parse fallback,
   # which also establishes the incremental anchor.
   behind=srv._messages_paged(SID,0)
   self.assertEqual([m["text"] for m in behind["messages"]],["first","second","third"])
   full=boxed({})
   full=json.loads(srv.gc.messages_tool({"session_id":SID,"after_revision":0,"message_limit":50})["content"][0]["text"])
   self.assertEqual(behind["revision"],full["revision"])
   # Caught up: incremental read returns nothing new without a full parse.
   cursor=srv._TRANSCRIPT_CURSOR[SID]
   caught_up=srv._messages_paged(SID,cursor[1])
   self.assertEqual(caught_up["messages"],[])
   self.assertEqual(caught_up["revision"],cursor[1])
   self.assertFalse(caught_up["has_more"])
   # Append two more messages: the fast path returns exactly the delta.
   append(["fourth","fifth"])
   delta=srv._messages_paged(SID,cursor[1])
   self.assertEqual([m["text"] for m in delta["messages"]],["fourth","fifth"])
   self.assertEqual(delta["revision"],full["revision"]+2)
   self.assertFalse(delta["has_more"])
   # A full parse must agree with the incremental accounting.
   verify=json.loads(srv.gc.messages_tool({"session_id":SID,"after_revision":full["revision"],"message_limit":50})["content"][0]["text"])
   self.assertEqual([m["text"] for m in verify["messages"]],["fourth","fifth"])

 def test_incremental_poll_falls_back_behind_cursor(self):
  chat_dir=SANDBOX/"home"/".gigacode"/"projects"/"ws"/"chats"
  chat_dir.mkdir(parents=True,exist_ok=True)
  chat=chat_dir/f"{SID2}.jsonl"
  with chat.open("w") as handle:
   for text in ("a","b","c","d","e"):
    handle.write(json.dumps({"type":"assistant","timestamp":"t","message":{"parts":[{"text":text}]}})+"\n")
  with patch.dict(srv._TRANSCRIPT_CURSOR,{},clear=True):
   anchor=srv._messages_paged(SID2,999)  # caller ahead: fallback, no messages
   self.assertEqual(anchor["revision"],999)
   # The anchor itself is at the true end of the transcript: revision 5.
   self.assertEqual(srv._TRANSCRIPT_CURSOR[SID2][1],5)
   # A second panel attaches at revision 0: full-parse fallback still pages.
   page=srv._messages_paged(SID2,0)
   self.assertEqual([m["text"] for m in page["messages"]],["a","b","c","d","e"])
   self.assertFalse(page["has_more"])

 def test_truncated_transcript_drops_cursor(self):
  chat_dir=SANDBOX/"home"/".gigacode"/"projects"/"ws"/"chats"
  chat_dir.mkdir(parents=True,exist_ok=True)
  chat=chat_dir/f"{SID}.jsonl"
  with chat.open("w") as handle:
   for text in ("a","b","c"):
    handle.write(json.dumps({"type":"assistant","timestamp":"t","message":{"parts":[{"text":text}]}})+"\n")
  with patch.dict(srv._TRANSCRIPT_CURSOR,{},clear=True):
   srv._messages_paged(SID,3)  # anchor
   cursor=srv._TRANSCRIPT_CURSOR[SID]
   chat.write_text(json.dumps({"type":"assistant","timestamp":"t","message":{"parts":[{"text":"reset"}]}})+"\n")
   # Truncation must not crash or corrupt revision accounting: the stale
   # cursor is dropped and the poll degrades to a full-parse fallback.
   result=srv._messages_paged(SID,cursor[1])
   self.assertEqual(result["messages"],[])
   self.assertIsInstance(result["revision"],int)
   # A fresh attach (revision 0) sees the rewritten transcript.
   fresh=srv._messages_paged(SID,0)
   self.assertEqual([m["text"] for m in fresh["messages"]],["reset"])

class EinPanelLeaks(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup)
  base=pathlib.Path(self.t.name)
  for attr in ("STATE","ACTIVE","SCOPES","LOG"):
   p=patch.object(ein_srv,attr,base/attr.lower());p.start();self.addCleanup(p.stop)
  ein_srv.STATE.mkdir(parents=True,exist_ok=True)

 def test_scope_registry_capped(self):
  for _ in range(ein_srv.MAX_SCOPES+5):
   ein_srv.register_scope("default",SID,0)
  scopes=json.loads(ein_srv.SCOPES.read_text())
  self.assertEqual(len(scopes),ein_srv.MAX_SCOPES)

 def test_scope_ttl_prunes_stale(self):
  now=time.time()
  ein_srv.SCOPES.write_text(json.dumps({
   "stale":{"instance":"default","session_id":SID,"initial_revision":1,"created":now-2*ein_srv.SCOPE_TTL_SEC},
  }))
  ein_srv.register_scope("default",SID,0)
  scopes=json.loads(ein_srv.SCOPES.read_text())
  self.assertNotIn("stale",scopes)

 def test_claims_capped_per_instance(self):
  claim_dir=ein_srv.STATE/"delivered-completions"/"default"
  claim_dir.mkdir(parents=True,exist_ok=True)
  for i in range(ein_srv.MAX_CLAIM_FILES+3):
   claim=claim_dir/f"{SID}.{i}.claimed"
   claim.write_text("x")
   stamp=time.time()-ein_srv.MAX_CLAIM_FILES+i
   os.utime(claim,(stamp,stamp))
  ein_srv.prune_claims("default")
  remaining=list(claim_dir.glob("*.claimed"))
  self.assertEqual(len(remaining),ein_srv.MAX_CLAIM_FILES)

 def test_server_log_rotates(self):
  log=pathlib.Path(self.t.name)/"log"/"server.jsonl"
  log.parent.mkdir(parents=True,exist_ok=True)
  with patch.object(ein_srv,"LOG",log),patch.object(ein_srv,"LOG_ROTATE_BYTES",400):
   for i in range(50):
    ein_srv.record("app_poll",session_id=SID,padding="x"*60,count=i)
  self.assertTrue(log.with_name(log.name+".1").exists())

if __name__=="__main__":unittest.main(verbosity=2)
