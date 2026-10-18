"""엔진·저장소 단위 테스트와, 임시 웹페이지를 상대로 한 전체 흐름 테스트."""

import json
import re
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from chojema_webdelta import engine, i18n, paths, store as store_module
from chojema_webdelta.server import AppServer, AutoChecker

PAGE = """<html><head><meta charset="{charset}"><style>.x{{}}</style></head><body>
<nav>메뉴 {nonce}</nav>
<div id="content"><h1>공지</h1><p>{body}</p><p>조회수 {views}</p></div>
<script>var t = {nonce};</script></body></html>"""


class ExtractTextTest(unittest.TestCase):
    def test_strips_scripts_and_normalizes_whitespace(self):
        html = "<body><p>  첫   줄 </p><script>x()</script><style>p{}</style><p>둘째</p></body>"
        self.assertEqual(engine.extract_text(html), "첫 줄\n둘째")

    def test_selector_limits_region(self):
        html = PAGE.format(charset="utf-8", nonce=1, body="본문", views=3)
        self.assertEqual(engine.extract_text(html, "#content"), "공지\n본문\n조회수 3")

    def test_ignore_patterns_remove_noise(self):
        html = PAGE.format(charset="utf-8", nonce=1, body="본문", views=3)
        self.assertEqual(engine.extract_text(html, "#content", r"조회수 \d+"), "공지\n본문")

    def test_decodes_euc_kr_from_meta(self):
        html = PAGE.format(charset="euc-kr", nonce=1, body="한글 본문", views=3).encode("euc-kr")
        self.assertIn("한글 본문", engine.extract_text(html, "#content"))

    def test_missing_selector_is_reported(self):
        with self.assertRaises(engine.CheckError):
            engine.extract_text("<body><p>a</p></body>", "#none")

    def test_invalid_selector_and_pattern_are_reported(self):
        with self.assertRaises(engine.CheckError):
            engine.extract_text("<body><p>a</p></body>", "p[")
        with self.assertRaises(engine.CheckError):
            engine.extract_text("<body><p>a</p></body>", "", "(")


class SelectorExamplesTest(unittest.TestCase):
    """화면(app.js)과 README에 실은 영역 예시가 설명대로 요소를 고르는지 확인한다."""

    HTML = """<body>
    <div id="content"><h2 class="title">제목</h2><p>본문</p></div>
    <ul class="board-list wide"><li>글 하나</li></ul>
    <a class="Link--primary Link" href="/releases/tag/v1.0">릴리스 v1.0</a>
    <a class="Link" href="/issues">이슈</a>
    <h2 class="title">바깥 제목</h2>
    <div id="notice">공지</div><div id="schedule">일정</div>
    </body>"""
    EXAMPLES = [
        ("#content", "제목\n본문"),
        (".board-list", "글 하나"),
        ("a.Link--primary", "릴리스 v1.0"),
        ('a[href^="/releases/tag/"]', "릴리스 v1.0"),
        ("#content .title", "제목"),
        ("#notice, #schedule", "공지\n일정"),
    ]

    def test_examples_select_what_they_describe(self):
        for selector, expected in self.EXAMPLES:
            with self.subTest(selector=selector):
                self.assertEqual(engine.extract_text(self.HTML, selector), expected)

    def test_attribute_values_are_not_compared(self):
        before = '<body><a class="x" href="/tag/v1">릴리스</a></body>'
        after = '<body><a class="x y" href="/tag/v2">릴리스</a></body>'
        self.assertEqual(engine.extract_text(before, "a.x"), engine.extract_text(after, "a.x"))


