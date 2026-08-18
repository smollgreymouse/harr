usage() {
  cat <<'EOF_HELP'
Harr — local harness supervisor for MCP infrastructure

Usage:
  harr install [all|leanctx|mcp]
  harr status
  harr secret set gitlab
  harr secret status
  harr secret unset gitlab
  harr leanctx apply
  harr leanctx status
  harr mcp list
  harr mcp start NAME|all
  harr mcp stop NAME|all
  harr mcp restart NAME|all
  harr mcp enable NAME|all
  harr mcp disable NAME|all
  harr mcp status [NAME]
  harr mcp logs NAME [-f|--follow]

Managed stack:
  LeanCTX 3.9.15
  @zereight/mcp-gitlab
  CodeGraph
  Supergateway bridge for CodeGraph stdio -> Streamable HTTP
EOF_HELP
}

mcp_usage() {
  cat <<'EOF_HELP'
Usage:
  harr mcp list
  harr mcp start NAME|all
  harr mcp stop NAME|all
  harr mcp restart NAME|all
  harr mcp enable NAME|all
  harr mcp disable NAME|all
  harr mcp status [NAME]
  harr mcp logs NAME [-f|--follow]
EOF_HELP
}
