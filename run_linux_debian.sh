#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[Siro] python3 가 필요합니다."
  echo "sudo apt update && sudo apt install -y python3 python3-venv python3-pip"
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "[Siro] .venv 가 없어 새로 생성합니다..."
  python3 -m venv .venv
fi

source .venv/bin/activate

python -m pip install -U pip
python -m pip install -r requirements.txt

exec python main.py
