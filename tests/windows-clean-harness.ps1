Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Temp = Join-Path ([IO.Path]::GetTempPath()) ('harr-windows-test-' + [guid]::NewGuid().ToString('N'))
$HomeDir = Join-Path $Temp 'home'
$LocalDir = Join-Path $Temp 'localappdata'
$ConfigDir = Join-Path $HomeDir '.config'
$CodexDir = Join-Path $HomeDir '.codex'
$OpenCodeDir = Join-Path $ConfigDir 'opencode'

try {
    New-Item -ItemType Directory -Force -Path $CodexDir, (Join-Path $OpenCodeDir 'commands'), (Join-Path $OpenCodeDir 'skills\external'), (Join-Path $ConfigDir 'lean-ctx'), $LocalDir | Out-Null
    $env:HARR_HOME = $HomeDir
    $env:HARR_LOCALAPPDATA = $LocalDir
    $env:USERPROFILE = $HomeDir
    $env:HOME = $HomeDir
    $env:LOCALAPPDATA = $LocalDir
    $env:XDG_CONFIG_HOME = $ConfigDir
    $env:CODEX_HOME = $CodexDir
    $env:HARR_CODEX_DISABLE_CLI = '1'

    Set-Content -NoNewline -Encoding utf8 -Path (Join-Path $CodexDir 'AGENTS.md') -Value 'OLD CODEX POLICY'
    @'
model = "keep-model"

[mcp_servers.external-mcp]
url = "https://example.invalid/codex-mcp"
enabled = true

[mcp_servers.lean-ctx]
command = "old-lean-ctx"
enabled = false
'@ | Set-Content -Encoding utf8 -Path (Join-Path $CodexDir 'config.toml')
    Set-Content -NoNewline -Encoding utf8 -Path (Join-Path $OpenCodeDir 'AGENTS.md') -Value 'OLD OPENCODE POLICY'
    @'
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": ["external-plugin", "opencode-mcp-triage"],
  "provider": {"external-provider": {"api": "keep"}},
  "tools": {"bash": false, "read": false, "external_tool": true},
  "permission": {"task": "allow", "bash": "deny", "external_perm": "allow"},
  "default_agent": "flow",
  "subagent_depth": 2,
  "agent": {"flow": {"description": "old"}, "custom-agent": {"description": "keep"}},
  "mcp": {
    "codegraph": {"type": "local", "command": ["codegraph", "serve", "--mcp"], "enabled": true},
    "gitlab": {"type": "remote", "url": "http://127.0.0.1:9999/mcp"},
    "lean-ctx": {"type": "local", "command": ["old-lean-ctx"], "enabled": true},
    "external-mcp": {"type": "remote", "url": "https://example.invalid/mcp"}
  }
}
'@ | Set-Content -Encoding utf8 -Path (Join-Path $OpenCodeDir 'opencode.jsonc')
    Set-Content -NoNewline -Encoding utf8 -Path (Join-Path $OpenCodeDir 'commands\quick.md') -Value 'old quick command'
    Set-Content -NoNewline -Encoding utf8 -Path (Join-Path $OpenCodeDir 'commands\custom.md') -Value 'external command'
    Set-Content -NoNewline -Encoding utf8 -Path (Join-Path $OpenCodeDir 'skills\external\SKILL.md') -Value '# external skill'
    Set-Content -NoNewline -Encoding utf8 -Path (Join-Path $ConfigDir 'lean-ctx\config.toml') -Value 'OLD LEANCTX CONFIG'

    $before = @{
        CodexAgents = Get-Content -Raw (Join-Path $CodexDir 'AGENTS.md')
        CodexConfig = Get-Content -Raw (Join-Path $CodexDir 'config.toml')
        OpenAgents = Get-Content -Raw (Join-Path $OpenCodeDir 'AGENTS.md')
        OpenConfig = Get-Content -Raw (Join-Path $OpenCodeDir 'opencode.jsonc')
        Quick = Get-Content -Raw (Join-Path $OpenCodeDir 'commands\quick.md')
        Lean = Get-Content -Raw (Join-Path $ConfigDir 'lean-ctx\config.toml')
    }

    & (Join-Path $Root 'install.ps1') -Clean -HarrOnly -NoPathUpdate -Mcp none

    $codexAgents = Get-Content -Raw (Join-Path $CodexDir 'AGENTS.md')
    $openAgents = Get-Content -Raw (Join-Path $OpenCodeDir 'AGENTS.md')
    if ($codexAgents -notmatch 'codegraph::codegraph_explore' -or $codexAgents -notmatch 'through `ctx_shell`') { throw 'Codex Harr policy was not applied' }
    if ($openAgents -notmatch 'lean-ctx_ctx_tools' -or $openAgents -notmatch 'Do not use native read/grep/glob/bash') { throw 'OpenCode Harr policy was not applied' }
    if ($codexAgents -match 'GitLab MR/pipeline' -or $codexAgents -match 'Grafana dashboard work') { throw 'Disabled MCP routing leaked into Codex policy' }
    if ($openAgents -match 'GitLab MR/pipeline' -or $openAgents -match 'Grafana dashboard work') { throw 'Disabled MCP routing leaked into OpenCode policy' }
    if ($codexAgents -match 'git-mcp' -or $openAgents -match 'git-mcp') { throw 'Retired git-mcp policy leaked into Windows install' }

    $selectionPath = Join-Path $ConfigDir 'harr\mcp-selection.json'
    $effectivePath = Join-Path $ConfigDir 'harr\mcp-registry.json'
    $selection = Get-Content -Raw $selectionPath | ConvertFrom-Json
    $effective = Get-Content -Raw $effectivePath | ConvertFrom-Json
    if (@($selection.enabled).Count -ne 1 -or $selection.enabled[0] -ne 'codegraph') { throw 'Windows required-only selection is wrong' }
    if (@($effective.servers).Count -ne 1 -or $effective.servers[0].name -ne 'codegraph') { throw 'Windows effective registry is wrong' }

    $leanText = Get-Content -Raw (Join-Path $ConfigDir 'lean-ctx\config.toml')
    if ($leanText -notmatch 'name = "codegraph"') { throw 'CodeGraph missing from LeanCTX gateway' }
    if ($leanText -match 'name = "gitlab"' -or $leanText -match 'name = "grafana"') { throw 'Disabled MCP leaked into LeanCTX gateway' }

    $harrSkill = Join-Path $OpenCodeDir 'skills\harr'
    if (Test-Path (Join-Path $harrSkill 'references\gitlab.md')) { throw 'Disabled GitLab reference installed' }
    if (Test-Path (Join-Path $harrSkill 'references\grafana.md')) { throw 'Disabled Grafana reference installed' }

    $leanCommand = Join-Path $LocalDir 'Harr\bin\lean-ctx.cmd'
    $open = Get-Content -Raw (Join-Path $OpenCodeDir 'opencode.jsonc') | ConvertFrom-Json
    if ($open.provider.'external-provider'.api -ne 'keep') { throw 'Unrelated OpenCode provider was not preserved' }
    if ($open.mcp.'external-mcp'.url -ne 'https://example.invalid/mcp') { throw 'Unrelated OpenCode MCP was not preserved' }
    if ($open.mcp.'lean-ctx'.command[0] -ne $leanCommand) { throw "Wrong OpenCode LeanCTX command: $($open.mcp.'lean-ctx'.command[0])" }
    $mcpNames = @($open.mcp.PSObject.Properties.Name)
    if ($mcpNames -contains 'codegraph' -or $mcpNames -contains 'gitlab') { throw 'Direct Harr MCP routes were not removed from OpenCode' }
    if (Test-Path (Join-Path $OpenCodeDir 'commands\quick.md')) { throw 'Retired workflow command survived clean takeover' }
    if (-not (Test-Path (Join-Path $OpenCodeDir 'commands\custom.md'))) { throw 'Unrelated OpenCode command was removed' }
    if (-not (Test-Path (Join-Path $OpenCodeDir 'skills\harr\SKILL.md'))) { throw 'Harr skill missing' }
    if (-not (Test-Path (Join-Path $OpenCodeDir 'skills\lean-ctx\SKILL.md'))) { throw 'LeanCTX skill missing' }

    $codexText = Get-Content -Raw (Join-Path $CodexDir 'config.toml')
    $tomlLeanCommand = $leanCommand.Replace('\', '\\')
    if (-not $codexText.Contains('model = "keep-model"') -or -not $codexText.Contains($tomlLeanCommand)) { throw 'Codex config did not preserve existing settings and register LeanCTX' }
    if (-not $codexText.Contains('default_tools_approval_mode = "auto"')) { throw 'Codex LeanCTX tools were not auto-approved' }

    if (-not (Test-Path (Join-Path $LocalDir 'Harr\libexec\common\mcp\registry.json'))) { throw 'Installed common MCP catalog missing' }
    if (-not (Test-Path (Join-Path $LocalDir 'Harr\bin\harr-mcp-run.cmd'))) { throw 'Generic Windows MCP runner missing' }

    & (Join-Path $Root 'uninstall.ps1')

    if ((Get-Content -Raw (Join-Path $CodexDir 'AGENTS.md')) -ne $before.CodexAgents) { throw 'Codex AGENTS rollback mismatch' }
    if ((Get-Content -Raw (Join-Path $CodexDir 'config.toml')) -ne $before.CodexConfig) { throw 'Codex config rollback mismatch' }
    if ((Get-Content -Raw (Join-Path $OpenCodeDir 'AGENTS.md')) -ne $before.OpenAgents) { throw 'OpenCode AGENTS rollback mismatch' }
    if ((Get-Content -Raw (Join-Path $OpenCodeDir 'opencode.jsonc')) -ne $before.OpenConfig) { throw 'OpenCode config rollback mismatch' }
    if ((Get-Content -Raw (Join-Path $OpenCodeDir 'commands\quick.md')) -ne $before.Quick) { throw 'OpenCode command rollback mismatch' }
    if ((Get-Content -Raw (Join-Path $ConfigDir 'lean-ctx\config.toml')) -ne $before.Lean) { throw 'LeanCTX config rollback mismatch' }
    if (-not (Test-Path (Join-Path $OpenCodeDir 'commands\custom.md'))) { throw 'Unrelated command disappeared after rollback' }
    if (-not (Test-Path (Join-Path $OpenCodeDir 'skills\external\SKILL.md'))) { throw 'Unrelated skill disappeared after rollback' }
    if ((Test-Path $selectionPath) -or (Test-Path $effectivePath)) { throw 'Harr MCP selection state survived rollback' }
    if (Test-Path (Join-Path $LocalDir 'Harr')) { throw 'Harr-created install root survived rollback' }
    if (Test-Path (Join-Path $LocalDir 'HarrState')) { throw 'Harr state root survived rollback' }

    Write-Host 'windows clean harness takeover/rollback: PASS'
}
finally {
    Remove-Item -LiteralPath $Temp -Recurse -Force -ErrorAction SilentlyContinue
}
