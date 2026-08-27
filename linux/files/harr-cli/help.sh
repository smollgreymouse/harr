usage() {
  cat <<'EOF_HELP'
Harr — global harness for token-efficient MCP infrastructure

First install / takeover:
  ./install.sh --clean
  ./install.sh --clean --all        # full install, no prompts
  ./install.sh --clean --mcp none   # LeanCTX + CodeGraph only

CLI:
  harr install [all|leanctx|mcp]
  harr status
  harr hosts apply
  harr hosts status
  harr agents apply [all|codex|opencode]
  harr agents status
  harr secret set NAME
  harr secret status
  harr secret unset NAME
  harr leanctx apply
  harr leanctx status
  harr git fetch [git-fetch-options] [remote] [refspec...]
  harr git publish [remote]
  harr git push [git-push-options] [remote] [refspec...]
  harr kube configure [--source PATHLIST] [--kubectl PATH] [--allow-exec] [--no-check]
  harr kube sync [--allow-exec] [--no-check]
  harr kube status [--no-check]
  harr kubectl <kubectl args...>
  harr mcp list
  harr mcp available
  harr mcp configure [none|all|name1,name2]
  harr mcp start NAME|all
  harr mcp stop NAME|all
  harr mcp restart NAME|all
  harr mcp enable NAME|all
  harr mcp disable NAME|all
  harr mcp status [NAME]
  harr mcp logs NAME [-f|--follow]
  harr uninstall

Managed baseline:
  LeanCTX 3.9.15 (required)
  CodeGraph (required; spawned by LeanCTX over stdio)
  optional registry MCPs are installed only when selected
  compact MCP-aware global AGENTS policy
  diagnostic Harr/LeanCTX skills filtered to the selected MCP set

GitLab transport:
  With GitLab enabled, `harr git publish [remote]` publishes the current named
  local branch to the same-named remote branch with an explicit HEAD refspec,
  verifies the remote SHA, and fixes stale upstream tracking. It uses the stored
  Harr GitLab PAT through GIT_ASKPASS over HTTPS and never needs an SSH attempt.
  `harr git fetch` and `harr git push` use the same HTTPS/PAT transport for
  remote reads and custom push refspecs. Harr never changes global Git URL rewrites.

Kubernetes transport:
  `harr kube configure` captures the working kubectl configuration as a private
  flattened Harr snapshot. `harr kubectl ...` always runs the real kubectl with
  that managed config, so agent hosts do not need access to ~/.kube/config.
  Exec credential helpers are rejected by default unless explicitly allowed.

Ownership:
  Harr owns its GLOBAL harness policy/configuration after --clean.
  Project-level AGENTS/config/skills are never touched.
  Third-party OpenCode MCPs/plugins/providers/agents/skills are preserved unless
  they are known retired opencode-workflow components replaced by Harr.

Rollback:
  harr uninstall restores the exact pre-Harr global snapshot.
EOF_HELP
}

mcp_usage() {
  cat <<'EOF_HELP'
Usage:
  harr mcp list
  harr mcp available
  harr mcp configure [none|all|name1,name2]
  harr mcp start NAME|all
  harr mcp stop NAME|all
  harr mcp restart NAME|all
  harr mcp enable NAME|all
  harr mcp disable NAME|all
  harr mcp status [NAME]
  harr mcp logs NAME [-f|--follow]
EOF_HELP
}
