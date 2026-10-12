#!/usr/bin/env bash
# macOS Finder에서 더블클릭으로 실행하기 위한 파일.
exec "$(dirname "$0")/run.sh" "$@"