class IgnorePatternExamplesTest(unittest.TestCase):
    """화면(app.js)과 README에 실은 무시 패턴 예시가 설명대로 동작하는지 확인한다."""

    # (패턴, 페이지에 있는 줄, 비교에 남아야 하는 글자. 줄이 통째로 빠지면 "")
    EXAMPLES = [
        (r"조회수?\s*:?\s*[\d,]+", "공지 조회 1,234", "공지"),
        (r"조회수?\s*:?\s*[\d,]+", "공지 조회수: 56", "공지"),
        (r"\d{4}[-./]\s?\d{1,2}[-./]\s?\d{1,2}\.?", "등록 2026-10-12", "등록"),
        (r"\d{4}[-./]\s?\d{1,2}[-./]\s?\d{1,2}\.?", "등록 2026. 10. 12.", "등록"),
        (r"\d{1,2}:\d{2}(:\d{2})?", "갱신 09:05", "갱신"),
        (r"\d{1,2}:\d{2}(:\d{2})?", "갱신 09:05:30", "갱신"),
        (r"\d+\s*(초|분|시간|일)\s*전", "홍길동 3분 전", "홍길동"),
        (r"\d+\s*(초|분|시간|일)\s*전", "홍길동 2 시간 전", "홍길동"),
        (r"(댓글|추천|좋아요)\s*\(?[\d,]+\)?", "제목 댓글 (12)", "제목"),
        (r"(댓글|추천|좋아요)\s*\(?[\d,]+\)?", "제목 추천 3", "제목"),
        (r"^.*광고.*$", "이번 주 광고 상품 모음", ""),
        (r"^오늘 방문자.*$", "오늘 방문자 1,024명", ""),
        (r"(?i)copyright.*$", "회사명 COPYRIGHT © 2026 All rights reserved", "회사명"),
        (r"\(광고\)", "(광고) 새 소식", "새 소식"),
    ]
    # 영어 화면과 README.md에 싣는 예시
    EXAMPLES_EN = [
        (r"(?i)views?:?\s*[\d,]+|[\d,.]+k?\s*views?", "Notice Views: 1,234", "Notice"),
        (r"(?i)views?:?\s*[\d,]+|[\d,.]+k?\s*views?", "Notice 1.2K views", "Notice"),
        (r"\d{4}[-./]\d{1,2}[-./]\d{1,2}", "Posted 2026-10-12", "Posted"),
        (r"\d{4}[-./]\d{1,2}[-./]\d{1,2}", "Posted 2026/10/12", "Posted"),
        (
            r"(?i)(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}",
            "Posted Oct 12, 2026", "Posted",
        ),
        (
            r"(?i)(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}",
            "Posted October 12 2026", "Posted",
        ),
        (r"(?i)\d{1,2}:\d{2}(:\d{2})?(\s*[ap]\.?m\.?)?", "Updated 09:05", "Updated"),
        (r"(?i)\d{1,2}:\d{2}(:\d{2})?(\s*[ap]\.?m\.?)?", "Updated 9:05:30 PM", "Updated"),
        (r"(?i)\d+\s*(seconds?|minutes?|mins?|hours?|hrs?|days?)\s+ago", "Alice 3 minutes ago", "Alice"),
        (r"(?i)\d+\s*(seconds?|minutes?|mins?|hours?|hrs?|days?)\s+ago", "Alice 2 hrs ago", "Alice"),
        (
            r"(?i)[\d,]+\s*(comments?|likes?|replies)|(comments?|likes?|replies)\s*\(?[\d,]+\)?",
            "Title 12 comments", "Title",
        ),
        (
            r"(?i)[\d,]+\s*(comments?|likes?|replies)|(comments?|likes?|replies)\s*\(?[\d,]+\)?",
            "Title Likes (3)", "Title",
        ),
        (r"^.*Sponsored.*$", "This week's Sponsored picks", ""),
        (r"^Visitors today.*$", "Visitors today: 1,024", ""),
        (r"(?i)copyright.*$", "Acme COPYRIGHT © 2026 All rights reserved", "Acme"),
        (r"\(Ad\)", "(Ad) New arrivals", "New arrivals"),
    ]

    def test_examples_remove_what_they_describe(self):
        for pattern, line, expected in self.EXAMPLES + self.EXAMPLES_EN:
            with self.subTest(pattern=pattern, line=line):
                html = f"<body><p>머리말</p><p>{line}</p></body>"
                kept = engine.extract_text(html, "", pattern).splitlines()[1:]
                self.assertEqual(kept, [expected] if expected else [])

    def test_patterns_do_not_touch_other_lines(self):
        cases = [
            (self.EXAMPLES, ["중간고사 일정 변경 안내", "도서관 휴관 안내"]),
            (self.EXAMPLES_EN, ["Midterm schedule change notice", "The library is closed on Friday"]),
        ]
        for examples, lines in cases:
            with self.subTest(first_line=lines[0]):
                patterns = "\n".join(dict.fromkeys(pattern for pattern, _, _ in examples))
                html = "<body>" + "".join(f"<p>{line}</p>" for line in lines) + "</body>"
                self.assertEqual(engine.extract_text(html, "", patterns), "\n".join(lines))

    def test_examples_are_the_ones_shown_on_screen(self):
        web = paths.web_dir()
        shown = (web / "app.js").read_text("utf-8") + (web / "messages.json").read_text("utf-8")
        for pattern, _, _ in self.EXAMPLES + self.EXAMPLES_EN:
            with self.subTest(pattern=pattern):
                # 화면 파일 안에서는 역슬래시가 한 번 더 이스케이프되어 있다.
                self.assertIn(pattern.replace("\\", "\\\\"), shown)

    def test_examples_are_the_ones_in_the_readme(self):
        root = Path(__file__).resolve().parent.parent
        for filename, examples in (("README.ko.md", self.EXAMPLES), ("README.md", self.EXAMPLES_EN)):
            readme = (root / filename).read_text("utf-8")
            for pattern, _, _ in examples:
                with self.subTest(readme=filename, pattern=pattern):
                    self.assertIn(pattern, readme)


