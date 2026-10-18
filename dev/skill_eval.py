"""개발 전용 짝지은 평가(FR-27) — 같은 과제를 스킬 있음·없음으로 돌려 통과율 차이를 환경(Claude Code·Codex)별로 잰다.

과제 6개 = intent-brief 3(IB1 F1A 전부 승소 준비서면 · IB2 F1B 조정 유도 준비서면 · IB3 F2B 손해 최소화 답변서)
         + case-search 3(CS1 민사소송법 제288조 원문 · CS2 대법원 2016다225353 판결요지 · CS3 녹화 밖 2019다12345).
두 조건은 플러그인이 있느냐만 다르다.
  Claude: 둘 다 새 CLAUDE_CONFIG_DIR(설치 플러그인·사용자 훅 0) + edb 토큰, 있음만 `--plugin-dir <repo>`.
  Codex: 둘 다 새 CODEX_HOME(인증 사본), 있음만 로컬 마켓플레이스로 lawfirm 설치.
intent-brief 는 인터뷰·설계 확인(1–4단계)을 replay.py 로 모델 없이 똑같이 끝낸 뒤 초안만 모델이 쓴다 —
있음은 replay 의 DRAFT_PROMPT(SKILL.md 5–7단계·스크립트), 없음은 같은 입력·같은 금지 사항에 스크립트 언급만 뺀 지시.
case-search 는 두 조건에 같은 질문을 준다. 웹 도구(WebFetch·WebSearch)는 두 조건 모두 끈다(Claude).
에이전트는 두 조건 모두 실행 폴더의 빈 HOME 으로 돌린다(개인 스킬 ~/.agents·~/.claude/skills 가 안 보이게 — Codex 는
~/.agents/skills 를 스스로 싣는다). 두 조건 공통 PreToolUse 훅(`guard`)이 법제처·빅케이스·루프백 밖 URL·개인 스킬·
repo 밖 workspace 접근을 막고, judge 전에 실행 기록의 실제 명령을 다시 센다(차단이 완전하지 않으므로 이중 확인).
평가 환경변수(재생 서버 주소·빅케이스 차단)는 플러그인 스크립트용이라 스킬 있음 조건에만 준다.
법제처는 실행마다 루프백 재생 서버(drf_replay), 빅케이스는 없는 키체인 서비스·빈 세션 폴더로 막는다(실서비스 0).
판정(judge)은 서면 형식(앵커)에 기대지 않는 같은 기준표로 두 조건을 본다. Jev 는 쓰지 않는다.

FR-26 측정(--suite fr26)은 같은 구동기로 미국 판례 질의 12개를 스킬 있음 조건에서 한 번씩 돌린다. 비율 = 같은 대화의
`us-search` 결과에 그때까지 나오지 않은 `opinion_id` 로 부른 `us-opinion` 수 ÷ 전체 `us-opinion` 수(목표 0%). FR-27 과 달리
`us-search` 는 실제 CourtListener 를 익명으로 부른다(질의당 몇 건). CourtListener 토큰은 주지 않는다 — 본문 조회는 no_key 로
끝나지만 모델이 어떤 식별자로 불렀는지는 실행 기록에 남는다. 토큰 입력 창(`key set --prompt`)은 무인 실행을 멈추게 하므로 막는다.

사용:
  skill_eval.py run   --env claude|codex --out <repo·홈 밖 폴더> [--runs 3] [--jobs 4] [--only IB1 ...] [--arms with without]
                      [--model sonnet] [--max-calls 36] [--weekly-cap 0.95]      실행 전 예상 호출 수를 찍고 상한을 넘으면 시작 안 함
  skill_eval.py run   --env ... --resume <실행 폴더>                              같은 식별값 결과는 건너뛴다
  skill_eval.py run   --suite fr26 --env claude --out <repo·홈 밖 폴더>           FR-26(스킬 있음만 · 질의당 1회 · 상한 12회)
                      [--invoke explicit]                                       질문 앞에 /lawfirm:case-search — 자동 선택과 따로 잰다
  skill_eval.py judge --out <실행 폴더> [<실행 폴더> ...]                          기준표 판정·통과율 표(judge.json)
"""
import argparse
import concurrent.futures as cf
import glob
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import drf_replay  # noqa: E402
import e2e  # noqa: E402
import replay as R  # noqa: E402

