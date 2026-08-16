<#
Builds MediaDownloader.exe.

    .\build.ps1              # single-file exe  -> dist\MediaDownloader.exe
    .\build.ps1 -OneDir      # folder build     -> dist\MediaDownloader\
    .\build.ps1 -WithFfmpeg  # bundle ffmpeg.exe next to the app

The folder build starts faster; the single file is easier to move around.
#>
[CmdletBinding()]
param(
    [switch]$OneDir,
    [switch]$WithFfmpeg,
    [switch]$SkipIcon
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "== Media Downloader build ==" -ForegroundColor Cyan

# Microsoft Store Python installs into a sandboxed, redirected location that
# PyInstaller cannot always read from. Warn early rather than fail cryptically.
$pyPath = (Get-Command python).Source
if ($pyPath -like "*WindowsApps*") {
    Write-Warning "You are using the Microsoft Store build of Python."
    Write-Warning "If PyInstaller fails, install Python from python.org and rebuild."
}

python -c "import PySide6, yt_dlp, mutagen, HdRezkaApi" 2>$null
if (-not $?) {
    Write-Host "Installing dependencies..." -ForegroundColor Yellow
    python -m pip install -r requirements.txt
}

if (-not $SkipIcon) {
    Write-Host "Generating icon..." -ForegroundColor Yellow
    python tools\make_icon.py
}

if ($WithFfmpeg) {
    $ffmpeg = (Get-Command ffmpeg -ErrorAction SilentlyContinue).Source
    if ($ffmpeg) {
        $dest = "mediadl\resources\ffmpeg"
        New-Item -ItemType Directory -Force $dest | Out-Null
        Copy-Item $ffmpeg $dest -Force
        $ffprobe = (Get-Command ffprobe -ErrorAction SilentlyContinue).Source
        if ($ffprobe) { Copy-Item $ffprobe $dest -Force }
        Write-Host "Bundled ffmpeg from $ffmpeg" -ForegroundColor Green
    } else {
        Write-Warning "ffmpeg not found on PATH; skipping bundling."
    }
}

# A running copy holds a lock on its own exe, so deleting dist fails with a
# permission error that looks nothing like the real cause.
$running = @(Get-Process -Name MediaDownloader -ErrorAction SilentlyContinue)
if ($running.Count -gt 0) {
    Write-Host "Closing $($running.Count) running instance(s)..." -ForegroundColor Yellow
    $running | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 800
}

if (Test-Path build) { Remove-Item build -Recurse -Force }
if (Test-Path dist) {
    try {
        Remove-Item dist -Recurse -Force -ErrorAction Stop
    } catch {
        Write-Error "Could not clear dist. Close MediaDownloader.exe and run again.`n$_"
        exit 1
    }
}

if ($OneDir) { $env:MEDIADL_ONEDIR = "1" } else { Remove-Item Env:\MEDIADL_ONEDIR -ErrorAction SilentlyContinue }

Write-Host "Running PyInstaller (this takes a few minutes)..." -ForegroundColor Yellow
python -m PyInstaller MediaDownloader.spec --noconfirm --log-level WARN

$target = if ($OneDir) { "dist\MediaDownloader\MediaDownloader.exe" } else { "dist\MediaDownloader.exe" }
if (Test-Path $target) {
    $size = [math]::Round((Get-Item $target).Length / 1MB, 1)
    Write-Host "`nBuilt $target ($size MB)" -ForegroundColor Green
} else {
    Write-Error "Build finished but $target is missing."
}
