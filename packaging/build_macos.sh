#!/usr/bin/env bash
# Mac 전용 환경에서 앱을 빌드한다. Windows 환경과 실행 파일은 유지한다.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ "$(uname -s)" != Darwin ]; then
  echo "이 스크립트는 macOS에서 실행하세요."
  exit 1
fi

if [ ! -x .venv-macos/bin/python ]; then
  python3 -m venv .venv-macos
fi

.venv-macos/bin/python -m pip install --disable-pip-version-check \
  --cache-dir "$PWD/build/macos/pip-cache" \
  -r requirements.txt 'pyinstaller>=6.16,<7'
cp requirements.txt .venv-macos/requirements.installed
.venv-macos/bin/python packaging/build.py

# 동기화 폴더가 Finder 속성을 다시 붙여도 압축본에는 포함하지 않는다.
xattr -dr com.apple.FinderInfo dist/ChojemaWebDelta.app
xattr -dr com.apple.ResourceFork dist/ChojemaWebDelta.app
codesign --verify --deep --strict dist/ChojemaWebDelta.app
# 앱과 함께 읽을 수 있도록 라이선스 고지를 ZIP에도 둔다.
ARCHIVE="dist/ChojemaWebDelta-macos-$(uname -m).zip"
ditto -c -k --keepParent --norsrc --noextattr dist/ChojemaWebDelta.app "$ARCHIVE"
/usr/bin/zip -j -X "$ARCHIVE" build/macos/legal/LICENSE.txt build/macos/legal/THIRD_PARTY_NOTICES.txt

echo "빌드 완료: dist/ChojemaWebDelta.app"
echo "압축본: dist/ChojemaWebDelta-macos-$(uname -m).zip"