ARMS = ("with", "without")
ASK = " 질문하지 말고 답만 하세요. 파일을 만들지 마세요."
SCENARIOS = {
    "IB1": {"skill": "intent-brief", "combo": "F1A"},
    "IB2": {"skill": "intent-brief", "combo": "F1B"},
    "IB3": {"skill": "intent-brief", "combo": "F2B"},
    "CS1": {"skill": "case-search",
            "question": "민사소송법 제288조의 조문을 법제처 원문 그대로 인용해 주세요. 원문을 확인하지 못했으면 그렇다고 밝혀 주세요.",
            "expect": "법원에서 당사자가 자백한 사실과 현저한 사실은 증명을 필요로 하지 아니한다. 다만, 진실에 어긋나는 자백은 "
                      "그것이 착오로 말미암은 것임을 증명한 때에는 취소할 수 있다."},
    "CS2": {"skill": "case-search",
            "question": "대법원 2016다225353 판결의 판결요지를 법제처 원문 그대로 알려 주세요. 원문을 확인하지 못했으면 그렇다고 밝혀 주세요.",
            "expect": "예비적 청구는 주위적 청구와 서로 양립할 수 없는 관계에 있어야 하므로, 주위적 청구와 동일한 목적물에 관하여 "
                      "동일한 청구원인을 내용으로 하면서 주위적 청구를 양적이나 질적으로 일부 감축하여 하는 청구는 주위적 청구에 "
                      "흡수되는 것일 뿐 소송상의 예비적 청구라고 할 수 없다."},
    "CS3": {"skill": "case-search",
            "question": "대법원 2019다12345 판결의 판결요지를 법제처 원문 그대로 알려 주세요. 원문을 확인하지 못했으면 그렇다고 밝혀 주세요.",
            "expect": None},
}
# FR-26 — 본문 문장을 원문 그대로 요구해 `us-opinion` 을 부를 이유를 준다(판례명·인용만으로는 답이 안 된다)
_US = [("US01", "Miranda v. Arizona", "구금 피의자 신문 전에 고지해야 할 권리"),
       ("US02", "Brown v. Board of Education of Topeka", "분리된 교육 시설은 본질적으로 불평등하다는 결론"),
       ("US03", "Marbury v. Madison", "무엇이 법인지 말하는 것은 사법부의 권한이자 의무라는 부분"),
       ("US04", "Gideon v. Wainwright", "가난한 피고인에게 변호인을 붙여 주는 권리"),
       ("US05", "New York Times Co. v. Sullivan", "공직자 명예훼손의 「현실적 악의(actual malice)」 기준"),
       ("US06", "Chevron U.S.A. Inc. v. Natural Resources Defense Council", "행정청 법 해석 존중의 두 단계 심사"),
       ("US07", "Loper Bright Enterprises v. Raimondo", "Chevron 판례를 폐기한다는 결론"),
       ("US08", "Obergefell v. Hodges", "동성 커플의 혼인할 권리"),
       ("US09", "Tinker v. Des Moines Independent Community School District", "학생도 교문에서 헌법상 권리를 잃지 않는다는 부분"),
       ("US10", "Celotex Corp. v. Catrett", "약식판결(summary judgment)에서 신청인의 입증 부담"),
       ("US11", "Bell Atlantic Corp. v. Twombly", "소장의 「그럴듯함(plausibility)」 기준"),
       ("US12", "Mapp v. Ohio", "위법수집증거 배제 원칙을 주 법원에 적용한다는 결론")]
US_SCENARIOS = {sid: {"skill": "case-search-us",
                      "question": "미국 연방대법원 %s 판결문 본문에서 %s 부분을 영어 원문 그대로 한두 문장 인용하고, 판례명과 "
                                  "인용(citation)을 밝혀 주세요. 원문을 확인하지 못했으면 그렇다고 밝혀 주세요." % (name, topic)}
                for sid, name, topic in _US}
SUITES = {"fr27": SCENARIOS, "fr26": US_SCENARIOS}
# fr26 은 한 번에 하나 — 익명 CourtListener 는 동시 4건에서 429(rate_limited)를 돌려줬다(2026-10-18 실측)
SUITE_DEFAULTS = {"fr27": {"arms": ARMS, "runs": 3, "max_calls": 36, "jobs": 4},
                  "fr26": {"arms": ("with",), "runs": 1, "max_calls": 12, "jobs": 1}}
ALL_SCENARIOS = dict(SCENARIOS, **US_SCENARIOS)
# 녹화(재생 서버)에 있는 사건번호 — 이 밖의 사건번호는 확인 표시(hedge)가 같은 문단에 있어야 한다
RECORDED_CASES = {k[5] for k in drf_replay.ROUTES if k[5]}
HEDGE = ("확인 필요", "미확인", "확인되지", "확인하지 못", "확인할 수 없")
NOT_FOUND = ("찾지 못", "찾을 수 없", "확인되지 않", "확인할 수 없", "확인하지 못", "조회되지 않", "결과가 없", "존재하지 않")
HOLDING = ("[1]", "판시하였", "판시했", "판시한", "라고 판단", "【판결요지】", "요지는 다음")
# 두 조건 공통 차단(PreToolUse 훅) — 실서비스(법제처·빅케이스·루프백 밖 URL)와 개인 스킬·workspace(이 repo 밖) 접근
_GUARD = re.compile(r"law\.go\.kr|bigcase\.ai|https?://(?!127\.0\.0\.1|localhost)|\.agents/|/\.claude/|k-public-data|kpd\.py"
                    r"|/Users/[^/\s\"']+/workspace/(?!ProjectLawFirm/lawfirm)"
                    r"|\bkey\s+(?:set|clear)\b|law-key-setup")  # 토큰 입력 창은 무인 실행을 멈춘다
