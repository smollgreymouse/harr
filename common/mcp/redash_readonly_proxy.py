#!/usr/bin/env python3
"""Fail-closed stdio MCP proxy for Redash read access."""
import json
import subprocess
import sys
import threading

ALLOWED = frozenset({
    'list_queries', 'get_query', 'get_query_parameters', 'list_data_sources',
    'get_schema', 'list_dashboards', 'get_dashboard', 'get_dashboard_by_slug',
    'get_dashboard_layout', 'get_visualization', 'get_dashboard_parameters',
    'get_widget_parameter_mappings', 'execute_query',
    'execute_parameterized_query', 'execute_adhoc_query',
})

ADHOC_SOURCE_ID = 20

EXECUTION_TOOL_NOTES = {
    'execute_query': 'Runs the saved query and returns its result rows.',
    'execute_parameterized_query': 'Runs the parameterized query and returns its result rows.',
    'execute_adhoc_query': (
        'Runs SQL and returns result rows. Harr routes this tool only to PerfDSP PROD '
        '(dataSourceId 20) and always applies Redash auto-limit.'
    ),
}

QUERY_METADATA_NOTES = {
    'list_queries': (
        'Lists saved query definitions only; it does not execute queries, refresh results, or return result rows.'
    ),
    'get_query': (
        'Returns saved query metadata and SQL definition only; it does not execute SQL, refresh results, or return result rows.'
    ),
    'get_query_parameters': (
        'Returns saved query parameter metadata only; it does not execute SQL or return result rows.'
    ),
}


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
                    visible = []
                    for tool in tools:
                        if not isinstance(tool, dict) or not allowed(tool.get('name')):
                            continue
                        execution_note = EXECUTION_TOOL_NOTES.get(tool.get('name'))
                        if execution_note:
                            tool = dict(tool)
                            description = tool.get('description')
                            tool['description'] = (
                                f'{description} {execution_note}'
                                if isinstance(description, str) and description
                                else execution_note
                            )
                        if tool.get('name') == 'execute_adhoc_query':
                            tool = dict(tool)
                            schema = dict(tool.get('inputSchema') or {})
                            properties = dict(schema.get('properties') or {})
                            source = dict(properties.get('dataSourceId') or {})
                            source['enum'] = [ADHOC_SOURCE_ID]
                            source['description'] = 'PerfDSP PROD Redash data source (id 20).'
                            properties['dataSourceId'] = source
                            schema['properties'] = properties
                            tool['inputSchema'] = schema
                        note = QUERY_METADATA_NOTES.get(tool.get('name'))
                        if note:
                            tool = dict(tool)
                            description = tool.get('description')
                            if isinstance(description, str) and description:
                                tool['description'] = f'{description} {note}'
                            else:
                                tool['description'] = note
                        visible.append(tool)
                    obj['result']['tools'] = visible
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
                if params.get('name') == 'execute_adhoc_query':
                    arguments = params.get('arguments')
                    if not isinstance(arguments, dict) or type(arguments.get('dataSourceId')) is not int or arguments['dataSourceId'] != ADHOC_SOURCE_ID:
                        if 'id' in obj:
                            send(sys.stdout.buffer, {'jsonrpc': '2.0', 'id': obj['id'], 'error': {'code': -32602, 'message': 'execute_adhoc_query is restricted to PerfDSP PROD (dataSourceId 20)'}})
                        continue
                    params = dict(params)
                    arguments = dict(arguments)
                    arguments['dataSourceId'] = ADHOC_SOURCE_ID
                    arguments['applyAutoLimit'] = True
                    params['arguments'] = arguments
                    obj = dict(obj)
                    obj['params'] = params
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
