---
name: case-search
description: 판례·법령 검색 — 법제처(공식 원문: 법령·조문·판례·헌재결정·법령해석례·법령용어·별표·서식), 빅케이스(bigcase.ai: 판결문 전문·하급심·유사 판례·서술문 검색·결정례/행정심판), 해외 판례(미국 CourtListener — 연방대법원 Supreme Court·연방법원 판결문 원문 opinion·citation, 독일 OpenLegalData)를 한곳에서 찾는다. 해외 판결문 원문·영어 원문 인용·citation 확인도 웹 검색·curl 보다 이 스킬로 한다(검색 결과의 식별자로 본문을 가져온다). 빅케이스 계정이 없으면 법제처·해외 판례만 쓴다. 트리거 — "/lawfirm:case-search", "판례 검색", "판례 찾아줘", "사건번호 찾아줘", "판결문 전문", "판결 이유", "법제처", "법령 찾아줘", "조문", "몇 조", "헌재 결정", "헌법재판소", "법령해석", "법률용어", "빅케이스", "bigcase", "유사 판례", "비슷한 판례", "행정심판", "결정례", "별표", "서식", "표준계약서 양식", "법정 서식", "미국 판례", "미국 연방대법원", "Supreme Court", "SCOTUS", "미국 판결문 원문", "영어 원문 인용", "독일 판례", "해외 판례", "US case", "BGH".
argument-hint: "[검색어 | 사건번호 | 법령명 제N조 | us <검색어> | de <검색어>]"
allowed-tools: Bash(uv run:*), Bash(python3:*), Bash(python:*), Bash(py:*)
---

# case-search — 판례·법령 검색

> Codex 에서는 셸에 `${CLAUDE_PLUGIN_ROOT}` 가 없다 — 이 문서를 연 경로에서 `.codex-plugin` 폴더가 있는 상위 폴더(플러그인 루트)를 찾아 그 절대경로로 바꿔 쓴다. Claude Code 에서는 그대로 둔다.

원천 셋을 쓴다. 명령은 모두 JSON(또는 Markdown)을 출력하고, `ok: false` 면 `error` 를 그대로 알린다(추측으로 채우지 않는다).

| 줄임 | 원천 | 명령 | 계정·키 |
|---|---|---|---|
| `LAW` | 법제처 Open API(공식 원문) | `"$PY" "${CLAUDE_PLUGIN_ROOT}/skills/intent-brief/scripts/lawapi.py"` | 법제처 OC 키(본인) |
| `BC` | 빅케이스 | `uv run "${CLAUDE_PLUGIN_ROOT}/skills/case-search/scripts/bigcase.py"` | 빅케이스 계정(본인, 선택) |
| `FX` | 미국 CourtListener · 독일 OpenLegalData | `"$PY" "${CLAUDE_PLUGIN_ROOT}/skills/case-search/scripts/foreigncase.py"` | 검색은 없이 · 미국 본문만 CourtListener 토큰 |

`$PY` 는 Python 3.9 이상: `python3 --version` → `python --version` → `py -3 --version` 순서로 찾는다.

## 0. 시작 — 쓸 수 있는 원천 확인

1. `LAW key status` — `configured: false` 면 `/lawfirm:law-key-setup` 절차(`commands/law-key-setup.md`)로 **입력 창에서** 키를 받아 저장한다. 키 값을 채팅으로 달라고 하지 않는다.
2. `BC status` — 네트워크 없이 등록 여부만 본다. `email` 이 비었거나 `password_saved: false` 면 **빅케이스 없이 진행한다** — 법제처(와 해외 판례)만 조회하고, 결과 끝에 「빅케이스 계정을 등록하면(`/lawfirm:case-search-setup`) 하급심 전문·유사 판례도 찾을 수 있습니다」 한 줄만 덧붙인다. 사용자가 빅케이스를 직접 요청했거나 등록하겠다고 할 때만 setup 을 실행한다. `uv` 가 없어도 같은 취급이다.
3. 해외 판례는 요청이 있을 때만 쓴다.
4. 검색어·사건번호·법령명이 없으면 무엇을 찾을지 한 번 묻는다.

## 1. 무엇을 어디서 찾나

