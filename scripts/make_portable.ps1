$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $root

$portableRoot = Join-Path $root "release\portable\SIMSOFT Posting"
$exe = Join-Path $root "src-tauri\target\release\simsoft-posting.exe"
$releaseRoot = Join-Path $root "release"
$pythonBridgeExe = Join-Path $root "dist-python\simsoft-python-bridge\simsoft-python-bridge.exe"

if (-not (Test-Path $exe)) {
  throw "Release executable not found. Run npm run tauri:build or npm run release first."
}
if (-not (Test-Path $pythonBridgeExe)) {
  throw "Bundled Python bridge not found at $pythonBridgeExe. Run npm run build:bridge first."
}

if (Test-Path $portableRoot) {
  Remove-Item -LiteralPath $portableRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $portableRoot | Out-Null
New-Item -ItemType Directory -Force -Path $releaseRoot | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $portableRoot "config") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $portableRoot "data") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $portableRoot "logs") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $portableRoot "storage\cache") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $portableRoot "storage\temp") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $portableRoot "storage\receipts\originals") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $portableRoot "storage\receipts\compressed") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $portableRoot "storage\receipts\thumbnails") | Out-Null

Copy-Item -LiteralPath $exe -Destination (Join-Path $portableRoot "SIMSOFT Posting.exe") -Force

Copy-Item -LiteralPath "dist-python" -Destination $portableRoot -Recurse -Force
Copy-Item -LiteralPath "core" -Destination $portableRoot -Recurse -Force
Copy-Item -LiteralPath "python_backend" -Destination $portableRoot -Recurse -Force
Copy-Item -LiteralPath "scripts" -Destination $portableRoot -Recurse -Force
Copy-Item -LiteralPath "assets" -Destination $portableRoot -Recurse -Force
Copy-Item -LiteralPath "requirements.txt" -Destination (Join-Path $portableRoot "requirements.txt") -Force

$configFiles = @("oauth_client.example.json", "oauth_client.json", "service_account.json", "mappings.json")
foreach ($fileName in $configFiles) {
  $source = Join-Path "config" $fileName
  if (Test-Path $source) {
    Copy-Item -LiteralPath $source -Destination (Join-Path $portableRoot "config\$fileName") -Force
  }
}

@"
SIMSOFT Posting Portable

This folder is self-contained for operator PCs. It includes the Tauri executable,
bundled Python bridge/runtime, Python libraries, app resources, OCR asset folder,
runtime data folders, and Google configuration files available at build time.

If credentials were not embedded by the build administrator, place production
credential files in the config folder:
- service_account.json
- oauth_client.json

Run SIMSOFT Posting.exe.
"@ | Set-Content -Encoding UTF8 -Path (Join-Path $portableRoot "README.txt")

$zipPath = Join-Path $releaseRoot "SIMSOFT_Portable.zip"
if (Test-Path $zipPath) {
  Remove-Item -LiteralPath $zipPath -Force
}
Compress-Archive -LiteralPath $portableRoot -DestinationPath $zipPath -Force

$makensisCandidates = @(
  (Join-Path $env:LOCALAPPDATA "tauri\NSIS\makensis.exe"),
  (Join-Path $env:LOCALAPPDATA "tauri\NSIS\Bin\makensis.exe"),
  "makensis.exe"
)
$makensis = $makensisCandidates | Where-Object {
  if ($_ -eq "makensis.exe") {
    $null -ne (Get-Command $_ -ErrorAction SilentlyContinue)
  } else {
    Test-Path $_
  }
} | Select-Object -First 1

if ($makensis) {
  $nsisPath = Join-Path $releaseRoot "portable.nsi"
  $portableExe = Join-Path $releaseRoot "SIMSOFT_Portable.exe"
  $zipForNsis = $zipPath.Replace("\", "\\")
  $portableExeForNsis = $portableExe.Replace("\", "\\")
  @"
OutFile "$portableExeForNsis"
SilentInstall silent
RequestExecutionLevel user
SetCompressor /SOLID lzma
Name "SIMSOFT Posting Portable"
Section
  SetOutPath "`$TEMP\SIMSOFT_Posting_Portable_Package"
  File "$zipForNsis"
  nsExec::ExecToLog 'powershell -NoProfile -ExecutionPolicy Bypass -Command "Remove-Item -LiteralPath $$env:TEMP\SIMSOFT_Posting_Portable -Recurse -Force -ErrorAction SilentlyContinue; Expand-Archive -LiteralPath $$env:TEMP\SIMSOFT_Posting_Portable_Package\SIMSOFT_Portable.zip -DestinationPath $$env:TEMP\SIMSOFT_Posting_Portable -Force"'
  Exec '"`$TEMP\SIMSOFT_Posting_Portable\SIMSOFT Posting\SIMSOFT Posting.exe"'
SectionEnd
"@ | Set-Content -Encoding ASCII -Path $nsisPath
  Start-Process -FilePath $makensis -ArgumentList @($nsisPath) -Wait -WindowStyle Hidden
  if (-not (Test-Path $portableExe)) {
    Write-Warning "NSIS did not create SIMSOFT_Portable.exe. Use SIMSOFT_Portable.zip instead."
  }
} else {
  Write-Warning "NSIS makensis is not available. Use SIMSOFT_Portable.zip instead."
}

if (-not (Test-Path (Join-Path $portableRoot "dist-python\simsoft-python-bridge\simsoft-python-bridge.exe"))) {
  throw "Portable package is missing bundled Python bridge."
}
if (-not (Test-Path (Join-Path $portableRoot "assets\ocr"))) {
  throw "Portable package is missing OCR assets folder."
}

Write-Host "Portable package created at $portableRoot" -ForegroundColor Green
Write-Host "Portable archive created at $zipPath" -ForegroundColor Green
