usage() {
  cat <<'EOF'
Harr — global token-efficient MCP harness

Usage:
  harr status
  harr install [all|leanctx|mcp]
  harr hosts apply|status
  harr agents apply [all|codex|opencode]
  harr agents status
  harr leanctx apply|status
  harr secret set NAME
  harr secret status
  harr secret unset NAME
  harr mcp list
  harr mcp start|stop|restart|enable|disable NAME|all
  harr mcp status [NAME]
  harr mcp logs NAME [-f|--follow]
  harr uninstall
EOF
}

mcp_usage() {
  printf '%s\n' \
    'Usage:' \
    '  harr mcp list' \
    '  harr mcp start|stop|restart|enable|disable NAME|all' \
    '  harr mcp status [NAME]' \
    '  harr mcp logs NAME [-f|--follow]'
}