| 요청 | 먼저 | 없거나 부족하면 |
|---|---|---|
| 법령·조문(「민법 제750조」) | `LAW law "민법" --article 750` (조의2 는 `--article 266-2`) | — |
| 사건번호로 판례(「2016다225353」) | `LAW prec-search "2016다225353" --nb` → `LAW prec <prec_id>` | `BC case <법원> <사건번호>` (법제처에 원문이 없는 판례가 있다 — 예: 2014다26187) |
| 키워드 판례 | `LAW prec-search "<검색어>" --fulltext [--court 대법원]` | `BC search <검색어>`(하급심·최신 판결 보강, 빅케이스 있을 때) |
| 판결문 전문·이유 | `LAW prec <prec_id>`(판시사항·판결요지·참조조문·전문) | `BC case <법원> <사건번호>`(하급심 전문) |
| 사실관계로 비슷한 판례 · 특정 판례와 비슷한 판례 | `BC brief <서술문>` · `BC similar <법원> <사건번호>` (빅케이스 전용) | 빅케이스가 없으면 `LAW prec-search --fulltext` 로 핵심어 검색 |
| 헌법재판소 결정 | `LAW search detc "<검색어>"` → `LAW detail detc <ID>` | — |
| 법령해석례(법제처) | `LAW search expc "<검색어>"` → `LAW detail expc <ID>` | `BC decisions 법령해석 <검색어>` |
| 행정심판 재결·위원회 결정례 | `BC decisions <행정심판\|결정례> <검색어>` → `BC decision <종류> <id>` | — |
| 행정규칙 | `LAW search admrul "<검색어>"` → `LAW detail admrul <ID>` | — |
| 법령용어 | `LAW term "소멸시효"` | — |
| 법정 서식·별표(표준계약서·신청서 양식 등) | `LAW form-search "근로계약서" --kind 서식` (법령명으로는 `--law`, 고시·예규는 `--admin`) → `LAW form-get <hwp 또는 pdf 번호> --out <사건 폴더>` | 법제처에 없는 부처 누리집 양식(예: 주택임대차표준계약서)은 출처 URL 을 안내 |
| 미국 판례 | `FX us-search "<영문 검색어>" [--court scotus] [--after YYYY-MM-DD]` → `FX us-opinion <opinion_id>` | 본문은 CourtListener 토큰 필요(`/lawfirm:law-key-setup us`) — 없으면 검색 결과의 판례명·인용·URL 까지만 |
| 독일 판례 | `FX de-search "<독일어 검색어>" [--court BGH] [--level Bundesgericht]` → `FX de-case <id>` | — |

- 검색으로 얻은 실제 일련번호·ID 로 상세를 조회한 것만 인용한다. 검색 목록만 보고 「판결문 확인」이라고 하지 않는다.
- 결과에는 출처를 밝힌다: 「법제처」「빅케이스」「CourtListener」「OpenLegalData」. 법제처에 원문이 없어 빅케이스에서만 찾은 판례는 「빅케이스 확인」이라고 쓴다.
- 긴 본문은 파일로 저장해 필요한 절만 읽는다. `FX` 본문은 8,000자씩 오며 `has_more` 면 `--offset <next_offset>` 으로 이어 읽는다. 해외 판례 본문은 원문 언어 그대로이니 요약·번역할 때 원문 언어를 밝힌다.
- 법제처가 제공한 행정해석(법령해석례)과 법원의 판단은 구별한다.

## 2. 빅케이스 명령

| 명령 | 하는 일 | 네트워크 |
|---|---|---|
| `BC status` | 등록 상태(이메일·비밀번호 저장 여부·토큰 남은 시간). 값은 출력 안 함 | 없음 |
| `BC setup [--email E] [--force]` | 자격증명 등록 — 로그인 1회로 확인한 뒤에만 키체인에 저장(`/lawfirm:case-search-setup`) | 로그인 |
| `BC login` | 저장 토큰을 무시하고 새로 로그인, 계정 요약(토큰 제외) | 로그인 |
| `BC search <검색어> [--page N] [--raw]` | 판례 검색 — `{total, results[10]}`(사건 표시·사건번호·법원·종류·결과·화면 URL) | POST |
| `BC case <법원> <사건번호>` · `BC case <판례 URL>` | 판결문 전문 Markdown — 판시사항·판결요지·참조조문·당사자·주문·이유·판사·첨부 목록·심급. `--raw` 는 JSON | GET |
| `BC similar <법원> <사건번호> [--limit N]` | 유사 판례(최대 50건 중 상위 N, `ranking` 포함) | GET |
| `BC brief <사건 서술문> [--laws]` · `echo … \| BC brief -` | 사실관계 서술로 비슷한 판례 찾기. `--laws` 는 관련 법령 조문 | POST |
| `BC decisions <결정례\|법령해석\|행정심판> <검색어>` · `BC decision <종류> <id>` | 위원회 결정례·부처 법령해석·행정심판 재결 검색 / 원문 PDF 주소 | POST·GET |
| `BC get <경로>` · `BC post <경로> --json '{...}'` | `/api/v1` 아래 인증 요청(API 탐색용, bigcase.ai 밖 주소는 거부) | GET·POST |
| `BC token` | 유효한 accessToken 만 출력 — 사용자가 요청할 때만, 옮겨 적지 않는다 | 필요 시 갱신 |
| `BC forget` | 키체인 항목·설정·토큰 파일 삭제 | 없음 |

