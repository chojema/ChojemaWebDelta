"""서버와 콘솔이 사용자에게 보여 주는 문구의 한국어·영어 목록.

화면(브라우저)의 문구는 web/messages.json에 따로 있다. 여기에는 API 오류, 점검 실패 사유,
콘솔 출력처럼 Python 쪽에서 만들어지는 문구만 둔다.
"""

import json
import os
import sys

LANGUAGES = ("ko", "en")
DEFAULT_LANGUAGE = "en"
LANGUAGE_ENV = "CHOJEMA_WEBDELTA_LANG"

MESSAGES = {
    # 점검 실패 사유 (engine)
    "bad_pattern": {
        "ko": "무시 패턴이 올바른 정규식이 아닙니다: {pattern} ({detail})",
        "en": "The ignore pattern is not a valid regular expression: {pattern} ({detail})",
    },
    "timeout": {
        "ko": "응답 시간 초과 ({seconds}초)",
        "en": "Timed out after {seconds} seconds",
    },
    "connect_failed": {
        "ko": "서버에 연결할 수 없습니다. 주소와 인터넷 연결을 확인하세요.",
        "en": "Could not connect to the server. Check the URL and your internet connection.",
    },
    "fetch_failed": {
        "ko": "접속 실패 ({detail})",
        "en": "Request failed ({detail})",
    },
    "http_error": {
        "ko": "서버가 오류를 돌려줌 (HTTP {status})",
        "en": "The server returned an error (HTTP {status})",
    },
    "bot_challenge": {
        "ko": "사이트가 자동 접속을 막고 브라우저 확인을 요구합니다 (HTTP {status}). 이 앱으로는 변경을 확인할 수 없으니, 필요하면 수동 확인 목록으로 옮겨 직접 열어 보세요.",
        "en": "The site blocks automated access and asks for a browser check (HTTP {status}). This app cannot check it for changes; if you need it, move it to the manual check list and open it yourself.",
    },
    "bad_selector": {
        "ko": "CSS 선택자가 올바르지 않습니다: {selector}",
        "en": "The CSS selector is not valid: {selector}",
    },
    "selector_no_match": {
        "ko": "선택자와 일치하는 영역이 없습니다: {selector}",
        "en": "No region matches the selector: {selector}",
    },
    "unexpected_error": {
        "ko": "예상하지 못한 오류: {detail}",
        "en": "Unexpected error: {detail}",
    },
    # 입력값 검증 (store, server)
    "bad_url": {
        "ko": "주소는 http:// 또는 https:// 로 시작해야 합니다.",
        "en": "The URL must start with http:// or https://.",
    },
    "interval_not_number": {
        "ko": "주기는 초 단위 숫자여야 합니다.",
        "en": "The interval must be a number of seconds.",
    },
    "interval_out_of_range": {
        "ko": "주기는 1분 이상 30일 이하로 정해 주세요.",
        "en": "Set the interval between 1 minute and 30 days.",
    },
    "site_ids_invalid": {
        "ko": "site_ids는 숫자 목록이어야 합니다.",
        "en": "site_ids must be a list of numbers.",
    },
    "import_no_list": {
        "ko": "사이트 목록이 들어 있지 않습니다.",
        "en": "No site list was provided.",
    },
    "import_too_many": {
        "ko": "한 번에 가져올 수 있는 사이트는 {limit}개까지입니다.",
        "en": "At most {limit} sites can be imported at once.",
    },
    "import_bad_entry": {
        "ko": "항목의 형식이 올바르지 않습니다.",
        "en": "The entry is not in a valid format.",
    },
    "body_not_json": {
        "ko": "요청 본문이 올바른 JSON이 아닙니다.",
        "en": "The request body is not valid JSON.",
    },
    "body_not_object": {
        "ko": "요청 본문은 JSON 객체여야 합니다.",
        "en": "The request body must be a JSON object.",
    },
    # API 응답 (server)
    "forbidden": {
        "ko": "허용되지 않은 접근입니다.",
        "en": "Access is not allowed.",
    },
    "json_only": {
        "ko": "JSON 요청만 받습니다.",
        "en": "Only JSON requests are accepted.",
    },
    "not_found": {
        "ko": "없는 주소입니다.",
        "en": "No such address.",
    },
    "site_not_found": {
        "ko": "사이트를 찾을 수 없습니다.",
        "en": "Site not found.",
    },
    "note_too_long": {
        "ko": "메모는 {limit}자 이내로 적어 주세요.",
        "en": "Keep the note within {limit} characters.",
    },
    "body_too_large": {
        "ko": "요청이 너무 큽니다.",
        "en": "The request is too large.",
    },
    # 콘솔 출력 (__main__)
    "cli_description": {
        "ko": "등록해 둔 웹페이지를 방문해 이전과 달라진 점을 확인하는 로컬 앱.",
        "en": "A local app that visits registered web pages and shows what changed.",
    },
    "cli_port_help": {
        "ko": "화면 서버 포트",
        "en": "port for the local screen server",
    },
    "cli_no_browser_help": {
        "ko": "브라우저를 자동으로 열지 않음",
        "en": "do not open the browser automatically",
    },
    "cli_already_running": {
        "ko": "{app}가 이미 실행 중입니다: {url}",
        "en": "{app} is already running: {url}",
    },
    "cli_no_port": {
        "ko": "사용할 수 있는 포트를 찾지 못했습니다 ({port}~).",
        "en": "Could not find a free port (tried from {port}).",
    },
    "cli_screen_url": {
        "ko": "화면 주소: {url}",
        "en": "Screen address: {url}",
    },
    "cli_data_dir": {
        "ko": "데이터 폴더: {path}",
        "en": "Data folder: {path}",
    },
    "cli_quit_hint": {
        "ko": "끝내려면 화면의 '종료' 버튼을 누르거나 이 창을 닫으세요.",
        "en": "To stop, press the Quit button on the screen or close this window.",
    },
}

