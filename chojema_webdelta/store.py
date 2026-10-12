"""사이트 목록과 스냅샷 저장소 (SQLite).

사이트마다 두 가지 텍스트를 둔다.
- baseline: 사용자가 마지막으로 확인(인정)한 상태. 비교의 기준.
- current: 가장 최근 점검에서 본 상태.
둘이 다르면 "변경됨"이고, 사용자가 확인하면 baseline이 current로 옮겨 간다.
"""

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from . import engine, i18n

STATUS_NEW = "new"
STATUS_UNCHANGED = "unchanged"
STATUS_CHANGED = "changed"
STATUS_ERROR = "error"

# 내보내기·가져오기에 담는 항목. 스냅샷과 점검 기록은 담지 않는다.
SETTING_FIELDS = ("name", "url", "selector", "ignore_patterns")

SCHEMA = """
CREATE TABLE IF NOT EXISTS sites (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    url             TEXT NOT NULL,
    selector        TEXT NOT NULL DEFAULT '',
    ignore_patterns TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL,
    baseline_text   TEXT,
    baseline_at     TEXT,
    current_text    TEXT,
    current_at      TEXT,
    last_checked_at TEXT,
    status          TEXT,
    last_error      TEXT
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def clean_site_fields(data: dict) -> dict:
    """입력값을 다듬고 검증한다. 문제가 있으면 사용자에게 보여 줄 InputError(ValueError)."""
    url = str(data.get("url") or "").strip()
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise i18n.InputError("bad_url")
    selector = str(data.get("selector") or "").strip()
    ignore_patterns = "\n".join(
        line.strip() for line in str(data.get("ignore_patterns") or "").splitlines() if line.strip()
    )
    try:
        engine.compile_ignore_patterns(ignore_patterns)
    except engine.CheckError as exc:
        raise i18n.InputError(exc.code, **exc.params) from exc
    name = str(data.get("name") or "").strip() or parts.netloc
    return {"name": name, "url": url, "selector": selector, "ignore_patterns": ignore_patterns}


class Store:
    def __init__(self, db_path: Path):
        self._db_path = str(db_path)
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self):
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def list_sites(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM sites ORDER BY id").fetchall()
        return [dict(row) for row in rows]

    def get_site(self, site_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM sites WHERE id = ?", (site_id,)).fetchone()
        return dict(row) if row else None

    def add_site(self, fields: dict) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO sites (name, url, selector, ignore_patterns, created_at) "
                "VALUES (:name, :url, :selector, :ignore_patterns, :created_at)",
                {**fields, "created_at": _now()},
            )
            return cursor.lastrowid

    def update_site(self, site_id: int, fields: dict) -> bool:
        """수정한다. 비교 대상이 달라지는 항목이 바뀌면 기준을 버리고 다시 잡게 한다."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM sites WHERE id = ?", (site_id,)).fetchone()
            if row is None:
                return False
            target_changed = any(
                row[key] != fields[key] for key in ("url", "selector", "ignore_patterns")
            )
            conn.execute(
                "UPDATE sites SET name = :name, url = :url, selector = :selector, "
                "ignore_patterns = :ignore_patterns WHERE id = :id",
                {**fields, "id": site_id},
            )
            if target_changed:
                conn.execute(
                    "UPDATE sites SET baseline_text = NULL, baseline_at = NULL, "
                    "current_text = NULL, current_at = NULL, last_checked_at = NULL, "
                    "status = NULL, last_error = NULL WHERE id = ?",
                    (site_id,),
                )
            return True

    def delete_site(self, site_id: int) -> bool:
        with self._connect() as conn:
            return conn.execute("DELETE FROM sites WHERE id = ?", (site_id,)).rowcount > 0

    def delete_sites(self, site_ids: list[int] | None = None) -> int:
        """여러 사이트를 지우고 지운 개수를 돌려준다. site_ids가 없으면 전부 지운다."""
        with self._connect() as conn:
            if site_ids is None:
                return conn.execute("DELETE FROM sites").rowcount
            if not site_ids:
                return 0
            marks = ",".join("?" * len(site_ids))
            return conn.execute(f"DELETE FROM sites WHERE id IN ({marks})", site_ids).rowcount

    def export_sites(self) -> list[dict]:
        return [{key: site[key] for key in SETTING_FIELDS} for site in self.list_sites()]

    def import_sites(self, entries: list[dict]) -> tuple[int, int]:
        """검증을 마친 항목들을 추가한다. 주소·영역·패턴이 같은 것이 이미 있으면 건너뛴다.

        (추가한 개수, 건너뛴 개수)를 돌려준다.
        """
        added = skipped = 0
        now = _now()
        with self._connect() as conn:
            existing = {
                (row["url"], row["selector"], row["ignore_patterns"])
                for row in conn.execute("SELECT url, selector, ignore_patterns FROM sites")
            }
            for fields in entries:
                key = (fields["url"], fields["selector"], fields["ignore_patterns"])
                if key in existing:
                    skipped += 1
                    continue
                existing.add(key)
                conn.execute(
                    "INSERT INTO sites (name, url, selector, ignore_patterns, created_at) "
                    "VALUES (:name, :url, :selector, :ignore_patterns, :created_at)",
                    {**fields, "created_at": now},
                )
                added += 1
        return added, skipped

    def record_text(self, site: dict, text: str) -> None:
        """점검 성공 결과를 반영한다. 점검 도중 설정이 바뀐 사이트는 건드리지 않는다."""
        now = _now()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM sites WHERE id = ?", (site["id"],)).fetchone()
            if row is None or self._target_differs(row, site):
                return
            if row["baseline_text"] is None:
                conn.execute(
                    "UPDATE sites SET baseline_text = ?, baseline_at = ?, current_text = ?, "
                    "current_at = ?, last_checked_at = ?, status = ?, last_error = NULL "
                    "WHERE id = ?",
                    (text, now, text, now, now, STATUS_NEW, site["id"]),
                )
                return
            status = STATUS_UNCHANGED if text == row["baseline_text"] else STATUS_CHANGED
            conn.execute(
                "UPDATE sites SET current_text = ?, current_at = ?, last_checked_at = ?, "
                "status = ?, last_error = NULL WHERE id = ?",
                (text, now, now, status, site["id"]),
            )

    def record_error(self, site: dict, message: str) -> None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM sites WHERE id = ?", (site["id"],)).fetchone()
            if row is None or self._target_differs(row, site):
                return
            conn.execute(
                "UPDATE sites SET last_checked_at = ?, status = ?, last_error = ? WHERE id = ?",
                (_now(), STATUS_ERROR, message, site["id"]),
            )

    def acknowledge(self, site_id: int | None = None) -> None:
        """변경을 확인 처리한다: 현재 상태를 새 기준으로 삼는다. site_id가 없으면 전부."""
        query = (
            "UPDATE sites SET baseline_text = current_text, baseline_at = current_at, "
            "status = ? WHERE status = ?"
        )
        params: list = [STATUS_UNCHANGED, STATUS_CHANGED]
        if site_id is not None:
            query += " AND id = ?"
            params.append(site_id)
        with self._connect() as conn:
            conn.execute(query, params)

    @staticmethod
    def _target_differs(row: sqlite3.Row, site: dict) -> bool:
        return any(row[key] != site[key] for key in ("url", "selector", "ignore_patterns"))
