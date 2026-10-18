"""개발 전용 e2e 재생 구동기 — 받는 변호사 PC 에는 쓰이지 않는다.

1) 픽스처를 실행 폴더로 복사 → 2) 인터뷰를 답 파일로 재생(모델 0회: score.py 가 다음 키를 내면 answers 에서
찾아 state.py apply, 없으면 실패 — 추측 답 금지) → 3) 설계 확인·resolve --write → 4) 사건메모 기록 ①(자동 확인,
이 구동기에만 있음) → 5) `claude -p --plugin-dir <repo>` 1회로 초안·검사·인용 대조(SKILL.md 5–7단계) →
6) render_docx → 7) 사건메모 기록 ②.

런타임 스크립트는 HOME·LOCALAPPDATA 를 실행 폴더로 바꿔 부른다(작업 폴더 기본 경로 로직을 그대로 시험).
`claude -p` 는 실제 HOME 으로 돈다(키체인 인증) — 경로는 절대경로로 넘긴다.
법제처·빅케이스 실서비스는 부르지 않는다 — 법제처는 루프백 재생 서버(`drf_replay.py`), 빅케이스는 끔.
세 변수(`INTENT_BRIEF_LAW_URL`·`INTENT_BRIEF_NO_CASESEARCH`·가짜 `INTENT_BRIEF_LAW_OC`)를 스크립트 환경·`claude -p`
환경·프롬프트의 인용 대조 명령 앞에 모두 넣고, 끝나면 재생 서버 요청 수를 `cite/*.req.json` 수와 대조한다.

사용:
  replay.py <픽스처 사건 폴더> <answers.json> --run-dir <폴더> --brief 준비서면|답변서 --name <약칭>
            [--skip-draft] [--claude claude] [--model sonnet] [--ident <JSON>]
  replay.py --precheck <폴더>     모델 없이 인용 대조만 재생 서버에 돌려 본다(과금 0 사전 시험)
"""
import argparse
import glob
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "skills", "intent-brief", "scripts")
TODAY = "2026-09-15"
FAKE_OC = "replay-fake-oc"  # 재생 서버는 키를 보지 않는다 — 저장된 실제 키보다 먼저 읽히게 환경변수로 준다
EXTRA_ENV = {}  # main 이 재생 서버를 띄운 뒤 채운다
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # -I 실행에서도 drf_replay 를 찾게
import drf_replay  # noqa: E402


class ReplayError(Exception):
    pass


def replay_env(url):
    return {"INTENT_BRIEF_LAW_URL": url, "INTENT_BRIEF_NO_CASESEARCH": "1", "INTENT_BRIEF_LAW_OC": FAKE_OC,
            "INTENT_BRIEF_NO_NOTICE": "1"}  # 첫 사용 고지는 재생 판정과 무관


def script_env(run_dir):
    env = dict(os.environ)
    env.update(EXTRA_ENV)
    env["HOME"] = os.path.join(run_dir, "home")
    env["LOCALAPPDATA"] = os.path.join(run_dir, "home", "AppData", "Local")
    env["INTENT_BRIEF_TODAY"] = TODAY
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def sh(run_dir, name, *args, ok_codes=(0,)):
    p = subprocess.run([sys.executable, "-I", os.path.join(SCRIPTS, name)] + list(args),
                       env=script_env(run_dir), capture_output=True)
    out = p.stdout.decode("utf-8")
    try:
        obj = json.loads(out)
    except ValueError:
        raise ReplayError("%s 출력 해석 실패(rc=%s): %s %s" % (name, p.returncode, out[:300], p.stderr.decode("utf-8", "replace")[:500]))
    if p.returncode not in ok_codes:
        raise ReplayError("%s 실패(rc=%s): %s" % (name, p.returncode, out[:500]))
    return obj


def answer_for(answers, nxt):
    for key in ("%s|%s" % (nxt["round_type"], nxt["issue_id"]), nxt["round_type"]):
        if key in answers:
            return key, answers[key]
    raise ReplayError("답 파일에 키가 없습니다: %s (추측 답 금지)" % json.dumps(nxt, ensure_ascii=False))


def to_update(key, ans, nxt):
    upd = {k: v for k, v in ans.items() if not k.startswith("_")}
    upd["round"] = {"round_type": nxt["round_type"], "issue_id": nxt.get("issue_id"), "axis": nxt.get("axis"),
                    "question": "replay:%s — %s" % (key, nxt.get("why", "")), "options": [],
                    "answer": ans.get("_answer", "재생 답"), "evidence_quote": ans.get("_quote"), "why": nxt.get("why")}
    return upd


