"""현재 운영체제용 실행 파일을 dist/ 아래에 만든다.

    python -m pip install pyinstaller
    python packaging/build.py

Windows에서는 dist/ChojemaWebDelta.exe, macOS에서는 dist/ChojemaWebDelta.app이 생긴다.
PyInstaller는 실행한 운영체제용 파일만 만들 수 있다.
"""

import os
import sys
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "chojema_webdelta" / "web"


def main() -> None:
    args = [
        str(ROOT / "packaging" / "run_app.py"),
        "--name", "ChojemaWebDelta",
        "--noconfirm",
        "--clean",
        "--windowed",  # 콘솔 창 없이 실행. 종료는 화면의 '종료' 버튼으로 한다.
        "--paths", str(ROOT),
        "--add-data", f"{WEB_DIR}{os.pathsep}chojema_webdelta/web",
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build"),
        "--specpath", str(ROOT / "build"),
    ]
    if sys.platform != "darwin":
        args.append("--onefile")  # macOS의 .app은 폴더 구조가 표준이라 한 파일로 묶지 않는다.
    PyInstaller.__main__.run(args)


if __name__ == "__main__":
    main()
