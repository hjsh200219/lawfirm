# lawfirm — 한국 변호사용 법률 업무 플러그인 (Claude Code·Codex)

민사 서면 초안, 법률 문서 초안, 판례·법령 검색, 사건 전략·계약 검토, 법정기간·소송비용 계산을 한 플러그인에서 합니다.

- **의도 기반 민사 서면(`intent-brief` 스킬)**: 변호사가 이번 서면으로 얻으려는 **의도**를 먼저 정하면, 그 의도와 당사자 지위에 맞춰 민사 준비서면·답변서 초안(.docx)과 내부용 의도대응표(.docx)를 만듭니다.
  - 의도 목록: 전부 승소(W) · 손해 최소화(M) · 조정·화해 유도(S) · 상대 입장 고정·증거 제출 압박(P) · 쟁점 재구성(R) · 상소 대비 기록(A) · 의뢰인 보고(C, 부 의도 전용)
  - 결정 축 4개(의도·쟁점 태도·증거 전략·절차) 모호도 인터뷰 → 고른 의도의 소송 전체 기준 유불리 검토(그대로 갈지 변호사가 결정) → 설계 확인 표(변호사가 어느 칸이든 덮어쓰기) → 초안 → 설계 준수 검사 → 조문·판례 존재 대조(법령명·사건번호 정확 일치) → .docx
  - 어떤 의도도 거부하지 않습니다. 다만 그 의도로 소송 전체에서 놓칠 수 있는 것(예: 항소심 청구취지 확장)을 먼저 보여 드리고, 그대로 진행하시면 할 일과 의도대응표에 남깁니다. 자료에 없는 사실은 `[확인 필요: …]` 로 남깁니다.
- **법률 문서 스킬 6종**: 내용증명·고소장·형사합의서·사실확인서·형사절차 시뮬레이터·양형 예측. 본문을 쓰기 전에 구성안(목표·쟁점과 증거·목차·확인 필요·인용 예정)을 보여 드리고 승인을 받습니다(「바로 작성」이면 건너뜀).
- **판례·법령 검색(`case-search` 스킬)**: 세 원천을 한곳에서 찾습니다.
  - 법제처(공식 원문): 법령·조문·판례·헌재결정·법령해석례·행정규칙·법령용어, 법령·행정규칙의 별표·서식(서식 파일 내려받기)
  - 빅케이스(bigcase.ai, 계정이 있을 때): 판결문 전문(하급심 포함)·유사 판례·사실관계 서술 검색·결정례·행정심판. 계정이 없으면 법제처·해외 판례만 씁니다.
  - 해외 판례: 미국(CourtListener)·독일(OpenLegalData) 검색과 판결문 본문(원문 언어)
  민사 서면의 인용 대조에도 법제처·빅케이스가 자동으로 쓰입니다.
- **사건 전략 메모(`brainstorming-lawfirm`)**: 쟁점마다 IRAC(쟁점·규범·포섭·결론) → 상대방 대리인 관점의 레드팀 반론·재반박 → 남는 약점의 위험 점수표(심각도×가능성, GREEN·YELLOW·ORANGE·RED) → 전략 선택지(기한·비용 포함)를 사건 폴더에 내부 메모로 씁니다.
- **계약 검토(`review-contract`·`triage-nda`)**: 사무소 플레이북(검토 기준) 대비 조항별 GREEN·YELLOW·RED, 바로 넣을 수정 문안, 협상 우선순위. 약관법·민법·상법·개인정보 보호법·하도급법·근로기준법·민사소송법·중재법 강행규정을 점검합니다. NDA 는 10개 항목으로 빠르게 분류합니다.
- **법정기간·소송비용(`litigation-calc`)**: 항소·상고·즉시항고·답변서·항소이유서·형사 상소·행정 제소기간 만료일(초일 불산입, 토요일·공휴일이면 다음 날), 인지액·송달료 회분·지연손해금. 사건메모 「주요 일정」의 기한·기일을 모아 세션을 시작할 때 14일 안의 것을 알려 드립니다(없으면 아무 말도 하지 않음).
- **독립 검토(`independent-review`)**: 제출 전 오탈자·설득력·문체·체계·누락·형식 6개 영역을 고치지 않고 지적만 합니다.
- **사이트 API 만들기(`site-api`)**: 판례·법령·공고 사이트 URL 하나로 그 사이트의 API 를 찾아 빅케이스 클라이언트와 같은 틀(키체인 자격증명·토큰 재사용·호스트 고정)의 Scrapling 클라이언트를 만듭니다.

