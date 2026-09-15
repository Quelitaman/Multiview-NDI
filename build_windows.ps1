#Requires -Version 5.1
<#
.SYNOPSIS
    Build NdiMultiview.exe on Windows (single-file executable).

.DESCRIPTION
    1. Installs Python + Node dependencies
    2. Builds the React frontend (yarn build)
    3. Runs PyInstaller with backend/NdiMultiview.spec
    4. Outputs backend\dist\NdiMultiview.exe

.NOTES
    Prerequisites on the Windows VM:
      * Python 3.11 x64  (https://www.python.org/downloads/windows/)
      * Node.js 20 + Yarn (npm i -g yarn)
      * NDI 6 Runtime      (https://ndi.video/tools)  <-- REQUIRED at runtime,
        provides Processing.NDI.Lib.x64.dll on PATH.
#>

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Write-Host "==> Building NDI Multiview .exe" -ForegroundColor Cyan
Write-Host "    Project root: $Root"

# ---- Frontend build ----
Write-Host "`n[1/3] Building React frontend..." -ForegroundColor Yellow
Push-Location "$Root\frontend"
if (-not (Test-Path "node_modules")) {
    yarn install --frozen-lockfile
}
$env:REACT_APP_BACKEND_URL = ""   # same-origin when served by FastAPI
yarn build
Pop-Location

# ---- Python env ----
Write-Host "`n[2/3] Installing Python build dependencies..." -ForegroundColor Yellow
Push-Location "$Root\backend"
if (-not (Test-Path ".venv")) {
    py -3.11 -m venv .venv
}
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements-exe.txt

# ---- PyInstaller ----
Write-Host "`n[3/3] Running PyInstaller..." -ForegroundColor Yellow
& .\.venv\Scripts\pyinstaller.exe NdiMultiview.spec --clean --noconfirm

Pop-Location

$exe = "$Root\backend\dist\NdiMultiview.exe"
if (Test-Path $exe) {
    Write-Host "`nSUCCESS -> $exe" -ForegroundColor Green
    Write-Host "Copy this single file to your Windows VM (with NDI Runtime installed) and run it."
} else {
    Write-Host "`nBuild failed: $exe not found" -ForegroundColor Red
    exit 1
}
