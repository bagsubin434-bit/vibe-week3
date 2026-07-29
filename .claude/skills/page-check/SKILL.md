---
name: page-check
description: This skill should be used when the user asks to "페이지 점검", "page check", "HTML 점검해줘", "이 페이지 문제 없는지 봐줘", or requests a review of an HTML file for title/broken links/image alt/mobile viewport/UTF-8 encoding issues.
version: 0.1.0
---

# Page Check

HTML 페이지를 다음 5가지 관점으로 점검하고, 발견된 문제를 심각도별로 분류해 보고한다.

1. **title** — `<title>` 태그 존재 및 내용 여부
2. **깨진 내부 링크** — `href`/`src`가 가리키는 로컬 파일이 실제로 존재하는지, 앵커 링크(`#id`)가 페이지 내 `id`와 매칭되는지
3. **이미지 alt** — `<img>`의 `alt` 속성 존재 여부와 빈 값 여부
4. **모바일 viewport** — `<meta name="viewport" ...>` 존재 및 `width=device-width` 포함 여부
5. **한글 인코딩(UTF-8)** — 파일이 실제로 UTF-8로 저장되어 있는지, `<meta charset="UTF-8">`가 있는지

## 사용 방법

1. 점검 대상 HTML 파일을 확인한다. 사용자가 파일을 지정하지 않으면 프로젝트 루트의 `index.html`을 기본 대상으로 삼는다. 여러 파일을 점검해야 하면 경로를 공백으로 나열해 한 번에 전달한다.
2. 점검 스크립트를 실행한다:

   ```bash
   python .claude/skills/page-check/scripts/check_page.py <파일1> [파일2 ...]
   ```

3. 스크립트가 출력한 결과를 그대로(또는 한국어 문장으로 자연스럽게 다듬어) 사용자에게 전달한다. 출력은 이미 다음 형식으로 심각도별로 그룹핑되어 있다:

   - 🔴 **심각** — 페이지의 핵심 기능·접근성·렌더링을 실제로 깨뜨리는 문제 (title 없음, viewport 없음, alt 속성 자체가 없음, 내부 링크 대상 파일 없음, UTF-8이 아님/charset 메타 없음)
   - 🟡 **주의** — 문제가 될 수 있지만 확정적이지 않은 항목 (viewport content 값 이상, 앵커가 가리키는 id를 못 찾음, charset이 UTF-8이 아니지만 한글이 없음)
   - 🟢 **제안** — 개선하면 좋지만 당장 깨지지는 않는 항목 (alt="" 사용 — 장식용 이미지가 맞는지 확인 필요)

4. 발견된 항목이 있으면 항목별로 어떤 코드를 어떻게 고치면 되는지 한두 문장으로 덧붙여 설명한다 (예: `<title>` 추가 위치, viewport 메타 태그 예시 코드).
5. 문제가 하나도 없으면 스크립트가 "문제가 발견되지 않았습니다" 메시지를 출력하므로, 이를 그대로 전달하면 된다.

## 참고 사항

- 스크립트는 외부 링크(`http(s)://`, `mailto:`, `tel:`, `data:` 등)는 검사하지 않는다. 로컬 상대 경로만 존재 여부를 확인한다.
- `<img>`뿐 아니라 `<a href>`, `<link href>`, `<script src>`도 내부 링크 점검 대상에 포함된다.
- 파일이 UTF-8이 아닌 인코딩(CP949/EUC-KR 등)으로 저장되어 있으면 스크립트 자체가 깨진 문자를 감지해 🔴로 보고한다.
- Python 3 표준 라이브러리만 사용하므로 추가 설치 없이 바로 실행 가능하다.