def memo_auto(run_dir, state, progress, todos):
    """사건메모 기록 — 재생 모드에서만 자동 확인(런타임 CLI 에는 이 경로가 없다)."""
    code = ("import sys; sys.path.insert(0, %r); import memo, json; "
            "pv = memo.preview(%r, %r, %r); r = memo.apply(%r, None, auto_confirm=True); "
            "print(json.dumps({'diff': pv['diff'], **r}, ensure_ascii=False))") % (SCRIPTS, state, progress, todos, state)
    p = subprocess.run([sys.executable, "-I", "-c", code], env=script_env(run_dir), capture_output=True)
    if p.returncode != 0:
        raise ReplayError("사건메모 기록 실패: %s" % p.stderr.decode("utf-8", "replace")[-800:])
    return json.loads(p.stdout.decode("utf-8"))


def interview(run_dir, case_dir, answers, brief):
    init = sh(run_dir, "state.py", "init", case_dir, "--brief", brief)
    state = init["state"]
    for _ in range(40):
        sc = sh(run_dir, "score.py", state)
        nxt = sc["next"]
        rt = nxt["round_type"]
        if rt == "stop_no_intent":
            sh(run_dir, "state.py", "set-status", state, "stopped")
            return state, "stopped"
        if rt == "done":
            return state, "done"
        if rt == "design_confirm":
            st = json.load(open(state, encoding="utf-8"))
            if st["status"] == "interviewing":
                sh(run_dir, "state.py", "set-status", state, "confirming")
            res = sh(run_dir, "intent.py", "resolve", state, ok_codes=(0, 3))
            if not res.get("ok"):
                need = res["needs"][0]
                key, ans = answer_for(answers, {"round_type": "conflict", "issue_id": need["key"]})
                sh(run_dir, "state.py", "apply", state, "--json", json.dumps(to_update(key, ans, dict(need, round_type="conflict")), ensure_ascii=False))
                continue
            key, ans = answer_for(answers, nxt)
            sh(run_dir, "state.py", "apply", state, "--json", json.dumps(to_update(key, ans, nxt), ensure_ascii=False))
            w = sh(run_dir, "intent.py", "resolve", state, "--write")
            return state, w["design_path"]
        key, ans = answer_for(answers, nxt)
        sh(run_dir, "state.py", "apply", state, "--json", json.dumps(to_update(key, ans, nxt), ensure_ascii=False))
    raise ReplayError("인터뷰가 40회 안에 끝나지 않았습니다")


DRAFT_PROMPT = """lawfirm 플러그인의 intent-brief 스킬로 민사 {brief} 초안을 쓴다. 인터뷰와 설계 확인은 이미 끝났다 — 질문하지 말고, 사용자 확인을 기다리지 말고, SKILL.md 의 「5. 초안 작성」「6. 검사 → 1회 고쳐 쓰기」「7. 인용 대조」만 수행한다.

- design.json: {design}
- 원자료(사건 폴더, 읽기만): {case}
- 초안을 쓸 경로: {draft}
- 스크립트 폴더: {scripts} (Python 은 `{py}`)
- 1차 검사: `{py} {scripts}/check_draft.py check "{draft}" "{design}" > "{wd}/check_first.json"`
- 실패 항목이 있으면 그 항목만 고쳐 초안을 다시 쓰고 `... > "{wd}/check_final.json"` (실패가 없으면 check_first.json 을 check_final.json 으로 복사)
- 인용 대조: `{lawenv} {py} {scripts}/cite_check.py run "{draft}"` (Bash timeout 600000 · 앞의 환경변수를 빼지 않는다)
- 사건 폴더나 다른 곳에 파일을 만들지 않는다. references/phrases.json 은 읽지 않는다.
끝나면 한 줄로 「완료」만 답한다."""


