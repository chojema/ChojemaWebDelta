"""실행 진입점: 로컬 서버를 띄우고 브라우저로 화면을 연다."""

import argparse
import json
import urllib.error
import urllib.request
import webbrowser

from . import APP_NAME, __version__, paths
from .server import AppServer
from .store import Store

DEFAULT_PORT = 8765
PORT_ATTEMPTS = 20
DB_FILENAME = "webdelta.sqlite3"


def running_instance_url(port: int) -> str | None:
    """해당 포트에서 이 앱이 이미 돌고 있으면 그 주소를 돌려준다."""
    url = f"http://127.0.0.1:{port}/"
    try:
        with urllib.request.urlopen(url + "api/ping", timeout=1) as response:
            if json.load(response).get("app") == APP_NAME:
                return url
    except (urllib.error.URLError, OSError, ValueError):
        pass
    return None


def main() -> None:
    parser = argparse.ArgumentParser(prog=APP_NAME, description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="화면 서버 포트")
    parser.add_argument("--no-browser", action="store_true", help="브라우저를 자동으로 열지 않음")
    args = parser.parse_args()

    server = None
    for port in range(args.port, args.port + PORT_ATTEMPTS):
        existing = running_instance_url(port)
        if existing:
            print(f"{APP_NAME}가 이미 실행 중입니다: {existing}")
            if not args.no_browser:
                webbrowser.open(existing)
            return
        try:
            server = AppServer(port, Store(paths.data_dir() / DB_FILENAME))
            break
        except OSError:
            continue  # 다른 프로그램이 쓰는 포트
    if server is None:
        raise SystemExit(f"사용할 수 있는 포트를 찾지 못했습니다 ({args.port}~).")

    print(f"{APP_NAME} {__version__}")
    print(f"화면 주소: {server.url}")
    print(f"데이터 폴더: {paths.data_dir()}")
    print("끝내려면 화면의 '종료' 버튼을 누르거나 이 창을 닫으세요.")
    if not args.no_browser:
        webbrowser.open(server.url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