class DiffLinesTest(unittest.TestCase):
    def test_marks_added_and_removed_lines(self):
        lines = engine.diff_lines("가\n나\n다", "가\n나나\n다")
        self.assertEqual(
            [(line.kind, line.text) for line in lines],
            [("ctx", "가"), ("del", "나"), ("add", "나나"), ("ctx", "다")],
        )

    def test_keeps_lines_that_look_like_diff_headers(self):
        lines = engine.diff_lines("--- 구분선", "+++ 구분선")
        self.assertEqual(
            [(line.kind, line.text) for line in lines],
            [("del", "--- 구분선"), ("add", "+++ 구분선")],
        )

    def test_identical_text_has_no_diff(self):
        self.assertEqual(engine.diff_lines("가", "가"), [])


class MessagesTest(unittest.TestCase):
    """서버와 화면의 문구 목록이 한국어와 영어를 빠짐없이 갖추었는지 확인한다."""

    PLACEHOLDER = re.compile(r"\{(\w+)\}")

    def setUp(self):
        web = paths.web_dir()
        self.screen = json.loads((web / "messages.json").read_text("utf-8"))
        self.html = (web / "index.html").read_text("utf-8")
        self.script = (web / "app.js").read_text("utf-8")

    def placeholders(self, template):
        # \d{4} 같은 정규식 예시의 {4}는 값이 들어갈 자리가 아니다.
        return {name for name in self.PLACEHOLDER.findall(template) if not name.isdigit()}

    def test_server_messages_exist_in_both_languages(self):
        for code, entry in i18n.MESSAGES.items():
            with self.subTest(code=code):
                self.assertEqual(set(entry), set(i18n.LANGUAGES))
                self.assertEqual(self.placeholders(entry["ko"]), self.placeholders(entry["en"]))

    def test_screen_messages_exist_in_both_languages(self):
        self.assertEqual(set(self.screen), set(i18n.LANGUAGES))

        # 개수에 따라 달라지는 문구는 언어마다 갖춘 형태(_one, _other)가 다를 수 있다.
        def base(key):
            return re.sub(r"_(one|other)$", "", key)

        ko, en = self.screen["ko"], self.screen["en"]
        self.assertEqual({base(key) for key in ko}, {base(key) for key in en})
        for key in en:
            with self.subTest(key=key):
                korean = ko[key] if key in ko else ko[f"{base(key)}_other"]
                if key.endswith("_one"):  # 하나일 때는 개수를 적지 않는 문장도 있다.
                    self.assertLessEqual(self.placeholders(en[key]), self.placeholders(korean))
                else:
                    self.assertEqual(self.placeholders(en[key]), self.placeholders(korean))
        for table in (ko, en):
            for key in table:
                if key.endswith("_one"):
                    self.assertIn(f"{base(key)}_other", table)

    def test_keys_used_by_the_screen_are_defined(self):
        used = set(re.findall(r'data-i18n(?:-html)?="([^"]+)"', self.html))
        for spec in re.findall(r'data-i18n-attr="([^"]+)"', self.html):
            used.update(pair.split(":")[1] for pair in spec.split(","))
        used.update(re.findall(r'\bt\("([a-z0-9_]+)"', self.script))
        counted = set(re.findall(r'\btn\("([a-z0-9_]+)"', self.script))
        for lang, table in self.screen.items():
            for key in used:
                with self.subTest(lang=lang, key=key):
                    self.assertIn(key, table)
            for key in counted:
                with self.subTest(lang=lang, key=key):
                    self.assertIn(f"{key}_other", table)

    def test_defined_keys_are_used_by_the_screen(self):
        words = set(re.findall(r"[a-z0-9_]+", self.html + self.script))
        for key in self.screen["en"]:
            with self.subTest(key=key):
                self.assertIn(re.sub(r"_(one|other)$", "", key), words)

    def test_language_is_picked_from_the_request_header(self):
        cases = [
            ("ko", "ko"), ("ko-KR,ko;q=0.9,en;q=0.8", "ko"), ("en-US,en;q=0.9", "en"),
            ("fr-FR,en;q=0.8,ko;q=0.5", "en"), ("fr", "en"), ("", "en"), (None, "en"),
        ]
        for header, expected in cases:
            with self.subTest(header=header):
                self.assertEqual(i18n.pick_language(header), expected)

    def test_stored_error_can_be_shown_in_either_language(self):
        stored = engine.CheckError("http_error", status=503).dump()
        self.assertEqual(i18n.render_stored(stored, "ko"), "서버가 오류를 돌려줌 (HTTP 503)")
        self.assertEqual(i18n.render_stored(stored, "en"), "The server returned an error (HTTP 503)")
        # 문구 코드를 쓰기 전에 저장된 글자는 그대로 보여 준다.
        self.assertEqual(i18n.render_stored("접속 실패", "en"), "접속 실패")
        self.assertEqual(i18n.render_stored("{not json", "en"), "{not json")
        self.assertIsNone(i18n.render_stored(None, "en"))


class StoreTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = store_module.Store(Path(self._tmp.name) / "test.sqlite3")
        fields = store_module.clean_site_fields({"url": "https://example.com/a"})
        self.site_id = self.store.add_site(fields)

    def site(self):
        return self.store.get_site(self.site_id)

    def test_name_defaults_to_domain(self):
        self.assertEqual(self.site()["name"], "example.com")

    def test_rejects_non_http_urls(self):
        for url in ("", "example.com", "javascript:alert(1)", "file:///etc/passwd"):
            with self.assertRaises(ValueError):
                store_module.clean_site_fields({"url": url})

    def test_change_stays_until_acknowledged(self):
        self.store.record_text(self.site(), "v1")
        self.assertEqual(self.site()["status"], store_module.STATUS_NEW)
        self.store.record_text(self.site(), "v1")
        self.assertEqual(self.site()["status"], store_module.STATUS_UNCHANGED)
        self.store.record_text(self.site(), "v2")
        self.assertEqual(self.site()["status"], store_module.STATUS_CHANGED)
        # 확인하지 않고 다시 점검해도 변경 표시는 남는다.
        self.store.record_text(self.site(), "v2")
        self.assertEqual(self.site()["status"], store_module.STATUS_CHANGED)
        self.store.acknowledge(self.site_id)
        self.assertEqual(self.site()["status"], store_module.STATUS_UNCHANGED)
        self.assertEqual(self.site()["baseline_text"], "v2")

    def test_reverting_to_baseline_clears_change(self):
        self.store.record_text(self.site(), "v1")
        self.store.record_text(self.site(), "v2")
        self.store.record_text(self.site(), "v1")
        self.assertEqual(self.site()["status"], store_module.STATUS_UNCHANGED)

    def test_error_keeps_baseline(self):
        self.store.record_text(self.site(), "v1")
        self.store.record_error(self.site(), "접속 실패")
        self.assertEqual(self.site()["status"], store_module.STATUS_ERROR)
        self.assertEqual(self.site()["baseline_text"], "v1")

    def test_editing_target_resets_baseline(self):
        self.store.record_text(self.site(), "v1")
        fields = store_module.clean_site_fields({"url": "https://example.com/a", "selector": "#x"})
        self.store.update_site(self.site_id, fields)
        self.assertIsNone(self.site()["baseline_text"])
        self.assertIsNone(self.site()["status"])

    def test_manual_entries_are_cleaned(self):
        fields = store_module.clean_manual_fields({"url": " https://example.com/x ", "note": " 매주\n 월요일 "})
        self.assertEqual(fields, {"name": "example.com", "url": "https://example.com/x", "note": "매주 월요일"})
        with self.assertRaises(ValueError):
            store_module.clean_manual_fields({"url": "example.com"})
        with self.assertRaises(ValueError):
            store_module.clean_manual_fields({"url": "https://example.com/", "note": "가" * 501})

    def test_move_to_manual_keeps_name_and_url(self):
        self.store.record_text(self.site(), "v1")
        manual_id = self.store.move_to_manual(self.site_id)
        self.assertIsNone(self.site())
        [item] = self.store.list_manual()
        self.assertEqual((item["id"], item["name"], item["url"]), (manual_id, "example.com", "https://example.com/a"))
        self.assertIsNone(item["last_opened_at"])
        self.assertTrue(self.store.mark_opened(manual_id))
        self.assertIsNotNone(self.store.list_manual()[0]["last_opened_at"])
        self.assertIsNone(self.store.move_to_manual(self.site_id))

    def test_stale_result_is_dropped_after_edit(self):
        before_edit = self.site()
        fields = store_module.clean_site_fields({"url": "https://example.com/b"})
        self.store.update_site(self.site_id, fields)
        self.store.record_text(before_edit, "옛 주소의 내용")
        self.assertIsNone(self.site()["baseline_text"])


