"""운영체제별 저장 위치."""

import os
import sys
from pathlib import Path

from . import APP_NAME

DATA_DIR_ENV = "CHOJEMA_WEBDELTA_DATA"


def data_dir() -> Path:
    """사이트 목록과 스냅샷을 두는 사용자 데이터 폴더. 없으면 만든다."""
    override = os.environ.get(DATA_DIR_ENV)
    if override:
        path = Path(override).expanduser()
    elif sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        path = Path(base) / APP_NAME
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        path = Path(base) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def web_dir() -> Path:
    """화면 파일(HTML/CSS/JS) 위치. PyInstaller로 묶인 경우에도 동작한다."""
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return Path(bundle_root) / "chojema_webdelta" / "web"
    return Path(__file__).resolve().parent / "web"
