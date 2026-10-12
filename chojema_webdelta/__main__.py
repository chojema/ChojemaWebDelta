"""실행 진입점: 로컬 서버를 띄우고 브라우저로 화면을 연다."""

import argparse
import json
import urllib.error
import urllib.request
import webbrowser

from . import APP_NAME, __version__, i18n, paths
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
    lang = i18n.system_language()

    def say(code: str, **params) -> str:
        return i18n.text(code, lang, **params)

    parser = argparse.ArgumentParser(prog=APP_NAME, description=say("cli_description"))
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=say("cli_port_help"))
    parser.add_argument("--no-browser", action="store_true", help=say("cli_no_browser_help"))
    args = parser.parse_args()

    server = None
    for port in range(args.port, args.port + PORT_ATTEMPTS):
        existing = running_instance_url(port)
        if existing:
            print(say("cli_already_running", app=APP_NAME, url=existing))
            if not args.no_browser:
                webbrowser.open(existing)
            return
        try:
            server = AppServer(port, Store(paths.data_dir() / DB_FILENAME))
            break
        except OSError:
            continue  # 다른 프로그램이 쓰는 포트
    if server is None:
        raise SystemExit(say("cli_no_port", port=args.port))

    print(f"{APP_NAME} {__version__}")
    print(say("cli_screen_url", url=server.url))
    print(say("cli_data_dir", path=paths.data_dir()))
    print(say("cli_quit_hint"))
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
