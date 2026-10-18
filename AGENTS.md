# AGENTS.md — lawfirm

한국 변호사용 법률 업무 Claude Code·Codex 플러그인. 스킬 14개 — `intent-brief`(의도 기반 민사 준비서면·답변서 초안 + 내부용 의도대응표) + `case-search`(판례·법령 검색 — 법제처·빅케이스·미국·독일) + thechain.lawyer 법률 문서 스킬 6개(lyn-lawfirm 에서 내장) + 0.6.0 의 `brainstorming-lawfirm`·`litigation-calc`·`review-contract`·`triage-nda`·`independent-review`·`site-api`. 0.4.0 에서 intent-brief·case-search·lyn-lawfirm 플러그인을 합쳤다(옛 repo 둘은 이전 안내용 마켓플레이스만 남는다). 법령·판례는 법제처 Open API 를 직접 부른다(키는 변호사에게 받아 저장, MCP 없음). 빅케이스에 로그인돼 있으면 민사 서면 인용 대조에 보조로 연결한다. 서버·DB·빌드 없음.

## 지도

| 무엇 | 어디 |
|---|---|
| 매니페스트 | Claude `.claude-plugin/plugin.json`·`marketplace.json` · Codex `.codex-plugin/plugin.json`·`.agents/plugins/marketplace.json`(버전 셋을 맞춘다 — `tests/test_codex_plugin.py`). 스킬·명령·훅 파일은 공용 — Codex 는 셸에 `CLAUDE_PLUGIN_ROOT` 를 주지 않고 `$ARGUMENTS` 명령을 빠뜨린다 |
| 스킬 절차(모델이 읽는 정본) | `skills/intent-brief/SKILL.md` · `skills/case-search/SKILL.md` |
| 해외 판례 클라이언트(표준 라이브러리, Python 3.9) | `skills/case-search/scripts/foreigncase.py` — 미국 CourtListener·독일 OpenLegalData · 키 등록 명령 `commands/law-key-setup.md` |
| 빅케이스 클라이언트(uv inline 의존성) | `skills/case-search/scripts/bigcase.py` · 설정 명령 `commands/case-search-setup.md` · API 근거 [docs/case-search/bigcase-api.md](docs/case-search/bigcase-api.md) · LBOX 정찰 [docs/case-search/lbox/](docs/case-search/lbox/README.md) |
| 내장 스킬 6개(lyn-lawfirm `9d620a9` 복사, 이후 따로 감) | `skills/certified-letter/` 외 5개 — 법령·판례는 `references/law-lookup.md`, CTA 는 `references/cta-config.md` |
| 0.6.0 스킬(런타임은 표준 라이브러리, Python 3.9) | `skills/litigation-calc/`(`deadline.py`·`costs.py`·`dday.py`, 공휴일 `skills/litigation-calc/references/holidays.json` 2024–2028 ← `dev/holidays_kasi.py`, 2029년 자료가 나오면 다시 생성) · `skills/brainstorming-lawfirm/`(`risk.py`) · `skills/review-contract/`(`playbook.py`, 기본 플레이북 `references/`) · `skills/triage-nda/` · `skills/independent-review/`(`doc_text.py`) · `skills/site-api/`(`extract.py`·`scaffold.py`, uv 쪽 `discover.py`·`templates/client.py.tmpl`) |
| 세션 시작 훅 | `hooks/hooks.json` → `dday.py hook`(다가오는 기한이 없으면 출력 없음 — 사건이 많아 상한에 걸리면 경고 1줄, 어떤 오류에도 exit 0) |
| 제3자 고지 | [third_party/anthropic-legal/NOTICE.md](third_party/anthropic-legal/NOTICE.md)(review-contract·triage-nda·위험 점수표 — Apache-2.0) · 법률 문서 공통 구성안 절차 `references/outline-approval.md` |
| 의도·채점·문구 데이터 | `skills/intent-brief/references/` — `intent-params.json`(섹션 어휘·충돌표), `response-keys.json`(법제처·빅케이스 응답 키 — 받는 PC 형식 검사·계약 점검 공용), `intents.md`, `scoring.md`, `phrases.json`, `brief-types/` |
| 런타임 스크립트 | `skills/intent-brief/scripts/` — 역할·의존 방향은 [ARCHITECTURE.md](ARCHITECTURE.md) |
| 테스트 | `tests/` — 픽스처 F1(하네스 데모 사본)·F2·F3(합성), `recorded/`(녹화 응답), `e2e/`(답 파일), `case_search/`(빅케이스 오프라인 — scrapling·keyring 없으면 건너뜀) |
| 개발 전용 도구 | `dev/` — `replay.py`(무인 재생)·`e2e.py`(E1–E8 판정)·`drf_replay.py`(e2e 용 법제처 루프백 재생 서버)·`secret_scan.py`(녹화·픽스처 비밀·개인정보 형식 검사)·`contract.py`(법제처·빅케이스 계약 점검·빅케이스 로컬 녹화 — 판 올림 절차 docs/QUALITY.md)·`smoke.py`(받는 PC 실기 점검)·`verify_docs.py`·`holidays_kasi.py`(공휴일 표 생성, KASI 키는 환경변수) |
| 품질 기준·부채 | [docs/QUALITY.md](docs/QUALITY.md) · [docs/exec-plans/tech-debt-tracker.md](docs/exec-plans/tech-debt-tracker.md) |
| 구현 전 함정 목록 | [docs/harness/harness-setup.md](docs/harness/harness-setup.md) |
| 하네스 채점 | [원칙](docs/harness/principles.md) · [성숙도](docs/harness/maturity-framework.md) · [개선 카탈로그](docs/harness/fix-catalog.md) · [GC 이력](docs/harness/gc-history.md) |

