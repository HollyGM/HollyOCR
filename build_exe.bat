@echo off
REM Build script to create standalone executable using PyInstaller
SETLOCAL EnableDelayedExpansion
cd /d "%~dp0"

echo ===== Building HollyOCR for Windows =====

REM Activate venv if exists, otherwise use system python
IF EXIST ".venv\Scripts\python.exe" (
    set PYTHON_EXE=.venv\Scripts\python.exe
) ELSE (
    set PYTHON_EXE=python
)

REM Instala ou atualiza o PyInstaller
echo Instaland/Atualizando PyInstaller...
%PYTHON_EXE% -m pip install pyinstaller
if %ERRORLEVEL% NEQ 0 (
    echo Erro ao instalar PyInstaller.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo Instalando dependencias do projeto...
%PYTHON_EXE% -m pip install -r hollyocr\requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo Erro ao instalar dependencias no requirements.txt.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo Limpando builds anteriores...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM Verifica quais arquivos de logo existem e prepara argumentos
set "LOGO_ARGS="
set "ICON_ARG="
set "POPPLER_ARGS="
set "POPPLER_SOURCE="

if exist logo.ico (
    echo Encontrado logo.ico - Sera usado como icone do executavel!
    set "ICON_ARG=--icon="logo.ico""
    set "LOGO_ARGS=--add-data "logo.ico;.""
)

if exist logo_ui.png (
    echo Encontrado logo_ui.png
    set "LOGO_ARGS=!LOGO_ARGS! --add-data "logo_ui.png;.""
)

if exist logo.png (
    echo Encontrado logo.png
    set "LOGO_ARGS=!LOGO_ARGS! --add-data "logo.png;.""
)

if exist logo.jpg (
    echo Encontrado logo.jpg
    set "LOGO_ARGS=!LOGO_ARGS! --add-data "logo.jpg;.""
)

if exist logo.jpeg (
    echo Encontrado logo.jpeg
    set "LOGO_ARGS=!LOGO_ARGS! --add-data "logo.jpeg;.""
)

if "!LOGO_ARGS!"=="" (
    echo AVISO: Nenhum arquivo de logo encontrado.
)

REM Localiza Poppler para embutir no executavel.
if exist "bin\poppler\Library\bin\pdftoppm.exe" set "POPPLER_SOURCE=bin\poppler"
if exist "bin\poppler\bin\pdftoppm.exe" set "POPPLER_SOURCE=bin\poppler"
if exist "bin\poppler\pdftoppm.exe" set "POPPLER_SOURCE=bin\poppler"

if "!POPPLER_SOURCE!"=="" (
    for /d %%D in ("bin\*poppler*") do (
        if "!POPPLER_SOURCE!"=="" if exist "%%~fD\Library\bin\pdftoppm.exe" set "POPPLER_SOURCE=%%~fD"
        if "!POPPLER_SOURCE!"=="" if exist "%%~fD\bin\pdftoppm.exe" set "POPPLER_SOURCE=%%~fD"
        if "!POPPLER_SOURCE!"=="" if exist "%%~fD\pdftoppm.exe" set "POPPLER_SOURCE=%%~fD"
    )
)

if not "!POPPLER_SOURCE!"=="" (
    echo Encontrado Poppler local - sera embutido no executavel.
    set "POPPLER_ARGS=--add-data "!POPPLER_SOURCE!;poppler""
) else (
    echo AVISO: Poppler local nao encontrado para embutir.
)

REM Build the executable
echo Gerando executavel...
if exist "HollyOCR.spec" (
    echo Usando HollyOCR.spec versionado.
    %PYTHON_EXE% -m PyInstaller --noconfirm --clean "HollyOCR.spec"
) else (
    %PYTHON_EXE% -m PyInstaller --noconfirm --onefile --windowed --clean ^
        --name "HollyOCR" ^
        !ICON_ARG! ^
        --hidden-import="PIL._tkinter_finder" ^
        --hidden-import="tkinter" ^
        --hidden-import="docx" ^
        --hidden-import="packaging" ^
        --hidden-import="pymupdf" ^
        --hidden-import="fitz" ^
        --hidden-import="pymupdf4llm" ^
        --hidden-import="urllib.request" ^
        --collect-all "customtkinter" ^
        !LOGO_ARGS! ^
        !POPPLER_ARGS! ^
        "hollyocr\app.py"
)

if %ERRORLEVEL% NEQ 0 (
    echo Erro durante o build do PyInstaller.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ========================================================
echo CONCLUIDO! O executavel esta na pasta "dist".
echo.
echo NOTA IMPORTANTE SOBRE DEPENDENCIAS EXTERNAS:
echo O Tesseract OCR NAO e embutido no .exe.
echo O Poppler local foi embutido no .exe quando encontrado em "bin".
echo Para que o executavel funcione em outro computador:
echo 1. Copie o arquivo "dist\HollyOCR.exe"
echo 2. Instale o Tesseract OCR ou coloque a pasta "Tesseract-OCR" ao lado do .exe.
echo ========================================================
pause
