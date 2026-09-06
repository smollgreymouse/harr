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
  harr git <git-arguments>
  harr kube configure [--source PATHLIST] [--kubectl PATH] [--allow-exec] [--no-check]
  harr kube sync [--allow-exec] [--no-check]
  harr kube status [--no-check]
  harr kubectl <kubectl args...>
  harr mcp list
  harr mcp available
  harr mcp configure [none|all|name1,name2]
  harr mcp start|stop|restart|enable|disable NAME|all
  harr mcp status [NAME]
  harr mcp logs NAME [-f|--follow]
  harr uninstall

LeanCTX and CodeGraph are required. Optional registry MCPs are installed only
when selected; global policy and Harr skill references follow the same set.

`harr git <git-arguments>` executes Git in a loopback-only Harr user service
outside the agent sandbox with the terminal SSH agent and credential helpers.
GitLab PAT secrets authenticate GitLab MCP API operations only.

`harr kube configure` captures the working kubectl configuration as a private
flattened Harr snapshot. `harr kubectl ...` always runs the real kubectl with
that managed config, so agent hosts do not need access to ~/.kube/config.
Exec credential helpers are rejected by default unless explicitly allowed.
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
