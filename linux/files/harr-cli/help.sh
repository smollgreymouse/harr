usage() {
  cat <<'EOF_HELP'
Harr — global harness for token-efficient MCP infrastructure

Initial user setup after package installation:
  harr setup --clean
  harr setup --clean --all        # full setup, no prompts
  harr setup --clean --mcp none   # LeanCTX + CodeGraph only

From a source checkout, ./install.sh is an equivalent installer entrypoint.

CLI:
  harr setup [--clean] [--start] [--all|--mcp SPEC] [--configure-mcp] [--harr-only]
  harr install [all|leanctx|mcp]
  harr status
  harr doctor [NAME] [--local|--json|--verbose|--strict] [--repair [--dry-run]]
  harr hosts apply
  harr hosts status
  harr agents apply [all|codex|opencode]
  harr agents status
  harr secret set NAME
  harr secret status
  harr secret unset NAME
  harr leanctx apply
  harr leanctx status
  harr workspace show|list
  harr workspace add PATH
  harr workspace remove PATH
  harr git <git-arguments>
  harr kube configure [--source PATHLIST] [--kubectl PATH] [--allow-exec] [--no-check]
  harr kube sync [--allow-exec] [--no-check]
  harr kube status [--no-check]
  harr kubectl <kubectl args...>
  harr ein configure                         # add/edit named Ein MCP workers
  harr ein apply                             # publish to LeanCTX and host skills/policy
  harr ein add --id NAME --adapter ADAPTER
  harr ein list|show NAME|edit NAME|enable NAME|disable NAME|remove NAME|test NAME
  harr mcp list
  harr mcp available
  harr mcp configure [none|all|name1,name2]
  harr mcp add NAME[,NAME...]|all
  harr mcp remove NAME[,NAME...]|all
  harr mcp start NAME|all
  harr mcp stop NAME|all
  harr mcp restart NAME|all
  harr mcp enable NAME|all
  harr mcp disable NAME|all
  harr mcp status [NAME]
  harr mcp logs NAME [-f|--follow]
  harr uninstall

Managed baseline:
  LeanCTX 3.11.0 Harr build (required)
  CodeGraph (required; spawned by LeanCTX over stdio)
  optional registry MCPs are installed only when selected
  compact MCP-aware global AGENTS policy
  diagnostic Harr/LeanCTX skills filtered to the selected MCP set

Host Git transport:
  `harr git <git-arguments>` executes Git in the Harr user service outside the
  agent sandbox. It preserves the current working directory and uses the user
  service's SSH_AUTH_SOCK, so terminal SSH keys and Git
  credential helpers work without changing repository or global Git config.
  GitLab PAT secrets authenticate GitLab MCP API operations only.

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
  harr mcp add NAME[,NAME...]|all
  harr mcp remove NAME[,NAME...]|all
  harr mcp start NAME|all
  harr mcp stop NAME|all
  harr mcp restart NAME|all
  harr mcp enable NAME|all
  harr mcp disable NAME|all
  harr mcp status [NAME]
  harr mcp logs NAME [-f|--follow]
EOF_HELP
}
