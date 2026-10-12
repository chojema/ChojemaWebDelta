@echo off
rem ChojemaWebDelta 실행 (Windows). 처음 실행할 때 전용 Python 환경을 만들고 필요한 패키지를 설치한다.
chcp 65001 >nul
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo 처음 실행 준비 중입니다. 잠시 기다려 주세요...
  py -3 -m venv .venv 2>nul || python -m venv .venv
)
if not exist ".venv\Scripts\python.exe" (
  echo Python 3.10 이상이 필요합니다. https://www.python.org/downloads/ 에서 설치한 뒤 다시 실행하세요.
  pause
  exit /b 1
)

fc /b requirements.txt ".venv\requirements.installed" >nul 2>&1
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements.txt
  if errorlevel 1 (
    echo 패키지 설치에 실패했습니다. 인터넷 연결을 확인한 뒤 다시 실행하세요.
    pause
    exit /b 1
  )
  copy /y requirements.txt ".venv\requirements.installed" >nul
)

".venv\Scripts\python.exe" -m chojema_webdelta %*
if errorlevel 1 pause
