function Git-Command([string[]]$CommandArgs) {
    if ($CommandArgs.Count -eq 0 -or $CommandArgs[0] -ne 'push') {
        throw 'usage: harr git push [git-push-options] [remote] [refspec...]'
    }
    Ensure-McpEffective
    if (@(Active-McpNames) -notcontains 'gitlab') {
        throw 'GitLab MCP is disabled; enable it before using `harr git push`'
    }
    $git = Get-Command git.exe -ErrorAction SilentlyContinue
    if (-not $git) { $git = Get-Command git -ErrorAction SilentlyContinue }
    if (-not $git) { throw 'git is required for `harr git push`' }

    [string[]]$pushArgs = @()
    if ($CommandArgs.Count -gt 1) { $pushArgs = @($CommandArgs[1..($CommandArgs.Count - 1)]) }
    [string[]]$pythonArgs = @(
        (Join-Path $CommonDir 'gitlab\git_https.py'),
        'push',
        '--registry', $McpEffective,
        '--config-dir', $McpConfig,
        '--secrets-dir', $SecretsDir,
        '--'
    ) + $pushArgs
    [void](Invoke-Python $pythonArgs)
}
