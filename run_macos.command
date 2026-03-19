#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

if [ ! -d ".venv" ]; then
  echo "[Siro] .venv 가 없습니다. 먼저 가상환경을 만들어 주세요."
  echo "python3.12 -m venv .venv"
  exit 1
fi

source .venv/bin/activate

unset QT_PLUGIN_PATH
unset QT_QPA_PLATFORM_PLUGIN_PATH
unset QT_QPA_PLATFORM
unset DYLD_FRAMEWORK_PATH
unset DYLD_LIBRARY_PATH

PYSIDE_ROOT=$(python - <<'PY'
import importlib.util
from pathlib import Path
spec = importlib.util.find_spec('PySide6')
if not spec or not spec.submodule_search_locations:
    print('')
else:
    p = Path(list(spec.submodule_search_locations)[0]) / 'Qt'
    print(str(p))
PY
)

if [ -z "$PYSIDE_ROOT" ]; then
  echo "[Siro] PySide6를 찾지 못했습니다."
  echo "python -m pip install -r requirements.txt"
  exit 1
fi

export QT_PLUGIN_PATH="$PYSIDE_ROOT/plugins"
export QT_QPA_PLATFORM_PLUGIN_PATH="$PYSIDE_ROOT/plugins/platforms"
export DYLD_FRAMEWORK_PATH="$PYSIDE_ROOT/lib"
export DYLD_LIBRARY_PATH="$PYSIDE_ROOT/lib"

exec python main.py
