#!/usr/bin/env python3
"""Fail-closed stdio MCP proxy for Redash metadata-only access."""
import json
import subprocess
import sys
import threading

ALLOWED = frozenset({
    'list_queries', 'get_query', 'get_query_parameters', 'list_data_sources',
    'get_schema', 'list_dashboards', 'get_dashboard', 'get_dashboard_by_slug',
    'get_dashboard_layout', 'get_visualization', 'get_dashboard_parameters',
    'get_widget_parameter_mappings',
})


def allowed(name):
    return isinstance(name, str) and name in ALLOWED


def main(argv):
    if not argv:
        raise SystemExit('missing upstream MCP command')
    child = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=None, bufsize=0)
    write_lock = threading.Lock()

    def send(stream, message):
        with write_lock:
            stream.write(json.dumps(message, separators=(',', ':')).encode() + b'\n')
            stream.flush()

    def responses():
        for line in child.stdout:
            try:
                obj = json.loads(line)
            except (ValueError, UnicodeDecodeError):
                continue  # never forward non-protocol stdout
            if isinstance(obj, dict) and isinstance(obj.get('result'), dict):
                tools = obj['result'].get('tools')
                if isinstance(tools, list):
                    obj['result']['tools'] = [t for t in tools if isinstance(t, dict) and allowed(t.get('name'))]
            send(sys.stdout.buffer, obj)

    thread = threading.Thread(target=responses, daemon=True)
    thread.start()
    try:
        for line in sys.stdin.buffer:
            try:
                obj = json.loads(line)
            except (ValueError, UnicodeDecodeError):
                continue
            if not isinstance(obj, dict):
                continue
            method = obj.get('method')
            if method == 'tools/call':
                params = obj.get('params')
                if not isinstance(params, dict) or not allowed(params.get('name')):
                    if 'id' in obj:
                        send(sys.stdout.buffer, {'jsonrpc': '2.0', 'id': obj['id'], 'error': {'code': -32601, 'message': 'Redash tool denied by Harr read-only policy'}})
                    continue
            elif method in ('resources/read', 'prompts/get', 'completion/complete'):
                if 'id' in obj:
                    send(sys.stdout.buffer, {'jsonrpc': '2.0', 'id': obj['id'], 'error': {'code': -32601, 'message': 'Redash access denied by Harr read-only policy'}})
                continue
            send(child.stdin, obj)
    finally:
        child.terminate()
        try:
            child.wait(timeout=3)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
        thread.join(timeout=2)


if __name__ == '__main__':
    main(sys.argv[1:])