AUDIT = ("law.go.kr", "WebFetch", "WebSearch", "curl ", "lawapi.py", "cite_check.py", "SKILL.md", "bigcase")
_CASE = re.compile(r"(?<!\d)(\d{4}|\d{2})\s*(가합|가단|가소|구합|구단|고합|고단|고정|카합|카단|재다|나|다|라|마|그|두|누|도|노|므|르|드|스|브|후|허)"
                   r"\s*(\d{1,7})(?!\d)")
CODEX_AUTH = os.environ.get("SKILL_EVAL_CODEX_AUTH") or os.path.expanduser("~/.codex/auth.json")
TOKEN_FILE = os.environ.get("INTENT_BRIEF_TOKEN_FILE") or os.path.expanduser("~/.claude/tokens/edb")
FOREIGN_TOKENS = ("COURTLISTENER_API_TOKEN", "OPENLEGALDATA_API_TOKEN")
FOREIGNCASE = os.path.join(REPO, "skills", "case-search", "scripts", "foreigncase.py")


class EvalError(Exception):
    pass


def nows(s):
    return re.sub(r"\s+", "", s or "")


# ── 환경·명령 조립 ──
def eval_env(url, run_dir):
    env = R.replay_env(url)
    env.update(BIGCASE_KEYRING_SERVICE="lawfirm-skill-eval-none", CASE_SEARCH_HOME=os.path.join(run_dir, "case-search-home"),
               INTENT_BRIEF_TODAY=R.TODAY)
    return env


def agent_vars(arm, ev):
    """에이전트 프로세스에 줄 평가 환경변수 — 플러그인 스크립트용 손잡이라 스킬 없음 조건에는 주지 않는다."""
    return dict(ev) if arm == "with" else {}


def guard_blocked(payload):
    inp = payload.get("tool_input")
    text = inp if isinstance(inp, str) else json.dumps(inp, ensure_ascii=False)
    return bool(_GUARD.search(text or ""))


def guard_hooks():
    cmd = "%s %s guard" % (shlex.quote(sys.executable), shlex.quote(os.path.abspath(__file__)))
    return {"hooks": {"PreToolUse": [{"hooks": [{"type": "command", "command": cmd}]}]}}


def skill_dirs_above(path):
    """path 의 상위 폴더에 있는 개인 스킬 폴더 — Claude Code 는 작업 폴더에서 위로 올라가며 .claude/skills 를 프로젝트 스킬로 싣는다."""
    found, cur = [], os.path.abspath(path)
    while True:
        for name in (".claude", ".agents"):
            if os.path.isdir(os.path.join(cur, name, "skills")):
                found.append(os.path.join(cur, name))
        parent = os.path.dirname(cur)
        if parent == cur:
            return found
        cur = parent


def _real_dirs():
    return {"UV_CACHE_DIR": os.path.expanduser("~/.cache/uv"),
            "UV_PYTHON_INSTALL_DIR": os.path.expanduser("~/.local/share/uv/python")}


def claude_bin():
    if os.environ.get("SKILL_EVAL_CLAUDE"):
        return os.environ["SKILL_EVAL_CLAUDE"]
    vers = glob.glob(os.path.expanduser("~/.local/share/claude/versions/*"))
    key = lambda v: [int(x) if x.isdigit() else 0 for x in os.path.basename(v).split(".")]  # noqa: E731
    return max(vers, key=key) if vers else "claude"  # 래퍼(~/.local/bin/claude)는 실제 HOME 을 요구한다


def claude_cmd(arm, model, claude="claude"):
    cmd = [claude, "-p", "--output-format", "stream-json", "--verbose", "--permission-mode", "bypassPermissions",
           "--disallowedTools", "WebFetch,WebSearch", "--model", model]
    return cmd + (["--plugin-dir", REPO] if arm == "with" else [])


def claude_env(run_dir, ev, base, token_file):
    if not os.path.exists(token_file):
        raise EvalError("무인 claude -p 토큰 파일이 없습니다: %s" % token_file)
    env = dict(base)
    env.update(_real_dirs())
    env.update(ev)
    for k in FOREIGN_TOKENS:  # 개발 PC 의 해외 판례 토큰을 물려주지 않는다
        env.pop(k, None)
    env["CLAUDE_CONFIG_DIR"] = os.path.join(run_dir, "claude-config")  # 설치 플러그인·사용자 훅을 싣지 않는다
    env["HOME"] = os.path.join(run_dir, "agent-home")  # 개인 스킬(~/.agents·~/.claude/skills)이 안 보이게
    env["CLAUDE_CODE_OAUTH_TOKEN"] = open(token_file, encoding="utf-8").read().strip()
    return env


def codex_config(ev):
    lines = ["[features]", "hooks = true", "", "[shell_environment_policy]", 'inherit = "all"', "",
             "[shell_environment_policy.set]"]  # KEY 가 든 이름은 기본 제외 대상이라 명시적으로 넣는다
    lines += ["%s = %s" % (k, json.dumps(v)) for k, v in sorted(ev.items())]
    return "\n".join(lines) + "\n"


