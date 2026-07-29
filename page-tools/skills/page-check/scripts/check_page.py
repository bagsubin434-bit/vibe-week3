#!/usr/bin/env python3
"""HTML 페이지를 5가지 관점(title, 내부 링크, img alt, viewport, UTF-8 인코딩)으로 점검한다.

사용법:
    python check_page.py <html-file> [<html-file> ...]

인자를 생략하면 현재 디렉터리의 index.html을 점검한다.
"""

import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

CRITICAL = "심각"
WARNING = "주의"
SUGGESTION = "제안"

ICON = {CRITICAL: "\U0001F534", WARNING: "\U0001F7E1", SUGGESTION: "\U0001F7E2"}

EXTERNAL_SCHEMES = {"http", "https", "mailto", "tel", "data", "javascript", "ftp"}

HANGUL_RE = re.compile(r"[가-힣]")


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = None
        self._in_title = False
        self.meta_tags = []
        self.img_tags = []
        self.link_srcs = []  # (attr_name, value, tag) for href/src on a/link/script/img
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        if "id" in attr_dict and attr_dict["id"]:
            self.ids.add(attr_dict["id"])

        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            self.meta_tags.append(attr_dict)
        elif tag == "img":
            self.img_tags.append(attr_dict)

        if tag in ("a", "link") and "href" in attr_dict:
            self.link_srcs.append((tag, "href", attr_dict["href"]))
        if tag in ("script", "img") and "src" in attr_dict:
            self.link_srcs.append((tag, "src", attr_dict["src"]))

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title = (self.title or "") + data


def load_bytes(path: Path):
    return path.read_bytes()


def check_encoding(raw_bytes, findings):
    try:
        text = raw_bytes.decode("utf-8")
        is_utf8 = True
    except UnicodeDecodeError:
        text = raw_bytes.decode("utf-8", errors="replace")
        is_utf8 = False

    if not is_utf8:
        findings.append((
            CRITICAL, "인코딩",
            "파일이 유효한 UTF-8로 저장되어 있지 않습니다. 한글이 깨져 보일 수 있습니다 "
            "(에디터에서 '인코딩: UTF-8'로 다시 저장하세요).",
        ))

    return text


def check_charset_meta(meta_tags, has_hangul, findings):
    charset_value = None
    for meta in meta_tags:
        if "charset" in meta:
            charset_value = meta["charset"]
            break
        http_equiv = meta.get("http-equiv", "").lower()
        if http_equiv == "content-type" and "content" in meta:
            m = re.search(r"charset=([\w-]+)", meta["content"], re.IGNORECASE)
            if m:
                charset_value = m.group(1)
                break

    if charset_value is None:
        findings.append((
            CRITICAL, "인코딩",
            "<meta charset=\"UTF-8\">가 없습니다. 브라우저가 한글을 잘못된 인코딩으로 "
            "해석해 깨진 글자로 표시할 수 있습니다.",
        ))
    elif charset_value.strip().lower() not in ("utf-8", "utf8"):
        severity = CRITICAL if has_hangul else WARNING
        findings.append((
            severity, "인코딩",
            f"charset이 '{charset_value}'로 설정되어 있습니다. UTF-8을 사용하는 것을 권장합니다.",
        ))


def check_title(title, findings):
    if title is None:
        findings.append((CRITICAL, "title", "<title> 태그가 없습니다. 브라우저 탭과 검색 결과에 페이지 제목이 표시되지 않습니다."))
    elif not title.strip():
        findings.append((WARNING, "title", "<title> 태그는 있지만 내용이 비어 있습니다."))


def check_viewport(meta_tags, findings):
    for meta in meta_tags:
        if meta.get("name", "").lower() == "viewport":
            content = meta.get("content", "")
            if "width=device-width" not in content.replace(" ", ""):
                findings.append((
                    WARNING, "viewport",
                    f"viewport 메타 태그는 있지만 내용이 비정상적입니다 (content=\"{content}\"). "
                    "'width=device-width, initial-scale=1' 형태를 권장합니다.",
                ))
            return
    findings.append((
        CRITICAL, "viewport",
        "모바일 viewport 메타 태그(<meta name=\"viewport\" content=\"width=device-width, "
        "initial-scale=1\">)가 없습니다. 모바일에서 페이지가 축소되어 보일 수 있습니다.",
    ))


