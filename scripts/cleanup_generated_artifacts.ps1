param(
  [switch]$Apply
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")

$candidatePatterns = @(
  ".pytest-*",
  ".pytest_cache",
  "build-python",
  "dist-python",
  "release",
  "dist"
)

$protectedNames = @(
  "core",
  "python_backend",
  "config",
  "data",
  "src",
  "tests",
  "tests-ts",
  "scripts",
  "node_modules",
  ".venv"
)

$candidates = foreach ($pattern in $candidatePatterns) {
  Get-ChildItem -LiteralPath $root -Force -Directory -Filter $pattern |
    Where-Object { $protectedNames -notcontains $_.Name }
}

if (-not $candidates) {
  Write-Output "No generated cleanup candidates found."
  exit 0
}

foreach ($candidate in $candidates | Sort-Object FullName -Unique) {
  if ($Apply) {
    Remove-Item -LiteralPath $candidate.FullName -Recurse -Force
    Write-Output "Removed $($candidate.FullName)"
  } else {
    Write-Output "DRY RUN $($candidate.FullName)"
  }
}

if (-not $Apply) {
  Write-Output "Dry run only. Re-run with -Apply after reviewing the list."
}