- 비밀번호를 채팅으로 받지 않는다. 사용자가 채팅에 붙여 넣으면 쓰지 말고 빅케이스에서 비밀번호를 바꾸라고 안내한다.
- `BC case` 의 stderr 에 `restricted=true` 가 나오면 본문이 잘린 것이니 그대로 알린다. 첨부(별지·증거목록)는 이미지라 받지 않는다.
- 토큰은 `~/.case-search/bigcase/session.json` 에 저장돼 재사용된다(만료 60초 전 갱신·실패면 재로그인·401 이면 1회 재시도) — 직접 다시 로그인시키지 않는다.

## 3. 법제처·해외 판례 명령

| 명령 | 하는 일 |
|---|---|
| `LAW key status` · `LAW key set --prompt` · `LAW key clear` | 키 상태(값은 출력 안 함) · 입력 창으로 받아 판례 1건으로 검증 후 저장 · 삭제 |
| `LAW law <법령명> [--article N]` | 법령명·약칭 정확 일치 → 조문 본문 |
| `LAW prec-search <검색어> [--nb] [--fulltext] [--court 대법원] [--display N]` | 판례 목록(`--nb` 는 사건번호 정확 일치, `--fulltext` 는 본문 검색) |
| `LAW prec <prec_id>` | 판례 상세(판시사항·판결요지·참조조문·전문) |
| `LAW search <expc\|detc\|admrul> <검색어>` · `LAW detail <expc\|detc\|admrul> <ID>` | 법령해석례·헌재결정·행정규칙 목록 / 원문 |
| `LAW term <용어>` | 법령용어 정의 |
| `LAW form-search <검색어> [--admin] [--kind 별표\|서식] [--law] [--display N]` | 법령(`--admin` 이면 행정규칙) 별표·서식 목록 — 번호(「별지 제3호」)·근거 법령·공포일·파일 번호(hwp·pdf) |
| `LAW form-get <파일 번호> --out <폴더>` | 서식 파일 내려받기(키 불필요) — 같은 이름이 있으면 `_2` 를 붙이고 덮어쓰지 않는다 |
| `FX us-search <검색어> [--court C] [--after D] [--before D] [--cursor C]` | 미국 판례 검색(익명) — 판례명·법원·선고일·인용·opinion id·URL, 다음 페이지는 `next_cursor` |
| `FX us-opinion <opinion_id> [--offset N]` | 미국 판결문 본문(영어) — CourtListener 토큰 필요 |

미국 판례 인용 규칙: `us-opinion` 은 같은 대화의 `us-search` 결과에 나온 `opinion_id` 로만 부른다 — 기억·추측한 식별자로 부르지 않고, 판례명·인용도 검색 결과에 나온 것만 쓴다.
| `FX de-search <검색어> [--court BGH] [--level Bundesgericht] [--page N]` | 독일 판례 본문 검색(익명) — 법원·선고일·결정 종류·발췌·URL |
| `FX de-case <id> [--offset N]` | 독일 판결문 본문(독일어) — 사건번호·ECLI 포함 |
| `FX key status` · `FX key set us --prompt` · `FX key clear us` | CourtListener 토큰 상태 · 입력 창으로 저장 · 삭제 |

오류: `no_key`(키 등록 필요 — `/lawfirm:law-key-setup`), `key_invalid`(키가 틀렸거나 법제처에 이 PC IP 미등록), `outage`(원천 장애 — 0건과 다르다), `rate_limited`(잠시 뒤 다시), `not_found`, `network_blocked`(장애가 아니라 Codex 샌드박스 차단 — 네트워크를 허용해 같은 명령을 다시 실행).

## 주의

- 각자 자기 계정·키로만 쓴다. 빅케이스·법제처·해외 원천 모두 사람이 화면에서 찾는 정도의 빈도로만 부르고, 페이지를 반복문으로 끝까지 넘기지 않는다. 대량 수집·재배포·다른 서비스의 데이터 소스로 쓰지 않는다(약관·저작권법 §93 DB제작자 권리).
- 키·토큰 값은 대화·파일·커밋에 옮겨 적지 않는다.
- API 근거: 법제처 `${CLAUDE_PLUGIN_ROOT}/references/law-lookup.md`, 빅케이스 `${CLAUDE_PLUGIN_ROOT}/docs/case-search/bigcase-api.md`. LBOX 정찰 자료는 `docs/case-search/lbox/`.