def truncate(value, limit=60):
    return value if len(value) <= limit else value[:limit] + "..."


def check_img_alt(img_tags, findings):
    for idx, img in enumerate(img_tags, start=1):
        src = truncate(img.get("src", "(src 없음)"))
        if "alt" not in img:
            findings.append((
                CRITICAL, "alt",
                f"{idx}번째 <img> (src=\"{src}\")에 alt 속성이 없습니다. 스크린 리더 사용자가 "
                "이미지 내용을 알 수 없습니다.",
            ))
        elif img["alt"].strip() == "":
            findings.append((
                SUGGESTION, "alt",
                f"{idx}번째 <img> (src=\"{src}\")의 alt=\"\"는 장식용 이미지에만 써야 합니다. "
                "의미 있는 이미지라면 내용을 설명하는 alt 텍스트를 추가하세요.",
            ))


def check_links(link_srcs, ids, base_dir, findings):
    seen = set()
    for tag, attr, raw_value in link_srcs:
        value = raw_value.strip()
        if not value or value in seen:
            continue
        seen.add(value)

        parts = urlsplit(value)

        if parts.scheme.lower() in EXTERNAL_SCHEMES:
            continue  # 외부 링크는 점검 범위 밖

        if not parts.path:
            # '#id' 형태의 순수 앵커 링크
            fragment = parts.fragment
            if fragment and fragment not in ids:
                findings.append((
                    WARNING, "링크",
                    f"<{tag} {attr}=\"{raw_value}\">가 가리키는 id=\"{fragment}\" 요소를 "
                    "페이지 안에서 찾을 수 없습니다.",
                ))
            continue

        target = (base_dir / parts.path).resolve()
        if not target.exists():
            findings.append((
                CRITICAL, "링크",
                f"<{tag} {attr}=\"{raw_value}\">가 가리키는 파일을 찾을 수 없습니다 "
                f"(확인 경로: {target}).",
            ))
        elif parts.fragment:
            # 다른 HTML 파일 내부의 id는 확인하지 않고, 존재만 확인했음을 알림 없이 통과
            pass


def format_report(file_path, findings):
    lines = [f"=== 페이지 점검 결과: {file_path} ==="]
    grouped = {CRITICAL: [], WARNING: [], SUGGESTION: []}
    for severity, category, message in findings:
        grouped[severity].append((category, message))

    any_findings = False
    for severity in (CRITICAL, WARNING, SUGGESTION):
        items = grouped[severity]
        if not items:
            continue
        any_findings = True
        lines.append(f"\n{ICON[severity]} {severity} ({len(items)})")
        for category, message in items:
            lines.append(f"- [{category}] {message}")

    if not any_findings:
        lines.append("\n문제가 발견되지 않았습니다. 5가지 항목 모두 통과했습니다.")

    return "\n".join(lines)


def check_file(path: Path) -> str:
    raw_bytes = load_bytes(path)
    findings = []

    text = check_encoding(raw_bytes, findings)
    has_hangul = bool(HANGUL_RE.search(text))

    parser = PageParser()
    parser.feed(text)

    check_title(parser.title, findings)
    check_viewport(parser.meta_tags, findings)
    check_charset_meta(parser.meta_tags, has_hangul, findings)
    check_img_alt(parser.img_tags, findings)
    check_links(parser.link_srcs, parser.ids, path.parent, findings)

    order = {CRITICAL: 0, WARNING: 1, SUGGESTION: 2}
    findings.sort(key=lambda f: order[f[0]])

    return format_report(path, findings)


def main(argv):
    targets = argv[1:] or ["index.html"]
    reports = []
    for target in targets:
        path = Path(target)
        if not path.exists():
            reports.append(f"=== 페이지 점검 결과: {target} ===\n파일을 찾을 수 없습니다.")
            continue
        reports.append(check_file(path))
    print("\n\n".join(reports))


if __name__ == "__main__":
    main(sys.argv)
