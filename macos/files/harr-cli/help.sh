usage() {
  cat <<'EOF'
Harr — global token-efficient MCP harness

First install / takeover:
  ./install.sh --clean
  ./install.sh --clean --all        # full install, no prompts
  ./install.sh --clean --mcp none   # LeanCTX + CodeGraph only

CLI:
  harr status
  harr install [all|leanctx|mcp]
  harr hosts apply|status
  harr agents apply [all|codex|opencode]
  harr agents status
  harr leanctx apply|status
  harr secret set NAME
  harr secret status
  harr secret unset NAME
  harr git push [git-push-options] [remote] [refspec...]
  harr mcp list
  harr mcp available
  harr mcp configure [none|all|name1,name2]
  harr mcp start|stop|restart|enable|disable NAME|all
  harr mcp status [NAME]
  harr mcp logs NAME [-f|--follow]
  harr uninstall

LeanCTX and CodeGraph are required. Optional registry MCPs are installed only
when selected; global policy and Harr skill references follow the same set.

With GitLab enabled, `harr git push` is the common host-independent fallback
for SSH/auth failures: it performs a real Git push over HTTPS using the stored
Harr GitLab PAT through GIT_ASKPASS without changing the repository remote.
EOF
}

mcp_usage() {
  printf '%s\n' \
    'Usage:' \
    '  harr mcp list' \
    '  harr mcp available' \
    '  harr mcp configure [none|all|name1,name2]' \
    '  harr mcp start|stop|restart|enable|disable NAME|all' \
    '  harr mcp status [NAME]' \
    '  harr mcp logs NAME [-f|--follow]'
}