class AutoCheckerTest(unittest.TestCase):
    class CountingChecker:
        def __init__(self):
            self.starts = 0

        def start(self):
            self.starts += 1

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = store_module.Store(Path(self._tmp.name) / "test.sqlite3")
        self.checker = self.CountingChecker()

    def make(self, **kwargs):
        auto = AutoChecker(self.store, self.checker, **kwargs)
        self.addCleanup(auto.stop)
        return auto

    def test_is_off_until_an_interval_is_set(self):
        auto = self.make()
        self.assertEqual(auto.snapshot(), {"interval_seconds": 0, "next_check_at": None})

    def test_starts_checks_on_schedule_and_stops_when_turned_off(self):
        auto = self.make(min_interval=0.05)
        auto.set_interval(0.1)
        time.sleep(0.55)
        self.assertGreaterEqual(self.checker.starts, 3)
        auto.set_interval(0)
        time.sleep(0.15)  # 끄는 순간 이미 시작된 한 번은 허용한다.
        after_off = self.checker.starts
        time.sleep(0.35)
        self.assertEqual(self.checker.starts, after_off)

    def test_first_check_waits_one_full_interval(self):
        auto = self.make()
        auto.set_interval(600)
        time.sleep(0.2)
        self.assertEqual(self.checker.starts, 0)
        self.assertIsNotNone(auto.snapshot()["next_check_at"])

    def test_interval_is_remembered_across_restarts(self):
        self.make().set_interval(1800)
        self.assertEqual(self.make().snapshot()["interval_seconds"], 1800)

    def test_rejects_intervals_out_of_range(self):
        auto = self.make()
        for bad in (30, -60, 31 * 24 * 60 * 60, "600", None, True):
            with self.subTest(interval=bad), self.assertRaises(ValueError):
                auto.set_interval(bad)
        self.assertEqual(auto.snapshot()["interval_seconds"], 0)


