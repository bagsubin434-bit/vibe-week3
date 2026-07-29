#!/usr/bin/env python3
"""HTML/JS 파일을 4가지 보안 관점으로 점검한다.

1. 하드코딩된 비밀번호/API 키
2. escape 없이 innerHTML에 넣는 사용자 입력 (XSS)
3. console.log의 민감 정보 노출
4. http:// 로 시작하는 외부 요청 (평문 전송)

사용법:
    python check_security.py <파일1> [<파일2> ...]

각 항목은 정규식 기반 휴리스틱 탐지이므로 오탐(false positive)이 섞일 수 있다.
스크립트 출력은 "검토 후보" 목록이며, 이 스크립트를 사용하는 쪽(SKILL.md 지침)에서
실제 코드 맥락을 읽고 오탐을 걸러낸 뒤 최종 보고서를 작성해야 한다.
"""

import re
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

CRITICAL = "심각"
WARNING = "주의"
SUGGESTION = "제안"

ICON = {CRITICAL: "\U0001F534", WARNING: "\U0001F7E1", SUGGESTION: "\U0001F7E2"}

SECRET_KEYWORDS = (
    r"password|passwd|pwd|secret|api[_-]?key|apikey|access[_-]?key|accesskey|"
    r"auth[_-]?token|authtoken|private[_-]?key|privatekey|token|credential"
)
SECRET_ASSIGN_RE = re.compile(
    rf"(?im)^[^\n]*?\b(\w*(?:{SECRET_KEYWORDS})\w*)\s*[:=]\s*(["
    r"'`])((?:(?!\2).)*)\2",
)

INNER_HTML_RE = re.compile(r"(?im)([\w.$\[\]]+)\.innerHTML\s*(\+?=)\s*([^;\n]+);?")
SANITIZER_HINT_RE = re.compile(r"(?i)\b(escape|sanitize|purify|encode|textcontent|dompurify)\w*\b")

CONSOLE_RE = re.compile(r"(?im)console\.(log|warn|error|debug|info)\s*\(([^\n]*)\)")
SENSITIVE_LOG_RE = re.compile(
    r"(?i)password|pwd|passwd|비밀\s?번호|token|토큰|secret|시크릿|api[_-]?\s?key|apikey|"
    r"api\s?키|credential|자격\s?증명|인증\s?정보|ssn|주민\s?등록\s?번호|주민\s?번호|"
    r"card\s?number|카드\s?번호|cvv|\bpin\b",
)

HTTP_URL_RE = re.compile(r"(?im)[\"'`](http://[^\"'`\s]+)[\"'`]")
LOCAL_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0", "::1")
NAMESPACE_HOSTS = ("www.w3.org", "w3.org")
XMLNS_PREFIX_RE = re.compile(r"(?i)xmlns[\w:-]*\s*=\s*$")


def line_of(text, offset):
    return text.count("\n", 0, offset) + 1


def line_text(lines, line_no):
    if 1 <= line_no <= len(lines):
        return lines[line_no - 1].strip()
    return ""


def truncate(value, limit=100):
    value = value.strip()
    return value if len(value) <= limit else value[:limit] + "..."


def check_hardcoded_secrets(text, lines, findings):
    for m in SECRET_ASSIGN_RE.finditer(text):
        name, quote, value = m.group(1), m.group(2), m.group(3)
        if not value.strip():
            continue
        if quote == "`" and "${" in value:
            continue  # 동적으로 생성되는 템플릿 리터럴은 하드코딩된 값이 아님
        line_no = line_of(text, m.start())
        findings.append((
            CRITICAL, "하드코딩된 비밀번호/API 키",
            line_no,
            f"`{name}` 변수에 값이 코드에 직접 하드코딩되어 있습니다 (값: \"{truncate(value, 40)}\"). "
            "클라이언트 측 HTML/JS는 브라우저에서 소스 보기로 누구나 볼 수 있으므로, "
            "이런 값은 노출되어서는 안 됩니다.",
            truncate(line_text(lines, line_no)),
        ))


