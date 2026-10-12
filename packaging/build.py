"""현재 운영체제용 실행 파일을 dist/ 아래에 만든다.

    python -m pip install pyinstaller
    python packaging/build.py

Windows에서는 dist/ChojemaWebDelta.exe, macOS에서는 dist/ChojemaWebDelta.app이 생긴다.
PyInstaller는 실행한 운영체제용 파일만 만들 수 있다.
"""

import os
import platform
import plistlib
import runpy
import subprocess
import sys
import zipfile
from pathlib import Path

import PyInstaller.__main__
from collect_notices import write_notices

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "chojema_webdelta" / "web"


def main() -> None:
    # Mac 중간 파일은 Windows 빌드 파일과 별도로 유지한다.
    build_dir = ROOT / "build" / "macos" if sys.platform == "darwin" else ROOT / "build"
    if sys.platform == "darwin":
        os.environ.setdefault("PYINSTALLER_CONFIG_DIR", str(build_dir / "cache"))
    legal_dir = write_notices(build_dir / "legal")
    args = [
        str(ROOT / "packaging" / "run_app.py"),
        "--name", "ChojemaWebDelta",
        "--noconfirm",
        "--clean",
        "--windowed",  # 콘솔 창 없이 실행. 종료는 화면의 '종료' 버튼으로 한다.
        "--paths", str(ROOT),
        "--add-data", f"{WEB_DIR}{os.pathsep}chojema_webdelta/web",
        "--add-data", f"{legal_dir}{os.pathsep}legal",
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(build_dir),
        "--specpath", str(build_dir),
    ]
    if sys.platform == "darwin":
        args.extend(["--osx-bundle-identifier", "com.chojema.webdelta"])
    else:
        args.append("--onefile")  # macOS의 .app은 폴더 구조가 표준이라 한 파일로 묶지 않는다.
    PyInstaller.__main__.run(args)
    if sys.platform == "darwin":
        app = ROOT / "dist" / "ChojemaWebDelta.app"
        info_path = app / "Contents" / "Info.plist"
        with info_path.open("rb") as stream:
            info = plistlib.load(stream)
        version = runpy.run_path(str(ROOT / "chojema_webdelta" / "__init__.py"))["__version__"]
        info.update(CFBundleShortVersionString=version, CFBundleVersion=version)
        with info_path.open("wb") as stream:
            plistlib.dump(info, stream)
        # 복사된 프레임워크의 Finder 메타데이터는 서명 검증을 방해한다.
        # 생성된 앱 안에서만 서명에 허용되지 않는 속성을 제거한다.
        for attr in ("com.apple.FinderInfo", "com.apple.ResourceFork"):
            subprocess.run(["xattr", "-dr", attr, str(app)], check=True)
        subprocess.run(["codesign", "--force", "--sign", "-", str(app)], check=True)
        subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)
    elif sys.platform == "win32":
        architecture = platform.machine().lower()
        if architecture in {"amd64", "x86_64"}:
            architecture = "x64"
        archive = ROOT / "dist" / f"ChojemaWebDelta-windows-{architecture}.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            bundle.write(ROOT / "dist" / "ChojemaWebDelta.exe", "ChojemaWebDelta.exe")
            for file in legal_dir.iterdir():
                bundle.write(file, file.name)


if __name__ == "__main__":
    main()
