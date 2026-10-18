# 품질 기준

| 영역 | 기준 | 검사 |
|---|---|---|
| 결정론 스크립트 | 공개 함수·하위 명령마다 테스트, 잘못된 입력은 상태를 바꾸지 않고 오류 JSON | `pytest tests/` |
| 받는 PC 호환 | 표준 라이브러리만, Python 3.9 문법, 한글·CRLF 경로 | `tests/test_params.py` · 3.9 로 `pytest` · `dev/smoke.py`(Windows 실기) |
| 의도 반영 | 같은 사건·다른 의도 초안이 E1–E8 을 통과(PRD §5.3) | `dev/e2e.py run` → `judge` |
| 인용 | 「확인됨」은 법제처 원문 존재(법령명·사건번호 정확 일치, 초안 선고일이 있으면 원문 선고일 일치)만(빅케이스에서만 찾은 것은 `external`), 미확인 판례에는 인용 판결 수 안내, 키 값은 출력·캐시에 남기지 않음 | `tests/test_cite.py` · `tests/test_lawapi.py` · `tests/test_casesearch.py` |
| 내장 스킬 | MCP·Cowork 경로·AskUserQuestion 없음, 안내한 명령 실존, 사용자 입력 JSON 을 셸 인자에 넣지 않음 | `tests/test_embedded_skills.py` |
| 사건메모 | 확인 토큰 없이는 쓰지 않음, CRLF 보존, casedb 형식 바이트 일치 | `tests/test_state_memo.py`(바이트 일치 계약은 데모 원본이 있는 PC 에서만 — `INTENT_BRIEF_DEMO_DIR`) |
| 매니페스트 | `validate --strict` 통과, 두 매니페스트 버전 일치 | `claude plugin validate --strict .` · `dev/verify_docs.py` |
| 문서 | 링크 유효, 검사 대상 31개(내장 SKILL.md·참조 문서 포함)·런타임 `.py` 머리말 경로 실존, AGENTS.md 120줄 이하, 계약 점검 기록 90일 이내(경고) | `dev/verify_docs.py`(pytest 가 함께 돌린다) |
| 공개 게시 안전 | 녹화·픽스처에 비밀·개인정보 형식 0, 기본 검사는 외부 주소로 나가지 않음, 런타임 송신 호스트 6개 고정 | `tests/test_publish_safety.py` · `dev/secret_scan.py` |
| 응답 형식 | 법제처·빅케이스 응답 형식 변경을 「미확인」으로 넘기지 않음(받는 PC), 녹화와 실서비스 구조 대조(개발 PC) | `tests/test_format_checks.py` · `dev/contract.py`(아래 절차) |

e2e 판정 기준값(E3 강한 표현 수, E6 길이비 1.3 등)은 `dev/e2e.py` 의 `judge_run`·`cmd_judge` 가 정본이다.

## 판 올림 절차

판 올림(매니페스트 버전 변경)은 이 절차를 거친 뒤에만 한다. CI 는 없다 — 개발 PC 에서 사람이 돌리고 아래 표에 1행을 남긴다.

1. Health Stack 5줄(AGENTS.md)을 돌린다. 셋째 줄(빅케이스)은 scrapling·keyring 이 있는 개발 PC 에서 25개 이상 통과·건너뜀 0 이어야 한다.
2. 내장 스킬 문서 생성 테스트(`generate.js`)가 건너뛰지 않게 개발 PC 에 `docx` 를 둔다: `npm install -g docx` 뒤 테스트는 `npm root -g` 를 `NODE_PATH` 로 쓴다(전역 설치만으로는 `require('docx')` 해석 경로에 없다).
3. 계약 점검은 발동 조건일 때만 — 마지막 점검 뒤 30일이 지났거나, 이번 판에서 `lawapi.py`·`bigcase.py`·`casesearch.py`·`tests/recorded/` 가 바뀌었을 때. 하루 1회 상한(집중 판 올림 기간에는 첫 판 올림만).
   - 법제처: `python3 dev/contract.py law` — 녹화 11개 요청 + 빈 법령 검색 1요청(12회, 간격 1초). 키는 작업 폴더의 저장 키.
   - 빅케이스: `uv run --no-project --with "scrapling[fetchers]>=0.4.11,<0.5" --with "keyring>=25,<26" python dev/contract.py bigcase` — 로그인돼 있을 때만, 데이터 명령 6개 1회씩(HTTP 10회 이하, 간격 2초 이상). 응답 본문은 남기지 않고 차이 경로만 낸다.
   - exit: 0 일치 · 1 구조 차이 · 3 키 없음 · 4 로그인 안 됨(건너뜀) · 6 HTTP 예산 소진(미완료).
