param(
  [string]$KeyPath = "$env:USERPROFILE\.tauri\posting-tools\updater.key",
  [string]$PasswordPath = "$env:USERPROFILE\.tauri\posting-tools\updater.key.password",
  [switch]$SkipBridge
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

if (-not (Test-Path -LiteralPath $KeyPath)) {
  throw "Updater private key not found at $KeyPath"
}

if (-not (Test-Path -LiteralPath $PasswordPath)) {
  throw "Updater key password file not found at $PasswordPath"
}

$env:TAURI_SIGNING_PRIVATE_KEY = (Get-Content -Raw -LiteralPath $KeyPath)
$env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD = (Get-Content -Raw -LiteralPath $PasswordPath).Trim()

if (-not $SkipBridge) {
  npm.cmd run build:bridge
}

npx.cmd tauri build --bundles nsis

$bundleDir = Join-Path $repoRoot "src-tauri\target\release\bundle\nsis"
$installer = Get-ChildItem -LiteralPath $bundleDir -Filter "*.exe" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$signature = Get-ChildItem -LiteralPath $bundleDir -Filter "*.sig" | Sort-Object LastWriteTime -Descending | Select-Object -First 1

if (-not $installer) {
  throw "NSIS installer was not generated in $bundleDir"
}

if (-not $signature) {
  throw "Updater signature was not generated in $bundleDir"
}

Write-Host "Generated NSIS installer: $($installer.FullName)"
Write-Host "Generated updater signature: $($signature.FullName)"
