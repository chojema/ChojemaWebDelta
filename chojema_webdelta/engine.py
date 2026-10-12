"""점검 엔진: 페이지 가져오기 → 감시 영역 추출 → 기준과 비교."""

import difflib
import re
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

TIMEOUT_SECONDS = 20
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 ChojemaWebDelta"
)
# 화면에 보이지 않거나 방문할 때마다 달라지기 쉬운 요소
NOISE_TAGS = ("script", "style", "noscript", "template", "svg", "iframe")
DIFF_CONTEXT_LINES = 2


class CheckError(Exception):
    """사용자에게 그대로 보여 줄 수 있는 점검 실패 사유."""


@dataclass
class DiffLine:
    kind: str  # "add" | "del" | "ctx" | "gap"
    text: str


def compile_ignore_patterns(raw: str) -> list[re.Pattern]:
    """한 줄에 하나씩 적은 정규식을 컴파일한다. 잘못된 식은 CheckError."""
    patterns = []
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            patterns.append(re.compile(line))
        except re.error as exc:
            raise CheckError(f"무시 패턴이 올바른 정규식이 아닙니다: {line} ({exc})") from exc
    return patterns


def fetch(url: str) -> bytes:
    try:
        response = httpx.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "ko,en;q=0.8"},
            follow_redirects=True,
            timeout=TIMEOUT_SECONDS,
        )
    except httpx.TimeoutException as exc:
        raise CheckError(f"응답 시간 초과 ({TIMEOUT_SECONDS}초)") from exc
    except httpx.ConnectError as exc:
        raise CheckError("서버에 연결할 수 없습니다. 주소와 인터넷 연결을 확인하세요.") from exc
    except httpx.HTTPError as exc:
        raise CheckError(f"접속 실패 ({exc.__class__.__name__})") from exc
    if response.status_code >= 400:
        raise CheckError(f"서버가 오류를 돌려줌 (HTTP {response.status_code})")
    return response.content


def extract_text(html: bytes | str, selector: str = "", ignore_patterns: str = "") -> str:
    """HTML에서 비교할 텍스트만 뽑아 정규화한다.

    바이트를 그대로 넘기면 BeautifulSoup이 meta 태그를 보고 인코딩(EUC-KR 등)을 판별한다.
    """
    patterns = compile_ignore_patterns(ignore_patterns)
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(NOISE_TAGS):
        tag.decompose()

    selector = (selector or "").strip()
    if selector:
        try:
            regions = soup.select(selector)
        except Exception as exc:  # soupsieve가 선택자 문법 오류에 던지는 예외가 여러 종류다
            raise CheckError(f"CSS 선택자가 올바르지 않습니다: {selector}") from exc
        if not regions:
            raise CheckError(f"선택자와 일치하는 영역이 없습니다: {selector}")
    else:
        regions = [soup.body or soup]

    lines = []
    for region in regions:
        for line in region.get_text("\n").splitlines():
            line = " ".join(line.split())
            for pattern in patterns:
                line = pattern.sub("", line)
            line = line.strip()
            if line:
                lines.append(line)
    return "\n".join(lines)


def check_page(url: str, selector: str = "", ignore_patterns: str = "") -> str:
    """페이지를 방문해 비교용 텍스트를 돌려준다. 실패하면 CheckError."""
    return extract_text(fetch(url), selector, ignore_patterns)


def diff_lines(old: str, new: str) -> list[DiffLine]:
    """기준 텍스트와 현재 텍스트의 차이를 화면에 그리기 쉬운 줄 목록으로 만든다."""
    result: list[DiffLine] = []
    unified = difflib.unified_diff(
        old.splitlines(), new.splitlines(), n=DIFF_CONTEXT_LINES, lineterm=""
    )
    for index, line in enumerate(unified):
        if index < 2:  # "---", "+++" 파일 머리말
            continue
        if line.startswith("@@"):
            if result:
                result.append(DiffLine("gap", ""))
        elif line.startswith("+"):
            result.append(DiffLine("add", line[1:]))
        elif line.startswith("-"):
            result.append(DiffLine("del", line[1:]))
        else:
            result.append(DiffLine("ctx", line[1:]))
    return result
