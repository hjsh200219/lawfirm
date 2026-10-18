# ARCHITECTURE — lawfirm

## 흐름

```
변호사 요청 → SKILL.md(모델) ─┬─ state.py   인터뷰 상태 저장·재개·purge
                              ├─ score.py   결정 축 4개 모호도 채점 → 다음 질문
                              ├─ intent.py  의도 검증·resolve → design.json · stats
                              ├─ memo.py    사건메모 읽기·diff 미리보기·확인 토큰 반영
                              ├─ (모델이 draft.md 작성)
                              ├─ check_draft.py  design.json 준수 검사
                              ├─ cite_check.py   조문·판례를 법제처 원문과 정확 일치 대조(lawapi.py)
                              │                  법제처에 없는 판례는 빅케이스 1회(casesearch.py → uv run skills/case-search/scripts/bigcase.py, 로그인 때만)
                              └─ render_docx.py  초안·의도대응표 .docx

판례·법령 요청 → skills/case-search/SKILL.md ─┬─ lawapi.py <명령>            법제처 법령·조문·판례·헌재·법령해석례
                                             ├─ uv run bigcase.py <명령>   빅케이스(계정 있을 때) 전문·유사 판례·결정례
                                             └─ foreigncase.py <명령>      미국 CourtListener·독일 OpenLegalData
/lawfirm:case-search-setup ── uv run bigcase.py setup        빅케이스 자격증명(OS 입력 창 → 키체인)
/lawfirm:law-key-setup ────── lawapi.py key set --prompt     법제처 OC(입력 창) · foreigncase.py key set us --prompt
```

모델이 판단할 일(인터뷰 문장, 초안 본문)과 결정론으로 끝낼 일(채점, 설계 해석, 준수 검사, 인용 대조, 렌더)을 나눈다. 결정론 쪽은 전부 스크립트이고 테스트가 있다.

## 레이어

| 레이어 | 위치 | 의존해도 되는 것 |
|---|---|---|
| L0 매니페스트 | `.claude-plugin/`(Claude Code) · `.codex-plugin/`·`.agents/plugins/`(Codex) — 스킬·명령·훅 파일은 공용 | 없음 |
| L1 데이터 | `skills/intent-brief/references/` | 없음 |
| L2 절차 | `skills/intent-brief/SKILL.md`, `skills/case-search/SKILL.md`, 내장 스킬 6개 `skills/*/SKILL.md`, `commands/` | L1, L3(명령으로 호출), 공용 `references/`(law-lookup·cta-config) |
| L3 런타임 | `skills/intent-brief/scripts/` | 표준 라이브러리, L1, 같은 레이어 |
| L3c 해외 판례 런타임 | `skills/case-search/scripts/foreigncase.py` | 표준 라이브러리만(Python 3.9) — 다른 런타임 파일을 import 하지 않는다 |
| L3d 0.6.0 스킬 런타임 | `skills/litigation-calc/scripts/`·`brainstorming-lawfirm/scripts/`·`review-contract/scripts/`·`independent-review/scripts/`·`site-api/scripts/{extract,scaffold}.py` | 표준 라이브러리만(Python 3.9). `dday.py` 만 L3 의 `_paths`·`memo`(사건메모 일정 절)를 import 한다 |
| L3e 사이트 API 발굴·생성 클라이언트 | `skills/site-api/scripts/discover.py`, `skills/site-api/templates/client.py.tmpl` | uv inline 의존성(Scrapling·keyring). 생성 클라이언트는 플러그인 밖 작업 폴더 `site-api/` 에 둔다 |
| L3b 빅케이스 런타임 | `skills/case-search/scripts/bigcase.py` | uv inline 의존성(Scrapling·keyring) — L3 는 import 하지 않고 하위 프로세스로만 부른다 |
| L4 개발 | `dev/`, `tests/` | 전부 |

L3 안의 방향: `_paths` ← `state` ← `intent`·`memo`·`check_draft` ← `render_docx`(`state` 는 각 파일 함수 안에서 지연 import). `score`·`lawapi`·`casesearch` 는 `_paths` 만, `cite_check` 는 `_paths`·`lawapi`·`casesearch` 를 쓴다. L3 는 L4 를 import 하지 않는다. 이 표는 `tests/test_params.py` 의 `test_runtime_import_direction` 이 강제한다.

## 교차 관심사

- **경로·저장**: `_paths.py` 하나 — 작업 폴더·사건 키 결정, 원자 저장(임시 파일 → 교체), 해시, 금액 표기·파싱, JSON 출력, 의도 서명(`intent_signature`·`review_current` — 유불리 검토가 지금 의도에 대한 것인지), 번호 비교용 공백 제거(`nows` — 유일한 정의), 응답 키 목록(`load_response_keys` ← `references/response-keys.json`)과 형식 변경 신고 안내(`FORMAT_GUIDE`). 법제처 Open API 호출·키(OC) 보관은 `lawapi.py` 하나 — 키는 작업 폴더 config.json(0600)에 두고 어떤 출력·캐시에도 쓰지 않는다. 키 검증(`verify_key`)과 오류 → 상태 매핑(`error_result`)도 `lawapi.py` 하나이고 키 등록·`cite_check ping` 이 같이 쓴다. 응답 형식 검사(`check_search`·`casesearch.check_list`)는 호출 지점이 켠다 — 인용 대조와 CLI `law`·`prec-search --nb` 1쪽은 켜고, 인용 수 셈·제목·본문 검색·키 등록은 끈다.
- **재현성**: `INTENT_BRIEF_TODAY`(`_paths.today()` 의 「오늘」 고정 — 테스트·재생), `INTENT_BRIEF_LAW_URL`(가짜 법제처 서버, 개발·테스트 전용), `INTENT_BRIEF_LAW_OC`(키 — `LAW_API_OC` 보다 먼저), `INTENT_BRIEF_UV`(uv 경로), `INTENT_BRIEF_NO_CASESEARCH`(빅케이스 끔 — 테스트는 늘 켬). 빅케이스 쪽은 `CASE_SEARCH_HOME`(보관 폴더, 기본 `~/.case-search`), `BIGCASE_ID`·`BIGCASE_PW`(키체인보다 우선), `BIGCASE_KEYRING_SERVICE`(키체인 서비스 이름). case-search 가 없거나 로그인 안 돼 있으면 법제처만 쓴다.
- **원격 장애**: `lawapi.py` 가 키 없음(`no_key` — 대조를 멈추고 키를 받는다)·키 오류(사용자 검증 실패·IP 미등록)·서버 장애(연결 실패·5xx·빈 응답)·형식 변경을 나눈다. 장애여도 초안 작성은 계속한다.
- **개인정보**: 사건 자료는 작업 폴더와 사건 폴더에만 남는다. `state.py purge` 로 지운다.
