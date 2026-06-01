param(
  [switch]$SkipVerify
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $root

$logDir = Join-Path $root "release\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logPath = Join-Path $logDir "release-build-$stamp.log"

function Run-Step($Name, $Command, $Arguments) {
  Write-Host "== $Name ==" -ForegroundColor Cyan
  Add-Content -Path $logPath -Value "== $Name =="
  $process = Start-Process -FilePath $Command -ArgumentList $Arguments -NoNewWindow -Wait -PassThru -RedirectStandardOutput "$logPath.out" -RedirectStandardError "$logPath.err"
  Get-Content "$logPath.out" | Add-Content -Path $logPath
  Get-Content "$logPath.err" | Add-Content -Path $logPath
  Remove-Item "$logPath.out","$logPath.err" -ErrorAction SilentlyContinue
  if ($process.ExitCode -ne 0) {
    throw "$Name failed with exit code $($process.ExitCode). See $logPath"
  }
}

function Run-Step-AllowFailure($Name, $Command, $Arguments) {
  Write-Host "== $Name ==" -ForegroundColor Cyan
  Add-Content -Path $logPath -Value "== $Name =="
  $process = Start-Process -FilePath $Command -ArgumentList $Arguments -NoNewWindow -Wait -PassThru -RedirectStandardOutput "$logPath.out" -RedirectStandardError "$logPath.err"
  Get-Content "$logPath.out" | Add-Content -Path $logPath
  Get-Content "$logPath.err" | Add-Content -Path $logPath
  Remove-Item "$logPath.out","$logPath.err" -ErrorAction SilentlyContinue
  return $process.ExitCode
}

function Assert-Artifact($Path, $Name) {
  if (-not (Test-Path $Path)) {
    throw "$Name was not created at $Path"
  }
  $item = Get-Item $Path
  if ($item.Length -le 0) {
    throw "$Name was created but is empty: $Path"
  }
}

function Assert-ReleaseArtifact($Path, $Name, $MinimumMegabytes = 20) {
  Assert-Artifact $Path $Name
  $item = Get-Item $Path
  if ($item.Length -lt ($MinimumMegabytes * 1MB)) {
    throw "$Name looks too small to be a valid self-contained release artifact: $Path ($($item.Length) bytes)"
  }
}

function Repair-MsiWithSkipValidation() {
  Write-Host "== msi skip-validation fallback ==" -ForegroundColor Cyan
  Add-Content -Path $logPath -Value "== msi skip-validation fallback =="

  $wixTools = Join-Path $env:LOCALAPPDATA "tauri\WixTools314"
  $wixDir = Join-Path $root "src-tauri\target\release\wix\x64"
  $light = Join-Path $wixTools "light.exe"
  $wixUi = Join-Path $wixTools "WixUIExtension.dll"
  $wixUtil = Join-Path $wixTools "WixUtilExtension.dll"
  $locale = Join-Path $wixDir "locale.wxl"
  $output = Join-Path $wixDir "output.msi"

  foreach ($requiredPath in @($light, $wixUi, $wixUtil, $locale, (Join-Path $wixDir "main.wixobj"))) {
    if (-not (Test-Path $requiredPath)) {
      throw "Cannot repair MSI; required WiX file is missing: $requiredPath"
    }
  }

  if (Test-Path $output) {
    Remove-Item -LiteralPath $output -Force
  }

  Push-Location $wixDir
  try {
    & $light -sval -ext $wixUi -ext $wixUtil -o "output.msi" -cultures:en-us -loc "locale.wxl" *.wixobj 2>&1 | Add-Content -Path $logPath
    if ($LASTEXITCODE -ne 0) {
      throw "WiX light.exe skip-validation fallback failed with exit code $LASTEXITCODE"
    }
  } finally {
    Pop-Location
  }

  $tauriConfig = Get-Content (Join-Path $root "src-tauri\tauri.conf.json") -Raw | ConvertFrom-Json
  $msiBundleDir = Join-Path $root "src-tauri\target\release\bundle\msi"
  New-Item -ItemType Directory -Force -Path $msiBundleDir | Out-Null
  $msiName = "$($tauriConfig.productName)_$($tauriConfig.version)_x64_en-US.msi"
  Copy-Item -LiteralPath $output -Destination (Join-Path $msiBundleDir $msiName) -Force
}

function Repair-NsisBundle() {
  $tauriConfig = Get-Content (Join-Path $root "src-tauri\tauri.conf.json") -Raw | ConvertFrom-Json
  $nsisWorkDir = Join-Path $root "src-tauri\target\release\nsis\x64"
  $nsisBundleDir = Join-Path $root "src-tauri\target\release\bundle\nsis"
  $expectedInstaller = Join-Path $nsisBundleDir "$($tauriConfig.productName)_$($tauriConfig.version)_x64-setup.exe"
  $actualInstaller = Join-Path $nsisWorkDir "nsis-output.exe"
  $installerScript = Join-Path $nsisWorkDir "installer.nsi"

  New-Item -ItemType Directory -Force -Path $nsisBundleDir | Out-Null

  if ((Test-Path $expectedInstaller) -and ((Get-Item $expectedInstaller).Length -ge 20MB)) {
    return
  }

  if (-not ((Test-Path $actualInstaller) -and ((Get-Item $actualInstaller).Length -ge 20MB))) {
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

    if (-not $makensis) {
      throw "Cannot repair NSIS installer; makensis.exe was not found."
    }
    if (-not (Test-Path $installerScript)) {
      throw "Cannot repair NSIS installer; installer script is missing: $installerScript"
    }

    Write-Host "== nsis direct makensis fallback ==" -ForegroundColor Cyan
    Add-Content -Path $logPath -Value "== nsis direct makensis fallback =="
    & $makensis /V3 $installerScript 2>&1 | Add-Content -Path $logPath
    if ($LASTEXITCODE -ne 0) {
      throw "NSIS makensis fallback failed with exit code $LASTEXITCODE"
    }
  }

  if (-not ((Test-Path $actualInstaller) -and ((Get-Item $actualInstaller).Length -ge 20MB))) {
    throw "NSIS fallback did not create a valid installer at $actualInstaller"
  }

  Copy-Item -LiteralPath $actualInstaller -Destination $expectedInstaller -Force
}

Run-Step "doctor" "powershell" @("-ExecutionPolicy", "Bypass", "-File", "scripts\doctor.ps1", "-Strict")

if (-not $SkipVerify) {
  Run-Step "verify" "npm.cmd" @("run", "verify")
}

Run-Step "build python bridge" "npm.cmd" @("run", "build:bridge")
Assert-Artifact (Join-Path $root "dist-python\simsoft-python-bridge\simsoft-python-bridge.exe") "Bundled Python bridge"
Run-Step "validate python bridge server" ".\.venv\Scripts\python.exe" @("-m", "pytest", "tests\test_python_bridge_server.py", "-q", "--basetemp", ".pytest-tmp-release-bridge", "-p", "no:cacheprovider")
Run-Step "tauri nsis build" "npx.cmd" @("tauri", "build", "--bundles", "nsis")
Repair-NsisBundle
$msiExitCode = Run-Step-AllowFailure "tauri msi build" "npx.cmd" @("tauri", "build", "--bundles", "msi", "--verbose")
if ($msiExitCode -ne 0) {
  Add-Content -Path $logPath -Value "Tauri MSI build exited with $msiExitCode. Trying WiX skip-validation fallback."
  Repair-MsiWithSkipValidation
}
Run-Step "portable" "powershell" @("-ExecutionPolicy", "Bypass", "-File", "scripts\make_portable.ps1")

$releaseDir = Join-Path $root "release"
New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null

$bundleDir = Join-Path $root "src-tauri\target\release\bundle"
$setup = Get-ChildItem -Path $bundleDir -Recurse -Filter "*.exe" -ErrorAction SilentlyContinue |
  Where-Object { $_.FullName -match "\\nsis\\" } |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1
$msi = Get-ChildItem -Path $bundleDir -Recurse -Filter "*.msi" -ErrorAction SilentlyContinue |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1

if ($setup) {
  Copy-Item -LiteralPath $setup.FullName -Destination (Join-Path $releaseDir "SIMSOFT_Setup.exe") -Force
}
if ($msi) {
  Copy-Item -LiteralPath $msi.FullName -Destination (Join-Path $releaseDir "SIMSOFT.msi") -Force
}

Assert-ReleaseArtifact (Join-Path $releaseDir "SIMSOFT_Portable.zip") "Portable ZIP" 20
Assert-ReleaseArtifact (Join-Path $releaseDir "SIMSOFT_Setup.exe") "NSIS setup executable" 20
Assert-ReleaseArtifact (Join-Path $releaseDir "SIMSOFT.msi") "MSI installer" 20

Write-Host "Release build completed. Log: $logPath" -ForegroundColor Green
Write-Host "Artifacts are in $releaseDir" -ForegroundColor Green
