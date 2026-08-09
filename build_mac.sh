#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

APP_NAME="HollyOCR"
APP_PATH="dist/${APP_NAME}.app"
EXECUTABLE="${APP_PATH}/Contents/MacOS/${APP_NAME}"
BUNDLE_ID="com.thiagoalbuquerque.hollyocr"

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "ERROR: build_mac.sh must run on macOS."
    exit 1
fi

if [[ "$(uname -m)" != "arm64" ]]; then
    echo "ERROR: native arm64 host required; Rosetta/x86_64 builds are not accepted."
    exit 1
fi

if [[ ! -x ".venv/bin/python" ]]; then
    echo "ERROR: .venv is missing. Create it with an arm64 Python 3.12 interpreter first."
    exit 1
fi

source .venv/bin/activate

python - <<'PY'
import platform
import sys

if sys.version_info[:2] != (3, 12):
    raise SystemExit(f"ERROR: Python 3.12 required, found {sys.version.split()[0]}")
if platform.machine() != "arm64":
    raise SystemExit(f"ERROR: arm64 Python required, found {platform.machine()}")
print(f"Python preflight: {sys.version.split()[0]} ({platform.machine()})")
PY

echo "Installing pinned macOS build/runtime dependencies..."
python -m pip install -r requirements-macos-lock.txt

echo "Running quality gates..."
python -m pyflakes hollyocr tests
python -m pytest tests/ -q
python hollyocr/app.py --help >/dev/null
python -m hollyocr --help >/dev/null

TRASH_BIN="$(command -v mavis-trash || true)"
if [[ -z "$TRASH_BIN" ]]; then
    echo "ERROR: mavis-trash is required for recoverable cleanup of build artifacts."
    exit 1
fi

for old_path in build dist; do
    if [[ -e "$old_path" ]]; then
        "$TRASH_BIN" "$old_path"
    fi
done

export PYTHONHASHSEED=0
export SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-1704067200}"
export PYINSTALLER_CONFIG_DIR="${PYINSTALLER_CONFIG_DIR:-/private/tmp/hollyocr-pyinstaller-cache}"

echo "Building ${APP_NAME}.app..."
python -m PyInstaller --noconfirm --clean HollyOCR.spec

if [[ ! -x "$EXECUTABLE" ]]; then
    echo "ERROR: expected executable not found: $EXECUTABLE"
    exit 1
fi

FILE_INFO="$(file "$EXECUTABLE")"
LIPO_INFO="$(lipo -info "$EXECUTABLE")"
if [[ "$FILE_INFO" != *"arm64"* ]] || [[ "$FILE_INFO" == *"x86_64"* ]]; then
    echo "ERROR: unexpected executable architecture: $FILE_INFO"
    exit 1
fi
if [[ "$LIPO_INFO" != *"arm64"* ]] || [[ "$LIPO_INFO" == *"x86_64"* ]]; then
    echo "ERROR: lipo rejected architecture: $LIPO_INFO"
    exit 1
fi

ACTUAL_BUNDLE_ID="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$APP_PATH/Contents/Info.plist")"
if [[ "$ACTUAL_BUNDLE_ID" != "$BUNDLE_ID" ]]; then
    echo "ERROR: bundle identifier is '$ACTUAL_BUNDLE_ID', expected '$BUNDLE_ID'."
    exit 1
fi

codesign --verify --deep --strict "$APP_PATH"

APP_SIZE_KB="$(du -sk "$APP_PATH" | awk '{print $1}')"
if (( APP_SIZE_KB >= 204800 )); then
    echo "ERROR: bundle is ${APP_SIZE_KB} KB; target is below 200 MB."
    exit 1
fi

TREE_SHA256="$({
    cd dist
    find "${APP_NAME}.app" -type f -print | LC_ALL=C sort | while IFS= read -r item; do
        shasum -a 256 "$item"
    done
} | shasum -a 256 | awk '{print $1}')"
printf '%s  %s\n' "$TREE_SHA256" "${APP_NAME}.app (tree digest)" > "dist/${APP_NAME}.app.sha256"

echo "Build complete: $APP_PATH"
echo "$FILE_INFO"
echo "$LIPO_INFO"
echo "Bundle size: ${APP_SIZE_KB} KB"
echo "SHA-256 tree digest: $TREE_SHA256"
