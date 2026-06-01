param(
  [switch]$Strict
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$checks = New-Object System.Collections.Generic.List[object]

function Add-Check($Name, $Ok, $Detail, $Required = $true) {
  $checks.Add([pscustomobject]@{ Name = $Name; Ok = [bool]$Ok; Required = [bool]$Required; Detail = $Detail })
}

function Test-Command($Name) {
  $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

Set-Location $root

Add-Check "Node.js" (Test-Command "node") ($(if (Test-Command "node") { node --version } else { "not found" }))
Add-Check "npm" (Test-Command "npm.cmd") ($(if (Test-Command "npm.cmd") { npm.cmd --version } else { "not found" }))
Add-Check "Rust cargo" (Test-Command "cargo") ($(if (Test-Command "cargo") { cargo --version } else { "not found" }))
Add-Check "Tauri CLI" (Test-Path "node_modules\@tauri-apps\cli") "node_modules/@tauri-apps/cli"
Add-Check "Python venv" (Test-Path ".venv\Scripts\python.exe") ".venv/Scripts/python.exe"
if (Test-Path ".venv\Scripts\python.exe") {
  Add-Check "Python version" $true (& ".\.venv\Scripts\python.exe" --version)
}
Add-Check "PyInstaller" (Test-Path ".venv\Scripts\pyinstaller.exe") ".venv/Scripts/pyinstaller.exe"
Add-Check "Tauri config" (Test-Path "src-tauri\tauri.conf.json") "src-tauri/tauri.conf.json"
Add-Check "Application icon" (Test-Path "src-tauri\icons\icon.ico") "src-tauri/icons/icon.ico"
Add-Check "OAuth example" (Test-Path "config\oauth_client.example.json") "config/oauth_client.example.json"
Add-Check "Service account file" (Test-Path "config\service_account.json") "config/service_account.json" $false
Add-Check "OAuth client file" (Test-Path "config\oauth_client.json") "config/oauth_client.json" $false
Add-Check "Requirements file" (Test-Path "requirements.txt") "requirements.txt"
Add-Check "Python bridge script" (Test-Path "scripts\python_bridge.py") "scripts/python_bridge.py"
Add-Check "OCR asset folder" (Test-Path "assets\ocr") "assets/ocr"
Add-Check "Storage cache folder" (Test-Path "storage\cache") "storage/cache"
Add-Check "Vite config" (Test-Path "vite.config.mjs") "vite.config.mjs"
Add-Check "Vitest config" (Test-Path "vitest.config.mjs") "vitest.config.mjs"

if (Test-Path "dist-python\simsoft-python-bridge\simsoft-python-bridge.exe") {
  Add-Check "Bundled Python bridge" $true "dist-python/simsoft-python-bridge/simsoft-python-bridge.exe"
} else {
  Add-Check "Bundled Python bridge" $false "Run npm run build:bridge before packaging" $false
}

$checks | Format-Table -AutoSize

$failed = @($checks | Where-Object { -not $_.Ok -and $_.Required })
if ($failed.Count -gt 0) {
  Write-Host ""
  Write-Host "Doctor found $($failed.Count) required issue(s)." -ForegroundColor Yellow
  if ($Strict) {
    exit 1
  }
}

Write-Host "Doctor completed." -ForegroundColor Green
