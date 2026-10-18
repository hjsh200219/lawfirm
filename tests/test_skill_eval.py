"""FR-27 짝지은 평가 구동기(dev/skill_eval.py) — 명령 조립·격리·기준표·호출 상한(과금 0, 모델 호출 없음)."""
import json
import os
import sys
import types

import pytest

from conftest import ROOT

sys.path.insert(0, os.path.join(ROOT, "dev"))
import skill_eval as E  # noqa: E402


def test_six_scenarios_two_skills():
    assert sorted(E.SCENARIOS) == ["CS1", "CS2", "CS3", "IB1", "IB2", "IB3"]
    assert {s["skill"] for s in E.SCENARIOS.values()} == {"intent-brief", "case-search"}
    assert E.ARMS == ("with", "without")


def test_eval_env_blocks_real_services(tmp_path):
    env = E.eval_env("http://127.0.0.1:9/DRF", str(tmp_path))
    assert env["INTENT_BRIEF_LAW_URL"] == "http://127.0.0.1:9/DRF" and env["INTENT_BRIEF_NO_CASESEARCH"] == "1"
    assert env["INTENT_BRIEF_NO_NOTICE"] == "1" and env["INTENT_BRIEF_LAW_OC"]
    assert env["BIGCASE_KEYRING_SERVICE"] != "case-search-bigcase"
    assert env["CASE_SEARCH_HOME"].startswith(str(tmp_path))


@pytest.mark.parametrize("arm", E.ARMS)
def test_claude_cmd_differs_only_in_plugin_dir(arm):
    cmd = E.claude_cmd(arm, "sonnet", claude="claude")
    assert ("--plugin-dir" in cmd) is (arm == "with")
    if arm == "with":
        assert cmd[cmd.index("--plugin-dir") + 1] == E.REPO
    assert "WebFetch,WebSearch" in cmd and cmd[cmd.index("--disallowedTools") - 1] != "--plugin-dir"
    assert "-p" in cmd and "stream-json" in cmd and cmd[cmd.index("--model") + 1] == "sonnet"
    rest = [x for x in cmd if x not in ("--plugin-dir", E.REPO)]
    assert rest == [x for x in E.claude_cmd("without", "sonnet", claude="claude")]


def test_claude_env_isolated_config_and_token(tmp_path):
    tok = tmp_path / "tok"
    tok.write_text("tok-value\n")
    env = E.claude_env(str(tmp_path / "run"), {"A": "1"}, {"PATH": "/bin", "CLAUDE_CONFIG_DIR": "/real"}, str(tok))
    assert env["CLAUDE_CONFIG_DIR"] == os.path.join(str(tmp_path / "run"), "claude-config")
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == "tok-value" and env["A"] == "1" and env["PATH"] == "/bin"
    assert env["HOME"] == os.path.join(str(tmp_path / "run"), "agent-home")  # 개인 스킬(~/.agents·~/.claude)이 안 보이게
    assert env["UV_CACHE_DIR"] and not env["UV_CACHE_DIR"].startswith(str(tmp_path))


def test_claude_env_requires_token(tmp_path):
    with pytest.raises(E.EvalError):
        E.claude_env(str(tmp_path), {}, {}, str(tmp_path / "없음"))


def test_codex_config_sets_env_explicitly():
    t = E.codex_config({"BIGCASE_KEYRING_SERVICE": "x-none", "INTENT_BRIEF_LAW_URL": "http://127.0.0.1:1/DRF"})
    assert "[shell_environment_policy.set]" in t and 'BIGCASE_KEYRING_SERVICE = "x-none"' in t
    assert "hooks = true" in t


def test_codex_config_without_arm_has_no_plugin_env():
    t = E.codex_config({})
    assert "INTENT_BRIEF" not in t and "BIGCASE" not in t


@pytest.mark.parametrize("cmd,blocked", [
    ('curl -s "https://www.law.go.kr/DRF/lawService.do?OC=test"', True),
    ("curl http://bigcase.ai/api", True),
    ("wget https://example.com/x", True),
    ('python3 -c "import urllib.request as u; u.urlopen(\'https://open.law.go.kr\')"', True),
    ('curl -s "http://127.0.0.1:5555/DRF/lawSearch.do"', False),
    ("python3 /r/skills/intent-brief/scripts/lawapi.py law 민사소송법 --article 288", False),
    ("cat ~/.agents/skills/k-law/SKILL.md", True),
    ("ls /Users/someone/.claude/skills", True),
])
def test_guard_blocks_external_and_personal(cmd, blocked):
    assert E.guard_blocked({"tool_name": "Bash", "tool_input": {"command": cmd}}) is blocked


