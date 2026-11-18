# Harr 0.3.12

Harr restores automatic Workspace binding for project-context LeanCTX launches. In `auto` mode, the launcher selects the nearest Git root from its working directory, or the working directory itself when it is outside a Git checkout. LeanCTX validates the candidate before Harr creates or changes a Workspace store. A suitable project starts with its normal project tools; an unavailable or unsafe candidate such as `$HOME` starts rootless, preserving the minimal pre-session MCP startup path.

OpenCode or ZCode processes launched before a project is selected remain rootless for that connection. Once a project is selected, reconnecting the host's project-context MCP launches LeanCTX with that project context and binds it automatically; users do not need a hardcoded per-project root in the global configuration. `HARR_WORKSPACE_ROOT` remains an explicit override, and `HARR_WORKSPACE_MODE=none` remains explicitly rootless.

Harr pins LeanCTX 3.11.0 Harr build 9, which adds a read-only typed Workspace-root preflight before startup. Invalid explicit roots and validator/store failures remain fatal. Regression coverage verifies automatic project binding and safe rootless fallback in both LeanCTX and Harr.
