"""로컬 화면 서버: 정적 화면 + JSON API + 백그라운드 점검 작업."""

import json
import sys
import threading
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import APP_NAME, __version__, engine, paths, store as store_module

MAX_PARALLEL_CHECKS = 6
MAX_DIFF_LINES = 400
MAX_BODY_BYTES = 1_000_000
MAX_IMPORT_SITES = 2000
EXPORT_FORMAT = 1
AUTO_INTERVAL_SETTING = "auto_interval_seconds"
MIN_AUTO_INTERVAL = 60
MAX_AUTO_INTERVAL = 30 * 24 * 60 * 60
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}
PUBLIC_SITE_FIELDS = (
    "id", "name", "url", "selector", "ignore_patterns", "created_at",
    "status", "last_error", "last_checked_at", "baseline_at", "current_at",
)


class Checker:
    """등록된 사이트를 백그라운드에서 돌며 점검한다. 한 번에 한 작업만 실행한다."""

    def __init__(self, store: store_module.Store):
        self._store = store
        self._lock = threading.Lock()
        self._running = False
        self._total = 0
        self._done = 0
        self._checking: set[int] = set()

    def start(self, site_ids: list[int] | None = None) -> bool:
        sites = self._store.list_sites()
        if site_ids is not None:
            wanted = set(site_ids)
            sites = [site for site in sites if site["id"] in wanted]
        with self._lock:
            if self._running:
                return False
            self._running = True
            self._total = len(sites)
            self._done = 0
            self._checking = set()
        threading.Thread(target=self._run, args=(sites,), daemon=True).start()
        return True

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "running": self._running,
                "total": self._total,
                "done": self._done,
                "checking": sorted(self._checking),
            }

    def _run(self, sites: list[dict]) -> None:
        try:
            with ThreadPoolExecutor(max_workers=MAX_PARALLEL_CHECKS) as pool:
                list(pool.map(self._check_one, sites))
        finally:
            with self._lock:
                self._running = False
                self._checking = set()

    def _check_one(self, site: dict) -> None:
        with self._lock:
            self._checking.add(site["id"])
        try:
            text = engine.check_page(site["url"], site["selector"], site["ignore_patterns"])
            self._store.record_text(site, text)
        except engine.CheckError as exc:
            self._store.record_error(site, str(exc))
        except Exception as exc:  # 한 사이트의 문제로 전체 점검이 멈추지 않게 한다
            self._store.record_error(site, f"예상하지 못한 오류: {exc.__class__.__name__}: {exc}")
        finally:
            with self._lock:
                self._checking.discard(site["id"])
                self._done += 1


class AutoChecker:
    """앱이 켜져 있는 동안 정해진 간격마다 변경 확인을 시작한다. 간격 0은 끔."""

    def __init__(self, store: store_module.Store, checker: Checker,
                 min_interval: float = MIN_AUTO_INTERVAL):
        self._store = store
        self._checker = checker
        self._min_interval = min_interval
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stopped = False
        self._interval = self._load_interval()
        # 실행 직후에 바로 방문하지 않고, 켠 시점부터 한 주기 뒤에 첫 확인을 한다.
        self._next_at = time.time() + self._interval if self._interval else None
        threading.Thread(target=self._run, daemon=True).start()

    def set_interval(self, seconds) -> None:
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
            raise ValueError("주기는 초 단위 숫자여야 합니다.")
        if seconds != 0 and not self._min_interval <= seconds <= MAX_AUTO_INTERVAL:
            raise ValueError("주기는 1분 이상 30일 이하로 정해 주세요.")
        self._store.set_setting(AUTO_INTERVAL_SETTING, str(seconds))
        with self._lock:
            self._interval = seconds
            self._next_at = time.time() + seconds if seconds else None
        self._wake.set()

    def snapshot(self) -> dict:
        with self._lock:
            next_at = self._next_at
            return {
                "interval_seconds": self._interval,
                "next_check_at": (
                    datetime.fromtimestamp(next_at).isoformat(timespec="seconds")
                    if next_at else None
                ),
            }

    def stop(self) -> None:
        with self._lock:
            self._stopped = True
        self._wake.set()

    def _load_interval(self) -> float:
        try:
            seconds = float(self._store.get_setting(AUTO_INTERVAL_SETTING, "0"))
        except ValueError:
            return 0
        if not self._min_interval <= seconds <= MAX_AUTO_INTERVAL:
            return 0
        return int(seconds) if seconds.is_integer() else seconds

    def _run(self) -> None:
        while True:
            with self._lock:
                if self._stopped:
                    return
                next_at = self._next_at
            # 벽시계 기준으로 기다린다: PC가 절전에서 깨어나 예정 시각이 지났으면 곧바로 확인한다.
            timeout = None if next_at is None else max(0.0, next_at - time.time())
            if self._wake.wait(timeout):
                self._wake.clear()  # 주기가 바뀌었거나 종료 요청: 처음부터 다시 계산한다.
                continue
            with self._lock:
                if self._stopped or self._next_at is None or time.time() < self._next_at:
                    continue
                self._next_at = time.time() + self._interval
            self._checker.start()  # 이미 확인 중이면 아무 일도 하지 않는다.


