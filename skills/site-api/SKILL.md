---
name: site-api
description: 웹사이트 URL 하나로 그 사이트의 API 를 찾아 Scrapling 클라이언트(.py)를 만든다 — 빅케이스 클라이언트(bigcase.py)와 같은 틀(키체인 자격증명·토큰 재사용·호스트 고정·요청 간격). 판례·법령·등기·공고 사이트를 브라우저 없이 조회하고 싶을 때. 「이 사이트 API 만들어줘」, 「URL 로 API 클라이언트」, 「이 사이트도 빅케이스처럼」, 「site-api」 요청에 쓴다.
allowed-tools: Bash(uv run:*), Bash(python3:*), Bash(python:*), Bash(py:*)
---

# site-api — URL → API 클라이언트

> Codex 에서는 셸에 `${CLAUDE_PLUGIN_ROOT}` 가 없다 — 이 문서를 연 경로에서 `.codex-plugin` 폴더가 있는 상위 폴더(플러그인 루트)를 찾아 그 절대경로로 바꿔 쓴다. Claude Code 에서는 그대로 둔다.

`$A` = `${CLAUDE_PLUGIN_ROOT}/skills/site-api/scripts`. 발굴(`discover.py`)과 만든 클라이언트는 uv 로 실행하며 Scrapling 을 uv 가 붙인다. 추출·생성(`extract.py`·`scaffold.py`)은 표준 라이브러리만 쓴다.

## 0. 이용 범위 — 먼저 확인

- 대상 사이트 URL 이 없으면 한 번 묻는다.
- 그 사이트의 이용약관이 자동화된 조회를 금지하는지 변호사에게 확인을 받는다(금지하면 만들지 않는다). `discover.py` 는 robots.txt 가 일반(`*`) 또는 AI 에이전트(`Claude-User`) 접근을 막으면 멈춘다 — 우회하지 않는다. 막힌 사이트는 만들지 않고 변호사에게 그 사실과 대안(공식 API·제휴 문의·빅케이스·법제처)을 알린다.
- 본인(사무소) 계정으로, 사람이 화면에서 찾는 정도의 빈도로만 쓴다. 만든 클라이언트는 요청 사이에 1초 이상 쉰다. 대량 수집·재배포·다른 사람 계정 사용에는 쓰지 않는다.
- 아이디·비밀번호는 채팅으로 받지 않는다. 만든 클라이언트의 `setup` 이 입력 창(터미널이면 숨김 입력, macOS·Windows는 OS 창 — `--prompt` 방식과 같다)으로 받아 키체인에 저장한다.
- uv 가 없으면 설치를 안내한다(macOS `curl -LsSf https://astral.sh/uv/install.sh | sh`, Windows `winget install astral-sh.uv`). `--cdp` 발굴이나 동적 페이지에는 브라우저 엔진이 필요하다: `uv tool run --from "scrapling[fetchers]" scrapling install` 를 한 번 실행한다.

## 1. 발굴

```
uv run "$A/discover.py" "<URL>" --out <작업 폴더>/spec
```

접속 실패·타임아웃이 나면 그대로 알리고 반복 호출하지 않는다. 정적 분석으로 페이지와 같은 호스트 스크립트에서 API 경로 후보(`endpoints`)·로그인 후보(`auth_candidates`)·GraphQL 작업명·HTML 에 심은 데이터(`inline_state`)를 찾아 `spec/endpoints.json` 에 쓴다.

후보가 비었거나 `inline_state` 만 나오면(SPA·서버 렌더링) 실제 네트워크를 잡는다. 사람이 원격 디버깅 Chrome 을 직접 띄우게 안내한다(Claude Code 는 입력 칸에 `!` 를 붙여 실행, Codex 는 사람이 자기 터미널에서 실행):
```
# macOS
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --remote-debugging-port=9222 --user-data-dir="$HOME/.cache/chrome-cdp"
# Windows (PowerShell) — Chrome 이 다른 곳에 있으면 "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
& "$env:ProgramFiles\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="$env:LOCALAPPDATA\chrome-cdp"
```
그 창에서 사람이 로그인·검색을 한 뒤:
```
uv run "$A/discover.py" "<URL>" --out <작업 폴더>/spec --cdp http://localhost:9222 --scroll 3
```
요청 본문·응답은 값 대신 JSON 키 구조만 저장하고 인증 헤더 값은 남기지 않는다. 헤드리스 브라우저는 쓰지 않는다(봇 탐지 사이트가 데이터 요청을 안 보낸다).

## 2. 스펙 정리

`spec/endpoints.json` 상위 후보에서 데이터를 담은 엔드포인트(검색·상세)와 로그인 엔드포인트를 고르고 근거(응답 구조·쪽 넘김 인자)와 함께 보여 준다. `<작업 폴더>/spec/<이름>.md` 에 정리한다: API 기준 주소, 인증 방식(Bearer 토큰 / 쿠키 / 없음), 로그인 경로와 아이디·비밀번호 필드 이름, 토큰 위치(예: `data.accessToken`), 엔드포인트별 메서드·인자·쪽 넘김·응답 필드.

## 3. 클라이언트 만들기

```
python3 "$A/scaffold.py" <이름> https://<호스트>/<API 경로> --auth bearer-login --login-path /auth/login \
  --id-field email --pw-field password --token-field accessToken --title "<사이트 이름>"
```

- `--auth`: `bearer-login`(로그인 응답의 토큰을 Bearer 로) · `cookie-login`(로그인 응답 쿠키를 저장해 보냄) · `none`.
- 결과 파일은 작업 폴더(macOS `~/.intent-brief/site-api/`, Windows `%LOCALAPPDATA%\intent-brief\site-api\`)에 생긴다. 같은 이름이 있으면 덮지 않고 `_2` 를 붙인다.
- 만든 파일은 API 호스트 밖 절대 주소로는 요청하지 않는다(인증 정보가 새지 않게). 자격증명은 키체인 서비스 `site-api-<이름>`, 세션은 `site-api/<이름>/session.json`(0600).
- 2의 엔드포인트마다 클라이언트에 명령을 더할 때는 bigcase.py(`${CLAUDE_PLUGIN_ROOT}/skills/case-search/scripts/bigcase.py`)의 `search`·`case` 처럼 메서드 하나 + 하위 명령 하나로 더하고, 출력은 요약 JSON 으로 한다.

## 4. 시험

```
uv run <만든 파일> status
uv run <만든 파일> setup        # 로그인이 필요한 사이트만 — 입력 창
uv run <만든 파일> get <경로> --param q=검색어
```
한 쪽만 조회해 필드·건수가 화면과 맞는지 사람에게 보여 준다. 맞지 않으면 2로 돌아간다. 401·403 이 반복되면 로그인 방식(토큰 위치·쿠키)을 다시 확인한다 — 우회 기법(캡차 풀기·차단 회피)은 쓰지 않는다.