_WINDOWS_LANG_KOREAN = 0x12


def text(code: str, lang: str = DEFAULT_LANGUAGE, **params) -> str:
    """문구 코드를 해당 언어의 문장으로 바꾼다. 모르는 언어는 기본 언어로 보여 준다."""
    entry = MESSAGES[code]
    return entry.get(lang, entry[DEFAULT_LANGUAGE]).format(**params)


def pick_language(accept_language: str | None) -> str:
    """Accept-Language 헤더에 적힌 순서대로 살펴, 지원하는 첫 언어를 고른다."""
    for item in (accept_language or "").split(","):
        tag = item.split(";", 1)[0].strip().lower()
        primary = tag.split("-", 1)[0]
        if primary in LANGUAGES:
            return primary
    return DEFAULT_LANGUAGE


def system_language() -> str:
    """콘솔 출력에 쓸 언어. 환경 변수로 정한 값, 없으면 운영체제의 표시 언어를 따른다."""
    candidates = [os.environ.get(LANGUAGE_ENV)]
    candidates += [os.environ.get(name) for name in ("LC_ALL", "LC_MESSAGES", "LANG")]
    for value in candidates:
        primary = (value or "").strip().lower().replace("_", "-").split("-", 1)[0].split(".", 1)[0]
        if primary in LANGUAGES:
            return primary
    if sys.platform == "win32":
        try:
            import ctypes

            if ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF == _WINDOWS_LANG_KOREAN:
                return "ko"
        except (AttributeError, OSError):
            pass
    return DEFAULT_LANGUAGE


class LocalizedError(Exception):
    """사용자에게 보여 줄 오류. 문장 대신 문구 코드와 값을 들고 있어 어느 언어로든 보여 줄 수 있다."""

    def __init__(self, code: str, **params):
        super().__init__(text(code, DEFAULT_LANGUAGE, **params))
        self.code = code
        self.params = params

    def text(self, lang: str) -> str:
        return text(self.code, lang, **self.params)

    def dump(self) -> str:
        """저장해 두었다가 render_stored로 원하는 언어의 문장을 만들 수 있는 문자열."""
        return json.dumps({"code": self.code, "params": self.params}, ensure_ascii=False)


class InputError(LocalizedError, ValueError):
    """사용자가 보낸 값이 올바르지 않을 때."""


def render_stored(value: str | None, lang: str) -> str | None:
    """LocalizedError.dump()로 저장한 값을 문장으로 바꾼다. 그 밖의 글자는 그대로 돌려준다."""
    if not value or not value.startswith("{"):
        return value
    try:
        data = json.loads(value)
        return text(data["code"], lang, **data["params"])
    except (ValueError, KeyError, TypeError, IndexError):
        return value
