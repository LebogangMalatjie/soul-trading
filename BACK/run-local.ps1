$ErrorActionPreference = 'Stop'

$env:BROKER = 'mt5'
$env:ALLOWED_ORIGINS = 'http://localhost:3000'

if (-not $env:SOUL_ACCESS_KEY) {
  $env:SOUL_ACCESS_KEY = 'replace-with-your-soul-access-key'
}
if (-not $env:SOUL_SHUTDOWN_KEY) {
  $env:SOUL_SHUTDOWN_KEY = 'replace-with-24-char-or-longer-shutdown-key'
}
if (-not $env:DATABASE_URL) {
  $env:DATABASE_URL = 'postgresql://postgres:postgres@127.0.0.1:5432/postgres'
}
if (-not $env:MT5_PATH) {
  $env:MT5_PATH = ''
}
if (-not $env:MT5_LOGIN) {
  $env:MT5_LOGIN = ''
}
if (-not $env:MT5_SERVER) {
  $env:MT5_SERVER = ''
}
if (-not $env:MT5_PASSWORD) {
  $env:MT5_PASSWORD = ''
}
if (-not $env:METAAPI_ACCOUNT_ID) {
  $env:METAAPI_ACCOUNT_ID = ''
}

& 'C:\Python314\python.exe' -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