def test_hook_settings_point_to_guard():
    h = E.guard_hooks()
    c = h["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert "skill_eval.py" in c and c.endswith("guard")


@pytest.mark.parametrize("arm", E.ARMS)
def test_agent_env_split(arm, tmp_path):
    ev = E.eval_env("http://127.0.0.1:9/DRF", str(tmp_path))
    a = E.agent_vars(arm, ev)
    assert (a == ev) is (arm == "with")
    if arm == "without":
        assert not any(k.startswith(("INTENT_BRIEF", "BIGCASE", "CASE_SEARCH")) for k in a)


def test_codex_cmd(tmp_path):
    cmd = E.codex_cmd(str(tmp_path), "질문", codex="codex")
    assert cmd[:2] == ["codex", "exec"] and "--dangerously-bypass-approvals-and-sandbox" in cmd and "--json" in cmd
    assert "--skip-git-repo-check" in cmd and cmd[-1] == "질문" and "--ignore-user-config" not in cmd


def test_case_search_prompt_same_for_both_arms():
    for sid in ("CS1", "CS2", "CS3"):
        assert E.cs_prompt(sid) and "lawapi" not in E.cs_prompt(sid) and "스킬" not in E.cs_prompt(sid)


def test_intent_brief_prompts():
    kw = dict(brief="준비서면", design="/r/design.json", case="/r/case", draft="/r/d.md", wd="/r", lawenv="A=1")
    w, wo = E.ib_prompt("with", **kw), E.ib_prompt("without", **kw)
    assert "cite_check.py" in w and "SKILL.md" in w
    assert "cite_check.py" not in wo and "SKILL.md" not in wo and "스크립트" not in wo
    for p in (w, wo):
        assert "/r/design.json" in p and "/r/d.md" in p and "질문하지" in p


# ── 기준표 ──
def test_extract_cases():
    t = "대법원 2016. 2. 21. 선고 2016다 225353 판결, 서울중앙지법 2026가합12345, 2019도1234 · 제2조"
    assert E.extract_cases(t) == {"2016다225353", "2026가합12345", "2019도1234"}


def test_citation_hygiene():
    ok = "대법원 2016다225353 판결 참조.\n\n대법원 2010다9999 판결[확인 필요: 법제처 미확인]."
    bad = "대법원 2010다9999 판결에 따르면 그렇다."
    assert E.citation_ok(ok, {"2016다225353"})[0]
    res = E.citation_ok(bad, {"2016다225353"})
    assert not res[0] and res[1] == ["2010다9999"]


def test_ib_rubric_f1a():
    t = "원고 준비서면\n\n피고의 변제 주장은 사실이 아닙니다. " * 40 + "\n\n피고는 원고에게 5,000만원을 지급하라는 판결을 구합니다. 청구 전부 인용."
    r = E.ib_rubric("IB1", t, set())
    assert r["pass"] and r["R1"] and r["R2"] and r["R3"]
    assert not E.ib_rubric("IB1", "짧다", set())["pass"]


def test_ib_rubric_f1b_and_f2b():
    t1 = "x" * 600 + "\n\n변제 1,000만원은 인정합니다. 조정에 회부해 주시고, 조정이 성립하지 않으면 4,000만원을 지급하라."
    assert E.ib_rubric("IB2", t1, set())["pass"]
    t2 = "x" * 600 + "\n\n일부 차용 사실은 인정합니다. 주위적으로 청구를 기각하고, 예비적으로 변제액을 공제한 나머지만 인정."
    assert E.ib_rubric("IB3", t2, set())["pass"]
    assert not E.ib_rubric("IB3", "x" * 600 + " 청구를 기각하라", set())["pass"]


def test_cs_rubric():
    art = "제288조(불요증사실) 법원에서 당사자가 자백한 사실과 현저한 사실은 증명을 필요로 하지 아니한다. 다만, 진실에 어긋나는 자백은 그것이 착오로 말미암은 것임을 증명한 때에는 취소할 수 있다."
    assert E.cs_rubric("CS1", "원문:\n" + art)["pass"]
    assert not E.cs_rubric("CS1", art.replace("때에는", "경우에는"))["pass"]
    assert E.cs_rubric("CS2", "판결요지: " + E.SCENARIOS["CS2"]["expect"])["pass"]
    assert E.cs_rubric("CS3", "법제처에서 대법원 2019다12345 판결을 찾지 못했습니다.")["pass"]
    assert not E.cs_rubric("CS3", "이 판결은 [1] 계약 해제의 효과에 관하여 판시하였다.")["pass"]
    assert not E.cs_rubric("CS3", "찾지 못했습니다. 다만 [1] 계약 해제는 원상회복 의무를 진다고 판시하였다.")["pass"]
    assert E.cs_rubric("CS3", "- 판결요지: 조회된 원문이 없어 기억이나 추정으로 쓰지 않았습니다. 확인하지 못했습니다.")["pass"]


def test_audit_events():
    ev = '{"type":"tool","input":{"command":"curl https://www.law.go.kr/x"}}\n{"name":"WebFetch"}\n{"cmd":"python3 lawapi.py law 민사소송법"}'
    a = E.audit_events(ev)
    assert a["law.go.kr"] == 1 and a["WebFetch"] == 1 and a["lawapi.py"] == 1 and a["bigcase"] == 0


# ── 호출 상한·사전 시험 순서(모델 호출 없이) ──
def _args(tmp_path, **kw):
    d = dict(env="claude", out=str(tmp_path), runs=3, jobs=1, only=None, arms=None, model="sonnet", max_calls=36,
             weekly_cap=0.95, resume=None)
    d.update(kw)
    return types.SimpleNamespace(**d)


def test_run_refuses_over_cap(tmp_path, capsys):
    calls = []
    rc = E.cmd_run(_args(tmp_path, max_calls=35), runner=lambda *x: calls.append(x), precheck=lambda o: {"ok": True},
                   usage=lambda: 0.5)
    assert rc == 2 and calls == []
    assert "claude -p 36회" in capsys.readouterr().out


def test_run_stops_when_precheck_fails(tmp_path):
    calls = []
    rc = E.cmd_run(_args(tmp_path), runner=lambda *x: calls.append(x), precheck=lambda o: {"ok": False}, usage=lambda: 0.5)
    assert rc == 3 and calls == []


def test_run_stops_over_weekly_cap(tmp_path):
    calls = []
    rc = E.cmd_run(_args(tmp_path), runner=lambda *x: calls.append(x), precheck=lambda o: {"ok": True}, usage=lambda: 0.96)
    assert rc == 4 and calls == []


def test_run_dispatches_all_jobs(tmp_path, capsys):
    calls = []
    rc = E.cmd_run(_args(tmp_path, env="codex", runs=1), runner=lambda out, job: calls.append(job) or True,
                   precheck=lambda o: {"ok": True}, usage=lambda: 0.0)
    assert rc == 0 and len(calls) == 12
    assert "Codex 12회" in capsys.readouterr().out


def test_run_refuses_out_inside_repo(capsys):
    calls = []
    rc = E.cmd_run(_args(None, out=os.path.join(ROOT, "docs", "prd", "x")), runner=lambda *x: calls.append(x),
                   precheck=lambda o: {"ok": True}, usage=lambda: 0.0)
    assert rc == 5 and calls == []


def test_precheck_uses_fresh_folder_on_resume(tmp_path):
    seen = []
    pre = lambda o: seen.append(o) or {"ok": True}  # noqa: E731
    for _ in range(2):
        E.cmd_run(_args(tmp_path, resume=str(tmp_path / "run"), runs=1, only=["CS1"], arms=["with"]),
                  runner=lambda out, job: True, precheck=pre, usage=lambda: 0.0)
    assert len(set(seen)) == 2 and all(not os.path.exists(os.path.join(s, "cite")) for s in seen)


def test_run_refuses_out_under_personal_skill_dirs(tmp_path):
    home = tmp_path / "home"
    (home / ".claude" / "skills").mkdir(parents=True)
    calls = []
    rc = E.cmd_run(_args(None, out=str(home / ".cache" / "eval")), runner=lambda *x: calls.append(x),
                   precheck=lambda o: {"ok": True}, usage=lambda: 0.0)
    assert rc == 6 and calls == []
    assert E.skill_dirs_above(str(home / ".cache" / "eval")) == [str(home / ".claude")]
    assert E.skill_dirs_above(str(tmp_path / "clean" / "x")) == []


@pytest.mark.parametrize("t,man,ok", [("5,000만원", 5000, True), ("5000만 원", 5000, True), ("금 50,000,000원", 5000, True),
                                      ("5천만원", 5000, True), ("40,000,000원", 4000, True), ("15,000,000원", 5000, False),
                                      ("550,000,000원", 5000, False)])
def test_amount_notation(t, man, ok):
    assert E.has_amount(t, man) is ok


def test_ib_rubric_accepts_won_notation():
    t = "x" * 600 + "\n\n피고의 주장은 사실이 아닙니다. 원고의 청구를 전부 인용하여 피고는 원고에게 50,000,000원을 지급하라."
    assert E.ib_rubric("IB1", t, set())["R2"]


# ── FR-26 미국 판례 식별자 측정(스킬 있음만, 질의 10개 이상) ──
def _tool_use(tid, cmd):
    return json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": tid, "name": "Bash", "input": {"command": cmd}}]}})


def _tool_result(tid, text):
    return json.dumps({"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": tid, "content": [{"type": "text", "text": text}]}]}})


