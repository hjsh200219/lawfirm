# 법령·판례 조회 (이 플러그인의 모든 스킬 공용)

> Codex 에서는 셸에 `${CLAUDE_PLUGIN_ROOT}` 가 없다 — 이 문서를 연 경로에서 `.codex-plugin` 폴더가 있는 상위 폴더(플러그인 루트)를 찾아 그 절대경로로 바꿔 쓴다. Claude Code 에서는 그대로 둔다.

MCP 를 쓰지 않는다. 법제처 Open API 를 직접 부르는 스크립트 `lawapi.py` 와, 빅케이스에 로그인돼 있으면 빅케이스 연결 `casesearch.py` 를 쓴다. 둘 다 intent-brief 스킬 폴더에 있다. 빅케이스 판례 전문·유사 판례·결정례를 본격적으로 찾을 때는 같은 플러그인의 `case-search` 스킬을 쓴다.

## 준비

- 스크립트 폴더 `$S`: 이 플러그인 루트의 `skills/intent-brief/scripts` (스킬을 불러올 때 표시되는 기준 경로가 `…/skills/<스킬>` 이면 `…/skills/intent-brief/scripts`). 플러그인으로 설치됐다면 `${CLAUDE_PLUGIN_ROOT}/skills/intent-brief/scripts`.
- Python 3.9 이상 `$PY`: `python3 --version` → `python --version` → `py -3 --version` 순서로 찾는다. 외부 패키지는 필요 없다.
- 법제처 키(OC): `"$PY" "$S/lawapi.py" key status` → `configured: false` 면 `/lawfirm:law-key-setup` 절차(`commands/law-key-setup.md`)대로 `"$PY" "$S/lawapi.py" key set --prompt` 로 사용자가 **입력 창**에 OC 값을 직접 넣게 해 저장한다(채팅으로 달라고 하지 않는다 · 판례 1건으로 검증 · 본인만 읽는 파일 · Bash timeout 600000). 입력 창을 띄울 수 없는 환경이면 사용자가 자기 터미널에서 같은 명령을 실행하게 한다. 키 값은 다시 출력하거나 다른 곳에 적지 않는다. `key_invalid` 면 키가 틀렸거나 이 PC 의 IP 가 법제처에 등록되지 않은 것이다. 법제처 장애(`outage`)로 검증이 안 되면 `--no-check` 를 붙여 저장한다.
- 빅케이스: `"$PY" "$S/casesearch.py" status` → `available: true` 면 판례 검색에 함께 쓴다(본인 계정, 사람이 찾는 정도의 빈도로만, 페이지를 끝까지 넘기지 않는다). `false` 면 법제처만 쓴다.

## 명령

| 하려는 일 | 명령 |
|---|---|
| 법령 확인(법령명·약칭 정확 일치) | `"$PY" "$S/lawapi.py" law "형법"` |
| 조문 본문 | `"$PY" "$S/lawapi.py" law "형법" --article 347` (조의2 는 `--article 347-2`) |
| 판례 검색(본문) | `"$PY" "$S/lawapi.py" prec-search "사기 피해액 집행유예" --fulltext [--court 대법원] [--display 10]` |
| 판례 검색(사건명) | `"$PY" "$S/lawapi.py" prec-search "손해배상"` |
| 사건번호로 판례 찾기 | `"$PY" "$S/lawapi.py" prec-search "2016다225353" --nb` |
| 판례 상세(판시사항·판결요지·참조조문·전문) | `"$PY" "$S/lawapi.py" prec <판례일련번호>` |
| 법령해석례 | `"$PY" "$S/lawapi.py" search expc "<검색어>"` → `"$PY" "$S/lawapi.py" detail expc <ID>` |
| 헌법재판소 결정 | `"$PY" "$S/lawapi.py" search detc "<검색어>"` → `"$PY" "$S/lawapi.py" detail detc <ID>` |
| 법령용어 | `"$PY" "$S/lawapi.py" term "소멸시효"` |
| 별표·서식 목록(법령 / 행정규칙) | `"$PY" "$S/lawapi.py" form-search "표준계약서" --kind 서식` / `… --admin` · 법령명으로 `--law` |
| 서식 파일 내려받기(hwp·pdf) | `"$PY" "$S/lawapi.py" form-get <파일 번호> --out <사건 폴더>` |
| 빅케이스 판례 검색(있을 때) | `"$PY" "$S/casesearch.py" search "<검색어>"` |
| 빅케이스 판결 전문(있을 때) | `"$PY" "$S/casesearch.py" case 대법원 2014다26187` |

모든 명령은 JSON 을 출력한다. `ok: false` 면 `error`(`no_key`·`key_invalid`·`outage`·`format_changed`)를 사용자에게 그대로 알리고 추측으로 채우지 않는다. `network_blocked` 는 장애가 아니라 Codex 샌드박스의 네트워크 차단이다 — 네트워크를 허용해 같은 명령을 다시 실행한다. 검색으로 얻은 실제 일련번호·ID 로 상세를 조회한 것만 인용한다. 법제처에 원문이 없는 판례도 있다(예: 2014다26187) — 빅케이스에서 찾았으면 「빅케이스 확인」이라고 밝힌다.
