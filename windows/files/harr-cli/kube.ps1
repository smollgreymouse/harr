function Invoke-KubeStateSnapshot {
    if (-not (Test-Path -LiteralPath $StateHelper)) {
        throw "Harr state helper is unavailable; refusing to change managed Kubernetes state without rollback ownership: $StateHelper"
    }
    & $StateHelper snapshot | Out-Null
}

function Kube-Bridge([string[]]$CommandArgs) {
    $bridge = Join-Path $CommonDir 'kubernetes\kubectl.py'
    if (-not (Test-Path -LiteralPath $bridge)) { throw "Harr Kubernetes bridge missing: $bridge" }

    [string[]]$cmd = @(Resolve-Python)
    $exe = $cmd[0]
    [string[]]$prefix = @()
    if ($cmd.Count -gt 1) { $prefix = @($cmd[1..($cmd.Count - 1)]) }
    & $exe @prefix $bridge @CommandArgs
    if ($LASTEXITCODE -ne 0) { throw "Harr Kubernetes command failed ($LASTEXITCODE)" }
}

function Kube-Command([string[]]$CommandArgs) {
    $sub = if ($CommandArgs.Count) { $CommandArgs[0] } else { 'status' }
    [string[]]$rest = @()
    if ($CommandArgs.Count -gt 1) { $rest = @($CommandArgs[1..($CommandArgs.Count - 1)]) }
    switch ($sub) {
        'configure' { Invoke-KubeStateSnapshot; Kube-Bridge (@('configure') + $rest) }
        'sync' { Invoke-KubeStateSnapshot; Kube-Bridge (@('sync') + $rest) }
        'status' { Kube-Bridge (@('status') + $rest) }
        default { throw 'usage: harr kube {configure [--source PATHLIST] [--kubectl PATH] [--allow-exec] [--no-check]|sync [--allow-exec] [--no-check]|status [--no-check]}' }
    }
}

function Kubectl-Command([string[]]$CommandArgs) {
    Kube-Bridge (@('run', '--') + $CommandArgs)
}
