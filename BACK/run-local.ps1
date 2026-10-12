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
# Broker-specific symbol map (JSON). Resolves ambiguous MT5 names to the exact
# contract you trade. Add/override here or in your user environment before launch.
if (-not $env:SYMBOL_MAP) {
  $env:SYMBOL_MAP = '{"US30":"US30m","XAUUSD":"XAUUSDm","XAGUSD":"XAGUSDm","BTCUSD":"BTCUSDm","US500":"US500m"}'
}
# News Bias Engine (enabled + live by default here; set DRY_RUN=1 to paper-trade).
if (-not $env:NEWS_BIAS_ENABLED) { $env:NEWS_BIAS_ENABLED = '1' }
if (-not $env:NEWS_BIAS_DRY_RUN) { $env:NEWS_BIAS_DRY_RUN = '0' }
if (-not $env:NEWS_BIAS_TARGET_ZAR) { $env:NEWS_BIAS_TARGET_ZAR = '15000' }
if (-not $env:AI_META_LAYER_PATH) { $env:AI_META_LAYER_PATH = 'C:\Users\lebog\OneDrive\Desktop\ai_meta_layer.py' }
if (-not $env:ALLOWED_ORIGINS) { $env:ALLOWED_ORIGINS = 'http://localhost:3000,http://127.0.0.1:3000' }

# Dual-stack bind so both 127.0.0.1 and ::1 (browser "localhost") reach the API.
& 'C:\Python314\python.exe' -m uvicorn main:app --host '::' --port 8000 --workers 1
