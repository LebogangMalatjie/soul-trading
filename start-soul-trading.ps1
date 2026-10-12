param(
    [switch]$Install
)

$ErrorActionPreference = 'Stop'

$backendPath = Join-Path $PSScriptRoot 'BACK'
$frontendPath = Join-Path $PSScriptRoot 'FRONT'
$aiMetaLayerPath = 'C:\Users\lebog\OneDrive\Desktop\ai_meta_layer.py'
$aiMetaConfigPath = Join-Path $PSScriptRoot 'ai_meta_config.json'
$pythonPath = 'C:\Python314\python.exe'
$nextCliPath = Join-Path $frontendPath 'node_modules\next\dist\bin\next'

if ($Install) {
    $requiredUserVariables = @(
        'DATABASE_URL',
        'SOUL_ACCESS_KEY',
        'SOUL_SHUTDOWN_KEY',
        'MT5_LOGIN',
        'MT5_SERVER'
    )
    $missingUserVariables = @(
        $requiredUserVariables | Where-Object {
            [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($_, 'User'))
        }
    )
    if ($missingUserVariables.Count -gt 0) {
        throw "Set these Windows user environment variables before installing startup: $($missingUserVariables -join ', ')."
    }
    if (
        [Environment]::GetEnvironmentVariable('SOUL_ACCESS_KEY', 'User').Length -lt 24 -or
        [Environment]::GetEnvironmentVariable('SOUL_SHUTDOWN_KEY', 'User').Length -lt 24
    ) {
        throw 'SOUL_ACCESS_KEY and SOUL_SHUTDOWN_KEY must each be at least 24 characters long.'
    }

    $startupPath = [Environment]::GetFolderPath('Startup')
    $shortcutPath = Join-Path $startupPath 'Soul Trading.lnk'
    $batchPath = Join-Path $PSScriptRoot 'start-soul-trading.bat'
    if (-not (Test-Path -LiteralPath $batchPath -PathType Leaf)) {
        throw "Startup batch file was not found: $batchPath"
    }
    $shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $batchPath
    $shortcut.Arguments = ''
    $shortcut.WorkingDirectory = $PSScriptRoot
    $shortcut.Description = 'Start Soul Trading, its AI learning layer and dashboard at sign-in'
    $shortcut.Save()
    Write-Host "Startup shortcut installed: $shortcutPath"
    exit 0
}

try {
    if (-not (Test-Path -LiteralPath $backendPath -PathType Container)) {
        throw "Backend folder not found: $backendPath"
    }
    if (-not (Test-Path -LiteralPath $frontendPath -PathType Container)) {
        throw "Frontend folder not found: $frontendPath"
    }
    if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
        throw "Python was not found at $pythonPath. Update the Python path in this script."
    }
    if (-not (Test-Path -LiteralPath $aiMetaLayerPath -PathType Leaf)) {
        throw "AI meta-layer was not found: $aiMetaLayerPath"
    }
    if (-not (Test-Path -LiteralPath $nextCliPath -PathType Leaf)) {
        throw "Next.js was not found at $nextCliPath. Install the frontend dependencies with npm install."
    }
    $nodePath = (Get-Command node.exe -ErrorAction Stop).Source

    $requiredVariables = @(
        'DATABASE_URL',
        'SOUL_ACCESS_KEY',
        'SOUL_SHUTDOWN_KEY',
        'MT5_LOGIN',
        'MT5_SERVER'
    )
    $missingVariables = @(
        $requiredVariables | Where-Object {
            [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($_))
        }
    )
    if ($missingVariables.Count -gt 0) {
        throw "Set these Windows user environment variables before startup: $($missingVariables -join ', ')."
    }
    if ($env:SOUL_ACCESS_KEY.Length -lt 24 -or $env:SOUL_SHUTDOWN_KEY.Length -lt 24) {
        throw 'SOUL_ACCESS_KEY and SOUL_SHUTDOWN_KEY must each be at least 24 characters long.'
    }

    $env:BROKER = 'mt5'
    $env:ALLOWED_ORIGINS = 'http://localhost:3000'
    $env:SYMBOL_MAP = '{"BTCUSD":"BTCUSDm"}'
    $env:AI_META_LAYER_PATH = $aiMetaLayerPath
    if (Test-Path -LiteralPath $aiMetaConfigPath -PathType Leaf) {
        $env:AI_META_CONFIG = $aiMetaConfigPath
    }
    else {
        Remove-Item Env:\AI_META_CONFIG -ErrorAction SilentlyContinue
    }

    $logDirectory = Join-Path $env:LOCALAPPDATA 'SoulTrading'
    New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
    $backendProcess = Start-Process `
        -FilePath $pythonPath `
        -ArgumentList @('-m', 'uvicorn', 'main:app', '--host', '0.0.0.0', '--port', '8000', '--workers', '1') `
        -WorkingDirectory $backendPath `
        -RedirectStandardOutput (Join-Path $logDirectory 'backend.log') `
        -RedirectStandardError (Join-Path $logDirectory 'backend-error.log') `
        -PassThru

    $nextCliArgument = '"' + $nextCliPath + '" dev'
    $frontendProcess = Start-Process `
        -FilePath $nodePath `
        -ArgumentList $nextCliArgument `
        -WorkingDirectory $frontendPath `
        -RedirectStandardOutput (Join-Path $logDirectory 'frontend.log') `
        -RedirectStandardError (Join-Path $logDirectory 'frontend-error.log') `
        -PassThru

    $backendReady = $false
    $frontendReady = $false
    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline -and (-not $backendReady -or -not $frontendReady)) {
        if (-not $backendReady) {
            try {
                $null = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 2 -UseBasicParsing
                $backendReady = $true
            }
            catch {}
        }
        if (-not $frontendReady) {
            try {
                $null = Invoke-WebRequest -Uri 'http://127.0.0.1:3000' -TimeoutSec 2 -UseBasicParsing
                $frontendReady = $true
            }
            catch {}
        }
        if (-not $backendReady -or -not $frontendReady) {
            Start-Sleep -Seconds 2
        }
    }

    if ($backendReady -and $frontendReady) {
        Start-Process 'http://localhost:3000'
    }
    Add-Content -LiteralPath (Join-Path $logDirectory 'startup.log') -Encoding UTF8 `
        -Value "$(Get-Date -Format o) Started via BAT: backend PID $($backendProcess.Id), frontend PID $($frontendProcess.Id), AI meta-layer $aiMetaLayerPath; ready backend=$backendReady frontend=$frontendReady."
}
catch {
    $message = $_.Exception.Message
    $logDirectory = Join-Path $env:LOCALAPPDATA 'SoulTrading'
    New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
    $logPath = Join-Path $logDirectory 'startup.log'
    Add-Content -LiteralPath $logPath -Encoding UTF8 -Value "$(Get-Date -Format o) Startup failed: $message"

    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show(
        "$message`n`nSee $logPath for startup details.",
        'Soul Trading startup failed',
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error
    ) | Out-Null
    exit 1
}