def codex_cmd(run_dir, prompt, codex="codex"):
    return [codex, "exec", "-C", run_dir, "--skip-git-repo-check", "--dangerously-bypass-approvals-and-sandbox",
            "--dangerously-bypass-hook-trust", "--json",
            "-o", os.path.join(run_dir, "last.txt"), prompt]


def cs_prompt(sid):
    return SCENARIOS[sid]["question"] + ASK


def scenario_prompt(sid, invoke="auto"):
    """invoke=explicit 은 스킬을 슬래시 명령으로 부른다 — 자동 선택(트리거)과 스킬 안 규칙 준수를 따로 재기 위해."""
    p = ALL_SCENARIOS[sid]["question"] + ASK
    return "/lawfirm:%s %s" % (ALL_SCENARIOS[sid]["skill"].replace("-us", ""), p) if invoke == "explicit" else p


NEUTRAL_DRAFT = """민사 {brief} 초안을 쓴다. 의뢰인 쪽 변호사와 인터뷰해 정한 서면 설계(의도·쟁점별 입장·결론 방향)가 아래 design.json 에 있다 — 질문하지 말고, 사용자 확인을 기다리지 말고 초안을 끝까지 쓴다.

- design.json: {design}
- 원자료(사건 폴더, 읽기만): {case}
- 초안을 쓸 경로(Markdown): {draft}
- 사건 폴더나 다른 곳에 파일을 만들지 않는다.
끝나면 한 줄로 「완료」만 답한다."""


def ib_prompt(arm, brief, design, case, draft, wd, lawenv):
    if arm == "with":
        return R.DRAFT_PROMPT.format(brief=brief, design=design, case=case, draft=draft, scripts=R.SCRIPTS,
                                     py=sys.executable, wd=wd, lawenv=lawenv)
    return NEUTRAL_DRAFT.format(brief=brief, design=design, case=case, draft=draft)


# ── 기준표(두 조건 공통, 서면 앵커와 무관) ──
def extract_cases(text):
    return {"%s%s%s" % m.groups() for m in _CASE.finditer(text or "")}


def citation_ok(text, allowed):
    bad = []
    for para in re.split(r"\n\s*\n", text or ""):
        if any(h in para for h in HEDGE):
            continue
        bad += [c for c in extract_cases(para) if c not in allowed]
    return not bad, sorted(set(bad))


def _any(t, words):
    return any(w in t for w in words)


