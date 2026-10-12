$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

function Show-AccountDialog {
  $form = New-Object System.Windows.Forms.Form
  $form.Text = 'Soul Trading - Local MT5 setup'
  $form.StartPosition = 'CenterScreen'
  $form.Size = New-Object System.Drawing.Size(480, 290)
  $form.FormBorderStyle = 'FixedDialog'
  $form.MaximizeBox = $false
  $form.MinimizeBox = $false

  $labels = @('MT5 login number', 'MT5 broker server', 'MT5 password', 'MT5 terminal path (optional)')
  $fields = @()
  for ($i = 0; $i -lt $labels.Count; $i++) {
    $label = New-Object System.Windows.Forms.Label
    $label.Text = $labels[$i]
    $label.Location = New-Object System.Drawing.Point(18, (20 + 42 * $i))
    $label.Size = New-Object System.Drawing.Size(175, 24)
    $form.Controls.Add($label)

    $field = New-Object System.Windows.Forms.TextBox
    $field.Location = New-Object System.Drawing.Point(198, (17 + 42 * $i))
    $field.Size = New-Object System.Drawing.Size(245, 24)
    if ($i -eq 2) { $field.UseSystemPasswordChar = $true }
    if ($i -eq 3) { $field.Text = '' }
    $form.Controls.Add($field)
    $fields += $field
  }

  $note = New-Object System.Windows.Forms.Label
  $note.Text = 'Your MT5 password is kept only in the backend process and is not saved.'
  $note.Location = New-Object System.Drawing.Point(18, 186)
  $note.Size = New-Object System.Drawing.Size(430, 32)
  $form.Controls.Add($note)

  $ok = New-Object System.Windows.Forms.Button
  $ok.Text = 'Continue'
  $ok.Location = New-Object System.Drawing.Point(270, 220)
  $ok.DialogResult = [System.Windows.Forms.DialogResult]::OK
  $form.Controls.Add($ok)
  $form.AcceptButton = $ok

  $cancel = New-Object System.Windows.Forms.Button
  $cancel.Text = 'Cancel'
  $cancel.Location = New-Object System.Drawing.Point(360, 220)
  $cancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
  $form.Controls.Add($cancel)
  $form.CancelButton = $cancel

  $result = $form.ShowDialog()
  if ($result -ne [System.Windows.Forms.DialogResult]::OK) {
    throw 'Setup cancelled.'
  }
  return @{
    Login = $fields[0].Text.Trim()
    Server = $fields[1].Text.Trim()
    Password = $fields[2].Text
    TerminalPath = $fields[3].Text.Trim()
  }
}

function New-LocalSecret {
  $bytes = New-Object byte[] 32
  $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  try {
    $generator.GetBytes($bytes)
  } finally {
    $generator.Dispose()
  }
  return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function Show-SecretDialog([string]$title, [string]$message, [string]$secret) {
  $form = New-Object System.Windows.Forms.Form
  $form.Text = $title
  $form.StartPosition = 'CenterScreen'
  $form.Size = New-Object System.Drawing.Size(570, 180)
  $form.FormBorderStyle = 'FixedDialog'
  $form.MaximizeBox = $false
  $form.MinimizeBox = $false

  $label = New-Object System.Windows.Forms.Label
  $label.Text = $message
  $label.Location = New-Object System.Drawing.Point(14, 15)
  $label.Size = New-Object System.Drawing.Size(525, 32)
  $form.Controls.Add($label)

  $value = New-Object System.Windows.Forms.TextBox
  $value.Text = $secret
  $value.ReadOnly = $true
  $value.Location = New-Object System.Drawing.Point(14, 52)
  $value.Size = New-Object System.Drawing.Size(525, 25)
  $form.Controls.Add($value)

  $copy = New-Object System.Windows.Forms.Button
  $copy.Text = 'Copy'
  $copy.Location = New-Object System.Drawing.Point(385, 90)
  $copy.Add_Click({ [System.Windows.Forms.Clipboard]::SetText($value.Text) })
  $form.Controls.Add($copy)

  $ok = New-Object System.Windows.Forms.Button
  $ok.Text = 'Continue'
  $ok.Location = New-Object System.Drawing.Point(465, 90)
  $ok.DialogResult = [System.Windows.Forms.DialogResult]::OK
  $form.Controls.Add($ok)
  $form.AcceptButton = $ok
  [void]$form.ShowDialog()
}

try {
  $account = Show-AccountDialog
  if ($account.Login -notmatch '^\d+$' -or [long]$account.Login -le 0) {
    throw 'MT5 login must be a positive account number.'
  }
  if ($account.Server.Length -lt 2) {
    throw 'Enter the MT5 broker server name.'
  }

  $accessKey = New-LocalSecret
  $shutdownKey = New-LocalSecret

  [Environment]::SetEnvironmentVariable('SOUL_ACCESS_KEY', $accessKey, 'User')
  [Environment]::SetEnvironmentVariable('SOUL_SHUTDOWN_KEY', $shutdownKey, 'User')
  [Environment]::SetEnvironmentVariable('MT5_LOGIN', $account.Login, 'User')
  [Environment]::SetEnvironmentVariable('MT5_SERVER', $account.Server, 'User')
  [Environment]::SetEnvironmentVariable('MT5_PATH', $account.TerminalPath, 'User')
  $symbolMap = '{"US30":"US30m","XAUUSD":"XAUUSDm"}'
  [Environment]::SetEnvironmentVariable('SYMBOL_MAP', $symbolMap, 'User')

  $env:SOUL_ACCESS_KEY = $accessKey
  $env:SOUL_SHUTDOWN_KEY = $shutdownKey
  $env:MT5_LOGIN = $account.Login
  $env:MT5_SERVER = $account.Server
  $env:MT5_PASSWORD = $account.Password
  $env:MT5_PATH = $account.TerminalPath
  $env:SYMBOL_MAP = $symbolMap
  $env:BROKER = 'mt5'
  $env:ALLOWED_ORIGINS = 'http://localhost:3000'
  if (-not $env:DATABASE_URL) {
    $env:DATABASE_URL = 'postgresql://dev:dev@127.0.0.1:5432/soul'
  }

  Show-SecretDialog 'Soul Trading access key' 'Copy this key and enter it in the CONNECT form. Keep it private.' $accessKey
  Show-SecretDialog 'Soul Trading shutdown key' 'Copy this key for the emergency shutdown control. Keep it private.' $shutdownKey

  Set-Location $PSScriptRoot
  Write-Host 'Starting the backend. Leave this PowerShell window open.'
  & 'C:\Python314\python.exe' -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
}
catch {
  [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, 'Soul Trading setup', 'OK', 'Error') | Out-Null
  exit 1
}