def draft(run_dir, state, design_path, case_dir, brief, claude, model):
    wd = os.path.dirname(state)
    draft_path = os.path.join(wd, "%s_draft.md" % brief)
    lawenv = " ".join("%s=%s" % (k, shlex.quote(v)) for k, v in sorted(EXTRA_ENV.items()))
    prompt = DRAFT_PROMPT.format(brief=brief, design=design_path, case=case_dir, draft=draft_path, scripts=SCRIPTS,
                                 py=sys.executable, wd=wd, lawenv=lawenv)
    env = dict(os.environ)
    env.update(EXTRA_ENV)
    env["INTENT_BRIEF_TODAY"] = TODAY
    tok = os.environ.get("INTENT_BRIEF_TOKEN_FILE")  # 무인 claude -p 에 쓸 OAuth 토큰 파일(선택)
    if "CLAUDE_CODE_OAUTH_TOKEN" not in env and tok and os.path.exists(tok):
        env["CLAUDE_CODE_OAUTH_TOKEN"] = open(tok, encoding="utf-8").read().strip()
    cmd = [claude, "-p", "--plugin-dir", REPO, "--permission-mode", "bypassPermissions", "--output-format", "json"]
    if model:
        cmd += ["--model", model]
    t0 = time.time()
    p = subprocess.run(cmd, input=prompt.encode("utf-8"), env=env, capture_output=True, cwd=run_dir, timeout=1800)
    log = os.path.join(run_dir, "claude.json")
    open(log, "wb").write(p.stdout)
    open(os.path.join(run_dir, "claude.err"), "wb").write(p.stderr)
    if p.returncode != 0 or not os.path.exists(draft_path):
        raise ReplayError("claude -p 초안 실패(rc=%s, draft=%s)" % (p.returncode, os.path.exists(draft_path)))
    st = json.load(open(state, encoding="utf-8"))
    for rec in ("first", "final"):
        f = os.path.join(wd, "check_%s.json" % rec)
        if os.path.exists(f):
            r = json.load(open(f, encoding="utf-8"))
            st["compliance"][rec] = {"rate": r["rate"], "failures": [x["id"] for x in r["failures"]]}
    st["draft_path"] = draft_path
    json.dump(st, open(state, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return draft_path, round(time.time() - t0, 1)


def cite_audit(wd, server_count):
    """재생 서버 요청 수 = 새로 쓴 `cite/*.req.json` 수 · format_changed 0 · 빅케이스 캐시 0 — 어긋나면 방향을 적는다."""
    req = len(glob.glob(os.path.join(wd, "cite", "*.req.json")))
    ext = len(glob.glob(os.path.join(wd, "cite", "external", "*")))
    res = os.path.join(wd, "cite_results.json")
    summary = json.load(open(res, encoding="utf-8")).get("summary", {}) if os.path.exists(res) else None
    r = {"server": server_count, "req_json": req, "external": ext, "summary": summary,
         "format_changed": (summary or {}).get("format_changed", 0)}
    if summary is None:
        r["error"] = "cite_results.json 없음 — 인용 대조가 돌지 않았다"
    elif server_count < req:
        r["error"] = "재생 서버 밖 요청(서버 %d < req.json %d)" % (server_count, req)
    elif server_count > req:
        r["error"] = "형식 변경으로 캐시가 지워짐 또는 대조 밖 법제처 요청(서버 %d > req.json %d)" % (server_count, req)
    elif r["format_changed"]:
        r["error"] = "format_changed %d건" % r["format_changed"]
    elif ext:
        r["error"] = "빅케이스 캐시(cite/external) %d개 — 빅케이스가 꺼지지 않았다" % ext
    r["ok"] = "error" not in r
    return r


PRECHECK_DRAFT = """## [sec:sec.body] 본문

원고의 주장은 민사소송법 제288조에 따라 다툼이 없는 사실이다. 민사소송법 제1조의 신의칙도 같다.
대법원 2017. 2. 21. 선고 2016다225353 판결과 대법원 2020. 3. 12. 선고 2019다12345 판결을 본다.
"""


def _cite_subprocess(draft_path, env):
    p = subprocess.run([sys.executable, "-I", os.path.join(SCRIPTS, "cite_check.py"), "run", draft_path],
                       env=env, capture_output=True, timeout=300)
    return None if p.returncode == 0 else "cite_check.py rc=%s: %s" % (p.returncode, p.stderr.decode("utf-8", "replace")[-300:])


def precheck(out, run_cite=_cite_subprocess):
    """과금 0 사전 시험 — 녹화 밖 조문 1·녹화 밖 사건번호 1을 인용한 가짜 초안을 모델 없이 재생 서버에 대조한다."""
    os.makedirs(out, exist_ok=True)
    draft_path = os.path.join(out, "precheck_draft.md")
    open(draft_path, "w", encoding="utf-8").write(PRECHECK_DRAFT)
    srv = drf_replay.Server().start()
    try:
        env = dict(os.environ)
        env.update(replay_env(srv.url))
        err = run_cite(draft_path, env)
        srv.dump(os.path.join(out, "drf_requests.json"))
        r = cite_audit(out, srv.count)
    finally:
        srv.stop()
    if err and r["ok"]:
        r.update(ok=False, error=err)
    return r


def _sha(*paths):
    h = hashlib.sha256()
    for path in paths:
        for f in sorted(glob.glob(os.path.join(path, "**"), recursive=True)) if os.path.isdir(path) else [path]:
            if os.path.isfile(f):
                h.update(os.path.relpath(f, path if os.path.isdir(path) else os.path.dirname(f)).encode("utf-8"))
                h.update(open(f, "rb").read())
    return h.hexdigest()[:16]


def main(argv=None):
    if argv is None and sys.argv[1:2] == ["--precheck"]:
        r = precheck(os.path.abspath(sys.argv[2]))
        print(json.dumps(r, ensure_ascii=False))
        return 0 if r["ok"] else 1
    ap = argparse.ArgumentParser()
    ap.add_argument("fixture"); ap.add_argument("answers")
    ap.add_argument("--run-dir", required=True); ap.add_argument("--brief", required=True); ap.add_argument("--name", required=True)
    ap.add_argument("--skip-draft", action="store_true"); ap.add_argument("--claude", default="claude"); ap.add_argument("--model")
    ap.add_argument("--ident", help="실행 식별값 JSON(e2e.py 가 준다 — HEAD·작업 트리 해시·모델)")
    a = ap.parse_args(argv)
    run_dir = os.path.abspath(a.run_dir)
    os.makedirs(os.path.join(run_dir, "home"), exist_ok=True)
    case_dir = os.path.join(run_dir, "case", os.path.basename(a.fixture.rstrip("/")))
    shutil.copytree(a.fixture, case_dir)
    answers = json.load(open(a.answers, encoding="utf-8"))
    report = {"fixture": a.fixture, "answers": a.answers, "case_dir": case_dir,
              "ident": json.loads(a.ident) if a.ident else None, "input_sha": _sha(a.fixture, a.answers),
              "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    srv = drf_replay.Server().start()
    EXTRA_ENV.clear()
    EXTRA_ENV.update(replay_env(srv.url))
    try:
        state, design = interview(run_dir, case_dir, answers, a.brief)
        report.update(state=state, design=design)
        st = json.load(open(state, encoding="utf-8"))
        connected = bool(st["memo"]["path"])
        d = json.load(open(design, encoding="utf-8"))
        names = d["intent_names"]
        label = "주: %s%s" % (names[d["primary"]], (" / 부: " + "·".join(names[s] for s in d["secondaries"])) if d["secondaries"] else "")
        if connected:
            report["memo1"] = memo_auto(run_dir, state, ["%s 의도 확정 — %s" % (a.brief, label)], [])
        if a.skip_draft:
            return print(json.dumps(report, ensure_ascii=False, indent=1))
        sh(run_dir, "state.py", "set-status", state, "designed") if st["status"] != "designed" else None
        report["draft"], report["draft_seconds"] = draft(run_dir, state, design, case_dir, a.brief, a.claude, a.model)
        r = sh(run_dir, "render_docx.py", "all", state, "--name", a.name)
        report["outputs"] = r["paths"]
        if connected:
            md = open(report["draft"], encoding="utf-8").read()
            n_tags = md.count("[확인 필요")
            todos = [t["text"] for t in d["todo"]]
            report["memo2"] = memo_auto(run_dir, state, ["%s 초안 v%d 작성 — %s · [확인 필요] %d건" % (
                a.brief, r["version"], os.path.basename(r["paths"]["draft"]), n_tags)], todos)
        srv.dump(os.path.join(run_dir, "drf_requests.json"))
        report["cite_audit"] = cite_audit(os.path.dirname(state), srv.count)
        if not report["cite_audit"]["ok"]:
            raise ReplayError("인용 대조 재생 점검 실패: %s" % report["cite_audit"]["error"])
        report["ok"] = True
    except (ReplayError, subprocess.TimeoutExpired) as e:
        report["ok"] = False
        report["error"] = str(e)
    finally:
        srv.stop()
    json.dump(report, open(os.path.join(run_dir, "report.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"ok": report["ok"], "run_dir": run_dir, "error": report.get("error")}, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
