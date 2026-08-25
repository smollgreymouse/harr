function Registry-Apply {
    New-Item -ItemType Directory -Force -Path $McpConfig, $SecretsDir | Out-Null
    Invoke-Manager @('install-configs', '--config-dir', $McpConfig)
}

function Apply-LeanCtx {
    New-Item -ItemType Directory -Force -Path $LeanConfigDir | Out-Null
    Invoke-Manager @('render-leanctx', '--base', (Join-Path $CommonDir 'leanctx\config.base.toml'), '--output', $LeanConfig, '--platform', 'windows', '--runner-command', 'harr-mcp-run')
    Write-Host "Applied Harr LeanCTX config from selected MCP registry: $LeanConfig"
}

function Write-CodeGraphWrapper {
    $launcher = Join-Path $NpmBin 'codegraph.cmd'
    if (-not (Test-Path -LiteralPath $launcher)) { throw "CodeGraph launcher missing: $launcher" }
    $cmd = "@echo off`r`n`"$launcher`" %*`r`n"
    Write-Utf8 (Join-Path $BinDir 'codegraph.cmd') $cmd
}

function Install-NodeStack {
    $node = Get-Command node.exe -ErrorAction SilentlyContinue
    if (-not $node) { $node = Get-Command node -ErrorAction SilentlyContinue }
    $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if (-not $npm) { $npm = Get-Command npm -ErrorAction SilentlyContinue }
    if (-not $node -or -not $npm) { throw 'Node.js and npm are required' }
    $major = [int](& $node.Source -p "Number(process.versions.node.split('.')[0])")
    if ($major -lt 20 -or $major -ge 25) { throw "Node.js 20-24 is required; current major: $major" }

    New-Item -ItemType Directory -Force -Path $NpmPrefix | Out-Null
    $packageText = (@(Manager-Lines @('npm-package-json')) -join "`n") + "`n"
    Write-Utf8 (Join-Path $NpmPrefix 'package.json') $packageText
    Write-Host 'Installing selected Harr npm MCP runtimes...'
    & $npm.Source install --prefix $NpmPrefix --omit=dev --no-audit --no-fund --package-lock=false
    if ($LASTEXITCODE -ne 0) { throw 'npm install failed for Harr MCP runtime' }
    Invoke-Manager @('prefetch-runtimes')
    $env:HARR_NPM_BIN_DIR = $NpmBin
    Write-CodeGraphWrapper
}

function Write-LeanWrapper {
    $wrapperScript = Join-Path $WindowsDir 'files\leanctx\lean-ctx-wrapper.ps1'
    $cmd = "@echo off`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$wrapperScript`" %*`r`n"
    Write-Utf8 $LeanCommand $cmd
}

function Install-LeanCtx {
    $arch = $env:PROCESSOR_ARCHITECTURE
    if ($arch -notin @('AMD64','x86_64')) { throw "Harr Windows currently supports x86_64 LeanCTX only; architecture: $arch" }
    $versionDir = Join-Path $VendorDir "lean-ctx\$LeanVersion"
    $real = Join-Path $versionDir 'lean-ctx.exe'
    if (Test-Path $real) {
        $versionOutput = & $real --version 2>$null
        if ($versionOutput -match [regex]::Escape($LeanVersion)) { Write-LeanWrapper; return }
    }

    $tmp = Join-Path ([IO.Path]::GetTempPath()) ('harr-leanctx-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path $tmp | Out-Null
    try {
        $assetName = 'lean-ctx-x86_64-pc-windows-msvc.zip'
        $base = "https://github.com/yvgude/lean-ctx/releases/download/v$LeanVersion"
        $archive = Join-Path $tmp $assetName
        $sums = Join-Path $tmp 'SHA256SUMS'
        Invoke-WebRequest -Uri "$base/$assetName" -OutFile $archive
        Invoke-WebRequest -Uri "$base/SHA256SUMS" -OutFile $sums
        $expected = $null
        foreach ($line in Get-Content $sums) {
            if ($line -match ('^([0-9a-fA-F]{64})\s+\*?' + [regex]::Escape($assetName) + '$')) { $expected = $Matches[1].ToLowerInvariant(); break }
        }
        if (-not $expected) { throw "Checksum entry not found for $assetName" }
        $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash.ToLowerInvariant()
        if ($actual -ne $expected) { throw "LeanCTX checksum mismatch: expected $expected, got $actual" }
        Expand-Archive -LiteralPath $archive -DestinationPath $tmp -Force
        $candidate = Get-ChildItem -Path $tmp -Filter 'lean-ctx.exe' -File -Recurse | Select-Object -First 1
        if (-not $candidate) { throw 'LeanCTX archive did not contain lean-ctx.exe' }
        New-Item -ItemType Directory -Force -Path $versionDir | Out-Null
        Copy-Item -LiteralPath $candidate.FullName -Destination $real -Force
        Write-LeanWrapper
    } finally {
        if (Test-Path $tmp) { Remove-Item -LiteralPath $tmp -Recurse -Force }
    }
}

function Secret-Meta([string]$Name) {
    $line = (Manager-Lines @('secret',$Name) | Select-Object -First 1)
    return ($line | ConvertFrom-Json)
}

function Secret-Command([string]$Action, [string]$Name = '') {
    if ($Action -eq 'status') {
        Write-Host ('{0,-16} {1}' -f 'SECRET','STATE')
        foreach ($line in @(Manager-Lines @('secrets'))) {
            if (-not $line) { continue }
            $meta = $line | ConvertFrom-Json
            $path = Join-Path $SecretsDir $meta.file
            $state = if ((Test-Path $path) -and (Get-Item $path).Length -gt 0) { 'configured' } else { 'missing' }
            Write-Host ('{0,-16} {1}' -f $meta.name,$state)
        }
        return
    }
    if (-not $Name) { throw 'usage: harr secret set|unset NAME | harr secret status' }
    $meta = Secret-Meta $Name
    $path = Join-Path $SecretsDir $meta.file
    if ($Action -eq 'set') {
        New-Item -ItemType Directory -Force -Path $SecretsDir | Out-Null
        $secure = Read-Host $meta.prompt -AsSecureString
        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        try { $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr); Write-Utf8 $path ($plain.Trim() + "`n") }
        finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
        Write-Host "$Name secret: configured"
    } elseif ($Action -eq 'unset') {
        Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
        Write-Host "$Name secret: missing"
    } else { throw 'usage: harr secret set|unset NAME | harr secret status' }
}

function Components-Status {
    $real = Join-Path $VendorDir "lean-ctx\$LeanVersion\lean-ctx.exe"
    $leanState = if (Test-Path $real) { 'installed' } else { 'missing' }
    Write-Host "leanctx $LeanVersion $leanState"
    foreach ($line in @(Manager-Lines @('components','--npm-prefix',$NpmPrefix))) { Write-Host $line }
}

function Install-Components([string]$Target) {
    Registry-Apply
    switch ($Target) {
        'all' { Install-NodeStack; Install-LeanCtx; Apply-LeanCtx; Register-ServiceTasks; Apply-Hosts; Apply-Agents 'all' }
        'mcp' { Install-NodeStack; Register-ServiceTasks; Apply-LeanCtx }
        'leanctx' { Install-LeanCtx; Apply-LeanCtx; Apply-Hosts; Apply-Agents 'all' }
        default { throw 'usage: harr install [all|leanctx|mcp]' }
    }
}