4. uv inline 의존(`bigcase.py`·`discover.py`·`site-api/templates/client.py.tmpl`)의 상한을 올릴 때는 그 판으로 셋째 줄을 돌린다. 전이 의존(`curl_cffi`)은 상한 대신 lock 재검토 대상이다.
5. 아래 표에 1행을 더한다. 점검을 안 돈 판 올림은 두 exit 칸 `-`·비고 「발동 조건 아님」. `dev/verify_docs.py` 는 실제로 대조한 행(exit 0·1)의 가장 늦은 날짜가 90일을 넘으면 경고한다.

## 실패 처리 점검(스킬 14개 × 3종)

2026-10-18 각 SKILL.md(과 참조 문서)를 읽어 실패 3종의 처리 문장이 있는지 봤다. 「보강」은 그날 문장을 넣은 칸 — `tests/test_skill_meta.py` 「FR-23」이 문장 존재를 막는다. 스킬을 고칠 때 이 표를 함께 갱신한다.

| 스킬 | 외부 장애 | 키 없음 | 입력 자료 없음 |
|---|---|---|---|
| intent-brief | 있음 | 있음 | 있음 |
| case-search | 있음(`network_blocked` 보강) | 있음 | 보강 |
| certified-letter · complaint-drafter | 있음(law-lookup.md) | 있음(law-lookup.md) | 있음 |
| criminal-procedure-simulator | 있음 | 있음 | 있음 |
| criminal-settlement · fact-confirmation | 해당 없음 | 해당 없음 | 있음 |
| sentencing-predictor | 보강(양형위원회 조회 실패) | 있음 | 있음 |
| brainstorming-lawfirm | 있음 | 보강 | 보강 |
| review-contract | 보강(law-lookup.md) | 보강 | 있음 |
| triage-nda | 보강(law-lookup.md) | 보강 | 보강 |
| independent-review | 해당 없음 | 해당 없음 | 보강 |
| litigation-calc | 해당 없음 | 해당 없음 | 있음 |
| site-api | 보강(접속 실패·타임아웃) | 있음 | 보강 |

공통: `references/law-lookup.md` 오류 목록에 `network_blocked`(Codex 샌드박스 차단 — 장애 아님)를 넣었다.

## 측정 기록

- 2026-10-18 빅케이스 사건번호 띄어쓰기 변형 재조회: 공개 사건번호 20개(대법원 10·하급심 10, 로컬 녹화에서 고름), HTTP 37회. 미확인 17 → 17(감소 0), 잘못 확인 0 — 효과가 없어 넣지 않는다. 법원명 약칭 변형은 번호 검색이라 해당 없음.

## 판 올림 기록

| 날짜 | 판 | Health Stack | 법제처 점검 exit | 빅케이스 점검 exit | 비고 |
|---|---|---|---|---|---|
| 2026-10-18 | 0.8.0 | 5줄 통과(전체 521·3.9 521 passed, 빅케이스 66 passed, validate 통과, verify_docs 오류 0) | 0 | 0 | 법제처 12요청 차이 0 · 빅케이스 녹화 HTTP 7·점검 HTTP 6 · 같은 날 응답 키 목록 확정(response-keys.json) |