> AI는 실수할 수 있습니다. 인용 대조의 「확인됨」은 그 조문·판례가 법제처 원문에 존재한다는 뜻이며 적합성은 보증하지 않습니다. 최종 검토와 제출 판단은 사용 변호사의 책임입니다.
>
> - 변호사 업무 보조용입니다. 초안·검토 결과는 참고 자료이고 결론은 변호사가 정합니다.
> - 사건 자료(파일·대화)는 쓰는 AI 도구(Claude Code·Codex)의 모델 제공자에게 전송·처리됩니다(국외일 수 있음). 이 플러그인 자체는 사용 통계 등을 PC 밖으로 보내지 않습니다.
> - 작업 폴더(macOS `~/.intent-brief/`, Windows `%LOCALAPPDATA%\intent-brief\`)에 인터뷰 상태·초안·인용 응답·사건메모 사본이 남습니다. 끝난 사건은 `state.py purge` 로 지우십시오(아래 「데이터 위치」).

## 설치

필요: Claude Code 또는 Codex, **Python 3.9 이상**(외부 패키지 없음). 두 도구에 함께 설치해도 됩니다 — 작업 폴더·키를 같이 씁니다.

### Claude Code

```
/plugin marketplace add hjsh200219/lawfirm
/plugin install lawfirm@lawfirm
```

Claude Code 2.1.275 이상이면 한 줄로도 됩니다: `/plugin install lawfirm --marketplace hjsh200219/lawfirm`. repo 폴더를 받아 두었다면 `claude plugin marketplace add <폴더 경로>` → `claude plugin install lawfirm@lawfirm`.

- 업데이트: `/plugin` → Marketplaces → lawfirm → Update marketplace(또는 Enable auto-update). 제3자 마켓플레이스는 자동 업데이트가 기본으로 꺼져 있습니다. 터미널에서는 `claude plugin marketplace update lawfirm` → `claude plugin update lawfirm@lawfirm`. 바뀐 내용은 Claude Code 를 다시 시작해야 적용됩니다.

### Codex

codex-cli 0.162.1(macOS)·0.160.0(Windows)에서 확인했습니다. 터미널에서:

```
codex plugin marketplace add hjsh200219/lawfirm
codex plugin add lawfirm@lawfirm
```

- 같은 스킬 14개를 씁니다. 명령 두 개는 Codex 에서 스킬로 바뀝니다(`source-command-law-key-setup`·`source-command-case-search-setup`) — `/lawfirm:law-key-setup` 대신 「법제처 키 등록해 줘」, 「빅케이스 계정 등록해 줘」처럼 말하면 됩니다.
- 세션 시작 기한 알림은 훅이라 Codex 가 처음 실행할 때 「Hooks need review」 창을 띄웁니다. 「Trust all and continue」를 고르면 켜집니다(고르지 않으면 알림만 꺼지고 나머지는 그대로).
- 작업 폴더(`~/.intent-brief`)·법제처 키·빅케이스 키체인을 Claude Code 와 같이 씁니다. 두 도구를 오가도 사건·키가 이어집니다.
- Codex 기본 샌드박스는 네트워크(법제처·빅케이스·해외 판례)와 작업 폴더 쓰기를 막습니다. 막히면 스크립트가 `network_blocked`·`sandbox_write_blocked` 로 알려 주고 Codex 가 권한 승인을 묻습니다. 매번 묻지 않게 하려면 `~/.codex/config.toml` 에 한 번 적어 둡니다(경로는 본인 것으로):

  ```toml
  [sandbox_workspace_write]
  network_access = true
  writable_roots = ["/Users/<사용자>/.intent-brief"]   # Windows: 'C:\Users\<사용자>\AppData\Local\intent-brief'
  ```
- 스크립트 경로: Codex 셸에는 `${CLAUDE_PLUGIN_ROOT}` 가 없어서, 스킬이 자기 문서 위치에서 플러그인 폴더를 찾아 절대경로로 바꿔 씁니다(따로 설정할 것 없음).
- 업데이트: `codex plugin marketplace upgrade lawfirm` → `codex plugin add lawfirm@lawfirm`. 설치 확인: `codex plugin list` 에 `lawfirm@lawfirm installed, enabled 0.8.1`.

쓰는 기능에 따라 더 필요한 것:

| 기능 | 필요한 것 |
|---|---|
| 조문·판례 인용 대조, 법령·판례 조회 | 법제처 Open API 키(OC) → `/lawfirm:law-key-setup`(입력 창, Codex 는 「법제처 키 등록해 줘」) — 아래 「원격 서버 의존」 |
| 빅케이스 판례 검색(선택) | [uv](https://docs.astral.sh/uv/) + 본인 빅케이스 계정 → `/lawfirm:case-search-setup`(Codex 는 「빅케이스 계정 등록해 줘」) — 아래 「uv·Scrapling」 |
| 사이트 API 만들기(선택) | uv(Scrapling 은 자동) · 네트워크 발굴(`--cdp`)을 쓰면 브라우저 엔진 — 아래 「uv·Scrapling」 |
| 미국 판결문 본문(선택) | CourtListener 무료 계정 API 토큰 → `/lawfirm:law-key-setup us`(검색은 토큰 없이 됩니다) |
| 내용증명·고소장·사실확인서·형사합의서 .docx | Node 와 `docx` 패키지 — `npm install --prefix ~ docx`(전역 설치 `-g` 만으로는 `require('docx')` 가 찾지 못합니다). 스킬이 만들기 전에 확인하고 없으면 이 안내를 보이고 멈춥니다 |

### uv·Scrapling

빅케이스 검색과 `site-api` 는 [Scrapling](https://github.com/D4Vinci/Scrapling)(브라우저 없이 사이트를 부르는 Python 라이브러리)을 씁니다. 직접 설치할 필요는 없습니다 — 스크립트를 `uv run` 으로 실행하면 uv 가 Scrapling(`scrapling[fetchers]>=0.4.11,<0.5`)·keyring(`>=25,<26`)을 알아서 받습니다.

1. uv 설치(한 번): macOS `curl -LsSf https://astral.sh/uv/install.sh | sh` · Windows `winget install --id=astral-sh.uv -e`
2. (`site-api` 의 네트워크 발굴 `--cdp` 나 브라우저가 필요한 사이트를 쓸 때만) 브라우저 엔진 한 번 설치: `uv tool run --from "scrapling[fetchers]" scrapling install` — 수백 MB 를 내려받습니다.

## 사용

- 「이 사건 준비서면 의도부터 정해서 써 줘」 → `intent-brief` 스킬
- 「피해자에게 보낼 내용증명 써 줘」, 「사기죄 양형 예측해 줘」 → 법률 문서 스킬
- 「이 사건 쟁점 IRAC 로 정리하고 레드팀 해 줘」 → `brainstorming-lawfirm` · 「이 용역계약서 검토해 줘」, 「이 NDA 서명해도 돼?」 → `review-contract`·`triage-nda`
- 「10월 17일 판결서 받았는데 항소기간 언제까지야?」, 「소가 3천만 원 항소장 인지대」, 「다가오는 기한 보여 줘」 → `litigation-calc`
- 「이 준비서면 제출 전에 검토해 줘」 → `independent-review` · 「이 사이트도 빅케이스처럼 API 만들어 줘: <URL>」 → `site-api`
- 「표준근로계약서 서식 찾아 줘」 → `case-search`(법제처 별표·서식)
- 「민법 제750조 보여 줘」, 「2016다225353 판결 전문 읽어줘」, 「부당해고 판례 찾아줘」, 「이런 사실관계와 비슷한 판례 찾아줘: …」, 「미국 adverse possession 판례」, 「독일 BGH Mietminderung 판결」 → `case-search` 스킬

## 스킬

| 스킬 | 하는 일 |
|---|---|
| `intent-brief` | 의도 기반 민사 준비서면·답변서 초안 + 의도대응표 |
| `case-search` | 판례·법령 검색 — 법제처(법령·조문·판례·헌재·법령해석례), 빅케이스(전문·유사 판례·서술문 검색·결정례/행정심판), 미국·독일 판례 |
| `certified-letter` | 내용증명 초안(.docx) |
| `complaint-drafter` | 형사 고소장 초안(.docx) |
| `criminal-settlement` | 형사 합의서(.docx, Node `docx` 패키지) |
| `fact-confirmation` | 사실확인서(.docx) |
| `criminal-procedure-simulator` | 형사절차 단계별 안내·시각화 |
| `sentencing-predictor` | 양형기준 기반 양형 예측 |
| `brainstorming-lawfirm` | IRAC·레드팀·위험 점수표·전략 선택지 내부 메모 |
| `review-contract` | 한국법 계약서 검토(플레이북 대비 GREEN·YELLOW·RED, 수정 문안) |
| `triage-nda` | 비밀유지계약 빠른 분류 |
| `litigation-calc` | 법정기간 만료일·인지액·송달료·지연손해금, 기한 D-day 점검 |
| `independent-review` | 제출 전 독립 검토(지적만) |
| `site-api` | URL → Scrapling API 클라이언트 |

명령(키·비밀번호는 모두 입력 창으로 받고 채팅으로 받지 않습니다. 입력 창을 띄우지 못하면 「취소」와 구별해 알립니다. Codex 에서는 같은 이름의 스킬로 바뀝니다):
- `/lawfirm:law-key-setup` — 법제처 OC 키(인자 `us` 면 CourtListener 토큰도)
- `/lawfirm:case-search-setup` — 빅케이스 이메일·비밀번호(OS 키체인)

세션 시작 훅: Claude Code·Codex 마다 처음 한 번 위 고지(①②③)의 요약을 보여 주고(작업 폴더 notice.json 에 기록, 문구가 바뀌면 다시), 사건메모 「주요 일정」에서 14일 안의 기한·기일을 알립니다(`hooks/hooks.json`). 사건 폴더를 모아 둔 폴더를 한 번 등록하면 됩니다 — 「다가오는 기한 점검하게 <폴더> 등록해 줘」. 다가오는 것이 없으면 아무것도 출력하지 않습니다.

법률 문서 스킬 6종은 thechain.lawyer(이영남 변호사 사무소)의 스킬입니다(MIT). 법령·판례 조회는 이 플러그인의 법제처 직접 호출을 쓰고(`references/law-lookup.md`), 산출물 끝에는 유의사항 1문장만 붙습니다 — 상담 안내는 사용 변호사가 자기 사무소 정보를 넣었을 때만 붙습니다(`references/cta-config.md`, 작업 폴더의 office.json). 원저작 출처는 이 문단에만 적습니다. 계약 검토·NDA 분류·위험 점수표는 Anthropic knowledge-work-plugins 의 legal 스킬(Apache-2.0) 구조를 한국법으로 다시 썼습니다 — [고지](third_party/anthropic-legal/NOTICE.md).

## 지원 범위 (0.8.1)

- `intent-brief` 서면: 민사 준비서면(원고·피고), 답변서(피고). 소장·항소이유서·가사·행정은 범위 밖(형사 문서는 위 법률 문서 스킬).
- `case-search`: 법제처·빅케이스·미국·독일. LBOX 는 준비 중(정찰 자료 `docs/case-search/lbox/`).
- `litigation-calc` 공휴일 표: 2024–2028(한국천문연구원 특일정보, 2026-10-15 생성). 범위 밖 연도·임시공휴일은 경고와 함께 토·일만 반영하니 `--holiday` 로 더하십시오. 공시송달·외국 송달의 효력 발생일, 소가 산정, 1회분 송달료 단가는 계산하지 않습니다.
- 환경: Claude Code·Codex on macOS·Windows(Windows Codex 는 기한 알림을 PowerShell 로 실행 — `py` → `python3` → `python` 순서). Cowork 는 아직 지원하지 않습니다.

## 데이터 위치

- 초안·대응표: 사건 폴더(지정한 폴더)에 `YYMMDD_<약칭>_<서면>_vN.docx`, `내부_…_의도대응표.docx`. 기존 파일은 덮어쓰지 않습니다.
- 인터뷰 상태·중간 초안·인용 응답·사건메모 사본: 작업 폴더 — macOS `~/.intent-brief/`, Windows `%LOCALAPPDATA%\intent-brief\`. 의뢰인 정보가 들어 있으니 끝난 사건은 지우십시오:
  `python <플러그인>/skills/intent-brief/scripts/state.py purge <사건폴더>` (전부: `--all`). 플러그인을 지워도 이 폴더는 남습니다.
- 사건 폴더에 `사건메모.md`(업무관리 하네스 형식)가 있으면 진행 경과·할 일을 diff 확인 후 기록합니다. 없으면 기록하지 않습니다.
- 사용 통계: 작업 폴더의 상태 파일에서만 셉니다 — `python <플러그인>/skills/intent-brief/scripts/intent.py stats` 가 허용 필드 7개(사건 수·의도×측·덮어쓴 칸·평균 질문 라운드·빠른 경로 비율·플러그인 판·집계 기간) 요약과 복사용 블록을 냅니다. 사건 폴더 이름·자유 입력은 넣지 않고(목록 밖 값은 other), 플러그인은 이 통계를 네트워크로 보내지 않습니다. 기본값·의도 목록 개선에 보태 주시려면 출력의 `share.mailto` 링크로 메일 앱을 열어(또는 복사용 블록을 inter349@gmail.com 으로) 내용을 확인한 뒤 직접 보내 주십시오 — 보낼지는 선택이고, 사건이 0건이면 링크가 나오지 않습니다.
- 빅케이스: 이메일 `~/.case-search/bigcase/config.json` · 비밀번호 OS 키체인(서비스 `case-search-bigcase`) · 토큰 `~/.case-search/bigcase/session.json`(두 파일 모두 macOS·Linux 는 이 PC 사용자만 읽게 권한 0600). 환경변수 `BIGCASE_ID`/`BIGCASE_PW` 가 있으면 키체인보다 우선하고, `CASE_SEARCH_HOME` 으로 보관 폴더를 바꿉니다. 지우기: `uv run <플러그인>/skills/case-search/scripts/bigcase.py forget`.
- 계약 검토 플레이북: 작업 폴더의 playbooks 폴더(playbook-contract.md·playbook-nda.md — 만들기 전에는 번들 기본값을 씀. 의뢰인별 기준은 `playbooks/<의뢰인>/`, `--profile <의뢰인>`). 기한 점검 등록 폴더 목록: 작업 폴더의 dday.json. `site-api` 가 만든 클라이언트·세션: 작업 폴더 `site-api/`(자격증명은 키체인 `site-api-<이름>`).
- 해외 판례 토큰: `~/.case-search/foreign.json`(macOS·Linux 는 이 PC 사용자만 읽게 권한 0600). 환경변수 `COURTLISTENER_API_TOKEN` 이 있으면 먼저 씁니다. 지우기: `python <플러그인>/skills/case-search/scripts/foreigncase.py key clear us`.

## 원격 서버 의존

조문·판례 대조는 **법제처 Open API 를 직접** 부릅니다(중계 서버·MCP 없음). 각자 자기 키(OC)가 필요합니다 — https://open.law.go.kr 에서 회원가입 → OPEN API 사용 신청(법령·판례)을 하고 받은 OC 값을 `/lawfirm:law-key-setup` 이 띄우는 입력 창에 넣으면 키 오류 검사(판례 1건 조회)를 통과한 뒤 저장합니다(채팅에 적지 않습니다). 키는 작업 폴더의 config.json 에 저장합니다(macOS `~/.intent-brief/config.json` 은 이 PC 사용자만 읽게 권한 0600, Windows `%LOCALAPPDATA%\intent-brief\config.json` 은 파일 권한을 따로 바꾸지 않음). 키 값은 출력·캐시·오류 문구에 쓰지 않습니다. 신청 때 이 PC 의 IP 주소 등록을 요구할 수 있습니다. 환경변수 `INTENT_BRIEF_LAW_OC`·`LAW_API_OC` 가 있으면 그 값을 먼저 씁니다. 법제처가 응답하지 않으면 초안 작성은 계속되고 인용에 `[법제처 장애 — 미확인]` 이 붙습니다.

**빅케이스 자동 연결**: `/lawfirm:case-search-setup` 으로 빅케이스에 로그인해 두면 민사 서면 인용 대조에도 따로 설정 없이 연결됩니다. 법제처에 원문이 없는 판례(예: 2014다26187)는 빅케이스에서 같은 사건번호를 한 번 찾아 「빅케이스 확인」으로 표시하고(「확인됨」과 구분), 쟁점 정리 때 판례 후보 검색에도 씁니다.

**해외 판례**: 미국 CourtListener(Free Law Project)·독일 OpenLegalData 공개 API 를 직접 부릅니다. 검색은 둘 다 익명으로 되고, 미국 판결문 본문만 CourtListener 토큰이 필요합니다. 본문은 번역 없이 원문 언어로 8,000자씩 이어 읽습니다.

**빅케이스 이용 범위**: 본인 빅케이스 계정으로, 사람이 화면에서 찾는 정도의 빈도로만 씁니다. 로그인 토큰은 `https://bigcase.ai` 로만 보내고 다른 주소로 가는 요청은 거부합니다. 대량 수집·페이지 끝까지 넘기기·재배포는 하지 않습니다. 로그인하지 않으면 하급심 판결은 이유가 앞부분만 오고(`restricted`), 주석서 본문·양형 통계는 계정 권한이 없으면 403 이라 명령을 두지 않았습니다.

## 개발

```
uv run --no-project --with pytest --with python-docx==1.2.0 pytest tests/
uv run --no-project --with "scrapling[fetchers]>=0.4.11,<0.5" --with "keyring>=25,<26" --with pytest --with python-docx==1.2.0 pytest tests/case_search -q
```
런타임 스크립트는 표준 라이브러리만 씁니다(테스트로 확인) — 예외는 uv inline 의존성을 쓰는 `bigcase.py`·`site-api` 의 `discover.py`·생성 클라이언트. 빅케이스 스크립트(`skills/case-search/scripts/bigcase.py`)는 uv inline 의존성(Scrapling·keyring)을 씁니다. API 형식 근거·실측 기록은 `docs/case-search/bigcase-api.md`. `dev/` 는 개발 전용입니다. 개발 지도·불변 조건은 [AGENTS.md](AGENTS.md).

## 변경 이력

- **0.8.1 (2026-10-18)** — 「미국 연방대법원 ○○ 판결문 본문 인용」처럼 미국 판결문 원문을 묻는 질문에서 case-search 가 선택되도록 트리거를 보강했습니다(시험 질문 12개에서 선택 0 → 12). CourtListener 토큰이 없어 미국 판결문 본문을 받지 못하면 판결문 문장을 기억으로 인용하지 않고, 검색 결과의 판례명·인용·URL·발췌만 씁니다.
- **0.8.0 (2026-10-18)** — Claude Code·Codex 마다 첫 세션에 한 번 사용 고지(변호사 업무 보조용 · 사건 자료가 모델 제공자에게 전송됨 · 작업 폴더 지우기)를 보여 줍니다. 법률 문서 스킬 6종의 산출물 끝에는 유의사항 1문장만 붙고, 상담 안내는 사용 변호사가 자기 사무소 정보(office.json)를 넣었을 때만 붙습니다. 의도대응표에서 법제처 원문과 대조해 확인된 인용에 원문 링크를 붙입니다. 법제처·빅케이스 응답 형식이 바뀌면 0건으로 넘기지 않고 「형식 변경」으로 알리며 업데이트 안내를 붙입니다. 빅케이스 판결 선고일이 원문에 없으면 확인됨으로 올리지 않습니다. 사용 통계 요약을 허용 필드 7개로 좁히고 그대로 붙여 넣을 공유 블록을 더했습니다. 계약 검토·NDA·양형 예측·사이트 API 등 스킬 7개에 외부 장애·키 없음·자료 없음 처리 문장을 보강했습니다. Node·docx 확인 명령을 한 줄로 맞췄습니다.
- **0.7.0 (2026-10-16)** — Codex 에서도 설치됩니다(`.codex-plugin/plugin.json`·`.agents/plugins/marketplace.json`, 위 「Codex」). 세션 시작 기한 알림이 두 도구가 다 받는 JSON 으로 나오고, 점검 자체가 실패하면 「점검하지 못했습니다」를 알립니다. Codex 샌드박스가 네트워크를 막으면 법제처 장애가 아니라 `network_blocked` 로, 작업 폴더 쓰기를 막으면 `sandbox_write_blocked` 와 설정 방법으로 알립니다(인용 대조가 장애로 넘어가지 않음). 키·계정 입력 창을 띄우지 못한 경우를 「취소」와 구별합니다. 사이트 API 발굴에 Windows Chrome 실행 명령을 넣었습니다. Codex 검토 지적 11건을 고쳤습니다: 서식 내려받기가 오류 페이지를 저장하던 문제, 이율 바뀌는 날 이자를 두 번 세던 문제, 콘텐츠 컨트롤 안 docx 문단을 못 읽던 문제, 「~~옛 날짜~~ 새 날짜」 정정 기한을 놓치던 문제, 사건이 많으면 기한 점검이 말없이 일부를 건너뛰던 문제(이제 경고), 의뢰인별 계약 검토 기준(`--profile`), 생성한 사이트 클라이언트가 다른 사이트 세션을 쓰거나 응답 속 토큰을 출력하던 문제 등.
- **0.6.0 (2026-10-15)** — 새 스킬 6개: `brainstorming-lawfirm`(IRAC·레드팀·위험 점수표), `litigation-calc`(법정기간 만료일·인지액·송달료·지연손해금, 기한 D-day 점검과 세션 시작 알림), `review-contract`·`triage-nda`(한국법 계약서 검토·NDA 분류), `independent-review`(지적만 하는 독립 검토), `site-api`(URL → Scrapling 클라이언트). 법률 문서 스킬 6종에 구성안 승인 단계를 넣었습니다. case-search 에 법제처 별표·서식 조회와 서식 파일 내려받기를 넣었고, 조문의 호·목이 빠지던 문제, 「상법」처럼 검색 결과 뒤쪽에 있는 법령을 못 찾던 문제, 조 번호 없는 한 문장 법령(예: 소송촉진법 법정이율 규정)을 읽지 못하던 문제를 고쳤습니다.
- **0.5.0 (2026-10-15)** — case-search 에 법제처 조회(법령·조문·판례·헌재결정·법령해석례·행정규칙·용어)와 해외 판례(미국 CourtListener·독일 OpenLegalData)를 넣었습니다. 빅케이스 계정이 없으면 법제처·해외 판례만 씁니다. 법제처 키·CourtListener 토큰을 `/lawfirm:law-key-setup` 입력 창으로 받아 저장합니다(명령행 인자로 받던 경로는 없앴습니다).
- **0.4.0 (2026-10-15)** — 이름을 lawfirm 으로 정하고 판례 검색(case-search)을 넣었습니다. 빅케이스 인증 정보를 bigcase.ai 밖으로 보내지 않게 막았고, 한국어 Windows 콘솔(cp949)에서 판례 조회 결과가 깨지던 문제를 고쳤습니다.
- **0.3.0 (2026-10-15, 중간판 0.2.0 과 함께 공개)** — 의도 유불리 검토 라운드(0.2.0), 법제처 Open API 직접 호출(k-data MCP 폐지), 빅케이스 자동 연결, 법률 문서 스킬 6종 내장.
- **0.1.0 (2026-10-14)** — 의도 기반 민사 준비서면·답변서 첫 공개.

## 라이선스

MIT
