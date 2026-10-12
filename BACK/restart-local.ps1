$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

function Read-LocalPassword {
  $form = New-Object System.Windows.Forms.Form
  $form.Text = 'Restart Soul Trading backend'
  $form.StartPosition = 'CenterScreen'
  $form.Size = New-Object System.Drawing.Size(470, 190)
  $form.FormBorderStyle = 'FixedDialog'
  $form.MaximizeBox = $false
  $form.MinimizeBox = $false

  $label = New-Object System.Windows.Forms.Label
  $label.Text = 'Enter the MT5 password again. It will stay in this process memory only.'
  $label.Location = New-Object System.Drawing.Point(16, 18)
  $label.Size = New-Object System.Drawing.Size(420, 32)
  $form.Controls.Add($label)

  $password = New-Object System.Windows.Forms.TextBox
  $password.UseSystemPasswordChar = $true
  $password.Location = New-Object System.Drawing.Point(16, 58)
  $password.Size = New-Object System.Drawing.Size(420, 24)
  $form.Controls.Add($password)

  $ok = New-Object System.Windows.Forms.Button
  $ok.Text = 'Restart'
  $ok.Location = New-Object System.Drawing.Point(270, 100)
  $ok.DialogResult = [System.Windows.Forms.DialogResult]::OK
  $form.Controls.Add($ok)
  $form.AcceptButton = $ok

  $cancel = New-Object System.Windows.Forms.Button
  $cancel.Text = 'Cancel'
  $cancel.Location = New-Object System.Drawing.Point(360, 100)
  $cancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
  $form.Controls.Add($cancel)
  $form.CancelButton = $cancel

  if ($form.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
    throw 'Backend restart cancelled.'
  }
  return $password.Text
}

try {
  $env:SOUL_ACCESS_KEY = [Environment]::GetEnvironmentVariable('SOUL_ACCESS_KEY', 'User')
  $env:SOUL_SHUTDOWN_KEY = [Environment]::GetEnvironmentVariable('SOUL_SHUTDOWN_KEY', 'User')
  $env:MT5_LOGIN = [Environment]::GetEnvironmentVariable('MT5_LOGIN', 'User')
  $env:MT5_SERVER = [Environment]::GetEnvironmentVariable('MT5_SERVER', 'User')
  $env:MT5_PATH = [Environment]::GetEnvironmentVariable('MT5_PATH', 'User')
  $env:SYMBOL_MAP = [Environment]::GetEnvironmentVariable('SYMBOL_MAP', 'User')
  if ([string]::IsNullOrWhiteSpace($env:SYMBOL_MAP)) {
    $env:SYMBOL_MAP = '{"US30":"US30m","XAUUSD":"XAUUSDm"}'
    [Environment]::SetEnvironmentVariable('SYMBOL_MAP', $env:SYMBOL_MAP, 'User')
  }

  if ([string]::IsNullOrWhiteSpace($env:SOUL_ACCESS_KEY) -or $env:SOUL_ACCESS_KEY.Length -lt 24) {
    throw 'SOUL_ACCESS_KEY is missing or too short in your Windows user environment.'
  }
  if ([string]::IsNullOrWhiteSpace($env:SOUL_SHUTDOWN_KEY) -or $env:SOUL_SHUTDOWN_KEY.Length -lt 24) {
    throw 'SOUL_SHUTDOWN_KEY is missing or too short in your Windows user environment.'
  }
  if ([string]::IsNullOrWhiteSpace($env:MT5_LOGIN) -or [string]::IsNullOrWhiteSpace($env:MT5_SERVER)) {
    throw 'MT5_LOGIN and MT5_SERVER must be set in your Windows user environment.'
  }

  $password = Read-LocalPassword
  $listeners = @(Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue)
  foreach ($listener in $listeners) {
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)"
    if (-not $proc -or $proc.Name -ne 'python.exe' -or $proc.CommandLine -notmatch '-m uvicorn main:app') {
      throw "Port 8000 is occupied by an unexpected process (PID $($listener.OwningProcess)); refusing to stop it."
    }
  }

  foreach ($listener in $listeners) {
    Stop-Process -Id $listener.OwningProcess
  }
  if ($listeners.Count -gt 0) {
    $deadline = (Get-Date).AddSeconds(15)
    while ((Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) -and (Get-Date) -lt $deadline) {
      Start-Sleep -Milliseconds 250
    }
    if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) {
      throw 'The previous backend did not release port 8000 in time.'
    }
  }

  $env:MT5_PASSWORD = $password
  $env:BROKER = 'mt5'
  $env:ALLOWED_ORIGINS = 'http://localhost:3000'
  if (-not $env:DATABASE_URL) {
    $env:DATABASE_URL = 'postgresql://dev:dev@127.0.0.1:5432/soul'
  }
  Set-Location $PSScriptRoot
  Write-Host 'Starting the backend with your existing keys. Leave this window open.'
  & 'C:\Python314\python.exe' -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
}
catch {
  [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, 'Soul Trading backend restart', 'OK', 'Error') | Out-Null
  exit 1
}
