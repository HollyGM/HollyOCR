
@echo off
REM Batch launcher for hollyocr - runs the script in GUI mode
SETLOCAL
SET "BASE_DIR=%~dp0"
cd /d "%BASE_DIR%"

echo ===== PDF/Word/Markdown to TXT Launcher =====

REM Create venv if missing
IF NOT EXIST "%BASE_DIR%.venv\Scripts\python.exe" (
  echo Creating virtual environment...
  py -3 -m venv "%BASE_DIR%.venv"
  IF ERRORLEVEL 1 (
    echo Failed to create virtualenv. Make sure Python 3.8+ is installed.
    pause
    exit /b 1
  )
)

REM Install/upgrade dependencies
echo Installing dependencies...
"%BASE_DIR%.venv\Scripts\python.exe" -m pip install --upgrade pip setuptools wheel >nul 2>&1
"%BASE_DIR%.venv\Scripts\python.exe" -m pip install -r "%BASE_DIR%hollyocr\requirements.txt"

REM Check for local dependencies (Poppler/Tesseract)
SET "POPPLER_FOUND="
IF EXIST "%BASE_DIR%bin\poppler\Library\bin\pdftoppm.exe" SET "POPPLER_FOUND=1"
IF EXIST "%BASE_DIR%bin\poppler\bin\pdftoppm.exe" SET "POPPLER_FOUND=1"
IF EXIST "%BASE_DIR%bin\poppler\pdftoppm.exe" SET "POPPLER_FOUND=1"

IF NOT DEFINED POPPLER_FOUND (
    FOR /D %%D IN ("%BASE_DIR%bin\*poppler*") DO (
        IF EXIST "%%~fD\Library\bin\pdftoppm.exe" SET "POPPLER_FOUND=1"
        IF EXIST "%%~fD\bin\pdftoppm.exe" SET "POPPLER_FOUND=1"
        IF EXIST "%%~fD\pdftoppm.exe" SET "POPPLER_FOUND=1"
    )
)

IF NOT DEFINED POPPLER_FOUND (
    echo.
    echo [INFO] Poppler dependency missing.
    echo Launching auto-installer...
    powershell -ExecutionPolicy Bypass -File "%BASE_DIR%install_dependencies.ps1"
)

REM Run the script in GUI mode
echo Starting PDF/Markdown conversion tool...
"%BASE_DIR%.venv\Scripts\python.exe" -u "%BASE_DIR%hollyocr\app.py" --gui

echo.
echo ===== Finished =====
pause
