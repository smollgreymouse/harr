"""End-to-end owner loss shuts down the actual GigaCode subprocess group."""
import pathlib, tempfile, sys, threading, time, os, unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]))
import importlib.util
spec=importlib.util.spec_from_file_location("test_real_gigacode",pathlib.Path(__file__).resolve().parents[2]/"common/executor/gigacode_runtime.py")
gc=importlib.util.module_from_spec(spec);spec.loader.exec_module(gc)

class OwnerTest(unittest.TestCase):
 def test_owner_death_terminates_worker(self):
  if not sys.platform.startswith("linux"):self.skipTest("Linux only")
  with tempfile.TemporaryDirectory() as d:
   root=pathlib.Path(d)
   fake=root/"gigacode"
   fake.write_text("#!/usr/bin/env python3\nimport time\ntime.sleep(30)\n")
   fake.chmod(0o755)
   owner={"pid":os.getpid(),"start_ticks":gc._owner_identity(os.getpid())}
   state={}
   result=[]
   def write(sid,payload):state.update(payload)
   with patch.object(gc,"ROOT",root),patch.object(gc,"CACHE_ROOT",root),patch.object(gc.shutil,"which",return_value=str(fake)),patch.object(gc,"_write_state",side_effect=write),patch.object(gc,"_append_runtime_log"),patch.object(gc,"_find_chat_path",return_value=None),patch.object(gc,"POLL_INTERVAL_SEC",0.05):
    th=threading.Thread(target=lambda:result.append(gc.run_gigacode("test",[],"test",0,job_id="test",owner=owner)))
    th.start()
    deadline=time.monotonic()+4
    while "pid" not in state and time.monotonic()<deadline:time.sleep(0.02)
    self.assertIn("pid",state)
    child=state["pid"]
    owner["start_ticks"]="-1"
    th.join(4)
    self.assertFalse(th.is_alive(),"worker did not stop after owner loss")
    self.assertEqual(result[0][0],-15)
    self.assertEqual(state.get("cancel_reason"),"owner_disconnected")
    evidence=state["owner_loss"]
    self.assertEqual(evidence["event"],"MCP_OWNER_LOST")
    self.assertEqual(evidence["owner_pid"],os.getpid())
    self.assertEqual(evidence["reason"],"owner_pid_reused")
    self.assertEqual(evidence["classification"],"owner_disappeared_possible_bridge_restart")
    with self.assertRaises(ProcessLookupError):os.kill(child,0)
if __name__=="__main__":unittest.main()