## Health Stack

```
uv run --no-project --with pytest --with python-docx==1.2.0 pytest tests/            # 전체(문서 검사 포함)
uv run --no-project --python 3.9 --with pytest --with python-docx==1.2.0 pytest tests/  # 받는 PC 최저 버전
uv run --no-project --with "scrapling[fetchers]>=0.4.11,<0.5" --with "keyring>=25,<26" --with pytest --with python-docx==1.2.0 pytest tests/case_search -q  # 빅케이스
claude plugin validate --strict .                                                     # 매니페스트
python3 dev/verify_docs.py                                                             # 문서 링크·버전·줄 수
```

`python-docx` 는 테스트에서 생성 docx 를 읽어 보는 데만 쓴다. 런타임 의존이 아니다. 첫 두 줄에서 `tests/case_search/` 는 의존성이 없어 건너뛴다(skipped) — 셋째 줄로 따로 돌린다.

## 불변 조건 (어기면 받는 PC 에서 깨진다)

1. intent-brief 런타임 스크립트(`skills/intent-brief/scripts/`)는 **표준 라이브러리만, Python 3.9 문법**(내장 스킬의 `generate.js` 는 Node). `tests/test_params.py` 가 import·문법을 검사한다. 외부 패키지가 필요한 `bigcase.py` 는 `skills/case-search/scripts/` 에만 두고 intent-brief 쪽은 `casesearch.py` 가 `uv run` 으로 부른다(import 하지 않는다).
2. 작업 폴더는 플러그인 밖 — macOS `~/.intent-brief/`, Windows `%LOCALAPPDATA%\intent-brief\`. `CLAUDE_PLUGIN_DATA` 는 uninstall 때 지워지므로 쓰지 않는다. 플러그인 이름이 lawfirm 으로 바뀌어도 이 이름은 바꾸지 않는다(진행 중 사건·법제처 키가 끊긴다). 빅케이스도 마찬가지로 키체인 서비스 `case-search-bigcase`·`~/.case-search/` 를 유지한다.
3. 사건 폴더의 `사건메모.md` 는 `memo.py apply` 의 확인 토큰으로만 쓴다. 줄바꿈(CRLF)을 보존하고, 사본에 먼저 적용해 성공했을 때만 바꾼다.
4. 법제처 키(OC)는 `lawapi.py` 만 다룬다 — 작업 폴더 config.json(0600)에 저장하고 출력·캐시·오류 문구에 값을 쓰지 않는다(URL 은 `OC=***` 로 가린다). 키가 없으면 대조를 멈추고 변호사에게 받는다.
5. 인용 「확인됨」은 법제처 원문 **정확 일치**일 때만(빅케이스에서만 찾은 것은 `external` — 「확인됨」과 섞지 않는다). 못 찾으면 `[확인 필요: 법제처 미확인]`, 서버 장애면 `[법제처 장애 — 미확인]`.
6. 어떤 의도도 거부하지 않는다. 의도를 정하면 소송 전체 기준 유불리를 먼저 보여 주고(`intent_review`) 진행 여부는 변호사가 정한다 — 설계 확정은 지금 의도에 대한 「진행」 결정을 요구한다. 자료에 없는 사실은 지어내지 않고 `[확인 필요: …]` 로 둔다.

## 개발 규칙

- 새 로직은 테스트를 먼저 쓴다(Red 확인 → Green). 커밋 본문에 Red/Green 을 적는다.
- 하네스 데모 트리(`agent-lawfirm/docs/references/업무관리시스템_데모/`)는 읽기만 한다. 그 안에서 Python 을 import·실행하지 않는다(바이트코드가 생긴다). casedb 계약 테스트는 경로가 있을 때만 돈다.
- 테스트는 실제 빅케이스를 부르지 않는다(`tests/conftest.py` 가 `INTENT_BRIEF_NO_CASESEARCH=1`, `tests/case_search/` 는 가짜 HTTP). 빅케이스는 이용 범위상 사람 빈도로만 부르고, 대량 수집·재배포는 하지 않는다. 실계정 자료(토큰·비밀번호·조회한 판결의 실명)는 커밋하지 않는다.
- `dev/replay.py`·`dev/e2e.py` 는 `claude -p` 를 여러 번 부른다(비용 발생 — `run` 이 예상 호출 수를 먼저 찍고 `--max-claude` 를 넘으면 시작하지 않는다). 법제처는 루프백 재생 서버, 빅케이스는 끔으로만 돌고(실서비스 0회), 첫 `claude -p` 전에 모델 없는 사전 시험을 통과해야 한다. 실행마다 새 폴더 · 식별값이 다른 결과는 재사용·판정하지 않는다. 판정 기준은 `dev/e2e.py` 의 `judge_run`. 선택 환경변수: `INTENT_BRIEF_TOKEN_FILE`(무인 실행 토큰 파일), `JEV_DIR`(블라인드 판별용 Jev 클라이언트), `INTENT_BRIEF_DEMO_DIR`(casedb 계약 테스트의 데모 원본).
- 공개 repo 다. 픽스처의 인명·사건번호는 가명이며 실제 의뢰인 자료를 넣지 않는다.
- 이 Mac 에서 `main` 커밋은 곧 공개 게시다 — post-commit 훅이 자동 push 하고 Claude·Codex 설치본을 갱신한다([R-push] 예외 열다섯, 끄기 `LAWFIRM_AUTOPUSH=0`, 로그 `~/Library/Logs/lawfirm-autopush.log`). 올리면 안 되는 작업은 다른 브랜치에 둔다. 설치한 사람에게 퍼뜨릴 변경은 버전을 올린다(같은 버전이면 업데이트되지 않는다).
- 의도 목록·기본값 개정은 사용 통계(`intent.py stats`)를 근거로 한다.
- 내장 스킬에 MCP·Cowork 경로·AskUserQuestion 을 다시 넣지 않는다(`tests/test_embedded_skills.py` 가 막는다). lyn-lawfirm 원본과는 자동 동기화하지 않는다.

## 문서

- 사용자 안내: [README.md](README.md)
- 구조·의존 방향: [ARCHITECTURE.md](ARCHITECTURE.md)
- 요구사항 정본(PRD)은 이 repo 밖, 개발 PC workspace 의 `.omc/plans/lawyer-intent-brief-skill.md` 에 있다(로컬 전용). 구현 결과·편차는 그 문서 §10에 있다.
