---
description: 법제처 Open API 키(OC)와(선택) 미국 판례 CourtListener 토큰을 입력 창으로 받아 저장한다 — 키를 채팅으로 받지 않는다
argument-hint: "[us]"
allowed-tools: Bash(python3:*), Bash(python:*), Bash(py:*)
---

# 법제처·해외 판례 키 등록

> Codex 에서는 셸에 `${CLAUDE_PLUGIN_ROOT}` 가 없다 — 이 문서를 연 경로에서 `.codex-plugin` 폴더가 있는 상위 폴더(플러그인 루트)를 찾아 그 절대경로로 바꿔 쓴다. Claude Code 에서는 그대로 둔다.

키는 사용자가 **입력 창**(터미널에서 실행하면 프롬프트)에 직접 넣는다. 채팅으로 달라고 하지 않는다. `$PY` 는 Python 3.9 이상(`python3` → `python` → `py -3`). `$PY` 는 셸 변수가 아니라 자리표시다 — 명령마다 찾은 실행기(`python3`·`py -3` 등)를 따옴표로 묶지 않고 그대로 적는다(`"py -3"` 처럼 묶으면 실행되지 않는다).

## 1. 법제처 OC 키

키가 아직 없다면 먼저 안내한다: https://open.law.go.kr 회원가입 → OPEN API 사용 신청(법령·판례) → 받은 OC 값. 신청 때 이 PC 의 IP 주소 등록을 요구할 수 있다.

실행 직전에 한 줄만 말한다:
> 화면에 「법제처 Open API」 입력 창이 뜨면 OC 값을 넣어 주세요. 값은 이 대화에 남지 않고 이 PC 에만 저장됩니다.

```bash
"$PY" "${CLAUDE_PLUGIN_ROOT}/skills/intent-brief/scripts/lawapi.py" key set --prompt
```

Bash 도구 `timeout` 은 **600000**(10분) — 사람이 입력하는 동안 끊기면 안 된다. 키 오류 검사를 통과해야 저장한다(판례 1건 조회 — 판례 검색 형식이 바뀐 날은 「확인 안 됨」으로 저장). 키는 작업 폴더의 config.json 에 저장합니다(macOS `~/.intent-brief/config.json` 은 이 PC 사용자만 읽게 권한 0600, Windows `%LOCALAPPDATA%\intent-brief\config.json` 은 파일 권한을 따로 바꾸지 않음). 키 값은 출력·캐시·오류 문구에 쓰지 않습니다.

결과에 따라:
- `ok: true`·`checked: true` → 「저장했습니다」. 값은 다시 출력하지 않는다.
- `ok: true`·`checked: false`(`warning` 있음) → 키 오류 검사는 통과해 저장했지만 판례 검색 응답 형식이 바뀌어 확인하지 못한 것(「확인 안 됨」). 그대로 알리고 나중에 `cite_check.py ping` 으로 다시 확인하게 한다.
- `key_invalid` → 키가 틀렸거나 이 PC 의 IP 가 법제처에 등록되지 않은 것. 그대로 알리고 open.law.go.kr 에서 IP 를 확인하게 한다.
- `format_changed`(저장 안 함) → 법제처가 JSON 이 아닌 응답(점검 화면 등)을 줘 키를 검증하지 못한 것. `--no-check` 로 저장하고 나중에 `cite_check.py ping` 으로 확인할 수 있다. `guide` 의 업데이트·신고 안내를 그대로 전한다.
- `outage` → 법제처 장애로 검증하지 못한 것. `--no-check` 를 붙여 다시 받아 저장하고, 나중에 `cite_check.py ping` 으로 확인한다.
- `network_blocked` 면 Codex 샌드박스가 네트워크를 막은 것이다(법제처 장애가 아니다) — `--no-check` 나 장애 태그로 넘기지 말고 네트워크 허용(권한 상승)으로 같은 명령을 다시 실행한다.
- 「입력을 취소했습니다」 → 저장하지 않았다고 알린다.
- 「입력 창을 띄우지 못했습니다(…)」 → 취소가 아니다. Codex 샌드박스면 권한 상승으로 같은 명령을 다시 실행하고, 그래도 안 되면 아래처럼 자기 터미널에서 실행하게 한다.
- 「입력 창을 띄울 수 없습니다」(원격 접속·리눅스 등) → 사용자가 **자기 터미널에서** 위 명령을 직접 실행하게 안내한다(경로는 실제 값으로 풀어서 보여 준다). 그것도 안 되고 사용자가 채팅에 값을 직접 적어 준 경우에만 `printf '%s\n' '<OC>' | "$PY" "…/lawapi.py" key set --stdin` 으로 저장하고, 그 값을 다른 곳에 옮겨 적지 않는다.

## 2. CourtListener 토큰 (인자가 `us` 이거나, 미국 판결문 본문이 필요할 때만)

미국 판례 검색은 토큰 없이 된다. 판결문 본문(`foreigncase.py us-opinion`)만 토큰이 필요하다 — https://www.courtlistener.com 무료 가입 → 프로필의 API 토큰.

> 화면에 「CourtListener」 입력 창이 뜨면 API 토큰을 넣어 주세요. 입력값은 가려지고 이 PC 에만 저장됩니다.

```bash
"$PY" "${CLAUDE_PLUGIN_ROOT}/skills/case-search/scripts/foreigncase.py" key set us --prompt
```

저장 위치는 `~/.case-search/foreign.json`(macOS·Linux 는 이 PC 사용자만 읽게 권한 0600, Windows 는 파일 권한을 따로 바꾸지 않음). 확인은 `foreigncase.py key status`(값은 출력하지 않음).
