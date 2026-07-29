---
name: security-check
description: This skill should be used when the user asks to "보안 점검", "security check", or requests a review of an HTML/JS file for hardcoded secrets, XSS via innerHTML, sensitive console.log output, or insecure http:// requests.
version: 0.1.0
---

# Security Check

HTML/JS 파일을 다음 4가지 보안 관점으로 점검하고, 발견된 문제를 심각도별로 분류해 파일:라인 근거와 함께 보고한다.

1. **하드코딩된 비밀번호·API 키** — 코드에 비밀번호/토큰/키 값이 문자열 그대로 박혀 있는지
2. **XSS (innerHTML)** — escape 없이 사용자 입력(또는 변수)을 `innerHTML`에 대입하는지
3. **console.log 민감 정보 노출** — 비밀번호·토큰 등 민감한 값을 콘솔에 그대로 출력하는지
4. **http:// 외부 요청** — 암호화되지 않은 `http://` 주소로 요청을 보내는지

## 사용 방법

1. 점검 대상 HTML/JS 파일을 확인한다. 사용자가 파일을 지정하지 않으면 대화 맥락에서 방금 다룬 파일, 없으면 프로젝트 루트의 모든 `*.html`을 대상으로 삼는다. 여러 파일은 경로를 공백으로 나열해 한 번에 전달한다.
2. 점검 스크립트를 실행한다:

   ```bash
   python .claude/skills/security-check/scripts/check_security.py <파일1> [파일2 ...]
   ```

3. **스크립트 출력은 정규식 기반 "검토 후보" 목록이며 그대로 신뢰하지 않는다.** 반드시 각 항목이 가리키는 파일:라인을 직접 읽고, 실제로 문제인지 판단한 뒤 최종 보고서에 포함한다. 특히 아래 유형은 오탐일 가능성이 높으니 걸러낸다:
   - "하드코딩된 비밀번호/API 키" 후보 중 값이 실제 비밀값이 아니라 `localStorage` 키 이름, 변수 설명용 라벨, 테스트/placeholder 문자열인 경우 (예: `PASSWORD_HASH_KEY = 'secretMemoPasswordHash'`처럼 변수명에 password가 들어가지만 실제로는 저장소 키 이름일 뿐 비밀값이 아닌 경우)
   - "XSS (innerHTML)" 후보 중 대입되는 값이 실제로는 서버/개발자가 완전히 통제하는 상수이거나, 이미 신뢰할 수 있는 방식으로 이스케이프된 경우
   - "http://" 후보 중 실제 네트워크 요청이 아니라 문서/네임스페이스 URI, 주석, 예시 텍스트인 경우
4. 오탐을 제외하고 남은 항목을 아래 형식으로 정리해 사용자에게 전달한다:

   - 🔴 **심각** — 실제로 악용 가능하거나 즉시 정보가 노출되는 문제 (하드코딩된 실제 비밀값, escape 없는 innerHTML에 사용자 입력이 들어가는 실제 XSS 경로, 민감한 값이 그대로 http://로 전송되는 경우)
   - 🟡 **주의** — 위험하지만 조건부이거나 영향이 제한적인 문제 (console.log의 민감 정보 노출, 일반 http:// 요청, 이스케이프 함수를 쓰고 있지만 커버리지를 확인해야 하는 innerHTML)
   - 🟢 **제안** — 당장 취약점은 아니지만 개선하면 좋은 항목
5. 각 항목은 반드시 `파일:라인` 형태의 근거와 함께 제시하고, 어떻게 고치면 되는지 한두 문장으로 덧붙인다 (예: `innerHTML` → `textContent`로 교체, 비밀값은 서버 측 환경 변수/백엔드로 이동, `console.log` 제거, `http://` → `https://`).
6. 검토 후보가 하나도 없거나 전부 오탐으로 걸러졌다면 "4가지 항목 모두 통과했습니다"라고 전달한다.

## 참고 사항

- 스크립트는 Python 3 표준 라이브러리만 사용하므로 추가 설치 없이 바로 실행 가능하다.
- 정규식 기반 휴리스틱이라 여러 줄에 걸친 대입문이나 복잡한 표현식은 놓칠 수 있다. 스크립트 결과와 별개로, 파일이 크지 않다면 `<script>` 블록 전체를 직접 훑어보며 스크립트가 놓쳤을 수 있는 패턴(특히 `innerHTML`, `eval(`, 인라인 이벤트 핸들러)을 보충 점검한다.
- `http://` 점검은 `xmlns="http://www.w3.org/..."` 같은 XML 네임스페이스 선언과 `localhost`/`127.0.0.1`은 자동으로 제외한다.
- 이 스킬은 클라이언트 사이드(브라우저에서 실행되는) HTML/JS를 대상으로 한다 — 서버 사이드 코드의 SQL 인젝션, 인증/인가 로직 등은 점검 범위 밖이다.
