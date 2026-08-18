usage() {
  cat <<'EOF_HELP'
Harr — global harness for token-efficient MCP infrastructure

First install / takeover:
  ./install.sh --clean

CLI:
  harr install [all|leanctx|mcp]
  harr status
  harr hosts apply
  harr hosts status
  harr agents apply [all|codex|opencode]
  harr agents status
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
  harr uninstall

Ownership:
  Harr owns its GLOBAL harness policy/configuration after --clean.
  Project-level AGENTS/config/skills are never touched.
  Third-party OpenCode MCPs/plugins/providers/agents/skills are preserved unless
  they are known retired opencode-workflow components replaced by Harr.

Managed stack:
  LeanCTX 3.9.15
  @zereight/mcp-gitlab (long-lived HTTP service)
  CodeGraph (installed by Harr, spawned by LeanCTX over stdio)
  compact host-specific global AGENTS policy
  diagnostic Harr/LeanCTX skills

Rollback:
  harr uninstall restores the exact pre-Harr global snapshot.
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
