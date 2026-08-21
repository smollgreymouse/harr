function Service-Names { return [string[]]@(Manager-Lines @('names','--lifecycle','service')) }
function All-Mcp-Names { return [string[]]@(Manager-Lines @('names')) }
function Catalog-Service-Names { return [string[]]@(Catalog-Manager-Lines @('names','--lifecycle','service')) }

function Task-Name([string]$Name) {
    foreach ($server in @(Catalog-McpServers)) {
        if ([string]$server.name -ne $Name) { continue }
        if ($server.PSObject.Properties.Name -contains 'windows_task' -and $server.windows_task) { return [string]$server.windows_task }
        break
    }
    return "Harr MCP $Name"
}

function Register-ServiceTasks {
    if (-not (Get-Command Register-ScheduledTask -ErrorAction SilentlyContinue)) { throw 'Windows ScheduledTasks module is required for service MCP lifecycle' }
    [string[]]$active = @(Service-Names)
    foreach ($name in @(Catalog-Service-Names)) {
        if (-not $name) { continue }
        $taskName = Task-Name $name
        if ($active -notcontains $name) {
            try { Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue } catch { }
            try { Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue } catch { }
            continue
        }
        $argument = "-NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $WindowsDir 'files\mcp\harr-mcp-run.ps1')`" -Log $name"
        $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $argument
        $trigger = New-ScheduledTaskTrigger -AtLogOn
        $identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
        $principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
        $settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
        Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
        Write-Host "Registered user logon task: $taskName"
    }
}

function Task-Exists([string]$Name) {
    $taskName = Task-Name $Name
    try { [void](Get-ScheduledTask -TaskName $taskName -ErrorAction Stop); return $true } catch { return $false }
}

function Endpoint-Reachable([string]$Url) {
    if (-not $Url) { return $null }
    try {
        $uri = [Uri]$Url
        $client = New-Object Net.Sockets.TcpClient
        try {
            $port = if ($uri.Port -gt 0) { $uri.Port } elseif ($uri.Scheme -eq 'https') { 443 } else { 80 }
            $async = $client.BeginConnect($uri.Host, $port, $null, $null)
            if (-not $async.AsyncWaitHandle.WaitOne(500)) { return $false }
            $client.EndConnect($async)
            return $true
        } finally { $client.Close() }
    } catch { return $false }
}

function Mcp-Targets([string]$Target) {
    [string[]]$services = @(Service-Names)
    if ($Target -eq 'all') { return $services }
    if ($services -notcontains $Target) { throw "unknown or non-service enabled Harr MCP: $Target" }
    return [string[]]@($Target)
}

function Mcp-Action([string]$Action, [string]$Target) {
    foreach ($name in @(Mcp-Targets $Target)) {
        $taskName = Task-Name $name
        if (-not (Task-Exists $name)) { throw "Harr MCP task is not installed: $taskName" }
        switch ($Action) {
            'start' { Start-ScheduledTask -TaskName $taskName }
            'stop' { Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue }
            'restart' { Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue; Start-Sleep -Milliseconds 200; Start-ScheduledTask -TaskName $taskName }
            default { throw "unknown MCP action: $Action" }
        }
    }
}

function Mcp-Status {
    Write-Host ('{0,-16} {1,-12} {2,-12} {3}' -f 'MCP','TASK','ENDPOINT','URL')
    foreach ($name in @(Service-Names)) {
        $taskState = 'missing'
        if (Task-Exists $name) { $taskState = (Get-ScheduledTask -TaskName (Task-Name $name)).State.ToString().ToLowerInvariant() }
        $url = (Manager-Lines @('server-field',$name,'url') | Select-Object -First 1)
        $reachable = Endpoint-Reachable $url
        $endpoint = if ($null -eq $reachable) { '-' } elseif ($reachable) { 'reachable' } else { 'unreachable' }
        Write-Host ('{0,-16} {1,-12} {2,-12} {3}' -f $name,$taskState,$endpoint,$url)
    }
}

function Mcp-Available {
    Ensure-McpEffective
    [string[]]$active = @(Active-McpNames)
    Write-Host ('{0,-14} {1,-10} {2}' -f 'MCP','STATE','KIND')
    Write-Host ('{0,-14} {1,-10} {2}' -f 'leanctx','enabled','required')
    foreach ($server in @(Catalog-McpServers)) {
        $name = [string]$server.name
        $state = if ($active -contains $name) { 'enabled' } else { 'disabled' }
        $kind = if ($server.required -eq $true) { 'required' } else { 'optional' }
        Write-Host ('{0,-14} {1,-10} {2}' -f $name,$state,$kind)
    }
}

function Mcp-Configure([string]$Spec = '') {
    Ensure-McpEffective
    [string[]]$selectorArgs = @('--catalog', $McpCatalog, '--selection', $McpSelection, '--effective', $McpEffective, '--default', 'all')
    if ($Spec) { $selectorArgs += @('--spec', $Spec) } else { $selectorArgs += '--configure' }
    [void](Invoke-Python (@($Selector) + $selectorArgs))
    Install-Components 'mcp'
    Apply-Agents 'all'
    Write-Host 'MCP selection applied. Disabled MCP env/secret files were preserved.'
}

function Mcp-Logs([string]$Name) {
    if (@(Service-Names) -notcontains $Name) { throw "unknown or non-service enabled Harr MCP: $Name" }
    $log = Join-Path $LogDir "$Name.log"
    if (Test-Path -LiteralPath $log) { Get-Content -Tail 100 -LiteralPath $log }
    else { Write-Host "No MCP log yet: $log" }
}

function Uninstall-Harr {
    if (-not (Test-Path $StateHelper)) { throw "Harr state helper missing: $StateHelper" }
    & $StateHelper safety-snapshot | Out-Host
    foreach ($name in @(Catalog-Service-Names)) {
        $taskName = Task-Name $name
        try { Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue } catch { }
        try { Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue } catch { }
    }
    & $StateHelper restore
    if (Test-Path $StateRoot) { Remove-Item -LiteralPath $StateRoot -Recurse -Force }
    Write-Host 'Harr rollback completed. Project files were not touched.'
}
