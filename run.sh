#!/usr/bin/env bash
# ChojemaWebDelta 실행 (macOS, Linux). 처음 실행할 때 전용 Python 환경을 만들고 필요한 패키지를 설치한다.
set -e
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  echo "처음 실행 준비 중입니다. 잠시 기다려 주세요..."
  if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3.10 이상이 필요합니다. https://www.python.org/downloads/ 에서 설치한 뒤 다시 실행하세요."
    exit 1
  fi
  python3 -m venv .venv
fi

if ! cmp -s requirements.txt .venv/requirements.installed; then
  .venv/bin/python -m pip install --quiet --disable-pip-version-check -r requirements.txt
  cp requirements.txt .venv/requirements.installed
fi

exec .venv/bin/python -m chojema_webdelta "$@"
