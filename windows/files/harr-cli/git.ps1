function Require-GitLabGitTransport {
    Ensure-McpEffective
    if (@(Active-McpNames) -notcontains 'gitlab') {
        throw 'GitLab MCP is disabled; enable it before using Harr GitLab transport'
    }
    $git = Get-Command git.exe -ErrorAction SilentlyContinue
    if (-not $git) { $git = Get-Command git -ErrorAction SilentlyContinue }
    if (-not $git) { throw 'git is required for Harr Git transport' }
}

function GitLab-Command([string[]]$CommandArgs) {
    if ($CommandArgs.Count -eq 0) {
        throw 'usage: harr gitlab {fetch [git-fetch-options] [remote] [refspec...]|publish [remote]|push [git-push-options] [remote] [refspec...]}'
    }

    $sub = $CommandArgs[0]
    Require-GitLabGitTransport
    [string[]]$pythonArgs = @(
        (Join-Path $CommonDir 'gitlab\git_https.py'),
        $sub,
        '--registry', $McpEffective,
        '--config-dir', $McpConfig,
        '--secrets-dir', $SecretsDir
    )

    if ($sub -in @('fetch','push')) {
        [string[]]$pushArgs = @()
        if ($CommandArgs.Count -gt 1) { $pushArgs = @($CommandArgs[1..($CommandArgs.Count - 1)]) }
        $pythonArgs += '--'
        $pythonArgs += $pushArgs
    } elseif ($sub -eq 'publish') {
        if ($CommandArgs.Count -gt 2) { throw 'usage: harr gitlab publish [remote]' }
        $pythonArgs += $(if ($CommandArgs.Count -gt 1) { $CommandArgs[1] } else { 'origin' })
    } else {
        throw 'usage: harr gitlab {fetch [git-fetch-options] [remote] [refspec...]|publish [remote]|push [git-push-options] [remote] [refspec...]}'
    }

    [void](Invoke-Python $pythonArgs)
}
