#!/usr/bin/env python3
"""Check loss/recovery of an MCP stdio connection using an existing completed worker."""
import json, pathlib, subprocess, select, time, sys
root=pathlib.Path(__file__).resolve().parents[2]
state=pathlib.Path.home()/"codex-desktop-test/state/gigacode-ui-invocations.json"
scopes=json.loads(state.read_text())
scope_id,info=next(reversed(scopes.items()))
sid=info["session_id"]
def server():
 return subprocess.Popen([sys.executable,str(root/"tests/gigacode-mcp-app/server.py")],cwd=root,stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,bufsize=1)
def call(p,id,after):
 args={"session_id":sid,"scope_id":scope_id,"after_revision":after,"wait_ms":0}
 p.stdin.write(json.dumps({"jsonrpc":"2.0","id":id,"method":"tools/call","params":{"name":"poll_gigacode_ui","arguments":args}})+"\n")
 p.stdin.flush()
 ready,_,_=select.select([p.stdout],[],[],8)
 assert ready,"server response timed out"
 data=json.loads(p.stdout.readline())
 assert "result" in data,data
 return data["result"]["structuredContent"]
p=server()
try:
 first=call(p,1,0)
 assert first["messages"],first
 cursor=first["revision"]
 print("before crash: messages",len(first["messages"]),"cursor",cursor)
 # Kill server while an MCP request is still outstanding.
 p.stdin.write(json.dumps({"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"poll_gigacode_ui","arguments":{"session_id":sid,"scope_id":scope_id,"after_revision":999999,"wait_ms":15000}}})+"\n");p.stdin.flush()
 p.kill();p.wait(timeout=5)
 p=server()
 remaining=call(p,3,cursor)
 assert not remaining["messages"],"duplicate transcript after reconnect"
 replay=call(p,4,0)
 assert [x["revision"] for x in replay["messages"]]==[x["revision"] for x in first["messages"]],"replay changed after restart"
 print("after crash: no duplicates, replay consistent, status",remaining["status"])
finally:
 p.kill();p.wait(timeout=5)
