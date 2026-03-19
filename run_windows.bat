@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
  set "PY_CMD=py -3"
) else (
  set "PY_CMD=python"
)

if not exist ".venv" (
  echo [Siro] .venv 가 없어 새로 생성합니다...
  %PY_CMD% -m venv .venv
  if errorlevel 1 (
    echo [Siro] 가상환경 생성 실패. Python 설치를 확인해 주세요.
    exit /b 1
  )
)

call .venv\Scripts\activate.bat
if errorlevel 1 (
  echo [Siro] 가상환경 활성화 실패.
  exit /b 1
)

python -m pip install -U pip
if errorlevel 1 (
  echo [Siro] pip 업그레이드 실패.
  exit /b 1
)

python -m pip install -r requirements.txt
if errorlevel 1 (
  echo [Siro] 의존성 설치 실패.
  exit /b 1
)

python main.py
exit /b %errorlevel%
