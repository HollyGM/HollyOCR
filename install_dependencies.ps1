# PowerShell script to install Poppler and check Tesseract
$ErrorActionPreference = "Stop"

$scriptPath = $MyInvocation.MyCommand.Path
$projectRoot = Split-Path $scriptPath

$binDir = Join-Path $projectRoot "bin"
if (-not (Test-Path $binDir)) {
    New-Item -ItemType Directory -Path $binDir | Out-Null
}

Write-Host "Checking dependencies..." -ForegroundColor Cyan

# --- POPPLER ---
$popplerDir = Join-Path $binDir "poppler"
$popplerCheck = Get-ChildItem -Path $binDir -Recurse -Filter "pdftoppm.exe" -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match "\\poppler[^\\]*\\" -or $_.FullName -match "\\poppler\\" } |
    Select-Object -First 1

if ($popplerCheck) {
    Write-Host "Poppler found at: $($popplerCheck.DirectoryName)" -ForegroundColor Green
} else {
    Write-Host "Poppler not found. Downloading..." -ForegroundColor Yellow

    # URL for Poppler (Release 24.02.0-0 from oschwartz10612)
    $popplerUrl = "https://github.com/oschwartz10612/poppler-windows/releases/download/v24.02.0-0/Release-24.02.0-0.zip"
    $zipPath = Join-Path $binDir "poppler.zip"

    try {
        Invoke-WebRequest -Uri $popplerUrl -OutFile $zipPath
        Write-Host "Extracting Poppler..."
        Expand-Archive -Path $zipPath -DestinationPath $binDir -Force

        # Rename the extracted folder (usually Release-24.02.0-0) to 'poppler'
        $extracted = Get-ChildItem -Path $binDir -Directory | Where-Object { $_.Name -like "Release-*" }
        if ($extracted) {
            Rename-Item -Path $extracted.FullName -NewName "poppler"
        }

        Remove-Item $zipPath
        Write-Host "Poppler installed successfully!" -ForegroundColor Green
    } catch {
        Write-Error "Failed to download or install Poppler: $_"
    }
}

# --- TESSERACT ---
Write-Host "`nChecking Tesseract OCR..." -ForegroundColor Cyan
$tesseractPath = $null
try {
    $tesseractPath = (Get-Command tesseract -ErrorAction SilentlyContinue).Source
} catch {}

if (-not $tesseractPath) {
    # Check common locations
    $commonPaths = @(
        "C:\Program Files\Tesseract-OCR\tesseract.exe",
        "C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        "$env:LOCALAPPDATA\Tesseract-OCR\tesseract.exe"
    )

    foreach ($path in $commonPaths) {
        if (Test-Path $path) {
            $tesseractPath = $path
            break
        }
    }
}

if ($tesseractPath) {
    Write-Host "Tesseract found at: $tesseractPath" -ForegroundColor Green
} else {
    Write-Host "WARNING: Tesseract OCR not found!" -ForegroundColor Red
    Write-Host "Please download and install Tesseract from:"
    Write-Host "https://github.com/UB-Mannheim/tesseract/wiki"
    Write-Host "During installation, check 'Portuguese' in language data."

    $choice = Read-Host "Do you want to open the download page now? (Y/N)"
    if ($choice -eq 'Y' -or $choice -eq 'y') {
        Start-Process "https://github.com/UB-Mannheim/tesseract/wiki"
    }
}

Write-Host "`nDependencies check complete." -ForegroundColor Cyan
Pause