FX = "python3 /r/skills/case-search/scripts/foreigncase.py"
SEARCH_OUT = json.dumps({"source": "CourtListener", "items": [
    {"case_name": "Miranda v. Arizona", "cluster_id": 107252, "opinion_ids": [107252001, 9411]}]})


def test_us_suite_separate_from_fr27():
    assert len(E.US_SCENARIOS) >= 10 and not set(E.US_SCENARIOS) & set(E.SCENARIOS)
    assert E.SUITES["fr27"] is E.SCENARIOS and E.SUITES["fr26"] is E.US_SCENARIOS
    for sid in E.US_SCENARIOS:
        p = E.scenario_prompt(sid)
        assert "원문" in p and "foreigncase" not in p and "opinion_id" not in p


def test_us_audit_id_after_search_passes():
    ev = "\n".join([_tool_use("a", FX + ' us-search "Miranda v. Arizona" --court scotus'), _tool_result("a", SEARCH_OUT),
                    _tool_use("b", FX + " us-opinion 9411"), _tool_result("b", '{"ok": false, "error": "no_key"}')])
    r = E.us_audit(ev)
    assert r["searches"] == 1 and r["opinions"] == 1 and r["violations"] == [] and r["no_key"] == 1


def test_us_audit_id_before_search_or_unseen_fails():
    ev = "\n".join([_tool_use("a", FX + " us-opinion 9411"), _tool_result("a", "{}"),
                    _tool_use("b", FX + ' us-search "Miranda"'), _tool_result("b", SEARCH_OUT),
                    _tool_use("c", FX + " us-opinion 107252"), _tool_result("c", "{}"),
                    _tool_use("d", FX + " us-opinion $ID"), _tool_result("d", "{}")])
    r = E.us_audit(ev)
    assert r["opinions"] == 3 and r["violations"] == ["9411", "107252", "$ID"]
    assert r["cluster_ids"] == ["107252"] and r["unparsed"] == ["$ID"]