def public_site(site: dict) -> dict:
    """화면에 보낼 사이트 정보. 변경된 사이트에는 차이를 함께 싣는다."""
    result = {key: site[key] for key in PUBLIC_SITE_FIELDS}
    if site["status"] == store_module.STATUS_CHANGED:
        lines = engine.diff_lines(site["baseline_text"] or "", site["current_text"] or "")
        result["diff"] = [asdict(line) for line in lines[:MAX_DIFF_LINES]]
        result["diff_truncated"] = len(lines) > MAX_DIFF_LINES
    return result


class ApiError(Exception):
    def __init__(self, status: HTTPStatus, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class AppServer(ThreadingHTTPServer):
    daemon_threads = True
    # Windows에서는 SO_REUSEADDR가 이미 사용 중인 포트에도 묶이게 해 버린다.
    allow_reuse_address = sys.platform != "win32"

    def __init__(self, port: int, store: store_module.Store):
        super().__init__(("127.0.0.1", port), Handler)
        self.store = store
        self.checker = Checker(store)
        self.auto = AutoChecker(store, self.checker)

    def server_close(self) -> None:
        self.auto.stop()
        super().server_close()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}/"


class Handler(BaseHTTPRequestHandler):
    server: AppServer
    server_version = APP_NAME

    def log_message(self, format, *args):  # noqa: A002 - 표준 라이브러리 시그니처
        pass

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def _dispatch(self, method: str) -> None:
        try:
            # 거절할 요청이라도 본문은 먼저 읽는다. 읽지 않고 닫으면 상대가 응답 대신 연결 끊김을 본다.
            self._body = self._read_body()
            self._guard_origin(method)
            path = self.path.split("?", 1)[0]
            if method == "GET" and path in STATIC_FILES:
                self._send_static(*STATIC_FILES[path])
                return
            self._send_json(self._route(method, path))
        except ApiError as exc:
            self._send_json({"error": exc.message}, exc.status)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _guard_origin(self, method: str) -> None:
        """다른 웹사이트가 사용자의 브라우저를 통해 이 로컬 서버를 조작하지 못하게 막는다."""
        port = self.server.server_address[1]
        allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host") not in allowed_hosts:
            raise ApiError(HTTPStatus.FORBIDDEN, "허용되지 않은 접근입니다.")
        if method == "GET":
            return
        origin = self.headers.get("Origin")
        if origin is not None and origin not in {f"http://{host}" for host in allowed_hosts}:
            raise ApiError(HTTPStatus.FORBIDDEN, "허용되지 않은 접근입니다.")
        # JSON 본문만 받는다: 다른 출처의 단순 폼 전송으로는 이 조건을 만족할 수 없다.
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            raise ApiError(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "JSON 요청만 받습니다.")

    def _route(self, method: str, path: str) -> dict:
        store, checker = self.server.store, self.server.checker
        parts = [part for part in path.split("/") if part]

        if (method, parts) == ("GET", ["api", "ping"]):
            return {"app": APP_NAME, "version": __version__}
        if (method, parts) == ("GET", ["api", "state"]):
            return {
                "sites": [public_site(site) for site in store.list_sites()],
                "job": checker.snapshot(),
                "auto": self.server.auto.snapshot(),
                "data_dir": str(paths.data_dir()),
                "version": __version__,
            }
        if (method, parts) == ("POST", ["api", "check"]):
            site_ids = self._read_json().get("site_ids")
            if site_ids is not None and not (
                isinstance(site_ids, list) and all(isinstance(i, int) for i in site_ids)
            ):
                raise ValueError("site_ids는 숫자 목록이어야 합니다.")
            return {"started": checker.start(site_ids)}
        if (method, parts) == ("POST", ["api", "auto"]):
            self.server.auto.set_interval(self._read_json().get("interval_seconds"))
            return self.server.auto.snapshot()
        if (method, parts) == ("POST", ["api", "ack"]):
            store.acknowledge()
            return {"ok": True}
        if (method, parts) == ("POST", ["api", "quit"]):
            # shutdown()은 serve_forever()가 끝나기를 기다리므로 요청 스레드에서 직접 부르면 안 된다.
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return {"ok": True}
        if (method, parts) == ("POST", ["api", "sites"]):
            site_id = store.add_site(store_module.clean_site_fields(self._read_json()))
            return {"id": site_id}
        if (method, parts) == ("GET", ["api", "export"]):
            return {
                "app": APP_NAME,
                "format": EXPORT_FORMAT,
                "exported_at": datetime.now().isoformat(timespec="seconds"),
                "sites": store.export_sites(),
            }
        if (method, parts) == ("POST", ["api", "import"]):
            return self._import_sites(self._read_json().get("sites"))
        if (method, parts) == ("POST", ["api", "sites", "delete"]):
            body = self._read_json()
            if body.get("all") is True:
                return {"deleted": store.delete_sites()}
            site_ids = body.get("site_ids")
            if not (isinstance(site_ids, list) and all(isinstance(i, int) for i in site_ids)):
                raise ValueError("site_ids는 숫자 목록이어야 합니다.")
            return {"deleted": store.delete_sites(site_ids)}

        if len(parts) >= 3 and parts[:2] == ["api", "sites"] and parts[2].isdigit():
            site_id = int(parts[2])
            rest = parts[3:]
            if method == "PUT" and not rest:
                fields = store_module.clean_site_fields(self._read_json())
                found = store.update_site(site_id, fields)
            elif method == "DELETE" and not rest:
                found = store.delete_site(site_id)
            elif method == "POST" and rest == ["ack"]:
                found = store.get_site(site_id) is not None
                store.acknowledge(site_id)
            else:
                raise ApiError(HTTPStatus.NOT_FOUND, "없는 주소입니다.")
            if not found:
                raise ApiError(HTTPStatus.NOT_FOUND, "사이트를 찾을 수 없습니다.")
            return {"ok": True}

        raise ApiError(HTTPStatus.NOT_FOUND, "없는 주소입니다.")

    def _import_sites(self, entries) -> dict:
        """올바른 항목만 추가하고, 넣지 못한 항목은 이유와 함께 돌려준다."""
        if not isinstance(entries, list):
            raise ValueError("사이트 목록이 들어 있지 않습니다.")
        if len(entries) > MAX_IMPORT_SITES:
            raise ValueError(f"한 번에 가져올 수 있는 사이트는 {MAX_IMPORT_SITES}개까지입니다.")
        valid, errors = [], []
        for position, entry in enumerate(entries, start=1):
            try:
                if not isinstance(entry, dict):
                    raise ValueError("항목의 형식이 올바르지 않습니다.")
                valid.append(store_module.clean_site_fields(entry))
            except ValueError as exc:
                errors.append({"position": position, "error": str(exc)})
        added, skipped = self.server.store.import_sites(valid)
        return {"added": added, "skipped": skipped, "errors": errors}

    def _read_body(self) -> bytes:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length > MAX_BODY_BYTES:
            self.close_connection = True
            raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "요청이 너무 큽니다.")
        return self.rfile.read(length) if length > 0 else b""

    def _read_json(self) -> dict:
        if not self._body:
            return {}
        try:
            data = json.loads(self._body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("요청 본문이 올바른 JSON이 아닙니다.") from exc
        if not isinstance(data, dict):
            raise ValueError("요청 본문은 JSON 객체여야 합니다.")
        return data

    def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, "application/json; charset=utf-8", body)

    def _send_static(self, filename: str, content_type: str) -> None:
        self._send(HTTPStatus.OK, content_type, (paths.web_dir() / filename).read_bytes())

    def _send(self, status: HTTPStatus, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)
