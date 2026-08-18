usage() {
  cat <<'EOF'
Harr — local harness supervisor for MCP servers

Usage:
  harr status
  harr mcp list
  harr mcp start NAME|all
  harr mcp stop NAME|all
  harr mcp restart NAME|all
  harr mcp enable NAME|all
  harr mcp disable NAME|all
  harr mcp status [NAME]
  harr mcp logs NAME [-f|--follow]
  harr version

Examples:
  harr mcp start gitlab
  harr mcp status gitlab
  harr mcp status
  harr status
  harr mcp restart all
EOF
}

mcp_usage() {
  cat <<'EOF'
Usage:
  harr mcp list
  harr mcp start NAME|all
  harr mcp stop NAME|all
  harr mcp restart NAME|all
  harr mcp enable NAME|all
  harr mcp disable NAME|all
  harr mcp status [NAME]
  harr mcp logs NAME [-f|--follow]
EOF
}