def has_amount(t, man):
    """금액 표기 차이(5,000만·5000만·5천만·50,000,000원)를 같은 금액으로 본다 — man 은 만 원 단위."""
    won = man * 10000
    forms = ["{:,}만".format(man), "%d만" % man, "{:,}".format(won), "%d" % won]
    if man % 1000 == 0:
        forms.append("%d천만" % (man // 1000))
    return any(re.search(r"(?<![\d,])%s(?![\d,])" % re.escape(f), t) for f in forms)


def ib_rubric(sid, text, allowed):
    ph = e2e.P.load_phrases()
    deny, admit = ph["stance_markers"]["deny"], ph["stance_markers"]["admit"]
    t = text or ""
    combo = SCENARIOS[sid]["combo"]
    if combo == "F1A":
        r2 = has_amount(t, 5000) and _any(t, deny) and ("인용" in t or "지급하라" in t)
    elif combo == "F1B":
        r2 = "조정" in t and has_amount(t, 4000) and _any(t, admit)
    else:
        r2 = all(w in t for w in ("주위적", "예비적", "공제")) and _any(t, admit)
    r3, bad = citation_ok(t, RECORDED_CASES | set(allowed))
    r = {"R1": len(nows(t)) >= 500, "R2": bool(r2), "R3": r3, "unverified": bad}
    r["pass"] = r["R1"] and r["R2"] and r["R3"]
    return r


def cs_rubric(sid, text):
    t = text or ""
    exp = SCENARIOS[sid]["expect"]
    if exp:
        return {"pass": nows(exp) in nows(t)}
    found, holding = _any(t, NOT_FOUND), _any(t, HOLDING)
    return {"pass": found and not holding, "not_found": found, "holding": holding}


def audit_events(text):
    return {k: (text or "").count(k) for k in AUDIT}


_US_OPINION = re.compile(r"\bus-opinion\s+(\S+)")
_OPINION_IDS = re.compile(r'"opinion_ids"\s*:\s*\[([^\]]*)')  # 닫는 괄호가 잘린 출력(head)도 읽는다
_CLUSTER_ID = re.compile(r'"cluster_id"\s*:\s*(\d+)')
_FOR = re.compile(r"\bfor\s+(\w+)\s+in\s+([^;]+?)\s*;\s*do\b")
_HOST = re.compile(r"https?://([^/\s\"'\\]+)")


def _blocks(text):
    for line in (text or "").splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        content = ((ev.get("message") or {}).get("content")) if isinstance(ev, dict) else None
        for b in content if isinstance(content, list) else []:
            if isinstance(b, dict):
                yield b


def _result_text(b):
    c = b.get("content")
    if isinstance(c, list):
        return "\n".join(x.get("text") or "" for x in c if isinstance(x, dict))
    return c or ""


def _opinion_args(cmd):
    """`us-opinion` 인자 — `for id in 1 2; do … us-opinion $id` 처럼 단순 반복문의 변수는 목록으로 펼친다."""
    loops = {v: items.split() for v, items in _FOR.findall(cmd)}
    out = []
    for arg in _US_OPINION.findall(cmd):
        arg = arg.strip("\"'\\;")
        var = re.fullmatch(r"\$\{?(\w+)\}?", arg)
        out += loops[var.group(1)] if var and var.group(1) in loops else [arg]
    return out


def us_audit(text):
    """FR-26 — Claude 실행 기록을 순서대로 읽어 `us-opinion` 식별자가 그때까지의 `us-search` 결과에 있었는지 본다."""
    seen, clusters, searches = set(), set(), set()
    r = {"searches": 0, "opinions": 0, "violations": [], "cluster_ids": [], "unparsed": [], "no_key": 0, "direct": 0}
    hosts = set()
    for b in _blocks(text):
        if b.get("type") == "tool_use":
            inp = b.get("input")
            cmd = inp.get("command") if isinstance(inp, dict) and isinstance(inp.get("command"), str) else json.dumps(inp, ensure_ascii=False)
            ext = [h for h in _HOST.findall(cmd) if not h.startswith(("127.0.0.1", "localhost"))]
            r["direct"] += len(ext)  # 스킬을 거치지 않은 외부 주소 시도(차단 훅이 막는다)
            hosts.update(ext)
            if "foreigncase" not in cmd:
                continue
            if "us-search" in cmd:
                r["searches"] += 1
                searches.add(b.get("id"))
            for oid in _opinion_args(cmd):
                r["opinions"] += 1
                if not oid.isdigit():
                    r["unparsed"].append(oid)
                if oid not in seen:
                    r["violations"].append(oid)
                    if oid in clusters:
                        r["cluster_ids"].append(oid)
        elif b.get("type") == "tool_result":
            out = _result_text(b)
            r["no_key"] += out.count('"no_key"')
            if b.get("tool_use_id") in searches:
                for group in _OPINION_IDS.findall(out):
                    seen.update(re.findall(r"\d+", group))
                clusters.update(_CLUSTER_ID.findall(out))
    r["direct_hosts"] = sorted(hosts)
    return r


def us_summary(rows):
    n = sum(r["opinions"] for r in rows)
    v = sum(len(r["violations"]) for r in rows)
    return {"opinions": n, "violations": v, "ratio": round(v / n, 2) if n else None}  # 0회는 0% 가 아니다


# ── 실행 1건 ──
def _report(rd):
    f = os.path.join(rd, "report.json")
    return json.load(open(f, encoding="utf-8")) if os.path.exists(f) else None


def _name(job):
    return "%s_%s_r%d" % job


def run_claude(run_dir, arm, prompt, ev, model):
    cmd = claude_cmd(arm, model, claude=claude_bin())
    env = claude_env(run_dir, ev, os.environ, TOKEN_FILE)
    os.makedirs(env["HOME"], exist_ok=True)
    os.makedirs(env["CLAUDE_CONFIG_DIR"], exist_ok=True)
    json.dump(guard_hooks(), open(os.path.join(env["CLAUDE_CONFIG_DIR"], "settings.json"), "w", encoding="utf-8"))
    p = subprocess.run(cmd, input=prompt.encode("utf-8"), env=env, capture_output=True, cwd=run_dir, timeout=1800)
    open(os.path.join(run_dir, "agent.jsonl"), "wb").write(p.stdout)
    open(os.path.join(run_dir, "agent.err"), "wb").write(p.stderr)
    out = {"rc": p.returncode, "final": None, "cost_usd": None, "is_error": None, "turns": None}
    for line in p.stdout.decode("utf-8", "replace").splitlines():
        try:
            ev_ = json.loads(line)
        except ValueError:
            continue
        if ev_.get("type") == "result":
            out.update(final=ev_.get("result"), cost_usd=ev_.get("total_cost_usd"), is_error=ev_.get("is_error"),
                       turns=ev_.get("num_turns"))
    return out


def run_codex(run_dir, arm, prompt, ev):
    codex = os.environ.get("SKILL_EVAL_CODEX", "codex")
    ch = os.path.join(run_dir, "codex-home")
    os.makedirs(ch)
    auth = os.path.join(ch, "auth.json")
    try:
        shutil.copyfile(CODEX_AUTH, auth)
        os.chmod(auth, 0o600)
        open(os.path.join(ch, "config.toml"), "w", encoding="utf-8").write(codex_config(ev))
        json.dump(guard_hooks(), open(os.path.join(ch, "hooks.json"), "w", encoding="utf-8"))
        env = dict(os.environ)
        env.update(_real_dirs())
        env.update(ev)
        for k in FOREIGN_TOKENS:
            env.pop(k, None)
        env["CODEX_HOME"] = ch
        env["HOME"] = os.path.join(run_dir, "agent-home")  # Codex 는 ~/.agents/skills 를 스스로 싣는다
        os.makedirs(env["HOME"], exist_ok=True)
        if arm == "with":
            for c in (["plugin", "marketplace", "add", REPO], ["plugin", "add", "lawfirm@lawfirm"]):
                q = subprocess.run([codex] + c, env=env, capture_output=True, timeout=120, cwd=run_dir)
                if q.returncode != 0:
                    raise EvalError("codex %s 실패: %s" % (" ".join(c[:2]), q.stderr.decode("utf-8", "replace")[-300:]))
        p = subprocess.run(codex_cmd(run_dir, prompt, codex=codex), env=env, capture_output=True, cwd=run_dir,
                           timeout=1800, stdin=subprocess.DEVNULL)
    finally:
        if os.path.exists(auth):
            os.remove(auth)  # 인증 사본은 실행 뒤 남기지 않는다
    open(os.path.join(run_dir, "agent.jsonl"), "wb").write(p.stdout)
    open(os.path.join(run_dir, "agent.err"), "wb").write(p.stderr)
    last = os.path.join(run_dir, "last.txt")
    usage = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}
    for line in p.stdout.decode("utf-8", "replace").splitlines():
        try:
            u = (json.loads(line).get("usage") or {})
        except (ValueError, AttributeError):
            continue
        for k in usage:
            usage[k] += int(u.get(k) or 0)
    return {"rc": p.returncode, "final": open(last, encoding="utf-8").read() if os.path.exists(last) else None,
            "usage": usage}


def run_one(env_name, run_dir, sid, arm, model, ident):
    os.makedirs(run_dir)
    sc = ALL_SCENARIOS[sid]
    invoke = ident.get("invoke", "auto")
    rep = {"env": env_name, "scenario": sid, "arm": arm, "ident": ident, "invoke": invoke, "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    srv = drf_replay.Server().start()
    t0 = time.time()
    try:
        ev = eval_env(srv.url, run_dir)
        if sc["skill"] == "intent-brief":
            fx, ans, brief, _ = e2e.COMBOS[sc["combo"]]
            case_dir = os.path.join(run_dir, "case", os.path.basename(fx))
            shutil.copytree(os.path.join(e2e.FX, fx), case_dir)
            R.EXTRA_ENV.clear()
            R.EXTRA_ENV.update(ev)  # 실행마다 별도 프로세스라 전역을 써도 섞이지 않는다
            state, design = R.interview(run_dir, case_dir, json.load(open(os.path.join(e2e.ANS, ans), encoding="utf-8")), brief)
            if not str(design).endswith(".json"):
                raise EvalError("인터뷰 재생이 설계에 이르지 못함: %s" % design)
            wd = os.path.dirname(state)
            draft = os.path.join(wd, "%s_draft.md" % brief)
            lawenv = " ".join("%s=%s" % (k, shlex.quote(v)) for k, v in sorted(ev.items()))
            prompt = ib_prompt(arm, brief=brief, design=design, case=case_dir, draft=draft, wd=wd, lawenv=lawenv)
            rep.update(case_dir=case_dir, design=design, draft=draft)
        else:
            prompt = scenario_prompt(sid, invoke)
        open(os.path.join(run_dir, "prompt.txt"), "w", encoding="utf-8").write(prompt)
        av = agent_vars(arm, ev)
        rep.update(run_claude(run_dir, arm, prompt, av, model) if env_name == "claude" else run_codex(run_dir, arm, prompt, av))
        rep["ok"] = rep["rc"] == 0
    except (EvalError, R.ReplayError, subprocess.TimeoutExpired, OSError) as e:
        rep.update(ok=False, error="%s: %s" % (type(e).__name__, e))
    finally:
        srv.stop()
        rep["drf_requests"] = srv.count
        rep["seconds"] = round(time.time() - t0, 1)
        cs_home = os.path.join(run_dir, "case-search-home")
        rep["bigcase_files"] = sorted(os.listdir(cs_home)) if os.path.isdir(cs_home) else []
    json.dump(rep, open(os.path.join(run_dir, "report.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return rep


# ── 실행 묶음 ──
def edb_weekly():
    """edb 계정 7일 사용률(마지막 기록 — ~/.claude/usage/edb.json). 리셋이 지났으면 0."""
    try:
        w = json.load(open(os.path.expanduser("~/.claude/usage/edb.json"), encoding="utf-8"))["windows"]["seven_day"]
    except (OSError, ValueError, KeyError):
        return None
    return 0.0 if w.get("resetsAt") and w["resetsAt"] < time.time() else float(w.get("utilization") or 0)


def us_precheck(folder):
    """FR-26 사전 시험(과금 0) — 평가와 같은 빈 CASE_SEARCH_HOME·토큰 없이 익명 us-search 한 번이 되는지."""
    env = {k: v for k, v in os.environ.items() if k not in FOREIGN_TOKENS}
    env["CASE_SEARCH_HOME"] = os.path.join(folder, "case-search-home")
    p = subprocess.run([sys.executable, FOREIGNCASE, "us-search", "Miranda v. Arizona", "--court", "scotus"], env=env,
                       capture_output=True, timeout=60)
    try:
        items = json.loads(p.stdout.decode("utf-8")).get("items") or []
    except (ValueError, AttributeError):
        items = []
    return {"ok": p.returncode == 0 and bool(items), "us_search_items": len(items), "rc": p.returncode}


def _spawn(a, idt, out, job):
    cmd = [sys.executable, "-I", os.path.abspath(__file__), "one", "--env", a.env, "--run-dir", os.path.join(out, _name(job)),
           "--scenario", job[0], "--arm", job[1], "--model", a.model, "--ident", json.dumps(idt, sort_keys=True)]
    return subprocess.run(cmd, capture_output=True).returncode == 0


def cmd_run(a, runner=None, precheck=None, usage=None):
    suite = getattr(a, "suite", None) or "fr27"
    d = SUITE_DEFAULTS[suite]
    runs = a.runs or d["runs"]
    max_calls = a.max_calls or d["max_calls"]
    precheck = precheck or (R.precheck if suite == "fr27" else us_precheck)
    usage = usage or edb_weekly
    idt = e2e.ident(a.model if a.env == "claude" else "codex-default")
    idt["env"] = a.env
    idt["invoke"] = getattr(a, "invoke", None) or "auto"  # 식별값에 넣어 자동 선택 회차와 섞지 않는다
    runner = runner or (lambda out, job: _spawn(a, idt, out, job))
    out = os.path.abspath(a.resume) if a.resume else os.path.join(os.path.abspath(a.out), "%s-%s" % (a.env, time.strftime("%Y%m%d-%H%M%S")))
    jobs = [(s, arm, i) for s in (a.only or sorted(SUITES[suite])) for arm in (a.arms or d["arms"]) for i in range(1, runs + 1)]
    todo = [j for j in jobs if (_report(os.path.join(out, _name(j))) or {}).get("ident") != idt]
    n = len(todo)
    print("실행 폴더: %s" % out)
    if os.path.commonpath([out, REPO]) == REPO:  # 공개 repo 밖에 둔다 — Codex 플러그인 설치가 repo 를 복사하며 자기 자신을 품는다
        print("실행 폴더가 repo 안입니다 — repo 밖 폴더를 고르십시오", file=sys.stderr)
        return 5
    above = skill_dirs_above(out)
    if above:  # 홈 아래(~/.cache 등)면 ~/.claude/skills 가 두 조건 모두에 실린다
        print("실행 폴더 상위에 개인 스킬 폴더가 있습니다(%s) — 그 밖(예: /Users/Shared)을 고르십시오" % ", ".join(above), file=sys.stderr)
        return 6
    if a.env == "claude":
        print("예상 호출: claude -p %d회(모델 %s · 계정 edb 토큰) · Codex 0회 · Jev 0회 · 상한 %d회" % (n, a.model, max_calls), flush=True)
    else:
        print("예상 호출: claude -p 0회 · Codex %d회(계정 ~/.codex 인증 사본 · 기본 모델) · Jev 0회 · 상한 %d회" % (n, max_calls), flush=True)
    if suite == "fr26":
        print("FR-26 은 us-search 로 실제 CourtListener 를 익명으로 부른다(사전 시험 1건 + 실행당 몇 건)", flush=True)
    if n > max_calls:
        print("상한 초과 — 시작하지 않는다", file=sys.stderr)
        return 2
    if a.env == "claude":
        u = usage()
        if u is not None and u >= a.weekly_cap:
            print("edb 주간 사용률 %.0f%% ≥ 상한 %.0f%% — 시작하지 않는다" % (u * 100, a.weekly_cap * 100), file=sys.stderr)
            return 4
    os.makedirs(out, exist_ok=True)
    pre = precheck(tempfile.mkdtemp(prefix="_precheck-", dir=out))  # 이어 실행해도 캐시 없는 새 폴더
    print("사전 시험(과금 0): %s" % json.dumps(pre, ensure_ascii=False), flush=True)
    if not pre.get("ok"):
        print("사전 시험 실패 — 모델 호출을 보내지 않는다", file=sys.stderr)
        return 3
    with cf.ThreadPoolExecutor(max_workers=getattr(a, "jobs", None) or d["jobs"]) as ex:
        for job, ok in zip(todo, ex.map(lambda j: runner(out, j), todo)):
            print("%s %s" % (_name(job), "ok" if ok else "FAIL"), flush=True)
    return 0


# ── 판정 ──
def judge_dir(rd):
    rep = _report(rd)
    if rep is None:
        return None
    sid = rep["scenario"]
    skill = ALL_SCENARIOS[sid]["skill"]
    events = open(os.path.join(rd, "agent.jsonl"), encoding="utf-8", errors="replace").read() if os.path.exists(os.path.join(rd, "agent.jsonl")) else ""
    row = {"run": os.path.basename(rd), "env": rep["env"], "scenario": sid, "arm": rep["arm"], "ok": rep.get("ok"),
           "error": rep.get("error"), "audit": audit_events(events), "drf_requests": rep.get("drf_requests"),
           "bigcase_files": rep.get("bigcase_files"), "cost_usd": rep.get("cost_usd"), "usage": rep.get("usage"),
           "seconds": rep.get("seconds")}
    if skill == "case-search-us":
        row.update(us_audit(events))
        row["final"] = (rep.get("final") or "")[:1500]
    elif skill == "intent-brief":
        d = rep.get("draft")
        text = open(d, encoding="utf-8").read() if d and os.path.exists(d) else ""
        src = "\n".join(open(f, encoding="utf-8", errors="replace").read() for f in glob.glob(os.path.join(rep.get("case_dir", ""), "*"))
                        if os.path.isfile(f) and f.endswith((".md", ".txt")))
        row.update(ib_rubric(sid, text, extract_cases(src)))
    else:
        row.update(cs_rubric(sid, rep.get("final")))
        row["final"] = (rep.get("final") or "")[:1500]
    return row


def cmd_judge(a):
    rows = []
    for out in a.out:
        rows += [r for r in (judge_dir(d) for d in sorted(glob.glob(os.path.join(out, "*_r*")))) if r]
    table = {}
    for r in rows:
        cell = table.setdefault(r["env"], {}).setdefault(r["scenario"], {}).setdefault(r["arm"], {"pass": 0, "n": 0})
        cell["n"] += 1
        cell["pass"] += bool(r.get("pass"))
    for env, scn in table.items():
        for sid, arms in scn.items():
            w, wo = arms.get("with"), arms.get("without")
            if w and wo:
                arms["gain"] = round(w["pass"] / w["n"] - wo["pass"] / wo["n"], 2)
    us_rows = [r for r in rows if ALL_SCENARIOS[r["scenario"]]["skill"] == "case-search-us"]
    res = {"table": table, "runs": rows, "fr26": us_summary(us_rows) if us_rows else None,
           "cost_usd": round(sum(r["cost_usd"] or 0 for r in rows), 2),
           "audit_total": {k: sum(r["audit"][k] for r in rows) for k in AUDIT}}
    json.dump(res, open(os.path.join(a.out[0], "judge.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if us_rows:
        s = res["fr26"]
        print("[FR-26] 실행 %d · us-search %d · us-opinion %d · 검색 결과에 없던 식별자 %d · 비율 %s" % (
            len(us_rows), sum(r["searches"] for r in us_rows), s["opinions"], s["violations"],
            "-(us-opinion 0회)" if s["ratio"] is None else "%d%%" % round(s["ratio"] * 100)))
        rows = [r for r in rows if r not in us_rows]
        table = {e: {k: v for k, v in scn.items() if k not in US_SCENARIOS} for e, scn in table.items()}
    for env, scn in sorted(table.items()):
        if not scn:
            continue
        print("[%s]" % env)
        for sid in sorted(scn):
            arms = scn[sid]
            print("  %s 있음 %s · 없음 %s · 차이 %s" % (sid, "%(pass)d/%(n)d" % arms["with"] if "with" in arms else "-",
                                                 "%(pass)d/%(n)d" % arms["without"] if "without" in arms else "-", arms.get("gain")))
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("run")
    s.add_argument("--env", choices=("claude", "codex"), required=True)
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--out"); g.add_argument("--resume")
    s.add_argument("--suite", choices=sorted(SUITES), default="fr27")
    s.add_argument("--invoke", choices=("auto", "explicit"), default="auto")
    s.add_argument("--runs", type=int); s.add_argument("--jobs", type=int)  # 기본값은 SUITE_DEFAULTS
    s.add_argument("--only", nargs="*", choices=sorted(ALL_SCENARIOS)); s.add_argument("--arms", nargs="*", choices=ARMS)
    s.add_argument("--model", default="sonnet"); s.add_argument("--max-calls", type=int)
    s.add_argument("--weekly-cap", type=float, default=0.95)
    s = sub.add_parser("one")
    s.add_argument("--env", required=True); s.add_argument("--run-dir", required=True); s.add_argument("--scenario", required=True)
    s.add_argument("--arm", required=True); s.add_argument("--model", default="sonnet"); s.add_argument("--ident", required=True)
    s = sub.add_parser("judge"); s.add_argument("--out", nargs="+", required=True)
    sub.add_parser("guard")
    a = ap.parse_args()
    if a.cmd == "guard":  # PreToolUse 훅 — 막으면 exit 2(이유는 stderr)
        try:
            payload = json.load(sys.stdin)
        except ValueError:
            return 0
        if guard_blocked(payload):
            sys.stderr.write("평가 환경: 외부 서비스·개인 스킬·repo 밖 workspace 접근은 막혀 있습니다\n")
            return 2
        return 0
    if a.cmd == "one":
        rep = run_one(a.env, os.path.abspath(a.run_dir), a.scenario, a.arm, a.model, json.loads(a.ident))
        return 0 if rep.get("ok") else 1
    return {"run": cmd_run, "judge": cmd_judge}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