def check_inner_html_xss(text, lines, findings):
    for m in INNER_HTML_RE.finditer(text):
        target, op, rhs = m.group(1), m.group(2), m.group(3).strip().rstrip(";").strip()
        line_no = line_of(text, m.start())

        is_static_literal = False
        if len(rhs) >= 2 and rhs[0] in "\"'`" and rhs[-1] == rhs[0]:
            inner = rhs[1:-1]
            if rhs[0] == "`" and "${" in inner:
                is_static_literal = False
            elif rhs[0] in inner:
                is_static_literal = False  # 이스케이프되지 않은 따옴표 등 복잡한 표현식일 가능성
            else:
                is_static_literal = True

        if is_static_literal:
            continue  # 정적 문자열만 대입 -> 사용자 입력이 섞일 수 없음

        if SANITIZER_HINT_RE.search(rhs):
            severity = SUGGESTION
            note = (
                f"`{target}.innerHTML {op} {truncate(rhs, 40)}`에서 이스케이프/새니타이즈로 보이는 "
                "함수를 사용 중입니다. 실제로 모든 태그·속성을 안전하게 이스케이프하는지 확인하세요."
            )
        else:
            severity = CRITICAL
            note = (
                f"`{target}.innerHTML {op} {truncate(rhs, 40)}` — 사용자 입력(또는 변수)이 escape 없이 "
                "innerHTML에 그대로 들어갑니다. 값에 `<script>`나 이벤트 속성이 포함되면 XSS로 이어질 수 "
                "있습니다. `textContent`를 사용하거나, HTML이 꼭 필요하면 이스케이프 함수를 거치세요."
            )

        findings.append((severity, "XSS (innerHTML)", line_no, note, truncate(line_text(lines, line_no))))


def check_console_log_leak(text, lines, findings):
    for m in CONSOLE_RE.finditer(text):
        method, args = m.group(1), m.group(2)
        if not SENSITIVE_LOG_RE.search(args):
            continue
        line_no = line_of(text, m.start())
        findings.append((
            WARNING, "console.log 민감 정보 노출",
            line_no,
            f"`console.{method}(...)` 호출 인자에 비밀번호/토큰 등 민감한 값으로 보이는 내용이 포함되어 "
            "있습니다. 브라우저 개발자 도구 콘솔이나 로그 수집 서비스에 그대로 남을 수 있으므로 제거하거나 "
            "마스킹하세요.",
            truncate(line_text(lines, line_no)),
        ))


def check_http_external_request(text, lines, findings):
    for m in HTTP_URL_RE.finditer(text):
        url = m.group(1)
        host = url[len("http://"):].split("/", 1)[0].split(":", 1)[0]
        if host in LOCAL_HOSTS or host in NAMESPACE_HOSTS:
            continue
        if XMLNS_PREFIX_RE.search(text[max(0, m.start() - 20):m.start()]):
            continue  # xmlns="http://..." 같은 XML 네임스페이스 선언은 네트워크 요청이 아님

        line_no = line_of(text, m.start())
        snippet = line_text(lines, line_no)
        if SENSITIVE_LOG_RE.search(snippet):
            severity = CRITICAL
            note = (
                f"암호화되지 않은 `http://` 주소({truncate(url, 60)})로 요청하면서 같은 줄에 민감한 값으로 "
                "보이는 내용도 있습니다. 평문 전송 중 중간자 공격(MITM)으로 값이 노출될 수 있으니 반드시 "
                "https://로 바꾸세요."
            )
        else:
            severity = WARNING
            note = (
                f"암호화되지 않은 `http://` 주소({truncate(url, 60)})로 외부 요청을 보냅니다. 가능하면 "
                "https://를 사용해 전송 구간을 암호화하세요."
            )
        findings.append((severity, "외부 요청 (http://)", line_no, note, truncate(snippet)))


def check_file(path: Path) -> str:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()

    findings = []
    check_hardcoded_secrets(text, lines, findings)
    check_inner_html_xss(text, lines, findings)
    check_console_log_leak(text, lines, findings)
    check_http_external_request(text, lines, findings)

    order = {CRITICAL: 0, WARNING: 1, SUGGESTION: 2}
    findings.sort(key=lambda f: (order[f[0]], f[2]))

    return format_report(path, findings)


def format_report(file_path, findings):
    lines_out = [f"=== 보안 점검 결과: {file_path} ==="]
    grouped = {CRITICAL: [], WARNING: [], SUGGESTION: []}
    for severity, category, line_no, message, snippet in findings:
        grouped[severity].append((category, line_no, message, snippet))

    any_findings = False
    for severity in (CRITICAL, WARNING, SUGGESTION):
        items = grouped[severity]
        if not items:
            continue
        any_findings = True
        lines_out.append(f"\n{ICON[severity]} {severity} ({len(items)})")
        for category, line_no, message, snippet in items:
            lines_out.append(f"- [{category}] {file_path}:{line_no} — {message}")
            lines_out.append(f"    근거: `{snippet}`")

    if not any_findings:
        lines_out.append("\n검토 후보가 발견되지 않았습니다. 4가지 항목 모두 통과했습니다.")

    return "\n".join(lines_out)


def main(argv):
    targets = argv[1:]
    if not targets:
        print("사용법: python check_security.py <파일1> [파일2 ...]")
        return
    reports = []
    for target in targets:
        path = Path(target)
        if not path.exists():
            reports.append(f"=== 보안 점검 결과: {target} ===\n파일을 찾을 수 없습니다.")
            continue
        reports.append(check_file(path))
    print("\n\n".join(reports))


if __name__ == "__main__":
    main(sys.argv)
