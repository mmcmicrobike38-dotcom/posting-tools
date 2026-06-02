param(
  [switch]$Apply
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$targets = @(
  "dist",
  "dist-python",
  "build-python",
  ".pytest-tmp-python",
  ".pytest-tmp-release-bridge",
  "src-tauri\target\release\bundle",
  "src-tauri\target\release\nsis",
  "src-tauri\target\release\wix",
  "release\SIMSOFT_Setup.exe",
  "release\SIMSOFT_Setup.exe.sig",
  "release\SIMSOFT.msi",
  "release\SIMSOFT_Portable.exe",
  "release\SIMSOFT_Portable.zip",
  "release\portable",
  "release\logs"
)

foreach ($target in $targets) {
  $path = Join-Path $root $target
  if (Test-Path $path) {
    if ($Apply) {
      Remove-Item -LiteralPath $path -Recurse -Force
      Write-Host "Removed $path"
    } else {
      Write-Host "DRY RUN $path"
    }
  }
}

if (-not $Apply) {
  Write-Host "Dry run only. Re-run with -Apply to remove generated release folders."
}
