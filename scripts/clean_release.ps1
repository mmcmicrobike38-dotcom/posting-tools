param(
  [switch]$Apply
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$targets = @(
  "dist",
  "dist-python",
  "build-python",
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
