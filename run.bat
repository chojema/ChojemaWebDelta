@echo off
rem ChojemaWebDelta 실행 (Windows). 처음 실행할 때 전용 Python 환경을 만들고 필요한 패키지를 설치한다.
chcp 65001 >nul
setlocal
cd /d "%~dp0"

rem 안내 문구의 언어: CHOJEMA_WEBDELTA_LANG, 없으면 Windows의 지역 설정을 따른다.
set "UI_LANG=%CHOJEMA_WEBDELTA_LANG%"
if not defined UI_LANG for /f "tokens=3" %%L in ('reg query "HKCU\Control Panel\International" /v LocaleName 2^>nul') do set "UI_LANG=%%L"
set "MSG_PREPARE=Preparing for the first run. Please wait..."
set "MSG_PYTHON=Python 3.10 or later is required. Install it from https://www.python.org/downloads/ and run this again."
set "MSG_INSTALL=Could not install the required packages. Check your internet connection and run this again."
if /i "%UI_LANG:~0,2%"=="ko" (
  set "MSG_PREPARE=처음 실행 준비 중입니다. 잠시 기다려 주세요..."
  set "MSG_PYTHON=Python 3.10 이상이 필요합니다. https://www.python.org/downloads/ 에서 설치한 뒤 다시 실행하세요."
  set "MSG_INSTALL=패키지 설치에 실패했습니다. 인터넷 연결을 확인한 뒤 다시 실행하세요."
)

if not exist ".venv\Scripts\python.exe" (
  echo %MSG_PREPARE%
  py -3 -m venv .venv 2>nul || python -m venv .venv
)
if not exist ".venv\Scripts\python.exe" (
  echo %MSG_PYTHON%
  pause
  exit /b 1
)

fc /b requirements.txt ".venv\requirements.installed" >nul 2>&1
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements.txt
  if errorlevel 1 (
    echo %MSG_INSTALL%
    pause
    exit /b 1
  )
  copy /y requirements.txt ".venv\requirements.installed" >nul
)

".venv\Scripts\python.exe" -m chojema_webdelta %*
if errorlevel 1 pause
