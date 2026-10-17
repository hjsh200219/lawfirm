# 기술 부채

| ID | 내용 | 영향 | 해소 조건 |
|---|---|---|---|
| TD-001 | 생성 docx 를 Word·한글로 연 확인이 없다(LibreOffice → PDF 렌더로만 확인, 2026-10-14) | 서식이 Word·한글에서 다르게 보일 수 있음 | Word 또는 한글이 있는 PC 에서 F1 산출물을 열어 확인 |
| TD-003 | 재생 기록(`replay.py`)의 질문 `options` 가 빈 배열이다(재생은 답 파일로 진행하므로 구조상 비어 있음) | 선택지 품질은 실제 대화 기록으로만 볼 수 있음 | 실제 대화 기록을 재생 입력으로 쓰는 경로가 생기면 |
| TD-005 | 기본값·의도 목록은 사용 통계 없이 정했다 | 실제 사무소 사용과 어긋날 수 있음 | 공개(2026-10-14) 4주 뒤인 2026-11-11 이후 `intent.py stats` 로 판단(PRD 의 4주 점검 결정) |
| TD-006 | Cowork 미지원 | Cowork 사용자는 쓸 수 없음 | 작업 폴더·스크립트 실행 경로를 Cowork 에서 확인 |
| TD-008 | 내장 스킬 3개(certified-letter·complaint-drafter·fact-confirmation)가 외부 「docx 스킬」·`npm install -g docx` 를 전제하고, `generate.js` 에 테스트가 없다(2026-10-15 GC) | Node·docx 가 없는 PC 에서 문서 생성 실패 | intent-brief `render_docx.py` 로 옮기거나 Node 의존을 설치 안내·실행 테스트로 묶는다 |
| TD-009 | 공백 정규화(`_nows`·`_norm_no`·casesearch 인라인)와 키 검증 사건번호·오류 매핑이 모듈마다 중복(2026-10-15 GC F4·F5) | 규칙이 한쪽만 바뀔 수 있음 | `_paths` 로 모으고 `lawapi` 의 검증 함수 하나를 `cite_check ping` 이 쓰게 |
| TD-010 | `dev/verify_docs.py` 가 루트 `references/`·내장 스킬 6개 SKILL.md·`.py` 머리말의 경로를 검사하지 않는다(2026-10-15 GC; 0.4.0 에서 `skills/case-search/SKILL.md`·`commands/case-search-setup.md`·`docs/case-search/bigcase-api.md` 는 추가) | 내장 스킬 문서·스크립트 docstring 의 낡은 경로를 테스트가 못 잡음(0.4.0 GC 때 `bigcase.py` docstring 경로가 이렇게 빠짐) | 검사 대상에 추가 |
| TD-011 | 빅케이스 테스트(`tests/case_search/`)는 scrapling·keyring 이 없는 기본 명령에서 통째로 skipped 되고, `bigcase.py` 줄 커버리지는 51%(2026-10-15 0.4.0 GC) | 기본 Health Stack 만 돌리면 빅케이스 회귀를 못 봄 | 로컬 GC 스크립트(`/sh:harness-setup --infra`)가 셋째 줄까지 돌리게 하고 setup·로그인 경로 테스트 추가 |
| TD-012 | 빅케이스 API 계약은 2026-10-15 수동 실측뿐이고 녹화 응답이 없다(비공식 API) | 빅케이스가 응답 형식을 바꾸면 테스트는 통과하고 실사용만 깨짐 | 실계정 정보를 가린 녹화 응답으로 계약 테스트 |
| TD-013 | `litigation-calc` 공휴일 표는 2024–2028 이다(2029년 특일정보 미발표, 2026-10-15) | 2029년 이후 만료일은 토·일만 반영하고 경고를 낸다(임시공휴일은 `--holiday`) | 한국천문연구원이 2029년 자료를 내면(보통 전년도 중반) `dev/holidays_kasi.py 2024 2029` 로 다시 만들고 `test_holiday_table_shape` 범위를 올린다 |
| TD-014 | uv inline 의존성이 하한만 있다(`scrapling[fetchers]>=0.4.11`, `keyring>=25`)·lock 파일 없음(GC Run #2 P10 4점) | Scrapling 새 판이 API 를 바꾸면 빅케이스·site-api 가 받는 PC 에서 깨질 수 있음 | 실측 판(0.4.15)으로 상한을 둘지, 판 올림 때 빅케이스 테스트(Health Stack 셋째 줄)를 돌리는 절차로 둘지 결정 |
| TD-015 | e2e E4(F2B 예비적 주장)는 `sec.alt_claim` 본문에 「공제」 글자가 있는지만 본다 — 소제목 줄은 본문에서 빠진다. 2026-10-18 재실행(HEAD `98c31b7`, sonnet)에서 F2B_r2 는 예비적 주장에 「원금 4,000만원 한도」「1,000만원 변제로 소멸」을 쓰고 「공제」는 소제목(`### [issue:2] 변제 항변 — 공제의 범위`)에만 둬 E4 2/3 실패로 셌다(자체 검사 `check_final` 은 1.0) | 같은 뜻을 다른 말로 쓴 초안을 회귀로 잘못 셀 수 있음 — 반대로 기준을 넓히면 진짜 누락을 놓칠 수 있음 | 다음 e2e 전에 E4 기준(소제목 포함·동의어 허용)을 정하고 그 기준으로 테스트를 먼저 쓴다 — 결과를 본 뒤 기준을 바꾸는 사후 조정이라 이번 판정은 그대로 둔다 |
