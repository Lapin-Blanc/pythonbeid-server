# Build the eid-agent tray executable and the Windows installer.
#
# Usage (from anywhere):
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1 [-SkipInstaller]
#
# Requirements:
#   - Python 3.10+ with pip
#   - Inno Setup 6 (for the installer step): https://jrsoftware.org/isinfo.php

param(
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
try {
    Write-Host "==> Installing build dependencies" -ForegroundColor Cyan
    python -m pip install --quiet --upgrade pip
    python -m pip install --quiet -e ".[tray,build]"
    if ($LASTEXITCODE -ne 0) { throw "pip install failed." }

    $version = python -c "import eid_agent; print(eid_agent.__version__)"
    if ($LASTEXITCODE -ne 0) { throw "Unable to read package version." }
    Write-Host "==> Building eid-agent-tray $version" -ForegroundColor Cyan

    Write-Host "==> Generating icon" -ForegroundColor Cyan
    python packaging\make_icon.py
    if ($LASTEXITCODE -ne 0) { throw "Icon generation failed." }

    Write-Host "==> Running PyInstaller" -ForegroundColor Cyan
    python -m PyInstaller --noconfirm --clean packaging\eid_agent_tray.spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }
    Write-Host "Executable: dist\eid-agent-tray\eid-agent-tray.exe"

    if ($SkipInstaller) {
        Write-Host "==> Installer step skipped (-SkipInstaller)" -ForegroundColor Yellow
        return
    }

    Write-Host "==> Compiling installer (Inno Setup)" -ForegroundColor Cyan
    $isccCandidates = @(
        "ISCC.exe",
        "$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
    )
    $iscc = $null
    foreach ($candidate in $isccCandidates) {
        $resolved = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($resolved) { $iscc = $resolved.Source; break }
        if (Test-Path $candidate) { $iscc = $candidate; break }
    }
    if (-not $iscc) {
        throw "ISCC.exe not found. Install Inno Setup 6 (winget install JRSoftware.InnoSetup) or rerun with -SkipInstaller."
    }

    & $iscc "/DMyAppVersion=$version" "packaging\eid-agent.iss"
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed." }
    Write-Host "Installer: packaging\output\eid-agent-setup-$version.exe" -ForegroundColor Green
}
finally {
    Pop-Location
}