class FullFlowTest(unittest.TestCase):
    """임시 웹페이지를 띄워 두고 API로 등록 → 점검 → 변경 감지 → 확인까지 돌려 본다."""

    def setUp(self):
        self.page = {"body": "처음 내용", "views": 0, "status": 200, "headers": {}}
        page = self.page

        class PageHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                page["views"] += 1
                body = PAGE.format(
                    charset="utf-8", nonce=time.time_ns(), body=page["body"], views=page["views"]
                ).encode("utf-8")
                self.send_response(page["status"])
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                for name, value in page["headers"].items():
                    self.send_header(name, value)
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.target = ThreadingHTTPServer(("127.0.0.1", 0), PageHandler)
        self.app = AppServer(0, store_module.Store(Path(self._tmp.name) / "test.sqlite3"))
        for server in (self.target, self.app):
            threading.Thread(target=server.serve_forever, daemon=True).start()
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)
        self.target_url = f"http://127.0.0.1:{self.target.server_address[1]}/notice"

    def call(self, method, path, body=None, headers=None):
        request = urllib.request.Request(
            self.app.url.rstrip("/") + path,
            method=method,
            data=None if method == "GET" else json.dumps(body or {}).encode("utf-8"),
            headers={"Content-Type": "application/json", **(headers or {})},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.load(response)

    def check_and_wait(self):
        self.assertTrue(self.call("POST", "/api/check")["started"])
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            state = self.call("GET", "/api/state")
            if not state["job"]["running"]:
                return state["sites"]
            time.sleep(0.05)
        self.fail("점검이 끝나지 않음")

    def test_detects_change_and_ignores_noise(self):
        self.call("POST", "/api/sites", {
            "url": self.target_url, "selector": "#content", "ignore_patterns": r"조회수 \d+",
        })
        self.assertEqual(self.check_and_wait()[0]["status"], "new")
        # 조회수와 스크립트 값은 매번 달라지지만 무시되어야 한다.
        self.assertEqual(self.check_and_wait()[0]["status"], "unchanged")

        self.page["body"] = "바뀐 내용"
        site = self.check_and_wait()[0]
        self.assertEqual(site["status"], "changed")
        self.assertEqual(
            [(line["kind"], line["text"]) for line in site["diff"]],
            [("ctx", "공지"), ("del", "처음 내용"), ("add", "바뀐 내용")],
        )

        self.call("POST", f"/api/sites/{site['id']}/ack")
        self.assertEqual(self.call("GET", "/api/state")["sites"][0]["status"], "unchanged")

        self.page["status"] = 503
        site = self.check_and_wait()[0]
        self.assertEqual(site["status"], "error")
        self.assertIn("503", site["last_error"])
        # 같은 실패 사유를 요청한 언어로 보여 준다.
        for lang, expected in (("ko", "서버가 오류를 돌려줌 (HTTP 503)"), ("en", "The server returned an error (HTTP 503)")):
            state = self.call("GET", "/api/state", headers={"Accept-Language": lang})
            self.assertEqual(state["sites"][0]["last_error"], expected)

    def test_reports_cloudflare_browser_check(self):
        self.call("POST", "/api/sites", {"url": self.target_url})
        self.page["status"] = 403
        self.page["headers"] = {"cf-mitigated": "challenge"}
        site = self.check_and_wait()[0]
        self.assertEqual(site["status"], "error")
        self.assertEqual(site["last_error"], i18n.text("bot_challenge", "en", status=403))
        self.assertIn("manual check list", site["last_error"])

    def test_errors_follow_the_requested_language(self):
        cases = [
            ("ko", "주소는 http:// 또는 https:// 로 시작해야 합니다."),
            ("en-US,en;q=0.9", "The URL must start with http:// or https://."),
            (None, "The URL must start with http:// or https://."),
        ]
        for header, expected in cases:
            headers = {"Accept-Language": header} if header else {}
            with self.subTest(header=header), self.assertRaises(urllib.error.HTTPError) as caught:
                self.call("POST", "/api/sites", {"url": "example.com"}, headers)
            self.assertEqual(json.load(caught.exception)["error"], expected)

        result = self.call(
            "POST", "/api/import", {"sites": [{"url": "nope"}, "text"]}, {"Accept-Language": "ko"}
        )
        self.assertEqual(
            [error["error"] for error in result["errors"]],
            ["주소는 http:// 또는 https:// 로 시작해야 합니다.", "항목의 형식이 올바르지 않습니다."],
        )

    def test_export_delete_and_import_round_trip(self):
        for number in (1, 2, 3):
            self.call("POST", "/api/sites", {
                "url": f"https://example.com/{number}", "name": f"사이트 {number}",
                "selector": "#content", "ignore_patterns": r"조회수 \d+",
            })
        exported = self.call("GET", "/api/export")
        self.assertEqual(len(exported["sites"]), 3)
        self.assertEqual(exported["sites"][0], {
            "name": "사이트 1", "url": "https://example.com/1",
            "selector": "#content", "ignore_patterns": r"조회수 \d+",
        })

        ids = [site["id"] for site in self.call("GET", "/api/state")["sites"]]
        self.assertEqual(self.call("POST", "/api/sites/delete", {"site_ids": ids[:2]}), {"deleted": 2})
        names = [site["name"] for site in self.call("GET", "/api/state")["sites"]]
        self.assertEqual(names, ["사이트 3"])

        # 남아 있는 '사이트 3'은 건너뛰고, 잘못된 항목은 이유와 함께 돌려준다.
        result = self.call("POST", "/api/import", {
            "sites": exported["sites"] + [{"url": "주소 아님"}, "문자열 항목"],
        })
        self.assertEqual((result["added"], result["skipped"]), (2, 1))
        self.assertEqual([error["position"] for error in result["errors"]], [4, 5])
        self.assertEqual(len(self.call("GET", "/api/state")["sites"]), 3)

        self.assertEqual(self.call("POST", "/api/sites/delete", {"all": True}), {"deleted": 3})
        self.assertEqual(self.call("GET", "/api/state")["sites"], [])
        self.assertEqual(self.call("POST", "/api/import", exported)["added"], 3)

    def test_manual_list_is_kept_apart_from_checks(self):
        self.call("POST", "/api/sites", {"url": self.target_url})
        self.page["status"] = 403
        self.page["headers"] = {"cf-mitigated": "challenge"}
        site = self.check_and_wait()[0]
        self.call("POST", f"/api/sites/{site['id']}/to-manual")
        state = self.call("GET", "/api/state")
        self.assertEqual(state["sites"], [])
        [moved] = state["manual"]
        self.assertEqual(moved["url"], self.target_url)

        manual_id = self.call("POST", "/api/manual", {"url": "https://example.com/notes", "note": "월요일"})["id"]
        self.call("PUT", f"/api/manual/{manual_id}", {"url": "https://example.com/notes", "name": "메모"})
        self.call("POST", f"/api/manual/{manual_id}/opened")
        item = self.call("GET", "/api/state")["manual"][1]
        self.assertEqual((item["name"], item["note"]), ("메모", ""))
        self.assertIsNotNone(item["last_opened_at"])

        # 변경 확인은 수동 확인 목록을 방문하지 않는다.
        views = self.page["views"]
        self.assertEqual(self.check_and_wait(), [])
        self.assertEqual(self.page["views"], views)

        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.call("POST", "/api/manual/999/opened")
        self.assertEqual(caught.exception.code, 404)

        exported = self.call("GET", "/api/export")
        self.assertEqual(exported["manual_sites"], [
            {"name": moved["name"], "url": self.target_url, "note": ""},
            {"name": "메모", "url": "https://example.com/notes", "note": ""},
        ])
        self.assertEqual(self.call("POST", "/api/sites/delete", {"all": True}), {"deleted": 2})
        result = self.call("POST", "/api/import", {**exported, "manual_sites": exported["manual_sites"] * 2})
        self.assertEqual((result["added"], result["skipped"]), (2, 2))
        self.call("DELETE", f"/api/manual/{self.call('GET', '/api/state')['manual'][0]['id']}")
        self.assertEqual(len(self.call("GET", "/api/state")["manual"]), 1)

    def test_auto_interval_can_be_set_through_the_api(self):
        self.assertEqual(self.call("GET", "/api/state")["auto"]["interval_seconds"], 0)
        result = self.call("POST", "/api/auto", {"interval_seconds": 600})
        self.assertEqual(result["interval_seconds"], 600)
        self.assertIsNotNone(self.call("GET", "/api/state")["auto"]["next_check_at"])

        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.call("POST", "/api/auto", {"interval_seconds": 30})
        self.assertEqual(caught.exception.code, 400)
        self.assertEqual(self.call("GET", "/api/state")["auto"]["interval_seconds"], 600)

        self.call("POST", "/api/auto", {"interval_seconds": 0})
        self.assertEqual(
            self.call("GET", "/api/state")["auto"], {"interval_seconds": 0, "next_check_at": None}
        )

    def test_bulk_delete_requires_an_explicit_target(self):
        self.call("POST", "/api/sites", {"url": "https://example.com/"})
        for body in ({}, {"all": "yes"}, {"site_ids": "1"}, {"site_ids": ["1"]}):
            with self.assertRaises(urllib.error.HTTPError) as caught:
                self.call("POST", "/api/sites/delete", body)
            self.assertEqual(caught.exception.code, 400)
        self.assertEqual(len(self.call("GET", "/api/state")["sites"]), 1)

    def test_rejects_requests_from_other_origins(self):
        cases = [
            ({"Origin": "https://evil.example"}, 403),
            ({"Host": "evil.example"}, 403),
            ({"Content-Type": "text/plain"}, 415),
        ]
        for headers, expected in cases:
            with self.assertRaises(urllib.error.HTTPError) as caught:
                self.call("POST", "/api/sites", {"url": self.target_url}, headers)
            self.assertEqual(caught.exception.code, expected)
        self.assertEqual(self.call("GET", "/api/state")["sites"], [])

    def test_serves_the_screen(self):
        with urllib.request.urlopen(self.app.url, timeout=5) as response:
            self.assertIn("ChojemaWebDelta", response.read().decode("utf-8"))
        with urllib.request.urlopen(self.app.url + "messages.json", timeout=5) as response:
            self.assertEqual(set(json.load(response)), {"ko", "en"})


if __name__ == "__main__":
    unittest.main()