def test_us_audit_counts_direct_external_attempts():
    ev = "\n".join([_tool_use("a", 'curl -s "https://www.courtlistener.com/api/rest/v4/opinions/1/"'),
                    _tool_use("b", 'curl -sL "https://supreme.justia.com/cases/federal/us/384/436/"'),
                    _tool_use("c", 'curl -s "http://127.0.0.1:5555/DRF/lawSearch.do"')])
    r = E.us_audit(ev)
    assert r["direct"] == 2 and r["direct_hosts"] == ["supreme.justia.com", "www.courtlistener.com"] and r["opinions"] == 0


def test_explicit_invoke_prefixes_slash_command():
    sid = sorted(E.US_SCENARIOS)[0]
    p = E.scenario_prompt(sid, invoke="explicit")
    assert p.startswith("/lawfirm:case-search ") and p.endswith(E.scenario_prompt(sid))
    assert E.scenario_prompt(sid, invoke="auto") == E.scenario_prompt(sid)


def test_us_summary_zero_calls_is_not_zero_percent():
    assert E.us_summary([{"opinions": 0, "violations": []}])["ratio"] is None
    s = E.us_summary([{"opinions": 3, "violations": ["1"]}, {"opinions": 1, "violations": []}])
    assert s == {"opinions": 4, "violations": 1, "ratio": 0.25}


@pytest.mark.parametrize("cmd", [FX + " key set us --prompt", FX + " key clear us", "/lawfirm:law-key-setup us"])
def test_guard_blocks_key_prompt(cmd):
    assert E.guard_blocked({"tool_name": "Bash", "tool_input": {"command": cmd}})


def test_guard_allows_foreign_search():
    assert not E.guard_blocked({"tool_name": "Bash", "tool_input": {"command": FX + ' us-search "Miranda v. Arizona"'}})


def test_claude_env_drops_inherited_foreign_tokens(tmp_path):
    tok = tmp_path / "tok"
    tok.write_text("t")
    env = E.claude_env(str(tmp_path / "run"), {}, {"COURTLISTENER_API_TOKEN": "x", "OPENLEGALDATA_API_TOKEN": "y"}, str(tok))
    assert "COURTLISTENER_API_TOKEN" not in env and "OPENLEGALDATA_API_TOKEN" not in env


def test_fr26_defaults_with_arm_one_run(tmp_path, capsys):
    calls = []
    rc = E.cmd_run(_args(tmp_path, suite="fr26", runs=None, max_calls=None), runner=lambda out, job: calls.append(job) or True,
                   precheck=lambda o: {"ok": True}, usage=lambda: 0.0)
    assert rc == 0 and len(calls) == len(E.US_SCENARIOS) and {j[1] for j in calls} == {"with"} and {j[2] for j in calls} == {1}
    assert "claude -p %d회" % len(E.US_SCENARIOS) in capsys.readouterr().out


def test_fr27_default_unchanged(tmp_path):
    calls = []
    E.cmd_run(_args(tmp_path, runs=None, max_calls=None), runner=lambda out, job: calls.append(job) or True,
              precheck=lambda o: {"ok": True}, usage=lambda: 0.0)
    assert len(calls) == 36 and {j[0] for j in calls} == set(E.SCENARIOS)


def test_invoke_goes_into_ident(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(E, "_spawn", lambda a, idt, out, job: seen.append(idt) or True)
    for inv in ("explicit", None):
        E.cmd_run(_args(tmp_path, suite="fr26", runs=None, max_calls=None, invoke=inv, only=["US01"]),
                  precheck=lambda o: {"ok": True}, usage=lambda: 0.0)
    assert [x["invoke"] for x in seen] == ["explicit", "auto"] and seen[0] != seen[1]


def test_us_audit_reads_truncated_search_output():
    # 모델이 `| head -60` 으로 잘라 읽으면 opinion_ids 배열의 닫는 괄호가 없다 — 본 식별자는 본 것으로 센다
    out = '{\n "items": [\n  {\n   "cluster_id": 107841,\n   "opinion_ids": [\n    9423907,\n    9423910,\n    107841,\n'
    ev = "\n".join([_tool_use("a", FX + ' us-search "Tinker"'), _tool_result("a", out),
                    _tool_use("b", FX + " us-opinion 107841")])
    r = E.us_audit(ev)
    assert r["opinions"] == 1 and r["violations"] == [] and r["cluster_ids"] == []


def test_fr26_runs_one_at_a_time(tmp_path, monkeypatch):
    seen = []
    real = E.cf.ThreadPoolExecutor
    monkeypatch.setattr(E.cf, "ThreadPoolExecutor", lambda max_workers: seen.append(max_workers) or real(max_workers=max_workers))
    for suite in ("fr26", "fr27"):
        E.cmd_run(_args(tmp_path, suite=suite, runs=None, max_calls=None, jobs=None), runner=lambda out, job: True,
                  precheck=lambda o: {"ok": True}, usage=lambda: 0.0)
    assert seen == [1, 4]


def test_us_audit_expands_for_loop():
    out = '{"items": [{"cluster_id": 145730, "opinion_ids": [9435068, 145730, 9435069]}]}'
    loop = 'S=/r/foreigncase.py; for id in 9435068 145730 777; do "$PY" "$S" us-opinion $id; done'
    ev = "\n".join([_tool_use("a", FX + ' us-search "Twombly"'), _tool_result("a", out), _tool_use("b", loop)])
    r = E.us_audit(ev)
    assert r["opinions"] == 3 and r["violations"] == ["777"] and r["unparsed"] == []
    braced = 'for oid in 9435068; do python3 /r/foreigncase.py us-opinion "${oid}"; done'
    r = E.us_audit("\n".join([_tool_use("a", FX + ' us-search "Twombly"'), _tool_result("a", out), _tool_use("b", braced)]))
    assert r["opinions"] == 1 and r["violations"] == []
